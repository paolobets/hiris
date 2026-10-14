# hiris/app/server.py
import asyncio
import contextlib
import logging
import os
import time
from datetime import timedelta
from functools import partial
from pathlib import Path

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .action.actuator import ActionActuator
from .action.construction.revisions import ConstructionStore
from .action.construction.workshop import Workshop
from .action.installation import start_installation
from .action.journal import Journal
from .action.registry import ServiceRegistry
from .api.admission import parse_access_flag
from .api.handlers_chat import handle_chat, handle_chat_reply_poll
from .api.handlers_chat_history import (
    handle_delete_conversation,
    handle_get_chat_history,
    handle_list_conversations,
    handle_new_conversation,
    handle_resume_conversation,
)
from .api.handlers_config import handle_config
from .api.handlers_health import handle_health
from .api.handlers_misure import handle_misure
from .api.handlers_models import (
    handle_get_models_config,
    handle_list_models,
    handle_save_models_config,
)
from .api.handlers_settings import (
    handle_get_settings,
    handle_save_settings,
)
from .api.handlers_usage import handle_reset_usage, handle_usage, handle_usage_history
from .api.middleware_csrf import csrf_middleware
from .api.middleware_internal_auth import internal_auth_middleware
from .api.shell import _compute_build_stamp, _read_static_pages, _security_headers, _serve_shell

# review C/#15: `_spawn`, l'unico posto che crea un compito senza padrone, vive
# in `background.py` dal 06/10/2026 (attori, Task 4.5): ne ha bisogno anche un
# modulo di `mind/`, che non importa questo file.
from .background import spawn as _spawn
from .chat_settings import ChatSettings, file_lacks_retention_days
from .chat_store import open_store as open_chat_store
from .chat_thread import SyncTurnsInFlight, thread_for
from .conservazione import (
    cancella_residui,
    decidi_vault,
    nightly,
    reasoning_sweep,
)
from .home_space import historian
from .home_space.behavior import reread_dashboards
from .home_space.historian import (
    house_timezone,
)
from .home_space.reader import HomeSpace
from .home_space.redaction import home_assistant_folder
from .home_space.registry_follower import schedule_registry_rebuild
from .home_space.rounds import (
    behavior_reader,
    integration_follower,
    reload_entity_inventory,
    reread_ha_problems,
    schedule_behavior_reread,
    schedule_dashboards_reread,
    tree_comparison_round,
)
from .home_space.topology import (
    rebuild,
)
from .keeper.exchange import interpreta_promise
from .keeper.store import AgendaStore
from .keeper.sweeper import Sweeper
from .memory.store import MemoryStore
from .mind import report
from .mind.analyst_round import analyst_round
from .mind.conditions_round import watch_automation_outcomes, watch_system_conditions
from .mind.day_report import (
    backfill_one_report,
    reaggregate_last_two_days,
    write_day_report,
)
from .mind.judgments import build_judgments
from .mind.knowledge import KnowledgeStore
from .mind.observer_round import hold_watcher_statistic_ids, reconsideration_round
from .mind.proposer_round import proposer_beat
from .mind.realignment import disconnection_recorder, mirror_reload_listener
from .mind.recipe_round import recipe_round
from .mind.reconciliation import after_rebuild
from .mind.seed import (
    REPO_PRIORITY,
    attribute_seed,
    judgment_seed,
    meaning_seed,
)
from .mind.state_words import prime_state_translations
from .mind.store import ObservationsStore
from .mind.watcher import Watcher
from .provider_occurrences import OccurrenceRegistry
from .providers import (
    CLAUDE,
    OLLAMA,
    OPENAI,
    OPENROUTER,
    SUBSCRIPTION,
    can_answer_at_startup,
    can_answer_now,
    credentials_present,
    outside_chain,
    providers_in_chain,
    subscription_has_token,
)
from .proxy.entity_cache import EntityCache
from .proxy.ha_client import HAClient
from .proxy.state_translations import StateTranslations

logger = logging.getLogger(__name__)



def _promise_delivery(app) -> dict:
    """I collaboratori con cui l'orologio consegna l'esito di una
    promessa (spec 2026-09-26 §2.4): chiusure su `app`, lette a ogni
    risveglio -- l'orologio non sa ne' di Home Assistant ne' della chat.

    - `recipients`: `recipients_for` sul client di Home Assistant di ADESSO
      e sul registro dei servizi dell'app (A-04: i `notify` da li', non da una
      lettura propria di `/api/services`);
    - `write_to_thread`: `chat_store.append_assistant_line` nella cartella
      dell'add-on (filtra i veleni, rifiuta un filo assente);
    - `ceiling`: `api/soffitto.py::ceiling_at_wake`, il soffitto di chi ha
      chiesto riletto al risveglio;
    - `owner_thread`: il filo del pannello del proprietario, se Home
      Assistant ne dice uno solo (`api/soffitto.py::sole_owner`) -- a chi
      l'orologio da' una promessa orfana che si sveglia prima che lui apra
      il pannello.
    """
    from .api.soffitto import ceiling_at_wake, sole_owner
    from .chat_store import append_assistant_line
    from .keeper.recipient import recipients_for

    async def _recipients(subject):
        return await recipients_for(subject, app.get("ha_client"),
                                    app.get("service_registry"))

    def _write(thread, content, *, quoted=None):
        return append_assistant_line(content, app["data_dir"], thread=thread,
                                     quoted=quoted)

    async def _ceiling(subject):
        return await ceiling_at_wake(app, subject)

    async def _owner_thread():
        # Il filo lo calcola `thread_for`, come per ogni richiesta dal
        # pannello (`ingress`): due calcoli dello stesso filo sono due fili.
        owner = await sole_owner(app)
        return thread_for(owner, "ingress") if owner else None

    return {"recipients": _recipients, "write_to_thread": _write,
            "ceiling": _ceiling, "owner_thread": _owner_thread}


def _bridge_active(store: dict | None) -> bool:
    """Il ponte e' acceso se, e solo se, `ponte.attivo` lo dice nell'archivio.

    Fino alla 2.3.1 questa funzione si chiamava `_chat_subscription_active` ed
    era un AND fra DUE opzioni dell'add-on (`chat_via_subscription` e
    `bridge_enabled`). L'AND era il fail-safe numero uno del rilascio: senza,
    si poteva instradare la chat in una coda che nessuno spazzava, e i
    messaggi restavano pendenti per sempre.

    Il proprietario ha fuso i due interruttori in uno solo (`ponte.attivo`,
    13 agosto 2026), e il fail-safe NON e' stato rimosso: e' diventato
    STRUTTURALE. C'e' UN valore, derivato UNA volta (`_recompute_chain`
    scrive `app["bridge_active"]`) e letto da tutti -- la spazzata,
    l'instradamento della chat, il gate del lavoratore del ponte, la pagina.
    L'invariante «non accodare mai in una coda che nessuno spazza» non regge
    piu' su un `and` da non sbagliare, e nemmeno su due chiamate alla stessa
    funzione: regge sul fatto che non c'e' niente da combinare.

    VERSIONE B (3.0.0): erano DUE argomenti, `interruttore` (da `BRIDGE_ENABLED`,
    cioe' dall'opzione `ponte.attivo`) e `piano_attivo` (`_sub_first_class`,
    cioe' `provider_subscription` acceso col suo token), combinati con un `or`.
    Il secondo era l'IMPLICAZIONE: il piano acceso accendeva il ponte da se'.
    Esce insieme all'opzione che lo alimentava, e non e' una perdita di
    comodita' senza contropartita -- era l'ultima seconda rappresentazione del
    prodotto (invariante 1): `app["bridge_active"]` poteva valere True mentre
    l'archivio, che e' cio' che la pagina Modelli mostra e scrive, diceva
    False. Con l'implicazione viva il bottone «Mettilo primo» non sarebbe
    costruibile: metterebbe a `true` un valore gia' scavalcato, e spegnere il
    ponte sarebbe impossibile per chiunque abbia un token.

    Chi aggiorna col token presente e `ponte.attivo` false perde il ponte, e
    NON in silenzio: `_bridge_notices` glielo dice all'avvio nel registro, la
    pagina Modelli lo dice in cima («Il Piano Claude Max ha il token, lo paghi,
    ed e' fuori dalla catena») e accanto a quella frase c'e' il bottone che lo
    riaccende in un gesto.

    Rimettere qui un secondo valore -- un `or` con una credenziale, un `and`
    con un interruttore -- farebbe cadere
    `test_chat_subscription_path.py::test_il_ponte_e_un_valore_solo`.
    """
    return bool(((store or {}).get("ponte") or {}).get("attivo", False))


def _bridge_notices(bridge_active: bool, token_presente: bool) -> list[str]:
    """Le due frasi che `run.sh` non puo' piu' dire, e perche' sono ancora qui.

    Fino alla 2.5.0 vivevano in `run.sh`: erano l'unico posto che parlava
    PRIMA che HIRIS partisse, e leggevano `PROVIDER_SUBSCRIPTION`/
    `BRIDGE_ENABLED`. Con la versione B quelle opzioni non esistono e il ponte
    vive nell'archivio di HIRIS, che da uno script di avvio non si legge. Le
    frasi non si cancellano -- descrivono i due stati che costano soldi senza
    dirlo -- si spostano dove l'archivio c'e'.

    Funzione PURA: restituisce le righe, non le scrive. E' cio' che permette di
    provarle senza montare un'applicazione, ed e' anche la ragione per cui il
    chiamante puo' decidere il livello.

    I due stati:

    - **ponte acceso, token assente**: nessun messaggio arriva al piano. Dal
      Task 14 il turno non si perde piu' (scende alla catena nella stessa
      richiesta), ma scende a un provider a consumo: un ripiego silenzioso dal
      forfait al consumo si scopre a fine mese.
    - **token presente, ponte spento**: e' lo stato in cui si ritrova chi
      aggiorna alla 3.0.0 avendo il piano acceso via `provider_subscription`
      SENZA aver mai acceso il ponte. Quell'opzione implicava il ponte; la
      versione B toglie l'implicazione (vedi `_bridge_active`), e la copia
      d'archivio della 2.5.0 aveva copiato l'OPZIONE `ponte.attivo`, non lo
      stato effettivo. Il ponte si spegne, e questa riga e' cio' che rende la
      cosa rumorosa invece che silenziosa: senza, la chat tornerebbe a pagare
      a consumo senza dirlo.
    """
    if bridge_active and not token_presente:
        return [("Il ponte e' acceso ma «Provider · Piano Claude Max — token» e' "
                f"vuoto: nessun messaggio arriva al {SUBSCRIPTION.name}, e ogni turno "
                "passa alla catena -- dal forfait al consumo. Incolla il token, "
                "oppure spegni il ponte dalla pagina Modelli di HIRIS.")]
    if token_presente and not bridge_active:
        return [(f"Hai il token del {SUBSCRIPTION.name}, ma il ponte e' spento: le "
                "risposte passano dalla catena, a consumo. Il ponte non si accende "
                "piu' da un'opzione dell'add-on -- si accende nella pagina Modelli "
                f"di HIRIS, col bottone accanto alla riga «Il {SUBSCRIPTION.name} ha il "
                "token, lo paghi, ed e' fuori dalla catena».")]
    return []


def should_start_agent_worker(bridge_active: bool) -> bool:
    """Gate worker del ponte in-addon: il ponte e' acceso, E il token c'e'.

    Fino alla 2.3.1 la seconda meta' della condizione leggeva
    CHAT_VIA_SUBSCRIPTION: era una delle tre cose che quell'opzione faceva, e
    l'unica che `bridge_enabled` non faceva. Fuse le due opzioni, questo gate
    e quello della spazzata leggono finalmente lo STESSO valore — prima si
    poteva far partire il worker (via `chat_via_subscription`) lasciando
    spenta la spazzata (`bridge_enabled`), e il worker sondava una coda che
    nessuno riempiva.

    VERSIONE B (3.0.0): non legge piu' NIENTE dall'ambiente per il ponte.
    `PROVIDER_SUBSCRIPTION` e `BRIDGE_ENABLED` erano le ultime due opzioni
    dell'add-on lette qui, e il valore arriva adesso come argomento --
    `app["bridge_active"]`, lo stesso che governa la spazzata e
    l'instradamento. E' una funzione di modulo senza `app`: passarglielo e'
    l'unico modo di tenerla una funzione pura e di renderla chiamabile ANCHE
    a caldo, cioe' quando la pagina Modelli accende il ponte senza un riavvio
    (`_recompute_chain`). Il token resta letto qui: e' una credenziale, e le
    credenziali stanno ancora nelle opzioni dell'add-on."""
    return bridge_active and subscription_has_token()


def _govern_bridge_worker(app) -> None:
    """Fa partire, o fa smettere, il lavoratore che risponde sul piano.

    Fino alla 2.5.0 questa decisione si prendeva UNA volta, alla fine
    dell'avvio, perche' l'interruttore del ponte era un'opzione dell'add-on e
    cambiarla voleva dire riavviare. Dalla versione B l'interruttore vive
    nell'archivio e la pagina Modelli lo riscrive: la decisione deve poterne
    seguire i cambiamenti, o accendere il ponte dalla pagina produrrebbe la
    peggiore delle due meta' (la chat instradata sul piano, e nessuno a
    rispondere: ogni turno aspetta la scadenza e poi ripiega sulla catena).

    Le due direzioni sono simmetriche e sono entrambe necessarie:
    - acceso e nessun lavoratore vivo -> si avvia;
    - spento e un lavoratore vivo -> si ferma. Senza questo ramo, spegnere il
      ponte lascerebbe un consumatore vivo per una coda che nessuno riempie,
      che si sveglierebbe a ogni turno accodato da chi non sa che il ponte e'
      spento.

    Senza un event loop in corso non si fa niente e non e' un ripiego: un
    compito asincrono non ha dove girare. Succede solo fuori dal server (i test
    che chiamano `_recompute_chain` come funzione), e in quel caso l'assenza
    del lavoratore e' il fatto vero, non una supposizione.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    voluto = should_start_agent_worker(bool(app.get("bridge_active")))
    current = app.get("agent_worker_task")
    live = current is not None and not current.done()

    if voluto and not live:
        from .agent import runner as _agent_runner
        from .usage.bridge_loads import BRIDGE_LOADS_KEY

        if app.get("usage") is not None:
            # I token dell'abbonamento smettono di finire solo nel log. Si
            # collega QUI, dove il lavoratore in-addon nasce.
            _agent_runner.set_usage_logger(app["usage"].log)
            # E il REGISTRO DEI TURNI, dalla stessa porta e per lo stesso
            # motivo (24/09/2026). Senza questa riga il ponte non scriveva
            # niente: 32 domande vere all'abbonamento Max avevano prodotto
            # zero righe, e il registro diceva «catena» di tutto perche'
            # quella era l'unica parola che qualcuno ci scriveva mai.
            # E la giunzione (spec «le misure complete» §4): i carichi che
            # /api/mcp annota per turno arrivano alla riga del ponte da qui.
            _agent_runner.set_turn_logger(_registra_turno_ponte(
                app["usage"], app.get(BRIDGE_LOADS_KEY)))
        # **Le intestazioni del ponte si coniano, non si leggono** (spec §5).
        # Un segreto letto dall'ambiente sarebbe unico, eterno, condiviso con
        # ogni altra integrazione, e finirebbe nella riga di comando del
        # sottoprocesso -- leggibile da qualunque processo del container.
        #
        # Adesso e' una credenziale che vive il doppio del turno piu' lungo
        # ammesso (`credenziali.durata_ponte_s`) e vale solo per il ponte. Il
        # sottoprocesso la riceve dalle STESSE intestazioni (vedi
        # `runner.reason`, che ne ricava `token` e `forms`), quindi anche
        # `--mcp-config` e la redazione dell'eco la seguono senza una riga in
        # piu'. Serve solo alla rotta degli strumenti: la coda il lavoratore
        # la legge direttamente (A-23, 06/10/2026).
        from .api.credenziali import credenziale_ponte_viva
        from .reasoning.consegna import consegna

        def _intestazioni_ponte() -> dict:
            return {"X-HIRIS-Internal-Token": credenziale_ponte_viva(app, adesso=time.time()),
                    "X-Requested-With": "hiris-agent"}

        async def _consegna(job_id, nonce, decision, now):
            return await consegna(app, job_id, nonce, decision, now)

        app["agent_worker_task"] = _spawn(
            _agent_runner.run_loop(
                app["reasoning_queue"],
                _consegna,
                "http://127.0.0.1:8099",
                _intestazioni_ponte,
                os.environ.get("HIRIS_AGENT_MODE", "live"),
            ),
            name="agent_worker",
        )
        logger.info(
            "Lavoratore del ponte avviato: il ponte e' acceso e il token del "
            "%s c'e'.", SUBSCRIPTION.name)
    elif not voluto and live:
        current.cancel()
        app["agent_worker_task"] = None
        # **Spegnere il ponte spegne il suo accesso, subito.** Aspettare la
        # scadenza vorrebbe dire che l'interruttore non stacca davvero niente.
        from .api.credenziali import revoca

        quante = revoca(app.get("credenziali") or {}, mestiere="ponte")
        (app.get("credenziale_ponte") or {}).clear()
        logger.info("ponte spento: revocate %d credenziali del turno", quante)
        logger.info(
            "Lavoratore del ponte fermato: il ponte e' spento, oppure manca il "
            "token del %s. La chat risponde dalla catena.", SUBSCRIPTION.name)


def _recompute_chain(app) -> None:
    """Rimette in vigore, a caldo, ciò che la pagina Modelli ha appena salvato.

    Senza questa funzione un riordino cambierebbe la PAGINA e non il RUNTIME:
    `handle_save_models_config` aggiorna `app["models_config"]`, ma la catena
    del router si costruiva solo all'avvio. Quindi il turno successivo usava
    l'ordine di prima e -- peggio -- la pagina, che descrive il runtime perché
    è la sola misura che ha, alla ricarica rimostrava l'ordine vecchio: il
    salvataggio sembrava perso. Era la stessa divergenza che questa fetta
    chiude, spostata di un livello, e fino al Task 10 c'era una riga in pagina
    che la confessava.

    VERSIONE B (3.0.0): rimette in vigore anche il PONTE. `app["bridge_active"]`
    era una copia presa all'avvio da `BRIDGE_ENABLED`, e finche' quel valore
    veniva da un'opzione dell'add-on non poteva cambiare senza un riavvio.
    Adesso viene dall'archivio, che la pagina Modelli riscrive: se restasse
    fermo all'avvio, accendere il ponte dalla pagina tornerebbe 200 e non
    farebbe niente fino al riavvio successivo -- esattamente il difetto che il
    Task 10 ha chiuso per la catena. Qui e' l'UNICO posto che lo scrive.
    """
    cfg = app.get("models_config") or {}
    # Un valore solo, derivato una volta, letto da tutti: la spazzata
    # (`conservazione.reasoning_sweep`), l'instradamento (`steering.who_answers`), la
    # pagina Consumi, il gate del lavoratore qui sotto. Nessuno dei quattro
    # ricalcola niente, quindi nessuno dei quattro puo' dire una cosa diversa.
    app["bridge_active"] = _bridge_active(cfg)
    # E il lavoratore del ponte SEGUE l'interruttore, invece di essere deciso
    # una volta all'avvio. Sono i due lati dello stesso fatto: accendere il
    # ponte senza far partire chi risponde vorrebbe dire accodare ogni turno in
    # una coda che nessuno serve, e ogni messaggio scadrebbe prima di ripiegare
    # sulla catena (Task 14) -- cioe' il bottone «Mettilo primo» sarebbe un
    # bottone che risponde 200 e fa aspettare. Spegnerlo senza fermarlo
    # lascerebbe un consumatore vivo per una coda che nessuno riempie.
    _govern_bridge_worker(app)
    router = app.get("llm_router")
    mappa = router._backend_map() if router is not None else {}
    risponde = can_answer_now(mappa, cfg)
    chain = providers_in_chain(cfg.get("chain_order") or [], risponde)
    # UN calcolo, DUE copie: quella che la pagina riceve e quella che il router
    # usa. Sono lo stesso valore -- se divergessero, divergerebbero da sé
    # stesse -- e sono due oggetti perché nessuno dei due possa modificare
    # l'altro per sbaglio (stessa ragione del `list(_chain)` dell'avvio).
    app["model_chain"] = list(chain)
    if router is None:
        return
    # NIENTE ripiego sulla policy precedente quando la catena è vuota: una
    # catena esplicitamente vuota vale per quello che dice. Un `or
    # router._chat_policy` rimetterebbe in piedi la regola legacy tolta al
    # Task 7 -- pagina che dice «la catena è vuota, HIRIS non può rispondere»
    # e chat che risponde lo stesso, usando l'ordine di prima.
    router._chat_policy = list(chain)
    ollama = mappa.get(OLLAMA.id)
    if ollama is not None:
        # L'unico valore della fetta che non si può leggere al momento
        # dell'uso: `AsyncOpenAI` cuoce il timeout nel client alla costruzione
        # (vedi `OpenAICompatRunner.apply_timeout`, che è un no-op quando il
        # numero non è cambiato).
        ollama.apply_timeout((cfg.get(OLLAMA.id) or {}).get(
            "timeout_s", OLLAMA.reply_timeout_s))


def _open_knowledge(app, data_dir: str) -> None:
    """Apre il sapere, lo semina e costruisce l'istantanea dei giudizi.

    **Il file e' `sapere.db`, NON `knowledge.db`**: quel nome e' gia' occupato
    su disco da un archivio documentale morto, dichiarato piu' sotto in
    `_on_startup`. Aprirlo qui troverebbe le sue tabelle, e il
    `CREATE TABLE IF NOT EXISTS` non direbbe niente.

    Il seme del repo scrive solo cio' che ancora non c'e': la casa scrive
    sopra, e un riavvio non cancella cio' che ha imparato.

    **Se aprire o seminare solleva, l'add-on parte lo stesso** (decisione del
    proprietario, 17/09/2026; spec 2026-09-16 §8): l'errore si logga, l'archivio
    aperto a meta' si chiude, `app["knowledge"]` resta `None` e l'istantanea
    si costruisce dal solo seme, col `perche` che porta l'errore vero -- e
    `/api/health` lo mostra. Ogni lettore di `app["knowledge"]` regge `None`:
    chi lo legge usa `app.get` o guarda `None` prima di usarlo (la chiave qui
    esiste sempre, quindi anche l'indice stretto del `Watcher` riceve `None`);
    `_on_cleanup` chiude solo un archivio che c'e'; la rotta di scrittura e
    quella del sapere rispondono 503.

    Una riga del sapere che non si interpreta non passa di qui: la gestisce
    `build_judgments`, con la stessa ricaduta sul seme.
    """
    knowledge = None
    try:
        knowledge = KnowledgeStore(os.path.join(data_dir, "sapere.db"))
        seeded = knowledge.seed(
            meaning_seed() + attribute_seed() + judgment_seed(),
            priority=REPO_PRIORITY)
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        # Con la traccia: un errore di programmazione dentro le funzioni del
        # seme non si diagnostica dal solo messaggio.
        logger.exception("sapere: non si apre, i giudizi vengono dal solo seme (%s)", reason)
        if knowledge is not None:
            try:
                knowledge.close()
            except Exception as close_error:
                logger.warning("sapere: chiusura dopo il guasto non riuscita (%s: %s)",
                               type(close_error).__name__, close_error)
        app["knowledge"] = None
        app["type_judgments"], app["type_judgments_status"] = build_judgments(
            None, unavailable_reason=reason)
        return
    if seeded:
        logger.info("sapere: %d righe del seme scritte (le altre c'erano gia')", seeded)
    app["knowledge"] = knowledge
    app["type_judgments"], app["type_judgments_status"] = build_judgments(knowledge)


def _chat_reply_submitter(app, data_dir: str):
    """La consegna del ponte per i turni `kind="chat"`, pubblicata
    dall'avvio in `app["submit_chat_reply"]`.

    Viveva annidata in `_on_startup`; e' una funzione di modulo dal
    03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'», D1) perche'
    le prove la possano costruire su un'app e una cartella loro invece di
    ritagliarla dal testo. Stesso codice, chiamata dallo stesso punto.
    """
    # Chat-via-abbonamento (Slice 4b, Task 1): submit-branch for kind="chat"
    # jobs — writes the runner's reply into chat_store instead of actuating
    # the house. Fetta «le chat divise»: la risposta va nel filo del job
    # (`thread`, letto dalla coda da `reasoning/consegna`) -- la
    # cronologia di chi ha scritto, non una sola per tutti.
    from .chat_store import _is_toxic_assistant as _is_toxic_chat_reply
    from .chat_store import append_messages as _append_chat_messages
    from .chat_thread import ChatThread

    async def _submit_chat_reply(reply_text: str, thread: ChatThread) -> None:
        if not reply_text:
            return
        # Final-review Fix 3 (Slice 4b): mirror the sync path's persistence
        # guard (handlers_chat.py) so a reply that arrived via the async
        # runner gets the same treatment as one from the local runner.
        if _is_toxic_chat_reply(reply_text):
            # Drop silently from the history, same as the sync path: the next
            # turn must not inherit a poisoned/leaked history. There's no
            # HTTP response here to carry a visible error (the caller already
            # got a 202 long ago) -- the poll route's chat_reply_skipped
            # handling is the user-facing side of this.
            #
            # Rilievo R1 della revisione indipendente sul tratto
            # `v3.22.2..HEAD`: la guardia sopra non deve tacere due volte.
            # Fino a questa correzione un turno del ponte tornato con uno dei
            # cinque sentinella d'errore (`chat_store.BRIDGE_SENTINELS`)
            # spariva qui senza lasciare NIENTE nel registro degli esiti --
            # non e' la stessa cosa di "non l'ho interrogato" (`occurrence()
            # is None`): il ponte ha risposto, e ha risposto con un
            # fallimento. Confondere le due e' la stessa contraddizione da
            # cui e' nato il Task 6 (Modelli che diceva «non l'hai ancora
            # usato» con turni riusciti in `consumo_giorno`), spostata dal
            # successo al fallimento. Il testo del sentinella non e' una
            # causa nota (nessun codice HTTP, nessuna credenziale, nessun
            # modello) -- e' `family="altro"`, come ogni guasto che il
            # prodotto misura senza inventarne il perche'.
            registry = app.get("occurrence_registry")
            if registry is not None:
                registry.fallimento(
                    SUBSCRIPTION.id, family="altro", code=None,
                    message=reply_text, durata_s=0.0)
            return
        # Task 6 (collaudo-3.22, indagine-abbonamento.md): QUI, e non prima
        # -- e non in `agent/runner.py::_logga_uso`, dove parte gia' Consumi.
        # Il ponte non passa mai da `LLMRouter.chat()` (l'unico chiamante di
        # `.successo(...)` fino a questa fetta): la pagina Modelli non aveva
        # nessun modo di sapere che il ponte avesse MAI risposto, e diceva
        # «non l'hai ancora usato» a un proprietario con 105 turni riusciti
        # da fine agosto (`GET /api/usage`, `last_use` di oggi).
        #
        # `_logga_uso` (che alimenta Consumi) e' PIU' A MONTE di questo punto:
        # gira dentro `_invoca`, prima che il chiamante guardi `invocation.rc`
        # o `occurrence.has_result` -- un turno con `rc != 0` o senza evento
        # finale puo' comunque avere un `usage` non vuoto (il conteggio dei
        # token puo' arrivare anche su un esito d'errore) e farebbe scrivere
        # un successo su un turno che non lo e' stato. Qui invece il successo
        # e' un fatto GIA' accertato: siamo dopo il filtro di tossicita' che
        # scarta i cinque sentinella d'errore del ponte
        # (`chat_store.BRIDGE_SENTINELS`) e dopo il controllo «reply non
        # vuota» -- se il codice arriva a questa riga, e' perche' sta per
        # scrivere in cronologia una risposta vera, la stessa che l'utente
        # sta per leggere. E' anche il motivo per cui NON sta in
        # `reasoning/consegna` (proposta dell'audit L3 dell'agosto
        # scorso, H2): li' la guardia e' solo «reply non vuota», che i
        # sentinella la superano -- registrare il successo li' avrebbe
        # sostituito la bugia di oggi con la bugia opposta.
        registry = app.get("occurrence_registry")
        if registry is not None:
            registry.successo(SUBSCRIPTION.id)
        _append_chat_messages([{"role": "assistant", "content": reply_text}], data_dir,
                              thread=thread)
    return _submit_chat_reply


#: Quanto l'avvio aspetta che Home Assistant confermi l'iscrizione prima di
#: leggere la casa (D2 della Tappa 2). Con Home Assistant su la conferma
#: arriva in una frazione di secondo; il tetto conta per l'avvio della
#: macchina, quando l'add-on parte prima del nucleo (`startup: services`) e
#: il websocket riprova ogni `RECONNECT_DELAY_S` (dieci secondi): oltre il
#: tetto l'avvio legge lo stesso, e lascia la rilettura alla prima connessione.
FIRST_CONNECTION_CAP_S = 10


async def _open_websocket(ha_client) -> bool:
    """Apre il websocket di lunga vita e aspetta, col tetto, che Home
    Assistant confermi l'iscrizione agli stati. Vero se e' arrivata.

    Se non arriva, l'avvio prosegue lo stesso -- non deve poter restare
    appeso a un nucleo che non c'e' -- e chiede al client che la PRIMA
    connessione, quando arrivera', faccia rileggere specchio, anagrafe,
    comportamento e plance (`HAClient.reread_after_first_connection`): cio'
    che l'avvio legge senza Home Assistant e' il vuoto, e senza quella
    rilettura resterebbe vuoto fino al primo evento di registro.
    """
    await ha_client.start_websocket()
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(ha_client.ws_ready.wait(), FIRST_CONNECTION_CAP_S)
    if ha_client.ws_ready.is_set():
        return True
    logger.warning(
        "Home Assistant non ha confermato l'iscrizione entro %ss: leggo la casa "
        "lo stesso, e la rileggo alla prima connessione", FIRST_CONNECTION_CAP_S)
    ha_client.reread_after_first_connection()
    return False


async def _on_startup(app: web.Application) -> None:
    # Serve ai lavori dello schedulatore, piu' sotto.
    import time as _time

    from .claude_runner import ClaudeRunner
    from .llm_router import LLMRouter

    # Pre-load static HTML so request handlers don't do sync open().read()
    # per request (would block the event loop). Cache invalidation happens via
    # _inject_version() on every render anyway.
    _read_static_pages(app)

    # `data_dir` si risolve qui in cima, e non piu' sotto insieme al resto degli
    # store: va risolta prima che qualunque middleware possa servire una
    # richiesta.
    data_dir = os.environ.get("HIRIS_DATA_DIR", "/data")
    app["data_dir"] = data_dir
    # CR-1: le reti sorgenti fidate. Il bypass dell'ingress vale solo per le
    # richieste che vengono di li', cosi' un `X-Ingress-Path` falsificato da un
    # client diretto (LAN, o un tunnel da un'altra macchina) non scavalca il
    # confine. Default: la rete Docker del Supervisor.
    #
    # A-3 (22/09/2026): le voci si VALIDANO. Prima si prendevano cosi' com'erano,
    # quindi `0.0.0.0/0` passava in silenzio e apriva `/api/*` a chiunque sapesse
    # scrivere un'intestazione. E un campo tutto sbagliato NON ripiega sul
    # default: ripiegare vorrebbe dire che scrivere male allarga il perimetro
    # invece di stringerlo.
    from .api.ingresso import perimetro_fidato

    _reti, _rifiutate, _come = perimetro_fidato(
        os.environ.get("SUPERVISOR_INGRESS_CIDR", ""))
    logger.info("ingress: mi fido di %s", _come)
    for _motivo in _rifiutate:
        logger.error("supervisor_ingress_cidr: %s", _motivo)
    if _rifiutate and not _reti:
        logger.error(
            "supervisor_ingress_cidr: nessuna voce valida, quindi NESSUNA rete "
            "è fidata e ogni richiesta dovrà autenticarsi. Correggi il campo "
            "nelle opzioni dell'add-on, oppure svuotalo per tornare al "
            "predefinito")
    app["supervisor_ingress_cidrs"] = [str(r) for r in _reti]
    ha_base_url = os.environ.get("HA_BASE_URL", "http://supervisor/core")
    if not ha_base_url.startswith("http://supervisor"):
        logger.warning(
            "HA_BASE_URL is %r — expected http://supervisor/core in production", ha_base_url
        )
    ha_client = HAClient(
        base_url=ha_base_url,
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
    )
    await ha_client.start()
    app["ha_client"] = ha_client

    # Cosa Home Assistant sa fare, in questa casa. Costruito vuoto: si carica
    # al primo uso (`ensure_fresh`), non all'avvio -- un caricamento qui
    # allungherebbe il boot per una cosa che potrebbe non servire in questa
    # sessione, e fallirebbe in silenzio se HA non fosse ancora pronto.
    app["service_registry"] = ServiceRegistry()

    # Il sapere: cio' che HIRIS ha capito, con la provenienza e le prove
    # (fetta «il sapere e le ricette», 12/09/2026, spec §8).
    #
    # **Nasce PRIMA della cache delle entita'**, insieme al suo seme e
    # all'istantanea dei giudizi, perche' lo prescrive la spec 2026-09-16 §8.
    # Oggi la cache non legge ne' il sapere ne' i giudizi: le sue porte del
    # vocabolario restano codice (spec §2) e l'istantanea non le arriva (§3).
    # L'ordine non ha quindi un lettore vivo che lo pretenda. Il blocco dipende
    # solo da `data_dir`, risolto in cima a questo avvio.
    _open_knowledge(app, data_dir)

    # **Prima l'iscrizione, poi la lettura** (D2 della Tappa 2, Task 7,
    # 03/10/2026). Fino a quel giorno l'avvio leggeva la casa e apriva il
    # websocket alla fine; la prima connessione rileggeva tutto -- specchio,
    # anagrafe, comportamento, plance -- per coprire gli eventi persi fra la
    # lettura e l'iscrizione: la casa letta due volte (R18). Adesso nascono
    # lo specchio e l'anagrafe, con i loro ascoltatori, si apre il websocket,
    # si aspetta che Home Assistant confermi l'iscrizione agli stati
    # (`ws_ready`), e POI si legge una volta: un evento arrivato durante la
    # lettura dello specchio finisce nel suo tampone (`EntityCache._reread`),
    # uno arrivato prima e' gia' nella fotografia. La prima connessione non
    # rilegge (`HAClient._listen`).
    entity_cache = EntityCache()
    ha_client.add_state_listener(entity_cache.on_state_changed)
    app["entity_cache"] = entity_cache

    # L'anagrafe nasce qui, vuota, e non piu' accanto alla sua prima
    # lettura (piu' sotto): l'iscrizione alle integrazioni le consegna le
    # voci appena il websocket si apre, e l'ascoltatore deve esserci prima.
    # Finche' la prima ricostruzione non e' riuscita le tiene solo in
    # `app["ha_integrations"]` (`HomeSpace.hold_integrations`).
    home_space_store = HomeSpace(data_dir, mirror=entity_cache)
    app["home_space_store"] = home_space_store
    ha_client.add_integration_listener(integration_follower(app))

    # **Chi tiene una copia della casa si iscrive PRIMA del websocket**
    # (revisione del ramo, 04/10/2026). Se Home Assistant non conferma entro
    # il tetto, `_open_websocket` chiede che la prima connessione avvisi
    # «riconnessione»; se quella connessione arriva mentre l'avvio e' ancora
    # qui sotto, l'avviso va a chi e' iscritto IN QUEL MOMENTO. Iscritti dopo,
    # specchio, anagrafe, comportamento, plance e servizi lo perdevano, e la
    # loro copia letta nel vuoto restava vuota fino al primo evento di
    # registro. Costruirli qui non legge niente: sono fabbriche di
    # ascoltatori, e le letture partono solo all'avviso o piu' sotto.
    #
    # L'anagrafe: si ricostruisce quando la casa cambia, e dopo ogni
    # ricostruzione riscalda le parole degli stati e riconcilia gli archivi
    # (`mind/reconciliation.after_rebuild`; legge `app.get(...)`: un avviso
    # arrivato prima della nascita di cio' che chiede, piu' sotto, lo dice e
    # non solleva). Lo specchio si rilegge alla riconnessione.
    ha_client.add_topology_listener(
        schedule_registry_rebuild(ha_client, home_space_store,
                                  then=lambda: after_rebuild(app)))
    ha_client.add_topology_listener(
        mirror_reload_listener(ha_client, entity_cache, lambda: app.get("watcher")))
    ha_client.add_disconnection_listener(disconnection_recorder(lambda: app.get("watcher")))
    # Il comportamento: la stessa `watch_behavior` che l'avvio chiama piu'
    # sotto per la prima lettura, e che lo schedulatore rilegge a cadenza.
    ha_config_dir = home_assistant_folder()
    watch_behavior = behavior_reader(
        ha_client, entity_cache, home_space_store,
        Path(ha_config_dir) if ha_config_dir else None,
    )
    ha_client.add_topology_listener(
        schedule_behavior_reread(watch_behavior))
    # Le plance: cadenza propria (DASHBOARD_EVENT), non i registri.
    ha_client.add_dashboard_listener(schedule_dashboards_reread(ha_client, home_space_store))
    # I servizi si rinfrescano su EVENTO, non a scadenza. Prima si ricaricavano
    # solo dopo 300 secondi, e per quei cinque minuti HIRIS rifiutava i servizi
    # di un'integrazione appena installata dicendo «non esiste in questa casa»:
    # una frase FALSA detta con sicurezza, che e' peggio di un «non lo so».
    #
    # Si INVALIDA e basta -- la rilettura la fa `ensure_fresh` al prossimo
    # comando. Installare un'integrazione emette una raffica di eventi, e una
    # lettura per ognuno sarebbe una tempesta per un dato che serve solo quando
    # qualcuno chiede di agire.
    _service_registry = app["service_registry"]
    ha_client.add_service_listener(lambda _type: _service_registry.invalidate())

    await _open_websocket(ha_client)

    try:
        await entity_cache.load(ha_client)
    except Exception as exc:
        logger.warning("EntityCache load failed: %s", exc)

    # Come si RENDE uno stato di Home Assistant (fetta «lo stato»,
    # 07/09/2026). Costruito vuoto, come il registro dei servizi qui sopra, e
    # **scaldato piu' sotto** (`prime_state_translations`, subito dopo
    # `app["home_space_store"]`, che e' dove la lingua della casa diventa
    # leggibile).
    #
    # Fino all'08/09/2026 la prima lettura avveniva «alla prima pagina che ne
    # ha bisogno», e la ragione scritta qui era buona: allungare l'avvio per
    # una tabella che quella sessione poteva non chiedere mai. **Non vale
    # piu'**: da quando le quattro tabelle scritte a mano non esistono (spec
    # §6), queste parole sono cio' con cui il NUCLEO rende ogni stato notevole,
    # a ogni turno e dal primo. La lettura pigra e' rimasta -- `read` continua
    # a costare zero finche' la casa non cambia versione o lingua -- ma adesso
    # c'e' qualcuno che la fa partire.
    app["state_translations"] = StateTranslations(ha_client)

    # I guasti che Home Assistant ha gia' diagnosticato. Qui la PRIMA lettura,
    # accanto all'inventario perche' e' la stessa specie di dato: una
    # fotografia momentanea che vive in RAM e non in archivio (il perche' per
    # esteso e' su `reread_ha_problems`). Le riletture sono un lavoro dello
    # schedulatore, piu' sotto.
    #
    # Prima di questa riga la chiave non esiste, e `compose()` lo legge come
    # «non ho chiesto» -- non come «non c'e' niente di rotto». Se Home
    # Assistant e' giu' proprio adesso, `problems()` risponde `{"errore": ...}`
    # e il nucleo lo dichiara: la finestra in cui HIRIS tace su questo e' larga
    # quanto il boot.
    await reread_ha_problems(app, ha_client)

    # Il cervello, per ora il solo osservatore (fetta «l'osservatore», Task 5:
    # docs/design/2026-08-26-l-osservatore.md). L'archivio nasce prima di lui
    # perche' e' il suo unico ingresso.
    app["observations"] = ObservationsStore(
        os.path.join(data_dir, "osservazioni.db"))
    # La quiete del recupero delle cronache (`BACKFILL_QUIET_S`): nasce qui,
    # prima che aiohttp congeli l'app, perche' il giro la usa ad app avviata.
    app["backfill_quiet"] = {}
    # Il sapere e' nato piu' sopra, prima della cache delle entita'.
    # L'osservatore riceve il sapere: da li' legge **quali attributi valga la
    # pena tenere** per un tipo (spec §5.4). Senza, scriverebbe come prima e
    # l'esempio fondativo del cervello -- «il riscaldamento parte alle 15:30,
    # la casa e' calda alle 16:30» -- resterebbe non rispondibile.
    app["watcher"] = Watcher(app["observations"], knowledge=app["knowledge"])
    # Rilegge dall'archivio le condizioni di sistema gia' aperte prima di
    # QUESTO avvio (task-5-correzioni.md, punto B): senza, ogni riavvio
    # dell'add-on -- che succede a ogni aggiornamento -- riscriverebbe
    # "aperto" per ogni guasto gia' aperto, come se fosse nato in quel
    # momento, e l'oggetto «guasto» perderebbe la sua unica informazione
    # utile: da quando dura. **Prima** del primo giro delle condizioni, qui
    # sotto. Non solleva mai (vedi il suo docstring).
    app["watcher"].rebuild_conditions()
    # LO STESSO rubinetto che alimenta lo specchio, non un secondo: due
    # sorgenti degli stessi eventi sarebbero due cose che possono divergere.
    # Si aggancia DOPO lo specchio: se un giorno l'ordine contasse, conta che
    # lo specchio sia aggiornato prima.
    ha_client.add_state_listener(app["watcher"].watch_reading)

    # L'istante di avvio di QUESTO processo (giro di correzioni Task 4):
    # serve al cursore delle tracce di automazione in
    # `watch_automation_outcomes`, per scartare una traccia piu' vecchia di
    # questo istante -- scattata mentre HIRIS era spento (o in un avvio
    # precedente), che non si recupera. Stessa disciplina gia' scritta per
    # `watch_system_conditions`: meglio un buco nella storia che una bugia
    # nella storia. Scritto QUI e non dentro `watch_automation_outcomes`
    # stesso: quella funzione gira ogni due minuti, e fissare l'istante ad
    # ogni chiamata lo farebbe scivolare in avanti a ogni giro invece di
    # restare l'istante del boot.
    app["automation_traces_boot_ts"] = time.time()

    # L'evento delle automazioni (Task 4 di «le tracce e il log»,
    # AUTOMATION_TRIGGERED_EVENT in `proxy/ha_client.py`): segna soltanto,
    # non scrive -- vedi il docstring di `Watcher.mark_automation` per il
    # perche'. Il glue e' qui e non un metodo di `Watcher` apposta:
    # l'interfaccia che questo task produce e' `mark_automation(entity_id)`
    # -- estrarre `entity_id` dal dizionario grezzo dell'evento e' cablaggio
    # di questo file, non un giudizio dell'osservatore. Il nome che l'evento
    # porta non si tiene (A-18): lo dice la casa all'esito.
    def _mark_triggered_automation(event_data: dict) -> None:
        if not isinstance(event_data, dict):
            return
        entity_id = event_data.get("entity_id")
        if isinstance(entity_id, str):
            app["watcher"].mark_automation(entity_id)
    ha_client.add_automation_listener(_mark_triggered_automation)

    # La prima lettura delle condizioni di sistema (problemi diagnosticati +
    # integrazioni non caricate; task-5-correzioni.md, punto A), qui accanto
    # per lo stesso motivo di `reread_ha_problems` piu' sopra: senza,
    # l'osservatore vedrebbe le condizioni gia' aperte solo al primo giro del
    # lavoro periodico, fino a dieci minuti dopo l'avvio. A differenza di
    # quella lettura, questa PUO' sollevare (`Watcher.watch_system`, se
    # `record` fallisce a meta'): un archivio che non risponde non deve
    # impedire il boot.
    try:
        await watch_system_conditions(app, ha_client)
    except Exception as exc:
        logger.warning(
            "cervello: primo giro delle condizioni di sistema fallito: %s", exc)

    # Il registro delle esecuzioni (`action/journal.py`): la riga di log che
    # la porta scriveva gia' con `logger.info`, resa CHIEDIBILE (fondamenta
    # n.4 -- nessuno poteva interrogarla). Nasce PRIMA della porta, perche' la
    # porta la riceve qui sotto.
    app["journal"] = Journal(os.path.join(data_dir, "azioni.db"))

    # L'archivio delle promesse (`keeper/store.py`): l'unica casa di
    # «cosa e quando». Nasce qui, accanto alla cronaca -- i due archivi nuovi
    # di questo cablaggio. La legge sia la chat (via
    # `create_tool_dispatcher`, per `promise`/`agenda`/`cancel`)
    # sia lo schedulatore -- l'orologio, montato piu' sotto insieme al
    # battito, perche' gli serve prima lo scheduler, costruito piu' avanti in
    # questa funzione.
    app["agenda"] = AgendaStore(os.path.join(data_dir, "promesse.db"))

    # L'unico punto del prodotto che esegue qualcosa su Home Assistant
    # (`action/actuator.py`). Sta QUI, e non accanto a `service_registry` piu'
    # sopra, per l'ordine: la porta ha bisogno dello specchio dello stato
    # (`entity_cache`) per rileggere dopo aver agito, e sopra la cache non
    # esiste ancora -- `app.get("entity_cache")` avrebbe dato `None` e la
    # porta avrebbe rifiutato OGNI azione con «non vedo lo stato di questa
    # casa», per sempre. Costruita una volta e condivisa: la chat la usa oggi
    # via `create_tool_dispatcher`, lo schedulatore e il brain
    # domani, senza che ne nasca una seconda.
    app["action_actuator"] = ActionActuator(ha_client, app["service_registry"],
                                      app.get("entity_cache"), app["journal"],
                                      home_space_store=app.get("home_space_store"))

    # L'archivio delle costruzioni e l'officina (fetta «costruire»,
    # docs/design/2026-08-22-costruire-in-home-assistant.md). Nascono QUI e non
    # piu' in alto per l'ordine: l'officina riceve la cronaca (che nasce sopra)
    # e il canale HA. Non riceve la porta e non la usa: sono due canali di
    # scrittura diversi -- «un canale, una porta», spec §2.1 -- e l'officina
    # non chiama mai un servizio.
    app["constructions"] = ConstructionStore(
        os.path.join(data_dir, "costruzioni.db"))

    app["workshop"] = Workshop(
        ha_client, app["constructions"], app["journal"],
        read_timezone=lambda: house_timezone(app.get("home_space_store")))

    # L'archivio dei modelli si legge prima di costruire `LLMRouter`, piu' sotto:
    # la catena si compone da `chain_order`.
    from .models_store import load_models_config
    # Qui c'era la semina delle opzioni dell'add-on (`options_migration.seed`):
    # copiava nell'archivio, una volta sola, sette valori che arrivavano
    # dall'ambiente. Dalla 3.0.0 `run.sh` non li esporta piu', e sulla casa la
    # copia e' avvenuta da tempo (misurato il 02/10/2026: `seminato` vero).
    # L'archivio e' la sola fonte, e i campi che non ha partono dai
    # predefiniti di `load_models_config`.
    app["models_config"] = load_models_config(data_dir)

    # Task 5 SDD casa: l'anagrafe (nata piu' sopra, prima del websocket) si
    # costruisce all'avvio e si rifa' quando la casa cambia. La costruzione
    # iniziale non deve poter impedire il boot: un Home Assistant non ancora
    # pronto lascia l'anagrafe vuota con un avviso nel log, non fa fallire
    # l'add-on -- la prima connessione (`reread_after_first_connection`) o il
    # primo evento di registro la ricostruiranno.
    #
    # I suoi ascoltatori sono iscritti piu' sopra, prima del websocket.

    # **L'anagrafe si legge SUBITO, prima di chi la usa.** Da quando la casa
    # non e' piu' replicata su disco, `read()` torna `{}` finche' una lettura
    # non e' riuscita -- e la riparazione d'avvio, qui sotto, ne ha bisogno:
    # `_report_ingredients` cerca le ricette dei dispositivi elencati
    # nell'anagrafe, e su una casa vuota non ne trova nessuna, quindi il
    # resoconto riparato nascerebbe senza misure.
    try:
        await rebuild(ha_client, home_space_store)
    except Exception as exc:
        logger.warning("costruzione iniziale dell'anagrafe fallita: %s", exc)

    # La riparazione d'avvio: scrive il resoconto degli ultimi due giorni
    # pieni che non ce l'hanno (vedi `_reaggregate_days`).
    #
    # **QUI, dopo `app["home_space_store"]` e dopo `rebuild`**: la riparazione
    # chiede all'anagrafe il fuso della casa e i dispositivi di cui cercare le
    # ricette. Chiamata prima lavorerebbe in UTC e su una casa vuota, mentre
    # l'aggregazione notturna (`_aggrega_ieri`, piu' sotto) lavora col fuso
    # vero: le due porte, sullo stesso grezzo, darebbero resoconti diversi.
    # L'ordine lo sorveglia, eseguendo questo blocco,
    # `test_la_riparazione_di_avvio_riceve_home_space_store_gia_costruito`
    # (`tests/test_mind_wiring.py`).
    #
    # Attesa, e in un try/except che non deve bloccare l'avvio: un cervello
    # che non riparte perche' non e' riuscito a rifare l'altro ieri sarebbe
    # peggio del buco che sta chiudendo.
    try:
        await reaggregate_last_two_days(app, ha_client)
    except Exception as exc:
        logger.warning(
            "cervello: riaggregazione degli ultimi due giorni all'avvio "
            "fallita (%s: %s)", type(exc).__name__, exc)

    # LE PAROLE DEGLI STATI, scaldate QUI e non accanto alla costruzione della
    # cache: `prime_state_translations` legge `(versione_ha, lingua)` dal
    # sistema di riferimento, che vive nell'anagrafe -- chiamarla piu' sopra,
    # dove `home_space_store` non esiste ancora, avrebbe letto una lingua vuota
    # e non avrebbe letto niente. Qui `rebuild()` e' gia' passata; e anche
    # quando non riesce, il sistema di riferimento e' l'unica cosa
    # dell'anagrafe che resta su disco fra un riavvio e l'altro
    # (`HomeSpace._write_reference_frame`, e il suo docstring dice
    # perche' proprio quella).
    #
    # E **dopo** la riparazione d'avvio, non in mezzo: quel blocco e' eseguito
    # per davvero da una prova che ne estrae il sorgente
    # (`test_mind_wiring.py::_estrai_blocco_riparazione_avvio`), e infilarci
    # dentro una chiamata che quella prova non conosce l'avrebbe fatta fallire
    # su un nome mancante invece che sull'ordine che sorveglia.
    #
    # E' il seguito della prima ricostruzione, lo stesso delle altre: con le
    # parole degli stati, la riconciliazione degli archivi (Tappa 8, D1), che
    # da sola si ferma se Home Assistant non si e' ancora dichiarato avviato.
    await after_rebuild(app)

    # L'archivio dei consumi: l'UNICA casa di «quanto ho speso, e per cosa».
    # Nasce DOPO `home_space_store` perche' gli chiede il fuso -- a ogni
    # scrittura, non alla costruzione: la casa puo' cambiarlo
    # (`core_config_updated`), e un fuso cotto qui sarebbe quello dell'avvio.
    from .usage.store import UsageStore

    app["usage"] = UsageStore(
        os.path.join(data_dir, "consumi.db"),
        read_timezone=lambda: house_timezone(home_space_store))

    # La verifica dell'albero: `hierarchy()` smette di essere un'affermazione
    # che nessuno controlla. Costruita QUI, subito dopo l'anagrafe, perche' e'
    # da quella che prende il campione; il primo giro parte adesso e i
    # successivi li chiama lo schedulatore (piu' sotto, quindici minuti).
    #
    # Il primo giro all'avvio non serve a trovare divergenze -- la replica e'
    # appena stata rifatta, e' il momento in cui e' piu' fresca (vedi
    # `tree_comparison_round`) -- ma a far vedere subito, dal vivo, che il
    # cablaggio c'e' e cosa risponde questa casa. Se Home Assistant e' giu'
    # adesso, l'esito lo dichiara area per area invece di tacere.
    # Una variabile locale e non una chiave di `app`: la chiusura la legge solo
    # lo schedulatore, qui sotto e dentro la stessa funzione. Metterla in `app`
    # sarebbe un dato scritto e mai letto da nessun altro.
    tree_comparison = tree_comparison_round(app, ha_client)
    try:
        await tree_comparison()
    except Exception as exc:
        logger.warning("primo confronto dell'albero non riuscito: %s", exc)

    # Il comportamento (il corpo di automazioni e script) segue lo stesso
    # principio dell'anagrafe -- prima lettura all'avvio senza poter impedire
    # il boot -- e dal 10/09/2026 la stessa fonte: Home Assistant. Due
    # inneschi, non uno: la cadenza di cinque minuti (sotto, job
    # "hiris_behavior_reader") e l'evento di registro entita', che scatta
    # quando un'automazione nasce o sparisce e fa rileggere subito.
    #
    # La cartella di Home Assistant serve ancora, per `secrets.yaml`: e' la
    # dichiarazione del proprietario su cosa sia segreto, e senza di essa i
    # corpi non si archiviano.
    #
    # **Una lettura sola all'avvio, questa** (Task 7 della Tappa 2, passo 3):
    # la prima connessione non fa piu' rileggere (D2), e la rilettura
    # sull'evento resta per i cambi e le riconnessioni. L'ascoltatore
    # che la richiama e' iscritto piu' sopra, prima del websocket.
    try:
        await watch_behavior()
    except Exception as exc:
        logger.warning("prima lettura del comportamento fallita: %s", exc)

    # Task 5 SDD casa: le plance, compresa la predefinita (url_path nullo)
    # che HIRIS non aveva mai visto. Cadenza propria (DASHBOARD_EVENT, non i
    # registri): non stanno in `reader.TABLES`, quindi una ricostruzione
    # dell'anagrafe non le tocca e viceversa. Come l'anagrafe, la prima
    # lettura non deve poter impedire il boot. Una lettura sola all'avvio,
    # questa, come per il comportamento; l'ascoltatore e' iscritto piu' sopra,
    # prima del websocket.
    try:
        await reread_dashboards(ha_client, home_space_store)
    except Exception as exc:
        logger.warning("prima lettura delle plance fallita: %s", exc)

    # L'archivio della memoria vive nel suo file (memoria.db): e' cio' che
    # l'utente ha detto e cio' che HIRIS ne ha capito, non una REPLICA
    # ricostruibile da HA (vedi memory/store.py). Nessuna lettura iniziale da
    # fare qui: a differenza dell'anagrafe non c'e' nulla da ricostruire
    # all'avvio.
    memory_store = MemoryStore(os.path.join(data_dir, "memoria.db"))
    app["memory_store"] = memory_store

    # L'archivio dei servizi accoppiati (22/09/2026). Qui non vive nessun
    # segreto: solo chiavi PUBBLICHE, il ruolo che il proprietario ha dato e lo
    # stato. Si puo' leggere per intero senza che ne esca niente di utile.
    from .api.servizi import open_services
    open_services(app, os.path.join(data_dir, "servizi.db"))

    # Il WebSocket verso Home Assistant e' gia' aperto (`_open_websocket`, piu'
    # sopra, prima della prima lettura). Gli ascoltatori iscritti dopo
    # l'apertura -- l'osservatore e le automazioni -- non perdono niente che
    # prima ricevessero: fino al Task 7 il websocket si apriva qui, e prima di
    # qui nessun evento arrivava a nessuno. Nessuno dei due riceve l'avviso
    # «riconnessione».

    # Le impostazioni della chat: un bot solo, senza id, coi default nel codice
    # (vedi `chat_settings.py`).
    chat_settings = ChatSettings.load(data_dir)
    app["chat_settings"] = chat_settings
    # L'archivio della chat, come gli altri (D-27): la finestra la legge dalle
    # impostazioni a ogni potatura, perche' la pagina la cambia a caldo.
    app["chat_store"] = open_chat_store(
        data_dir, read_retention_days=lambda: app["chat_settings"].retention_days)

    # `giorni_conservazione` arriva al disco al primo avvio. `load()` da' il
    # default quando la chiave non c'e', ma non lo SCRIVE, e `save()` ha un solo
    # chiamante di produzione (la PUT di «Impostazioni chat»): chi quella
    # pagina non la apre mai non produrrebbe mai la chiave. Nasce come meta'
    # di una migrazione (il valore arrivava da `HISTORY_RETENTION_DAYS`, letta
    # fino al 02/10/2026); oggi scrive il default, una volta sola: dal secondo
    # avvio il file porta la chiave e questo ramo non fa piu' niente.
    #
    # Un disco che non collabora non deve impedire il boot: si dichiara e si
    # prosegue, come per l'anagrafe e il comportamento qui sopra. Il valore in
    # memoria e' comunque quello giusto; a mancare sarebbe solo la persistenza,
    # e il cancello del rilascio la verifica esplicitamente
    # (docs/prova-modelli-e-catena.md, quarta precondizione).
    if file_lacks_retention_days(data_dir):
        try:
            chat_settings.save(data_dir)
            logger.info(
                "'giorni_conservazione' (%d) e' stato scritto in "
                "impostazioni_chat.json: si cambia dalla pagina Impostazioni "
                "chat.",
                chat_settings.retention_days,
            )
        except OSError as exc:
            logger.warning(
                "'giorni_conservazione' (%d) NON e' stato scritto su disco "
                "(%s). Il valore vale per questo avvio, e al prossimo si "
                "riparte dal default: per fissarlo, salvalo dalla pagina "
                "Impostazioni chat.",
                chat_settings.retention_days, exc,
            )

    # Lo scheduler (APScheduler) non era mai stato concettualmente
    # dell'entita' Chatbot -- ci viveva sopra solo perche' ChatbotEngine lo
    # ospitava (avviato/fermato nel suo start()/stop()), ma i lavori che
    # registra piu' sotto (ricarica inventario, sentinella comportamento,
    # retention, spazzata della coda di ragionamento)
    # non hanno niente a che fare coi chatbot. Con l'entita' uscita per
    # intero, trova casa direttamente qui.
    # **Nessun `timezone=` esplicito, ed e' una scelta verificata, non una
    # dimenticanza** (cancello-rilascio-brief.md, punto 4). `AsyncIOScheduler()`
    # senza `timezone` risolve col fuso LOCALE del sistema
    # (`apscheduler.util.astimezone(None) or get_localzone()`, via `tzlocal`),
    # che su Linux legge PRIMA la variabile d'ambiente `TZ`. Ne' `config.yaml`,
    # ne' `Dockerfile`, ne' `run.sh` la impostano (cercato nei tre, nessun
    # risultato) -- ma non serve che lo facciano: il Supervisor di Home
    # Assistant imposta `TZ` da SOLO in OGNI container di add-on, al fuso
    # configurato in Home Assistant (fallback: quello dell'host, poi UTC).
    # Verificato leggendo il sorgente vero del Supervisor (non indovinato):
    # `supervisor/docker/app.py` (`DockerApp.environment`, la property che
    # costruisce l'ambiente Docker di OGNI add-on) scrive sempre
    # `{ENV_TIME: self.sys_timezone}` con `ENV_TIME = "TZ"`
    # (`supervisor/docker/const.py`), e `sys_timezone`/`CoreSys.timezone`
    # (`supervisor/coresys.py`) e' `config.timezone` (il fuso di HA) con
    # ripiego sul fuso dell'host e poi su `"UTC"`. Quindi in produzione (sotto
    # il Supervisor vero, non `docker run` nudo) `TZ` c'e' sempre, e le 00:20
    # dichiarate da pagina, README e piano sono davvero le 00:20 della casa --
    # la stessa fonte del fuso che `home_space_store.reference_frame()`
    # legge per l'aggregazione stessa (§0 sopra). Nessuna correzione: ne' al
    # container/schedulatore (gia' corretto da chi lo ospita), ne' alle tre
    # frasi (gia' vere). Resta vero solo FUORI dal Supervisor -- uno sviluppo
    # locale con `docker run` nudo vedrebbe UTC -- ma quel caso non e' come
    # l'add-on gira davvero.
    scheduler = AsyncIOScheduler()
    scheduler.start()
    app["scheduler"] = scheduler

    app["theme"] = os.environ.get("THEME", "auto")

    api_key = os.environ.get("CLAUDE_API_KEY", "")
    local_model_url = os.environ.get("LOCAL_MODEL_URL", "")
    if local_model_url:
        try:
            from .backends.ollama import _validate_ollama_url
            _validate_ollama_url(local_model_url)
        except ValueError as exc:
            logger.error("Invalid LOCAL_MODEL_URL (%s) — disabling local model", exc)
            local_model_url = ""
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
    # Le credenziali stanno nell'app, dove le leggono anche la pagina Modelli e
    # `/api/models`: la tabella dei provider le misura da qui
    # (`providers.credentials_present`), all'avvio come in ogni richiesta.
    app["claude_api_key"] = api_key
    app["openai_api_key"] = openai_api_key
    app["openrouter_api_key"] = openrouter_api_key
    app["local_model_url"] = local_model_url

    # ── Le credenziali, e nient'altro ──────────────────────────────────
    # fetta «la catena diventa l'unica verita'»: qui c'erano i cinque
    # interruttori `provider_*` incrociati con le credenziali
    # (`derive_active_providers`), cioe' la SECONDA rappresentazione dello
    # stato di un provider. Adesso l'unica cosa che si misura qui e' se la
    # credenziale c'e'; chi la USA lo dice `chain_order`.
    _credentials = credentials_present(app)

    # Le semine dell'archivio dei modelli: `options_migration.seed_at_startup`.
    from .options_migration import seed_at_startup
    seed_at_startup(app, data_dir, _credentials)

    # Qui viveva `_sub_first_class`, cioe' `_credenziali["subscription"] and
    # env_bool("PROVIDER_SUBSCRIPTION")`: il Piano Claude Max acceso col suo
    # token IMPLICAVA il ponte, e l'implicazione entrava in tutti e due i gate
    # (la spazzata e l'instradamento). E' USCITA con la versione B, insieme
    # all'opzione che la alimentava -- l'ultimo dei cinque interruttori ancora
    # letto, e l'ultima seconda rappresentazione del prodotto: con lei viva,
    # `app["bridge_active"]` poteva dire True mentre `ponte.attivo`, cioe' cio'
    # che la pagina Modelli mostra e scrive, diceva False. Il ponte adesso e'
    # un valore solo (`_bridge_active`, che legge l'archivio), e si accende
    # dalla pagina -- dove c'e' anche il bottone che lo fa in un gesto.
    #
    # Le due frasi che `run.sh` diceva su questo stato si sono spostate qui
    # sotto (`_bridge_notices`): da uno script di avvio l'archivio non si
    # legge, e restare in silenzio avrebbe reso muta proprio la transizione che
    # questa versione produce.

    decidi_vault(data_dir)

    # Ricarica dell'inventario entita' dopo un avvio senza Home Assistant.
    # `entity_cache.load` piu' sopra logga e prosegue se fallisce: senza questo
    # lavoro la cache resterebbe "mai caricata" fino al riavvio dell'addon, e
    # gli strumenti che la leggono continuerebbero a rispondere "non ancora
    # pronto" per sempre.
    #
    # Due minuti: un'indisponibilita' passeggera (riavvio del core, rete che
    # balbetta) rientra entro il giro successivo invece che alla prossima notte.
    # Il costo con Home Assistant giu' per davvero e' una GET /api/states ogni
    # due minuti -- meno della ronda della sentinella -- e appena la lettura
    # riesce il lavoro torna a essere il controllo di una bandiera, senza
    # toccare piu' Home Assistant.
    async def _reload_inventory() -> None:
        await reload_entity_inventory(app.get("entity_cache"), ha_client)

    scheduler.add_job(
        _reload_inventory,
        trigger="interval", minutes=2,
        id="hiris_entity_cache_reload", replace_existing=True,
        misfire_grace_time=120,
    )

    # La rilettura dei problemi diagnosticati da Home Assistant. Cinque minuti,
    # la stessa cadenza della sentinella del comportamento qui sotto e per una
    # ragione simmetrica: un `repair` si apre e si chiude con una cadenza di
    # ore, non di secondi, e il costo di un giro e' un solo comando WebSocket.
    # Serve soprattutto al verso opposto -- un problema RIPARATO dall'utente
    # deve sparire dal nucleo da solo, o HIRIS continuerebbe ad annunciare un
    # guasto che non c'e' piu' fino al riavvio dell'add-on.
    async def _reread_problems() -> None:
        await reread_ha_problems(app, ha_client)

    scheduler.add_job(
        _reread_problems,
        trigger="interval", minutes=5,
        id="hiris_ha_problems", replace_existing=True,
        misfire_grace_time=300,
    )

    # Le parole degli stati. Cinque minuti come i problemi, e per una ragione
    # che NON e' «la tabella cambia spesso»: non cambia quasi mai, e infatti
    # `read` risponde dalla cache senza nemmeno chiamare finche' la casa non
    # cambia versione o lingua. Il giro serve al caso opposto -- **la prima
    # lettura fallita**: se all'avvio Home Assistant non era ancora pronto, il
    # nucleo dice «traduzioni non lette» a ogni turno finche' qualcuno non
    # riprova, e nessun altro lo farebbe. Cinque minuti e' quanto si accetta
    # che duri.
    async def _reread_state_translations() -> None:
        await prime_state_translations(app)

    scheduler.add_job(
        _reread_state_translations,
        trigger="interval", minutes=5,
        id="hiris_state_translations", replace_existing=True,
        misfire_grace_time=300,
    )

    # La verifica dell'albero contro Home Assistant. Quindici minuti, e la
    # cadenza e' piu' larga di quella dei problemi qui sopra per due ragioni
    # scritte per esteso su `tree_comparison_round`: cio' che si cerca e'
    # una replica che INVECCHIA (guardare piu' spesso non la fa invecchiare
    # prima), e una divergenza non si ripara con un clic -- rientra da sola
    # alla prossima ricostruzione dell'anagrafe. A coprire tutta la casa non e'
    # la frequenza ma la rotazione del campione: tre aree a giro, in ordine di
    # id, ricominciando da capo alla fine.
    scheduler.add_job(
        tree_comparison,
        trigger="interval", minutes=15,
        id="hiris_tree_comparison", replace_existing=True,
        misfire_grace_time=900,
    )

    # Task 4 SDD casa: la sentinella dell'mtime, registrata come lavoro
    # periodico come gli altri qui sopra. Cinque minuti: il comportamento
    # cambia con una cadenza di giorni, non serve un giro piu' stretto, e un
    # giro costa 66 ms misurati -- venti secondi di traffico al giorno.
    scheduler.add_job(
        watch_behavior,
        trigger="interval", minutes=5,
        id="hiris_behavior_reader", replace_existing=True,
        misfire_grace_time=300,
    )

    # I QUATTRO lavori periodici del cervello (fetta «l'osservatore», Task 5:
    # docs/design/2026-08-26-l-osservatore.md; il quarto, la cadenza breve
    # delle tracce di automazione, e' Task 4 di «le tracce e il log»).
    #
    # Le condizioni di sistema, ogni dieci minuti: la stessa funzione della
    # prima lettura fatta qui sopra all'avvio, `watch_system_conditions`
    # -- vedi il suo docstring per il perche' un giro si salta interamente
    # quando una delle TRE letture fallisce (problemi, integrazioni, registro
    # di errori -- il terzo e' Task 2 di «le tracce e il log»;
    # task-5-correzioni.md, punto A.1, ne discuteva due perche' il registro
    # di errori non esisteva ancora): un errore letto come lista vuota
    # chiuderebbe ogni condizione aperta, che e' peggio di non saperlo. I
    # problemi li prende da `app["ha_problems"]`, che `hiris_ha_problems` qui
    # sopra rilegge ogni cinque minuti (A-02).
    async def _watch_conditions() -> None:
        try:
            await watch_system_conditions(app, ha_client)
            await hold_watcher_statistic_ids(app, ha_client)
        except Exception as exc:
            logger.warning(
                "cervello: giro delle condizioni di sistema fallito (%s: %s)",
                type(exc).__name__, exc)

    scheduler.add_job(
        _watch_conditions,
        trigger="interval", minutes=10,
        id="hiris_mind_conditions", replace_existing=True,
        misfire_grace_time=600,
    )

    # Le tracce delle automazioni SEGNATE, ogni DUE minuti -- non dieci come
    # le condizioni qui sopra, e il numero non e' arbitrario (Task 4 di «le
    # tracce e il log»). `stored_traces` e' un tetto di CINQUE tracce in
    # TOTALE per automazione sulla gran parte della finestra di versioni che
    # `hiris/config.yaml:22` dichiara supportata (per secchio solo da HA
    # 2026.7.0 in poi -- vedi il docstring di `HAClient.traces()`
    # per i tag verificati; questo lavoro si disegna sul caso conservativo,
    # tetto totale, e non dipende dal secchio `not_triggered`). Un'automazione
    # innescata dal movimento puo' bruciare cinque tracce in pochi minuti.
    # Misurato sulla casa vera il 30-31/08 (spec §8): 72 tracce su 16
    # automazioni -- **la finestra CONSERVATA nel tetto di cinque per
    # automazione, non una frequenza giornaliera** (un numero non misurato
    # non si scrive: non e' stata misurata alcuna cadenza di esecuzioni al
    # giorno). Un'automazione sola puo' comunque saturare il proprio tetto
    # in pochi minuti, ed e' il caso che PERDE le tracce prima che questo
    # giro le legga, non la media. Due minuti e' la cadenza piu'
    # corta che non aggiunge un carico apprezzabile (un comando WebSocket per
    # automazione segnata, non per la casa intera).
    async def _watch_automation_traces() -> None:
        try:
            await watch_automation_outcomes(app, ha_client)
        except Exception as exc:
            logger.warning(
                "cervello: giro delle tracce di automazione fallito (%s: %s)",
                type(exc).__name__, exc)

    scheduler.add_job(
        _watch_automation_traces,
        trigger="interval", minutes=2,
        id="hiris_mind_automation_traces", replace_existing=True,
        misfire_grace_time=120,
    )

    # L'anello dell'osservatore (fetta «i tre attori», §5.1), ogni MINUTO.
    # Non e' la cadenza di riconsiderazione -- quella e' misurata e sta sulle
    # ORE (84 sulla casa vera): questo e' ogni quanto ci si CHIEDE se sia ora,
    # e la domanda e' locale e costa due letture dell'archivio. La misura della
    # memoria di Home Assistant, che costa un secondo e mezzo MB, si paga solo
    # quando il giro parte davvero (vedi `reconsideration_round`).
    #
    # **Era dieci minuti, ed e' sceso a uno l'11/09/2026** perche' dalla fetta
    # dei lotti una riconsiderazione non e' piu' un giro solo: e' una CAMPAGNA
    # di quattro turni, e a dieci minuti l'uno la casa intera ci metteva
    # quaranta minuti a essere giudicata -- quaranta minuti in cui, al primo
    # avvio, lo scope e' vuoto e HIRIS non registra niente. A un minuto ci
    # mette cinque. Fuori da una campagna non cambia niente: la risposta resta
    # «non e' ora» e costa quanto costava.
    #
    # E migliora anche l'innesco che non puo' aspettare: un'entita' installata
    # stamattina passa da dieci minuti d'attesa a uno, e cio' che non e'
    # osservato non esiste piu'.
    async def _reconsider() -> None:
        await reconsideration_round(app, ha_client)

    scheduler.add_job(
        _reconsider,
        trigger="interval", minutes=1,
        id="hiris_mind_reconsideration", replace_existing=True,
        misfire_grace_time=600,
    )

    # L'anello delle ricette (spec §7), ogni DIECI minuti e **un dispositivo
    # per volta**. Non e' la cadenza dell'osservatore: quella decide COSA
    # guardare, questa decide COME si misura cio' che si guarda.
    #
    # Dieci minuti e non uno, e uno per volta, per una ragione di costo che si
    # vede solo facendo il conto: trenta dispositivi che pesano sono trenta
    # turni del modello contro il tetto giornaliero del piano -- chiesti
    # insieme lo svuoterebbero da soli, e da li' in poi ogni turno (chat
    # compresa) passerebbe ai provider a pagamento. Uno ogni dieci minuti
    # copre trenta dispositivi in cinque ore, e poi **smette**: una ricetta
    # scritta -- o un rifiuto registrato -- non si richiede mai piu'.
    async def _anello_ricette() -> None:
        await recipe_round(app)

    scheduler.add_job(
        _anello_ricette,
        trigger="interval", minutes=10,
        id="hiris_mind_recipes", replace_existing=True,
        misfire_grace_time=600,
    )

    # Il recupero dei resoconti: un giorno per giro, dal piu' vecchio.
    # Nasce da una misura del 14/09/2026 -- sulla casa vera esistevano i
    # resoconti del 12 e del 13 e basta, mentre cinque giorni prima avevano
    # oggetti e grezzo e nessun resoconto: nessuno dei due scrittori (la
    # riparazione d'avvio, due giorni; la notturna, ieri) arriva indietro.
    # Dal 17/09/2026 lo stesso giro rifa' anche la sola cronaca dei giorni nati
    # con un altro giudizio (spec 2026-09-16 §6, vedi `backfill_one_report`).
    #
    # Ogni cinque minuti perche' e' un lavoro che non ha nessuna fretta, e un
    # giorno mancante costa una richiesta di statistiche (rifare la sola
    # cronaca non ne costa nessuna, solo l'archivio): ventidue giorni si coprono in
    # meno di due ore, e finito il recupero il giro non fa piu' niente e non
    # lo dice -- un lavoro che stampa «niente da fare» per sempre e' rumore
    # sano che seppellisce cio' che e' rotto.
    async def _recupero_resoconti() -> None:
        try:
            await backfill_one_report(app, ha_client)
        except Exception as error:
            logger.warning(
                "cervello: recupero dei resoconti fallito (%s: %s) -- "
                "si riprova al giro dopo", type(error).__name__, error)

    # L'anello dell'analista: legge le misure di molti giorni e dice cosa si
    # potrebbe fare (spec §10). Ogni ora, non ogni dieci minuti: la domanda
    # pesa ~35.000 token -- misurato sulla casa vera il 15/09/2026, venti
    # giorni e 146 serie -- e un giorno ha UNA analisi sola. Quando ce l'ha,
    # il giro non fa niente e non lo dice.
    async def _anello_analista() -> None:
        await analyst_round(app)

    scheduler.add_job(
        _anello_analista,
        trigger="interval", minutes=report.ANALYST_EVERY_MINUTES,
        id="hiris_mind_analyst", replace_existing=True,
        misfire_grace_time=1800,
    )

    # Il PROPONENTE (piano degli attori, Task 4.2): lo stesso battito
    # dell'analista, un giro per analisi. Il giro vive in
    # `mind/proposer_round.py`, spento finche' `ENABLED` e' falso; qui c'e'
    # solo l'iscrizione.
    scheduler.add_job(
        proposer_beat, args=(app,),
        trigger="interval", minutes=60,
        id="hiris_mind_proposer", replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        _recupero_resoconti,
        trigger="interval", minutes=report.BACKFILL_EVERY_MINUTES,
        id="hiris_mind_backfill", replace_existing=True,
        misfire_grace_time=300,
    )

    # L'aggregazione notturna: costruisce gli oggetti del giorno appena
    # finito (`mind/facts.py::aggregate_day`). Gira alle 00:20 e non a
    # mezzanotte: aggregare a mezzanotte esatta prenderebbe un giorno ancora
    # aperto, e venti minuti bastano perche' gli ultimi eventi della sera
    # siano arrivati. Senza questo lavoro il grezzo si accumula e nessun
    # oggetto nasce mai.
    async def _aggrega_ieri() -> None:
        try:
            # `timezone`/`ieri` DENTRO il try: se il loro calcolo sollevasse
            # FUORI da qui il warning contestualizzato non partirebbe --
            # l'eccezione finirebbe nel registro di apscheduler senza il
            # prefisso «cervello:», e la notte salterebbe in silenzio.
            timezone = house_timezone(app.get("home_space_store"))
            ieri = (historian.today(timezone) - timedelta(days=1)).isoformat()
            # **IL RESOCONTO** (spec §9), per la strada unica: la notte
            # rifa' ieri anche se c'e' gia'.
            count = await write_day_report(app, ha_client, day=ieri, timezone=timezone,
                                           when_ts=time.time())
            logger.info("cervello: %s voci di cronaca per %s", count, ieri)
        except Exception as error:
            logger.warning("cervello: aggregazione notturna fallita (%s: %s)",
                           type(error).__name__, error)

    scheduler.add_job(
        _aggrega_ieri,
        trigger="cron", hour=report.NIGHTLY_HOUR, minute=report.NIGHTLY_MINUTE,
        id="hiris_mind_aggregation", replace_existing=True,
        misfire_grace_time=3600,
    )

    # La conservazione: un lavoro solo, alle 03:00, per tutti gli archivi
    # (`conservazione.nightly`).
    scheduler.add_job(
        partial(nightly, app),
        trigger="cron", hour=3, minute=0,
        id="hiris_retention", replace_existing=True,
        misfire_grace_time=3600,
    )

    # Il battito dello schedulatore delle promesse (Task 7 SDD schedulatore).
    #
    # Le prese a meta' del giro precedente (`keeper/store.py::risana`):
    # al riavvio diventano `fallita`, col motivo, e non ripartono (spec §7,
    # «mai due volte»). PRIMA di registrare il battito, non dopo: se il primo
    # giro del battito arrivasse prima di questa riga, potrebbe prendere in
    # mano una promessa che risana() avrebbe dovuto dichiarare fallita. Un
    # disco che non collabora non deve impedire il boot -- stessa disciplina
    # dell'anagrafe e del comportamento qui sopra: si dichiara e si prosegue,
    # e le promesse `in_corso` restano tali fino al prossimo riavvio.
    try:
        app["agenda"].risana(now=_time.time())
    except Exception as exc:
        logger.warning("risanamento delle promesse in sospeso fallito: %s", exc)

    # Fetta «costruire»: le proposte rimaste `in_corso` da un riavvio a meta'.
    # Come per le promesse, si chiude PRIMA che qualcuno possa applicarne una
    # nuova -- una riga rivendicata e mai conclusa non e' piu' toccabile da
    # nessuna `apply`, e resterebbe un fantasma fino alla potatura.
    try:
        app["constructions"].risana(now=_time.time())
    except Exception as exc:
        logger.warning("risanamento delle costruzioni in sospeso fallito: %s", exc)

    # L'orologio (`keeper/sweeper.py`): non conosce ne' la chat ne' il
    # modello, riceve solo `execute` (la porta unica, costruita sopra) e
    # `interpreta` (il turno di `chiedi`, `keeper/exchange.py`).
    # `interpreta_promise` prende DUE argomenti (`app`, `promessa`); l'orologio
    # chiama `interpreta(promessa)` con uno solo -- la chiusura qui sotto e'
    # quel secondo argomento, catturato.
    async def _interpreta(promise: dict) -> dict:
        return await interpreta_promise(app, promise)

    # Fetta «il seguito delle chat divise» (spec 2026-09-26 §2.4): l'esito
    # torna a chi l'ha chiesta -- il recapito, la riga nel filo e il soffitto
    # riletto al risveglio (`_promise_delivery`, qui sopra nel modulo).
    app["sweeper"] = Sweeper(
        app["agenda"],
        execute=app["action_actuator"].execute,
        interpreta=_interpreta,
        **_promise_delivery(app),
    )

    async def _battito() -> None:
        await app["sweeper"].batti(_time.time())

    # Quindici secondi, battito FISSO: la verita' e' la tabella, non un timer
    # per promessa. Un battito fisso non si perde se l'ora di sistema salta
    # (NTP, ora legale), e `misfire_grace_time` corto perche' un battito perso
    # lo rimpiazza quello dopo: e' la tolleranza dello SCHEDULATORE (120 s,
    # spec §7, `TOLLERANZA_S`) a decidere cosa e' troppo tardi, non APScheduler.
    scheduler.add_job(
        _battito,
        trigger="interval", seconds=15,
        id="hiris_keeper_heartbeat", replace_existing=True,
        misfire_grace_time=30,
    )

    from .backends.openai_compat_runner import OpenAICompatRunner
    from .backends.openrouter_runner import OpenRouterRunner

    # Il ponte: la coda dei turni di ragionamento. La usa il ramo chat qui sotto.
    from .reasoning.queue import ReasoningQueue

    reasoning_queue = ReasoningQueue(
        os.path.join(data_dir, "reasoning.db"),
        read_timezone=lambda: house_timezone(home_space_store))
    app["reasoning_queue"] = reasoning_queue

    app["submit_chat_reply"] = _chat_reply_submitter(app, data_dir)

    # La spazzata della coda del ponte: `conservazione.reasoning_sweep`.
    scheduler.add_job(
        partial(reasoning_sweep, app), trigger="interval", minutes=2,
        id="hiris_reasoning_sweep", replace_existing=True, misfire_grace_time=120)

    # Il punto di cablaggio -- da qui `handle_chat` sa se instradare il turno
    # sul ponte -- NON e' piu' qui: e' `_recompute_chain`, l'unica riga del
    # prodotto che scrive `app["bridge_active"]`, e viene chiamata sia all'avvio
    # (`_rimetti_in_vigore`, piu' sotto) sia a ogni salvataggio della pagina
    # Modelli. Doveva spostarsi: il valore viene adesso dall'archivio, che la
    # pagina riscrive, e un cablaggio fatto una volta all'avvio avrebbe
    # riprodotto per il ponte il difetto che il Task 10 ha chiuso per la
    # catena -- salvataggio accettato con 200, effetto solo al riavvio.
    #
    # `steering._bridge_on` verifica soltanto che `app["reasoning_queue"]`
    # sia agganciata -- e in produzione lo e' sempre, perche' la coda si crea
    # incondizionatamente piu' su -- quindi da sola non dice che
    # qualcuno reclami o spazzi quei job. E' `app["bridge_active"]` a dirlo:
    # tenere il gate li', invece di insegnare l'archivio a `_bridge_on`, lascia
    # ai test la possibilita' di agganciare o sganciare la
    # coda senza toccare la configurazione.

    # Il modello per provider, come LETTURA e non come valore. È la metà
    # nascosta del difetto peggiore trovato dal progetto: fino alla 2.4.1 qui
    # si leggeva `provider_models` UNA volta e lo si passava ai runner come
    # argomento di costruzione, mentre `api/handlers_chat._enqueue_chat_job`
    # rilegge `app["models_config"]` a OGNI turno -- quindi lo stesso valore
    # aveva effetto immediato sul ponte e solo al riavvio sull'API, e la pagina
    # ne dichiarava uno solo (invariante 4: «un valore si applica in un modo
    # solo»). La chiusura chiude su `app`, non su un valore: `models_config` è
    # RIASSEGNATO a ogni PUT (`handle_save_models_config`), quindi la lettura
    # vede sempre l'ultimo archivio, e la sostituzione del dizionario intero
    # è ciò che rende la lettura atomica -- un turno non può mai vedere metà
    # di un salvataggio.
    def _model_of(provider: str):
        def read() -> str:
            return ((app.get("models_config") or {})
                    .get("provider_models", {}).get(provider, ""))
        return read

    def _local_model() -> str:
        """Il modello di Ollama non vive in `provider_models` (è un fantasma
        lì: `_clean_provider_models` lo scarta in lettura e in scrittura): la
        sua unica casa è `models_config["ollama"]["modello"]`."""
        return (app.get("models_config") or {}).get(OLLAMA.id, {}).get("modello", "")

    # Il modello di Ollama, dalla SUA UNICA CASA. Fino alla 2.4.1 veniva da
    # `LOCAL_MODEL_NAME`, cioè da un'opzione dell'add-on: era il modello messo
    # dove si custodiscono le credenziali invece che dove si prendono le
    # decisioni, e `provider_models["ollama"]` restava un fantasma
    # (`_PROVIDER_MODEL_KEYS` non lo contiene, `_clean_provider_models` lo
    # scarta in lettura E in scrittura -- e resta così: NON è un doppione da
    # far rivivere).
    _ollama_model = (app["models_config"].get(OLLAMA.id) or {}).get("modello", "")
    _risponde = can_answer_at_startup(_credentials, app["models_config"])

    claude_runner = None
    if api_key and _credentials[CLAUDE.id]:
        claude_runner = ClaudeRunner(
            api_key=api_key,
            read_model=_model_of(CLAUDE.id),
            log_usage=app["usage"].log,
        )

    # I quattro contatori di prima entrano nell'archivio UNA volta sola, come
    # una riga «(prima del dettaglio)» per provider: il totale ereditato non si
    # puo' attribuire a un modello -- nessuno lo ha mai registrato -- e dirlo
    # e' meglio che spalmarlo. Stanno nella cartella dei dati: fino
    # all'08/10/2026 il primo si leggeva da `USAGE_DATA_PATH`, una variabile
    # che `run.sh` non esportava (D6 della Tappa 8).
    app["usage"].importa_legacy([
        os.path.join(data_dir, name)
        for name in ("usage.json", "usage_openai.json", "usage_openrouter.json",
                     "usage_ollama.json")
    ], now=time.time())
    # I residui si cancellano DOPO l'importazione: un contatore registrato
    # come importato e' un residuo come gli altri (D6).
    cancella_residui(data_dir, imported=app["usage"].legacy_imported())

    openai_runner = None
    if openai_api_key and _credentials[OPENAI.id]:
        openai_runner = OpenAICompatRunner(
            base_url=OPENAI.api_base,
            api_key=openai_api_key,
            read_model=_model_of(OPENAI.id),
            log_usage=app["usage"].log,
        )

    ollama_runner = None
    # Il runner locale nasce con l'INDIRIZZO, che è la credenziale, e non più
    # con `url AND modello`. Il modello è una decisione, si legge a ogni uso, e
    # cambiarlo dalla pagina Modelli deve poter valere dal prossimo messaggio:
    # con la costruzione legata anche al modello, chi ne sceglieva uno su
    # un'installazione partita senza si sarebbe trovato con un gesto che non fa
    # niente -- il backend non esiste, e servirebbe un riavvio, cioè la
    # didascalia che questa fetta toglie. Chi può RISPONDERE resta `_risponde`
    # (indirizzo E modello) e governa la catena: senza modello il runner c'è ma
    # nessuno lo mette in catena, quindi `_ordered_backends_with_name` non lo incontra.
    if local_model_url:
        ollama_runner = OpenAICompatRunner(
            base_url=local_model_url.rstrip("/") + "/v1",
            api_key="ollama",
            local=True,
            # Dall'ARCHIVIO, non da `OLLAMA_REQUEST_TIMEOUT`: è lo stesso
            # numero che la pagina Modelli mostra sul connettore, e leggerlo in
            # due posti era la seconda rappresentazione (invariante 1).
            timeout_s=(app["models_config"].get(OLLAMA.id) or {}).get(
                "timeout_s", OLLAMA.reply_timeout_s),
            read_model=_local_model,
            log_usage=app["usage"].log,
        )
    if _risponde[OLLAMA.id]:
        # Quick reachability check — warn but don't abort startup.
        try:
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as _sess, _sess.get(
                local_model_url.rstrip("/") + "/api/tags",
                timeout=_aiohttp.ClientTimeout(total=5),
            ) as _r:
                if _r.status == 200:
                    _tags = await _r.json()
                    _names = [m.get("name", "") for m in _tags.get("models", [])]
                    if _ollama_model in _names:
                        logger.info("Ollama OK — modello '%s' pronto", _ollama_model)
                    else:
                        logger.warning(
                            "Ollama raggiungibile ma il modello '%s' non è nella lista %s — "
                            "pull potrebbe essere necessario",
                            _ollama_model, _names,
                        )
                else:
                    logger.warning("Ollama /api/tags ha risposto con status %s", _r.status)
        except Exception as _exc:
            logger.warning(
                "Ollama non raggiungibile a %s (%s) — le richieste al modello locale falliranno",
                local_model_url, _exc,
            )

    openrouter_runner = None
    if openrouter_api_key and _credentials[OPENROUTER.id]:
        openrouter_runner = OpenRouterRunner(
            api_key=openrouter_api_key,
            read_model=_model_of(OPENROUTER.id),
            log_usage=app["usage"].log,
        )
        logger.info("OpenRouter abilitato (200+ modelli via openrouter.ai)")

    # `app["local_model_name"]` e' USCITO col Task 9. Era una copia del modello
    # di Ollama presa all'avvio: dopo il Task 6 la casa del valore e'
    # l'archivio, e una copia in memoria che nessuna PUT aggiorna e' la
    # seconda rappresentazione da cui questa fetta esiste per liberarsi -- i
    # suoi due lettori (`handle_list_models`, `_models_in_use`) avrebbero
    # continuato a mostrare il modello di prima dopo un salvataggio. Leggono
    # `models_config["ollama"]["modello"]`, come tutti.

    # ── La catena: l'appartenenza, e nient'altro ──────────────────────────
    # fetta «la catena diventa l'unica verita'»: qui c'erano l'ordine di
    # strategia, l'override manuale e `reconcile_chain` che li fondeva
    # accodando i provider attivi mancanti. Adesso c'e' una cosa sola --
    # l'ordine scritto nell'archivio, filtrato a chi ha una credenziale. Chi
    # diventa credenziato NON entra da solo: compare in «Fuori dalla catena»,
    # a un gesto di distanza.
    #
    # `app["model_chain"]` qui NON si scrive: lo scrive `_recompute_chain`,
    # chiamata poche righe sotto, ed e' l'unica scrittura (la Tappa 7 ha tolto
    # quella dell'avvio, che il ricalcolo sovrascriveva prima che qualcuno la
    # leggesse: voce M-30).
    # Il filtro e' `_risponde`, non `_credentials` (Task 9): in catena ci puo'
    # stare solo chi ha un backend costruito. Con la sola credenziale, un
    # `chain_order` che nomina Ollama senza un modello scelto avrebbe messo in
    # catena un anello che il router salta -- la pagina lo avrebbe disegnato
    # numerato, col suo connettore, e nessun messaggio ci sarebbe mai passato.
    # Un anello a schermo che non risponde mai e' esattamente la bugia che
    # questa fetta ritira, e la differenza fra i due dizionari e' UNA riga.
    _chain = providers_in_chain(app["models_config"].get("chain_order") or [], _risponde)
    # Nessuna perdita in silenzio: chi ha una credenziale e NON sta in catena
    # non viene consultato, e prima `reconcile_chain` lo accodava da solo. Il
    # cambio di comportamento si dichiara nel registro, dove un operatore lo
    # cerca, invece di lasciarlo dedurre da un provider che non risponde mai.
    _fuori = outside_chain(_risponde, _chain)
    if _fuori:
        logger.info(
            "Provider con credenziale FUORI dalla catena: %s. HIRIS non li "
            "consulta: un provider e' usato se e solo se sta in catena, e in "
            "catena ci si mette dalla pagina Modelli.", ", ".join(_fuori),
        )

    if any([claude_runner, openai_runner, openrouter_runner, ollama_runner]):
        router = LLMRouter(
            claude=claude_runner,
            openai=openai_runner,
            openrouter=openrouter_runner,
            ollama=ollama_runner,
            model_chain=_chain,
            # Il ciclo di ripiego e' il SOLO posto in cui HIRIS vede come si
            # comporta un provider davvero, e fino a questa fetta lo buttava
            # via. Lo stesso oggetto che la pagina Modelli legge: se fossero
            # due, divergerebbero -- e la pagina racconterebbe un traffico che
            # non e' quello che c'e' stato.
            registry=app["occurrence_registry"],
        )
        app["claude_runner"] = claude_runner  # backward compat (may be None)
        app["llm_router"] = router
    else:
        app["claude_runner"] = None
        app["llm_router"] = None

    # ── Rimettere in vigore, a caldo ──────────────────────────────────────
    # Fuori da entrambi i rami, e con UNA implementazione sola: il ramo `else`
    # (nessun provider configurato) è il PRIMO gesto di chi installa HIRIS, e
    # senza `app["recompute_chain"]` la prima PUT solleverebbe
    # `TypeError: 'NoneType' object is not callable`.
    #
    # Si chiama anche QUI, all'avvio. Non serve a mettere in vigore niente di
    # nuovo -- `_chain` è appena entrata nel router -- ma fa sì che la strada
    # che rimette in vigore sia la STESSA che mette in vigore la prima volta:
    # se le due derivazioni potessero divergere, divergerebbero all'avvio,
    # dove ogni prova le guarda, invece che al primo salvataggio di un utente.
    def _rimetti_in_vigore() -> None:
        _recompute_chain(app)

    app["recompute_chain"] = _rimetti_in_vigore
    _rimetti_in_vigore()

    # ── Chat-via-abbonamento worker in-addon (Plan 2B Task 4) ──────────────
    # Polls the internal reasoning queue and reasons via `claude -p` under the
    # user's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of metered
    # API spend. Il server MCP interno che la chat usava per i tool di
    # CONTROLLO casa usci' con la Fetta E2 Task 3 e non e' tornato: quando
    # l'azione e' rientrata (fetta «comandare») e' rientrata come UNO strumento
    # nel catalogo unico, non come un secondo server. Questo worker non ragiona
    # piu' in puro testo -- dalla fetta "il ponte riceve gli strumenti"
    # (parita' B) riceve gli strumenti dalla rotta `POST /api/mcp` registrata
    # piu' sotto, e il prompt lo dichiara al modello solo quando la sonda ha
    # confermato che ci sono davvero (vedi agent/runner.py).
    #
    # QUI c'era il `if should_start_agent_worker():` che lo avviava una volta
    # sola. Vive adesso in `_govern_bridge_worker`, che
    # `_rimetti_in_vigore()` ha gia' chiamato poche righe sopra: l'avvio e il
    # salvataggio dalla pagina Modelli passano dalla STESSA strada, che e' la
    # disciplina del Task 10 (la catena) applicata al ponte. Se fosse rimasto
    # qui, accendere il ponte dalla pagina instraderebbe la chat su una coda
    # senza nessuno a servirla: ogni turno aspetterebbe la scadenza prima di
    # ripiegare, e il bottone «Mettilo primo» sarebbe un bottone che risponde
    # 200 e fa aspettare.
    #
    # Le due frasi sul ponte che `run.sh` non puo' piu' dire (da uno script di
    # avvio l'archivio non si legge): ponte acceso senza token, e token senza
    # ponte. Sono l'ultima cosa dell'avvio perche' sono le prime che un
    # operatore cerca in coda al registro quando la chat costa piu' del
    # previsto.
    for _notice in _bridge_notices(bool(app.get("bridge_active")),
                                   _credentials[SUBSCRIPTION.id]):
        logger.warning(_notice)


async def _on_cleanup(app: web.Application) -> None:
    from .chat_store import close_all_stores
    # M-2 (Plan 2B final review, fast-follow): stop the reasoning-queue
    # consumer (agent_worker_task) and bound the wait. A claimed job can be
    # sitting inside `serve`'s
    # run_in_executor offload of the blocking `reason` (subprocess.run with
    # the turn's remaining time, S-09, + httpx.Client timeout=330) -- an unbounded
    # `await aw` after cancel() would then stall addon shutdown for up to
    # ~5 minutes, since cancelling the outer task does not interrupt a
    # thread already blocked inside the executor. `asyncio.wait_for` caps
    # that wait; on timeout we give up on a clean join and move on rather
    # than hang shutdown, and TimeoutError is suppressed same as
    # CancelledError since either outcome means "stop waiting, proceed".
    aw = app.get("agent_worker_task")
    if aw is not None:
        aw.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(aw, timeout=5)
    # L'installazione (`start_installation`): puo' essere
    # ancora in attesa del nucleo. Non tiene niente da chiudere, quindi si
    # ferma e si aspetta senza tetto proprio.
    installation = app.get("installation_task")
    if installation is not None:
        installation.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await installation
    if "reasoning_queue" in app:
        app["reasoning_queue"].close()
    if "memory_store" in app:
        app["memory_store"].close()
    # I due archivi del Task 7 (keeper): stessa disciplina dei due qui
    # sopra -- senza chiuderli un riavvio lascerebbe il file sqlite bloccato.
    if "agenda" in app:
        app["agenda"].close()
    if "journal" in app:
        app["journal"].close()
    # Fetta «costruire» (Task 8): l'archivio delle proposte/versioni
    # dell'officina (`action/construction/revisions.py`), costruito in
    # `_on_startup` accanto a `app["journal"]`. Stessa disciplina dei due
    # archivi qui sopra: senza chiuderlo il file sqlite resterebbe bloccato
    # al riavvio.
    if "constructions" in app:
        app["constructions"].close()
    # I CONSUMI e i SERVIZI accoppiati. Tutti e due mancavano da qui -- `usage`
    # da mesi, `servizi` dal giorno in cui e' nato (22/09/2026) -- e nessuna
    # delle prove accanto poteva accorgersene, perche' ognuna nominava a mano
    # l'archivio che il suo autore ricordava. Li ha trovati il cancello
    # derivato `tests/test_archivi_chiusi.py`, che da oggi li chiede al codice.
    if "usage" in app:
        app["usage"].close()
    if "servizi" in app:
        app["servizi"].close()
    # Fetta «l'osservatore» (Task 5): l'archivio dei cambi e degli oggetti
    # del cervello (`mind/store.py`), costruito in `_on_startup`
    # accanto a `app["journal"]`. Stessa disciplina degli archivi qui sopra:
    # senza chiuderlo il file sqlite resterebbe bloccato al riavvio.
    if "observations" in app:
        app["observations"].close()
    # Il sapere (`mind/knowledge.py`, fetta «il sapere e le ricette»): stessa
    # disciplina dell'archivio qui sopra, con una differenza sola -- la chiave
    # puo' esserci e valere `None`, quando all'avvio il sapere non si e' aperto
    # (`_open_knowledge`, Task 7b). Per questo si guarda il valore, non la
    # presenza della chiave.
    if app.get("knowledge") is not None:
        app["knowledge"].close()
    # `wait=False`: non si aspettano i job in corso al momento dello shutdown.
    if "scheduler" in app:
        app["scheduler"].shutdown(wait=False)
    await app["ha_client"].stop()
    close_all_stores()


def create_app() -> web.Application:
    app = web.Application(middlewares=[
        internal_auth_middleware,
        csrf_middleware,
        _security_headers,
    ])

    app.on_startup.append(_on_startup)
    # Dopo `_on_startup`, che crea `app["ha_client"]`. Parte in un compito a
    # parte e non si aspetta: l'add-on puo' avviarsi prima del nucleo, e una
    # Home Assistant che non risponde non deve tenere chiuso HIRIS.
    app.on_startup.append(start_installation)
    app.on_cleanup.append(_on_cleanup)

    # Spec 2026-09-27 §2: l'opzione dell'add-on e' l'UNICA fonte della scelta,
    # letta qui una volta. Chi decide l'accesso legge `app[...]`, mai
    # l'ambiente per richiesta: cambiarlo a processo avviato non apre niente.
    app["non_admin_access"] = parse_access_flag(
        os.environ.get("HIRIS_NON_ADMIN_ACCESS"))

    static_path = os.path.join(os.path.dirname(__file__), "static")
    # Build stamp: hash del contenuto del frontend, per verificare in UI/health
    # QUALE build gira davvero (diagnostica cache vs container non ricostruito).
    app["build_stamp"] = _compute_build_stamp(static_path)

    # Che cosa e' successo davvero, per provider (fetta «cosa e' successo
    # davvero», Task 11). Nasce QUI e non in `_on_startup` per due ragioni,
    # entrambe di sostanza: non ha niente da cui dipendere (e' un dizionario in
    # memoria con un orologio), e la pagina Modelli lo legge anche in un
    # processo dove i runner non ci sono -- un add-on senza nessuna
    # credenziale ha comunque una pagina Modelli, e quella pagina deve poter
    # dire «nessuna osservazione da quando l'add-on è partito» invece di non
    # dire niente.
    #
    # Nessuna persistenza: muore col processo, e «da quando l'add-on e'
    # partito» e' un'eta' dichiarabile (progetto §11.2). Nessuna scadenza: un
    # esito di due ore fa resta li', vecchio, e la pagina ne dice l'eta'.
    app["occurrence_registry"] = OccurrenceRegistry()
    # I fili con un turno sincrono in volo (fetta «il seguito delle chat
    # divise»): scritto da `handle_chat`, letto dalle rotte delle
    # conversazioni per il 409. Nasce qui per la stessa ragione del registro
    # sopra: non dipende da niente, e dopo l'avvio l'app non si scrive piu'.
    app["sync_turns"] = SyncTurnsInFlight()
    app.router.add_static("/static", static_path, show_index=False)

    app.router.add_get("/", _serve_shell("html_index"))
    app.router.add_get("/config", _serve_shell("html_config"))
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/config", handle_config)
    # **ROTTA TEMPORANEA** (3.66.x): i due registri in lettura, per la
    # fase delle misure. Esce quando i verdetti hanno deciso le tre leve
    # -- vedi `api/handlers_misure.py` e `docs/BACKLOG.md`.
    app.router.add_get("/api/misure", handle_misure)
    app.router.add_get("/api/usage", handle_usage)
    app.router.add_get("/api/usage/history", handle_usage_history)
    app.router.add_post("/api/usage/reset", handle_reset_usage)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)
    # Una cronologia sola, senza identificatore nel percorso: la legge
    # `static/chat/agents.js` per ripristinare la conversazione.
    app.router.add_get("/api/chat/history", handle_get_chat_history)
    # Fetta «il seguito delle chat divise» (spec 2026-09-26 §4): piu'
    # conversazioni nel filo. `GET /api/chat/history` resta -- e' la
    # conversazione attiva -- e `DELETE /api/chat/history` («cancella tutto»)
    # e' uscita: il cestino cancella una conversazione per volta
    # (decisione 9). Le tre scritture passano dal `csrf_middleware` come ogni
    # altra su /api/.
    app.router.add_get("/api/chat/conversations", handle_list_conversations)
    app.router.add_post("/api/chat/conversations", handle_new_conversation)
    app.router.add_post("/api/chat/conversations/{id}/resume", handle_resume_conversation)
    app.router.add_delete("/api/chat/conversations/{id}", handle_delete_conversation)
    # fetta E5 Task 2 ("il frontend"): le impostazioni della chat hanno di
    # nuovo una superficie. Fino a qui i sette campi di `ChatSettings` si
    # cambiavano solo scrivendo a mano `/data/impostazioni_chat.json`
    # (`save()` non aveva chiamanti di produzione). Il PUT passa dallo stesso
    # `csrf_middleware` di ogni altra rotta di scrittura -- nessuna
    # autenticazione propria -- e la pagina che lo chiama e' `#/settings`
    # (static/config/settings-route.js), nello stesso commit.
    app.router.add_get("/api/chat-settings", handle_get_settings)
    app.router.add_put("/api/chat-settings", handle_save_settings)
    app.router.add_get("/api/models", handle_list_models)
    app.router.add_get("/api/models/config", handle_get_models_config)
    app.router.add_put("/api/models/config", handle_save_models_config)

    # L'accoppiamento dei servizi esterni (spec 2026-09-21 §7, rifatta il
    # 22/09). `present` e' l'unica rotta esente dal confine, e solo mentre la
    # finestra e' aperta: vedi `middleware_internal_auth` e il cancello in
    # `tests/test_servizi_rotte.py`.
    from .api.handlers_servizi import (
        handle_close_window,
        handle_open_window,
        handle_service_approve,
        handle_service_present,
        handle_service_revoke,
        handle_services,
    )
    app.router.add_get("/api/services", handle_services)
    app.router.add_post("/api/services/present", handle_service_present)
    app.router.add_post("/api/services/window/open", handle_open_window)
    app.router.add_post("/api/services/window/close", handle_close_window)
    app.router.add_post("/api/services/approve", handle_service_approve)
    app.router.add_post("/api/services/revoke", handle_service_revoke)

    # fetta "il ponte riceve gli strumenti" (parita' B) Task 1: l'adattatore
    # JSON-RPC che porta gli strumenti della casa anche al ponte via
    # abbonamento -- l'unico modo in cui la CLI `claude` accetta strumenti
    # nostri (vedi il docstring di api/handlers_mcp.py).
    #
    # CHI LA CHIAMA: il sottoprocesso `claude` che il worker del ponte avvia
    # dentro l'add-on (`--mcp-config`), e la sonda `tools/list` che il runner
    # fa PRIMA di comporre il turno (`agent/runner.py::probe_tools`).
    # Fino al Task 3 di questa fetta nessun chiamante di produzione esisteva e
    # la rotta fu un ORFANO DICHIARATO, contato da `scripts/censimento.py` fra
    # le «rotte HTTP chiamate solo dai test»: col Task 3 l'orfano e' stato
    # raccolto e il censimento e' tornato a 43.
    #
    # COSA NON E': una superficie remota. Vive sul listener che c'e' gia',
    # raggiungibile su `127.0.0.1` dall'interno del container -- nessuna porta
    # nuova, nessun port mapping, nessuna opzione `Network`, nessuna opzione
    # dell'add-on. L'handler accetta inoltre la SOLA credenziale di un turno
    # del ponte (`auth_via == "turno"`): ne' l'ingress del Supervisor ne' la
    # valvola di sviluppo `HIRIS_ALLOW_NO_TOKEN` la aprono.
    from .api.handlers_mcp import create_rounds_per_exchange, handle_mcp
    app.router.add_post("/api/mcp", handle_mcp)
    # M-2 della review totale della fetta: i contatori dei giri di strumento
    # per turno si creano QUI, mentre l'app si compone, e non alla prima
    # `tools/call` servita. Scrivere in `app[...]` a richiesta gia' servita fa
    # emettere ad aiohttp «Changing state of started or joined application is
    # deprecated» -- oggi un warning nell'output della suite, con aiohttp 4 un
    # errore.
    create_rounds_per_exchange(app)
    # Spec «le misure complete» §4(2): cio' che /api/mcp consegna al ponte,
    # per turno. Creato qui per la stessa ragione dei contatori (M-2).
    from .usage.bridge_loads import create_bridge_loads
    create_bridge_loads(app)

    # I ruoli di Home Assistant (invariante I-1): il contenitore nasce QUI,
    # mentre l'app si compone, per la stessa ragione dei contatori qui sopra --
    # scrivere in `app[...]` a richiesta gia' servita e' deprecato in aiohttp 3
    # e un errore in aiohttp 4. Chi lo riempie e' `soffitto._person_row`,
    # alla prima richiesta che ha bisogno di sapere chi comanda.
    from .api.soffitto import prepara_ruoli
    prepara_ruoli(app)

    # I canali esterni e le loro chiavi pubbliche (spec 2026-09-21). Stesso
    # motivo di sopra per cui i contenitori nascono qui e non alla prima
    # richiesta servita.
    # Le credenziali effimere del ponte (spec §5, ingresso 7).
    from .api.credenziali import prepara_credenziali
    prepara_credenziali(app)

    # L'accoppiamento dei servizi (decisione del proprietario, 22/09/2026): la
    # finestra vive in MEMORIA e nasce chiusa -- una finestra che sopravvive a
    # un riavvio e' una finestra che ti sei dimenticato aperta.
    from .api.servizi import prepara_finestra
    prepara_finestra(app)
    from .api.canali import prepara_canali
    prepara_canali(app)

    # Task 6 SDD casa: sola lettura, per guardare dal vivo cio' che l'archivio
    # ha ricostruito -- la suite verde non prova che la lettura funzioni.
    # Dalla fetta E5 Task 8 e' anche la fonte della home della
    # configurazione: vedi il commento di /api/briefing piu' sotto.
    from .api.handlers_home_space import handle_get_home_space
    app.router.add_get("/api/home-space", handle_get_home_space)

    # Task 4 SDD memoria: la pagina "cio' che HIRIS sa" -- la decisione (5)
    # del progetto della memoria. Nessun frontend in questo task: si guarda
    # dal browser come /api/home-space.
    from .api.handlers_memory import (
        handle_delete_memory,
        handle_get_memories,
        handle_patch_memory,
    )
    app.router.add_get("/api/memories", handle_get_memories)
    app.router.add_patch("/api/memories/{id}", handle_patch_memory)
    app.router.add_delete("/api/memories/{id}", handle_delete_memory)

    # Task 8 SDD schedulatore: le promesse -- la faccia dello schedulatore
    # legge di qui, e disdice di qui. Le stesse due operazioni che il
    # modello ha come strumenti (`agenda`/`cancel` in
    # `home_space/tools.py`), sulla stessa serializzazione
    # (`keeper/promise.py::serializza`, dentro l'archivio): due porte,
    # una forma sola. Passa dallo stesso `csrf_middleware` di
    # `/api/memories/{id}` -- nessuna rotta mutante e' esente.
    from .api.handlers_agenda import (
        handle_delete_promise,
        handle_get_agenda,
        handle_get_execution,
        handle_mark_read,
    )
    app.router.add_get("/api/agenda", handle_get_agenda)
    app.router.add_delete("/api/agenda/{id}", handle_delete_promise)
    # Il segno di lettura: la pagina Impegni dichiara quali esiti ha
    # mostrato, e quelli smettono di contare nel pallino.
    #
    # Convive con `/api/agenda/{id}` qui sopra, che a `read` darebbe lo
    # stesso percorso: non si scontrano perche' i metodi sono diversi (DELETE
    # contro POST). Non e' un ragionamento da fidarsi a memoria -- e' pinnato
    # da `test_api_pending.py`, che questa POST la manda davvero e si aspetta
    # 200, non un 405. Il giorno in cui `/api/agenda/{id}` prendesse anche la
    # POST, quel test diventerebbe rosso: e' li' che si scopre.
    #
    # E' una scrittura: passa dal `csrf_middleware` come ogni altra rotta
    # mutante, e `test_post_senza_x_requested_with_e_403_e_non_segna` lo
    # verifica insieme al fatto che un rifiuto non lasci traccia.
    app.router.add_post("/api/agenda/read", handle_mark_read)
    # La cronaca si chiede A PARTE, per identificatore (review finale,
    # rilievo ①): la promessa porta solo `esecuzione_id`, mai i fatti
    # dell'esecuzione ricopiati. Rotta di lettura -- niente csrf_middleware
    # da rispettare, stessa esenzione di GET /api/agenda.
    app.router.add_get("/api/executions/{id}", handle_get_execution)

    # Task 10 SDD costruire: la faccia dell'officina -- guardare le proposte,
    # aprirne una, confermare, rimettere com'era. Le due GET sono metodi
    # safe, come `GET /api/agenda`; le due POST di conferma e ripristino
    # scrivono su Home Assistant e passano dallo stesso `csrf_middleware` di
    # ogni altra scrittura -- quel middleware protegge per METODO
    # (`POST`/`PUT`/`PATCH`/`DELETE` sotto `/api/*`), non per un elenco di
    # rotte scritto a mano: non c'e' niente da aggiungere altrove perche'
    # queste due non saltino la protezione.
    from .api.handlers_constructions import (
        handle_confirm_construction,
        handle_get_construction,
        handle_get_constructions,
        handle_reject_construction,
        handle_restore_construction,
    )
    app.router.add_get("/api/constructions", handle_get_constructions)
    app.router.add_get("/api/constructions/{id}", handle_get_construction)
    app.router.add_post("/api/constructions/{id}/confirm", handle_confirm_construction)
    app.router.add_post("/api/constructions/{id}/restore", handle_restore_construction)
    # Il «no» del proprietario (Task 10-bis): stessa protezione CSRF delle
    # due righe sopra -- il middleware la copre per METODO e prefisso, non
    # per un elenco di rotte, quindi non c'e' niente da aggiungere altrove
    # perche' anche questa non la salti. Non scrive su Home Assistant: si
    # scrive nell'archivio e basta (vedi il modulo `handlers_constructions`).
    app.router.add_post("/api/constructions/{id}/reject", handle_reject_construction)
    # Le proposte da fare a mano (spec 2026-09-21 §3): le rotte le dichiara
    # il loro modulo (`handlers_proposals.add_routes`).
    from .api.handlers_proposals import add_routes as add_proposal_routes
    add_proposal_routes(app.router)

    # I due numeri dei pallini, in una richiesta sola. Sta qui, dopo i due
    # archivi che legge, e non dentro nessuno dei due blocchi sopra: non
    # appartiene ne' all'agenda ne' all'officina. Il perche' delle chiavi
    # asimmetriche e del 503 sta nel modulo.
    from .api.handlers_pending import handle_get_pending
    app.router.add_get("/api/pending", handle_get_pending)

    # Task 3 SDD nucleo: vedere cio' che il modello vedra' -- il testo
    # ESATTO che compone `home_space.briefing.compose()`, non una sua descrizione.
    # Nata senza faccia, come /api/home-space e /api/memories: dalla fetta E5
    # Task 8 una faccia ce l'ha -- la home della configurazione
    # (`static/config/dashboard.js`) legge questa rotta e /api/home-space, e non
    # ne ricalcola nessun dato per conto proprio.
    from .api.handlers_home_space import handle_get_briefing
    app.router.add_get("/api/briefing", handle_get_briefing)

    # Fetta «l'osservatore», Task 7 (docs/design/2026-08-26-l-osservatore.md
    # §7): la pagina che dice «cosa sto guardando e perche'» e mostra gli
    # oggetti che l'aggregazione notturna ha costruito. Nata come due GET; oggi
    # quattro GET e due POST (l'obiettivo e i giudizi sui tipi), e le POST
    # passano dal `csrf_middleware` come ogni altra scrittura su /api/.
    from .api.handlers_mind import (
        handle_analysis,
        handle_knowledge,
        handle_report,
        handle_set_judgment,
        handle_set_objective,
        handle_set_scope,
        handle_watching,
    )
    app.router.add_get("/api/mind/watching", handle_watching)
    # Il resoconto (spec §9): un giorno, lo stesso giorno come documento, o le
    # misure degli ultimi trenta. Tre forme, un archivio.
    app.router.add_get("/api/mind/report", handle_report)
    app.router.add_get("/api/mind/analysis", handle_analysis)
    # La porta del sapere: cosa HIRIS ha capito, e cosa NON ha capito.
    app.router.add_get("/api/mind/knowledge", handle_knowledge)
    # La sola manopola del prodotto: fino al 14/09/2026 l'obiettivo si
    # poteva solo LEGGERE, e sulla casa vera era ancora quello di fabbrica.
    app.router.add_post("/api/mind/objective", handle_set_objective)
    # La porta unica dei giudizi sui tipi (spec 2026-09-16 §4): scrive,
    # ricostruisce l'istantanea e la sostituisce -- la correzione vale subito.
    # E' una scrittura: passa dal `csrf_middleware` come l'obiettivo.
    app.router.add_post("/api/mind/judgment", handle_set_judgment)
    app.router.add_post("/api/mind/scope", handle_set_scope)

    return app



def _registra_turno_ponte(archivio, carichi=None):
    """Collega il registro dei turni al ponte.

    Non traduce niente: il ponte emette gia' le chiavi di `log_turn`. Un
    vocabolario intermedio qui sarebbe un terzo posto in cui una colonna
    nuova si dimentica di comparire.

    `subject` arriva nella riga: per un turno di chat e' il soggetto che
    `handlers_chat` mette nel contesto del job all'accodamento (fetta «le chat
    divise»), letto da `runner._measure_turn`; per le altre specie e' `None`,
    perche' nessuna persona le ha aperte. Qui non si inventa niente.

    **La giunzione** (spec «le misure complete» §4): la riga porta
    l'`exchange_id`, la composizione e i giri dello stream; `carichi` (il
    `BridgeLoads` dell'app) sa le definizioni e i risultati che /api/mcp ha
    servito a quel turno. `payload_rows_ponte` li unisce. Gira nel thread
    dell'executor del ponte: `BridgeLoads` ha il suo lock.

    Una riga senza composizione (la forma di prima del 28/09/2026) scrive il
    solo turno: `payload_rows_ponte` non inventa giri senza cio' che e' stato
    consegnato. Un guasto qui non fa cadere il turno: lo prende il
    `try` di `runner._measure_turn`, che chiama questo gancio.
    """
    from .usage.giro import payload_rows_ponte

    def registra(riga: dict) -> str:
        riga = dict(riga)
        soggetto = riga.pop("subject", None)
        exchange_id = riga.pop("exchange_id", "")
        composizione = riga.pop("composition", None)
        giri = riga.pop("exchanges", None) or []
        adesso = time.time()
        ident = archivio.log_turn(**riga, subject=soggetto, now=adesso)
        preso = carichi.take(exchange_id) if carichi is not None else None
        for pesi in payload_rows_ponte(composizione, giri, preso):
            archivio.log_payload(ident, now=adesso, **pesi)
        return ident

    return registra
