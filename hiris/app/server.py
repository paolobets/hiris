# hiris/app/server.py
import asyncio
import contextlib
import hashlib
import logging
import os
import re
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .action.actuator import ActionActuator
from .action.construction.revisions import ConstructionStore
from .action.construction.workshop import Workshop
from .action.installation import disinstalla_card_lovelace, start_panel_sync
from .action.journal import Journal
from .action.registry import ServiceRegistry
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

# review C/#15: `_spawn`, l'unico posto che crea un compito senza padrone, vive
# in `background.py` dal 06/10/2026 (attori, Task 4.5): ne ha bisogno anche un
# modulo di `mind/`, che non importa questo file.
from .background import spawn as _spawn
from .chat_settings import ChatSettings, file_lacks_retention_days
from .chat_thread import SyncTurnsInFlight, thread_for
from .home_space import historian
from .home_space.behavior import reread, reread_dashboards
from .home_space.energy import energy_dashboard
from .home_space.historian import (
    day_boundaries,
    home_space_zone,
    house_timezone,
    instant_epoch,
    local_date,
)
from .home_space.house import House
from .home_space.house_history import statistic_ids_for_round
from .home_space.privacy import PresenceMask
from .home_space.reader import HomeSpace
from .home_space.redaction import home_assistant_folder
from .home_space.registry_follower import schedule_registry_rebuild
from .home_space.topology import (
    AREAS_PER_ROUND,
    choose_sample,
    compare_with_home_assistant,
    hierarchy,
    rebuild,
    tree_areas,
)
from .keeper.exchange import interpreta_promise
from .keeper.outcome import tell_failure
from .keeper.store import AgendaStore
from .keeper.sweeper import Sweeper
from .memory.store import MemoryStore
from .mind import analyst, analyst_turn, recipe_turn, report
from .mind.analyst_round import ANALYST_DAYS, write_analysis
from .mind.cadence import cadence_from, measure_memory_window, reason_to_reconsider
from .mind.facts import (
    aggregate_day,
    chronicle_is_stale,
    rebuild_chronicle,
)
from .mind.flatline import HISTORY_DAYS, frozen_refusals, split_at
from .mind.judgments import build_judgments
from .mind.knowledge import KnowledgeStore
from .mind.observer import SCOPE_TURN_KIND
from .mind.observer import apply_answer as observer_apply_answer
from .mind.observer import bridge_turn as observer_bridge_turn
from .mind.observer import reconsider as observer_reconsider
from .mind.proposer_round import proposer_round
from .mind.realignment import disconnection_recorder, reload_and_realign
from .mind.recipes import (
    Recipe,
    hourly_points,
    muted_recipes,
    silent_entities,
    unread_series,
)
from .mind.seed import (
    REPO_PRIORITY,
    attribute_seed,
    judgment_seed,
    meaning_seed,
)
from .mind.state_words import prime_state_translations
from .mind.store import READING_RETENTION_S, ObservationsStore
from .mind.watcher import Watcher
from .models_store import bridge_deadline_min
from .panel_visibility import parse_access_flag
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
from .proxy.entity_cache import EntityCache, automation_config_id
from .proxy.ha_client import HAClient
from .proxy.state_translations import StateTranslations
from .reasoning.queue import turn_answer
from .steering import (
    ANALYST_SPECIES,
    JOB_SPECIES,
    OBSERVER_SPECIES,
    RECIPES_SPECIES,
    SPECIES,
    chain_answer,
    chain_turn,
    declare_refused,
    enqueue_turn,
    refused_problems,
    start,
    too_soon_to_ask_again,
    turn_in_flight,
)
from .version import read_version

logger = logging.getLogger(__name__)



def _close_expired_promise(app, job: dict) -> None:
    """Il turno del piano e' scaduto: la promessa fallisce dichiarando l'attesa.

    Estratta invece che scritta in linea dentro lo sweep perche' ha una
    ragione sua e va provata da sola: e' l'unico punto che impedisce a una
    promessa servita dal ponte di restare `in_corso` per sempre quando il
    piano non risponde. `risana()` la chiuderebbe soltanto al prossimo
    riavvio -- cioe' forse mai.

    L'id viene da `wake`: `sweep_expired` azzera `context_json` come fa
    `submit`, e `wake` e' la sola parte del job che sopravvive.
    """
    ident = (job.get("wake") or {}).get("promessa_id") or ""
    store = app.get("agenda")
    riga = store.read(ident) if (store is not None and ident) else None
    if riga is None or riga.get("stato") != "in_corso":
        # Gia' conclusa da `concludi` mentre il turno finiva: non si
        # riapre. E' lo stesso ordine di controlli della consegna
        # (`reasoning/consegna`), per la stessa ragione.
        return
    # **L'attesa e' quella del turno** (S-02, Tappa 6 Task 2): la scadenza
    # viaggia col job, e la `scadenza_min` di ADESSO puo' essere un'altra --
    # l'utente puo' averla cambiata mentre il turno era in coda. Stessa durata
    # che il registro degli esiti riceve qui sotto: una sola, letta una volta.
    durata_s = (float(job.get("deadline_ts", 0.0))
                - float(job.get("created_ts", 0.0)))
    minuti = round(durata_s / 60)
    reason = (f"ho aspettato il {SUBSCRIPTION.name} per {minuti} minuti e non ha "
              "risposto: non so cosa dirti.")
    # Ruling 3.8: chi l'ha chiesta lo legge anche nella sua chat -- una riga,
    # solo se la promessa ha un filo, e nessuna push. `concludi` e' guardato
    # sullo stato: se nel frattempo e' arrivato `conclude`, niente riga.
    if store.concludi(ident, state="fallita", now=time.time(), reason=reason):
        tell_failure(app.get("data_dir"), riga, reason)
    # Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`:
    # terza strada delle promesse sul ponte, dopo il successo (`api/
    # handlers_mcp`) e il turno finito senza «conclude» (`reasoning/
    # consegna`). Stessa famiglia `scaduto` del ramo chat
    # (`api/handlers_chat`): il piano non ha rifiutato, non ha risposto.
    registry = app.get("occurrence_registry")
    if registry is not None:
        registry.fallimento(
            SUBSCRIPTION.id, family="scaduto", code=None,
            message="nessuna conclusione entro la scadenza del ponte (promessa)",
            durata_s=durata_s)
    logger.warning(
        "promessa %s: il turno sul piano e' scaduto dopo %d minuti",
        ident, minuti)


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


async def reload_entity_inventory(cache, ha_client) -> bool:
    """Ritenta la rilettura dello specchio delle entita' quando l'ultima non e'
    riuscita: il caricamento iniziale, o la rilettura dopo una riconnessione
    (`EntityCache.stale`, A-09). Ritorna True se questo giro l'ha rimesso in
    piedi.

    `_on_startup` logga e prosegue quando `EntityCache.load` fallisce (Home
    Assistant che parte dopo l'addon, riavvio del core, rete che balbetta):
    da li' in poi la cache resta `loaded is False` e gli strumenti che
    la leggono rispondono "non ancora pronto". Onesto, ma senza qualcuno che
    riprovi resterebbe cosi' fino al riavvio dell'addon: piu' onesto di prima
    e piu' scomodo. Questo e' quel qualcuno.

    **Anche la rilettura della riconnessione, dal 03/10/2026** (A-09): dopo un
    riavvio di Home Assistant lo specchio rilegge la casa (`reload`), e se in
    quel momento Home Assistant non risponde ancora lo specchio resta quello
    di prima -- leggibile, ma senza gli eventi di quando la connessione era
    giu'. Fino a quel giorno questo giro guardava solo `loaded`, ed era vero:
    lo specchio restava vecchio fino alla riconnessione successiva.

    Non tocca una cache viva e fresca: da quel momento la mantengono
    aggiornata gli eventi di stato, e rileggere tutta la casa a ogni giro
    sarebbe traffico inutile verso Home Assistant. Modulo-level (non chiuso dentro
    `_on_startup`) per essere unit-testabile con un semplice dict al posto
    di `app`: si prova senza avviare l'applicazione.

    Non solleva mai: gira nello scheduler, e un Home Assistant ancora giu' e'
    il caso previsto, non un errore da propagare -- il giro successivo
    riprovera'.
    """
    if cache is None or ha_client is None:
        return False
    if cache.loaded and not cache.stale:
        return False
    try:
        await cache.load(ha_client)
    except Exception as exc:
        logger.warning("Ricarica dell'inventario entita' non riuscita: %s", exc)
        return False
    logger.info(
        "Inventario entita' ricaricato: %d entita' (l'ultima lettura era fallita)",
        len(cache.all_states()) if hasattr(cache, "all_states") else -1,
    )
    # Qui c'erano due chiamate WebSocket per ricostruire una mappa area->entita'
    # che nessuno leggeva, e che sbagliava (per nome invece che per id, senza
    # l'area ereditata dal dispositivo). Le aree le ricostruisce
    # `home_space.topology.rebuild`, che le legge per id e dichiara i registri
    # caduti.
    return True


async def reread_ha_problems(app, ha_client) -> dict | None:
    """Rilegge i guasti che Home Assistant ha gia' diagnosticato e li mette in
    `app["ha_problems"]`. Ritorna cio' che ha scritto (`None` senza client).

    DOVE VIVONO I PROBLEMI, e perche' qui e non dentro l'anagrafe
    (`HomeSpace`, `home_space/reader.py`).

    Un `repair` e' momentaneo. L'utente apre Home Assistant, clicca «ripara»,
    e quel problema non esiste piu': un'anagrafe riletta solo quando i
    registri cambiano continuerebbe ad annunciarlo per ore -- e un falso
    allarme ripetuto in ogni prompt e' precisamente il rumore che questa
    lettura esiste per non produrre. E' lo stesso ragionamento, sullo stesso
    genere di dato, per cui `state` non entra nel sistema di riferimento della
    casa (`home_space.topology.reference_frame`: «in un archivio che si
    rilegge di rado mentirebbe poche ore dopo, ed e' peggio che non saperlo»).

    C'e' anche una ragione meccanica, e da sola basterebbe: l'anagrafe si
    ricostruisce sugli eventi dei REGISTRI (`TOPOLOGY_EVENTS`), e il registro
    dei problemi non ne emette nessuno. Messo nell'anagrafe, nessun innesco lo
    aggiornerebbe: sarebbe un dato letto all'avvio e vecchio da li' in poi.

    Quindi in `app`, accanto a `entity_cache` -- che e' l'altra fotografia
    momentanea del prodotto -- e riletta da un lavoro periodico
    (`hiris_ha_problems`): il costo e' un solo comando WebSocket, e un guasto
    riparato sparisce dal nucleo entro il giro successivo invece che al
    riavvio dell'add-on.

    La strada migliore esisterebbe: Home Assistant emette
    `repairs_issue_registry_updated`, e ascoltarlo renderebbe il numero esatto
    invece che fresco di cinque minuti. Sottoscriverlo pero' vuol dire toccare
    `proxy/ha_client.py` (le sottoscrizioni si aprono tutte li', in `_ws_loop`),
    che questa fetta non possiede. Resta la prima cosa da fare quando quel file
    si riapre; la lettura periodica non andra' buttata, e' il ripiego che copre
    un HA che si riavvia e perde le sottoscrizioni.

    Non solleva mai: `HAClient.problems()` restituisce gia' `{"errore": ...}`
    sui guasti, e quell'errore e' un'informazione da portare al modello, non
    un'eccezione da propagare in uno schedulatore.
    """
    if ha_client is None:
        return None
    reader = getattr(ha_client, "problems", None)
    if reader is None:
        # Un client vecchio o un finto di prova che non dichiara `problemi`:
        # non si scrive niente, cosi' `app["ha_problems"]` resta `None` e il
        # nucleo tace invece di affermare che la casa e' sana.
        return None
    try:
        report = await reader()
    except Exception as exc:  # non previsto: `problems()` cattura gia' da se'
        logger.warning("lettura dei problemi diagnosticati da HA fallita: %s", exc)
        report = {"errore": "Home Assistant non ha risposto"}
    app["ha_problems"] = report
    return report


async def watch_system_conditions(app, ha_client) -> int | None:
    """Le condizioni di sistema (problemi diagnosticati + integrazioni non
    caricate + voci del registro di errori) verso
    `app["watcher"].watch_system` (fetta «l'osservatore», Task 5; il registro
    di errori e' Task 2 di «le tracce e il log»). Torna quante ne ha scritte,
    o `None` se il giro e' stato saltato.

    **I problemi NON si rileggono qui** (A-02, 03/10/2026): li legge gia' il
    giro dei cinque minuti (`reread_ha_problems`, `hiris_ha_problems`) verso
    `app["ha_problems"]`, e questo giro, ogni dieci, prende quelli -- vecchi
    al piu' cinque minuti dentro una cadenza di dieci. Fino a quel giorno
    `repairs/list_issues` si chiedeva due volte, ed era scritto qui sotto
    come «doppione tollerato». Se la chiave non c'e' ancora (un giro partito
    prima della prima lettura) si fa quella lettura, una volta, e resta in
    `app["ha_problems"]` per tutti.

    **Le integrazioni NON si leggono qui** (Task 7 della Tappa 2, decisione di
    Paolo del 03/10/2026, «avviso»): arrivano per evento, dall'iscrizione
    `config_entries/subscribe` (`integration_follower`), in
    `app["ha_integrations"]` e nell'anagrafe. Fino a quel giorno questo giro le
    rileggeva (`read_registry("integrazioni")`, Task 5) e le consegnava
    all'anagrafe ogni dieci minuti: una seconda lettura della stessa cosa,
    vecchia fino a un giro. Se l'elenco non e' ancora arrivato (l'iscrizione
    non ha ancora risposto), il giro si salta come per una lettura fallita.

    **Se una delle TRE letture fallisce, il giro si salta INTERAMENTE**
    (`task-5-correzioni.md`, punto A.1 -- la stessa disciplina, estesa al
    registro di errori). `HAClient.problems()` torna la busta del guasto
    quando Home Assistant non risponde, e il suo docstring dice perche' un
    elenco vuoto non e' un ripiego accettabile: significherebbe «non c'e'
    niente che non va». `HAClient.system_log()` dichiara la stessa cosa per la
    stessa ragione (vedi il suo docstring). `Watcher.watch_system` chiude una
    condizione dopo DUE giri consecutivi in cui non la trova piu' nell'elenco
    che riceve (l'isteresi contro i buchi di un giro solo, misurati il 03/09)
    -- quindi un errore letto come lista vuota, ripetuto per due giri di
    fila, scriverebbe comunque «chiuso» su OGNI guasto aperto (una voce di
    log compresa): l'archivio registrerebbe che tutto si e' risolto nel
    momento esatto in cui abbiamo smesso di poterlo vedere.
    Vale identico per le integrazioni: un elenco che l'iscrizione non ha
    ancora mandato manca, non e' un elenco vuoto che direbbe «va tutto bene».
    Meglio un buco nella storia che una bugia nella storia.

    Chiamata una volta all'avvio (subito dopo `rebuild_conditions`) e
    ogni dieci minuti dal lavoro periodico registrato piu' sotto in
    `_on_startup` -- stessa funzione, due chiamanti, come
    `tree_comparison_round`/`watch_behavior` qui accanto.

    Non solleva mai per le tre letture (i client la dichiarano gia' cosi'):
    puo' sollevare da `watch_system` stesso, se `record` fallisce a meta' --
    e in quel caso deve propagare, per il motivo scritto sul suo docstring.
    """
    watcher = app.get("watcher")
    if watcher is None:
        return None
    problems_report = app.get("ha_problems")
    if problems_report is None:
        problems_report = await reread_ha_problems(app, ha_client)
    if not isinstance(problems_report, dict) or "errore" in problems_report:
        logger.warning(
            "cervello: condizioni di sistema non lette, i problemi non sono "
            "stati letti (%s) -- giro saltato",
            problems_report.get("errore") if isinstance(problems_report, dict)
            else "nessun lettore")
        return None
    integrations = app.get("ha_integrations")
    if integrations is None:
        logger.warning(
            "cervello: condizioni di sistema non lette, l'elenco delle "
            "integrazioni non e' ancora arrivato dall'iscrizione "
            "(config_entries/subscribe) -- giro saltato")
        return None
    log_report = await ha_client.system_log()
    if "errore" in log_report:
        logger.warning(
            "cervello: condizioni di sistema non lette, system_log() ha "
            "fallito (%s) -- giro saltato", log_report["errore"])
        return None
    return watcher.watch_system(
        problems=problems_report.get("problemi") or [],
        integrations=list(integrations),
        log_entries=log_report.get("voci") or [])


def integration_follower(app):
    """Restituisce l'ascoltatore dell'iscrizione alle integrazioni
    (`HAClient.add_integration_listener`, Task 7 della Tappa 2): riceve i
    cambi cosi' come Home Assistant li manda e tiene le voci in
    `app["ha_integrations"]` -- le righe grezze, la stessa forma di
    `config_entries/get` (`ConfigEntry.as_json_fragment`, vedi
    `CONFIG_ENTRIES_SUBSCRIPTION` in `proxy/ha_client.py`) -- e nell'anagrafe,
    con lo stesso costruttore della ricostruzione
    (`HomeSpace.hold_integrations`).

    **Dove vivono, e perche' due posti.** `app["ha_integrations"]` e' il
    grezzo che il giro delle condizioni passa all'osservatore
    (`Watcher.watch_system` legge `state`, `source`, `domain`, `title` di
    Home Assistant), accanto ad `app["ha_problems"]` che e' la stessa specie
    di dato; l'anagrafe ne tiene la forma di HIRIS (`dominio`, `stato`,
    `motivo`), come per ogni altra tabella. L'ascoltatore non ha una memoria
    sua: il suo stato E' `app["ha_integrations"]`.

    **L'elenco intero sostituisce, i cambi si applicano.** Un messaggio con
    voci a `type` nullo -- o vuoto: una casa senza integrazioni -- e' l'elenco
    iniziale, che l'iscrizione manda a ogni connessione: sostituisce cio' che
    si sapeva, cosi' una voce tolta mentre la connessione era giu' sparisce
    alla riconnessione. `added`/`updated` mettono la voce al suo posto per
    `entry_id`, `removed` la toglie. Un cambio arrivato prima di un elenco
    (Home Assistant non lo fa: conferma, poi manda l'elenco) si ignora: un
    elenco fatto di soli cambi direbbe che la casa ha una integrazione sola.

    **Cosa NON copre, dichiarato.** Anche la ricostruzione dell'anagrafe
    (`topology.rebuild`) legge le integrazioni, con tutti i registri; se un
    annuncio arriva fra la sua lettura e la sua consegna, l'anagrafe tiene la
    lettura fino al prossimo annuncio. `app["ha_integrations"]` no: lo scrive
    solo l'iscrizione.
    """
    def follow(changes) -> None:
        if not isinstance(changes, list):
            return
        listing = not changes or any(
            isinstance(change, dict) and change.get("type") is None for change in changes)
        if not listing and "ha_integrations" not in app:
            logger.debug("integrazioni: un cambio prima dell'elenco iniziale, ignorato")
            return
        entries = {} if listing else {
            row.get("entry_id"): row for row in app["ha_integrations"]}
        for change in changes:
            entry = change.get("entry") if isinstance(change, dict) else None
            if not isinstance(entry, dict) or not entry.get("entry_id"):
                continue
            if change.get("type") == "removed":
                entries.pop(entry["entry_id"], None)
            else:
                entries[entry["entry_id"]] = entry
        rows = list(entries.values())
        app["ha_integrations"] = rows
        home_space_store = app.get("home_space_store")
        if home_space_store is not None:
            home_space_store.hold_integrations(rows)

    return follow


async def watch_automation_outcomes(app, ha_client) -> int | None:
    """La cadenza BREVE (due minuti -- vedi il commento sul lavoro in
    `_on_startup` per il perche' di questo numero) verso
    `app["watcher"].watch_automation_outcome` (Task 4 di «le tracce e il
    log»): rilegge le tracce di ogni automazione che l'evento ha SEGNATO
    (`Watcher.mark_automation`, sottoscritto piu' sopra in `_on_startup`) e
    scrive un cambio quando un'esecuzione e' in errore o quando un'esecuzione
    riuscita chiude un errore aperto in precedenza. Torna quante ne ha
    scritte, o `None` se il giro e' stato saltato per intero (nessun
    `watcher` -- boot non ancora arrivato li').

    **L'evento porta un `entity_id`, Home Assistant archivia le tracce per
    id di CONFIGURAZIONE: la risoluzione avviene qui.** `automation_
    triggered` nomina l'automazione con il suo `entity_id`, ed e' quello che
    `Watcher.marked_automations()` restituisce; ma la chiave con cui HA
    archivia le tracce e' `automation.<id della configurazione>`
    (`config_block.get(CONF_ID)`, catena verificata sui tag `2024.7.0` e
    `2026.9.0` nel docstring di `HAClient.traces()`). Su una casa
    vera i due valori non coincidono quasi mai -- l'interfaccia di HA genera
    id numerici come `"1771346155970"` -- e chiedere le tracce con
    l'`object_id` non ne sbaglia una: non ne legge MAI nessuna, per nessuna
    automazione. La traduzione sta QUI e non dentro il client (che resta
    «legge e non giudica», senza dipendere dallo stato): la fa
    `proxy/entity_cache.automation_config_id`, che legge lo specchio gia'
    cablato in `app["entity_cache"]` -- nessuna lettura nuova verso Home
    Assistant, nessun secondo rubinetto.

    **Un id che non si risolve NON e' «non ha mai girato».** Se lo specchio
    non e' pronto, o l'automazione e' scritta in YAML senza `id:` (allora
    `attributes["id"]` non esiste proprio, e le sue tracce vivono sotto la
    chiave condivisa `"automation.None"`, non indirizzabile per automazione),
    questa funzione **salta quell'automazione senza toccarne il cursore e
    senza scrivere nessun fatto**, e lo dice. Scrivere sarebbe
    un'affermazione su una casa che non abbiamo potuto guardare -- la stessa
    disciplina del «meglio un buco nella storia che una bugia nella storia»
    gia' applicata alle tracce anteriori all'avvio.

    **Lo dice UNA volta per entita' a voce alta, poi sottovoce.**
    `Watcher.marked_automations()` non si svuota mai: un'automazione YAML
    senza `id:` che e' scattata una volta resta segnata per tutta la vita del
    processo, e un WARNING a ogni cadenza sarebbero 720 avvisi al giorno per
    una condizione che non puo' cambiare a caldo. Il primo giro che non
    risolve una certa entita' logga WARNING, i successivi DEBUG
    (`app["automation_trace_unresolved"]`, l'insieme delle entita' gia'
    segnalate). Il fatto non si tace: cambia di livello. L'insieme e'
    limitato da quello dei segnati, quindi non cresce da solo, e un'entita'
    che torna a risolversi ne ESCE -- cosi' un guasto nuovo, dopo un periodo
    di normalita', si fa sentire di nuovo invece di restare muto per sempre.

    **Una raffica sola per tutte, e ogni automazione fallisce da sola.**
    Ogni `entity_id` segnato si risolve nel proprio id di configurazione
    (vedi il blocco qui sopra), e gli id risolti partono insieme in
    `HAClient.traces()` -- una connessione per giro, non una per
    automazione (A-21 e A-32, Tappa 2, Task 8: fino al 04/10/2026 ogni
    automazione segnata era una connessione sua, ogni due minuti). Al
    client non arriva mai un `entity_id`. Una chiave che Home Assistant
    rifiuta, o che non risponde in tempo, sta in `non_letti` e non deve
    impedire di leggere le altre: si salta QUELLA automazione, si continua
    con le prossime -- il "parziale tollerato", non il "tutto o niente"
    delle tre letture di sistema di `watch_system_conditions`. Se non parte
    la raffica intera, il giro si salta tutto, senza toccare nessun
    cursore.

    **Il cursore per automazione, e perche' esiste (giro di correzioni,
    rilievo 1 -- CRITICO, dimostrato dal revisore col `Watcher` vero).**
    `HAClient.traces()` non toglie mai una traccia dalla sua
    risposta finche' HA non la espelle da solo (tetto `stored_traces`):
    senza un cursore, OGNI giro di due minuti rivedrebbe ancora una volta
    OGNI traccia ancora conservata, e `watch_automation_outcome` decide
    solo «e' aperto adesso?» -- non «l'ho gia' vista?». Misurato dal
    revisore su tre finestre fisse: `[finished, error]` scrive 1 alla
    prima lettura e **2 a OGNI lettura successiva** (il `finished` non
    aveva niente da chiudere la prima volta -- l'errore non era ancora
    aperto -- ma lo richiude e lo riapre a ogni giro dopo, perche'
    rivisto sempre nello stesso ordine); un'automazione rotta una volta e
    guarita produce un episodio di guasto NUOVO ogni due minuti (720 al
    giorno), «una bugia nella storia» ripetuta. Il cursore
    (`app["automation_trace_cursors"]`, `entity_id -> {run_id gia'
    processati}`) **si sostituisce** con l'insieme del giro corrente, non
    si accumula: resta quindi limitato dal tetto che HA stesso impone
    alle tracce conservate, non cresce mai da solo.

    Due cautele, entrambe verificate alla fonte:

    - **una traccia ANCORA IN CORSO non entra nel cursore.**
      `ActionTrace._script_execution` (`trace/models.py`, tag `2026.9.0`)
      resta `None` finche' `finished()` non viene chiamato: una lettura
      che arriva a meta' esecuzione vede `script_execution: None` (non una
      stringa) e non ha ancora un esito da giudicare. Se la marcassimo
      "vista" comunque, il giro in cui si conclude troverebbe il suo
      `run_id` gia' nel cursore e il suo esito vero non arriverebbe MAI.
    - **una traccia con `timestamp.start` precedente all'avvio di questo
      processo non produce un fatto** (ma ENTRA nel cursore: e'
      permanentemente fuori scope, non "da riconsiderare"). E' scattata
      mentre HIRIS era spento, o in un avvio precedente -- non si
      recupera, stessa disciplina di `watch_system_conditions` ("meglio un
      buco nella storia che una bugia nella storia"). `timestamp.start` e'
      un `datetime` di HA serializzato ISO-8601 (`helpers/json.py`,
      `JSONEncoder.default`: `datetime.datetime -> o.isoformat()`) --
      `instant_epoch` lo legge gia' cosi'. **Conseguenza dichiarata**: se
      un'automazione era rotta prima del riavvio dell'add-on, il suo
      episodio resta APERTO finche' non gira bene di nuovo -- un buco
      nella storia, non una bugia.

    Una traccia il cui `script_execution` non e' una stringa (l'unico
    caso vero e' quello in corso qui sopra: **non** `not_triggered`, che
    da HA 2026.7.0 in poi vale la stringa `"not_triggered"` -- verificato
    alla fonte, `automation/__init__.py::_handle_not_triggered`,
    `script_execution_set("not_triggered")`, assente prima di quel tag --
    e su una `not_triggered` questa funzione la inoltra comunque a
    `watch_automation_outcome`, che la ignora perche' non e' ne' `"error"`
    ne' `"finished"`) si scarta senza processarla.

    **L'ordine delle tracce dentro `tracce` conta, ed e' gia' quello
    giusto.** Verificato alla fonte (`homeassistant/util/limited_size_
    dict.py`, `LimitedSizeDict._check_size_limit`: evizione FIFO via
    `popitem(last=False)`; `trace/util.py::async_store_trace`:
    `bucket[trace.run_id] = trace`, che in un `OrderedDict` appende in
    coda) -- la lista che `traces()` restituisce per una chiave e' dal PIU'
    VECCHIO al piu' recente. Processarla in quest'ordine, chiamando
    `watch_automation_outcome` una volta per traccia NUOVA (secondo il
    cursore), fa si' che l'ultima chiamata rifletta sempre l'esito piu'
    recente -- se un'automazione ha fallito e poi e' guarita nella STESSA
    finestra di due minuti, l'errore apre e il successo lo richiude nello
    stesso giro, nell'ordine vero.

    `outcome` e' `script_execution` cosi' come HA lo scrive (`"finished"`,
    `"error"`, `"failed_conditions"`, ...): questa funzione non lo giudica,
    lo passa cosi' com'e' -- il giudizio (quale valore apre, quale chiude,
    quale non fa niente) vive tutto in `Watcher.watch_automation_outcome`.
    `title` e' il nome che la casa da' all'automazione ADESSO (`House.name`,
    D1: quello che si vede in Home Assistant; A-18, Tappa 3, Task 12) --
    fino al 04/10/2026 era quello che l'evento portava al primo scatto, e
    non seguiva le rinomine. Un'automazione che la casa sa nominare solo con
    l'id viaggia senza titolo, come prima senza nome. Viaggia identico a
    ogni chiamata per la stessa automazione: e' il metodo che decide se
    scriverlo (solo sull'apertura), non questa funzione.

    Non solleva mai per la lettura delle tracce (`traces()` la dichiara
    gia' cosi', vedi il suo docstring): un guasto di rete per
    un'automazione diventa un WARNING e un `continue`, non un'eccezione che
    fermerebbe le altre. Se la lettura fallisce, il cursore di
    QUELL'automazione non si tocca -- resta quello dell'ultimo giro
    riuscito, invece di essere azzerato da una risposta che non e' mai
    arrivata.
    """
    watcher = app.get("watcher")
    if watcher is None:
        return None
    boot_ts = app.get("automation_traces_boot_ts", 0.0)
    cursors = app.setdefault("automation_trace_cursors", {})
    cache = app.get("entity_cache")
    unresolved = app.setdefault("automation_trace_unresolved", set())
    written = 0
    # Prima si risolvono tutte, poi si chiede UNA volta (A-21, Tappa 2, Task
    # 8): fino al 04/10/2026 ogni automazione segnata era una lettura sua,
    # cioe' una connessione WebSocket nuova ogni due minuti per ognuna.
    resolved: list[tuple[str, str]] = []
    for entity_id in watcher.marked_automations():
        automation_id = automation_config_id(cache, entity_id)
        if automation_id is None:
            # NON si tocca il cursore, e NON si scrive nessun fatto: un id
            # irrisolto non e' «non ha mai girato», e' «non ho potuto
            # guardare». Si salta questa automazione come si salta una
            # lettura fallita, e le altre proseguono.
            #
            # WARNING la PRIMA volta per entita', poi DEBUG. `_marked_
            # automations` non si svuota mai, quindi un'automazione YAML
            # senza `id:` che e' scattata una volta resterebbe segnata per
            # tutta la vita del processo: un avviso ogni due minuti, 720 al
            # giorno, per una condizione che non puo' cambiare a caldo. La
            # legge del prodotto -- «se una cosa funziona non va segnalata,
            # il rumore sano seppellisce la rotta» -- vale anche per i log:
            # un WARNING ripetuto per sempre smette di essere un avviso e
            # diventa lo sfondo davanti a cui gli avvisi veri spariscono.
            # Il fatto non si tace, cambia di livello.
            (logger.debug if entity_id in unresolved else logger.warning)(
                "cervello: l'id di configurazione di %s non si risolve dallo "
                "specchio (automazione senza `id:` in YAML, oppure inventario "
                "non ancora pronto) -- le sue tracce non si possono chiedere, "
                "questo giro la salta", entity_id)
            unresolved.add(entity_id)
            continue
        # Risolta: si dimentica di averla mai segnalata. Cosi' il WARNING e'
        # «la prima volta di OGNI tratto di irrisolvibilita'», non «la prima
        # volta in assoluto» -- un'automazione risolta oggi e irrisolvibile
        # domani (inventario ricaricato male, HA riavviato) torna a farsi
        # sentire una volta, invece di restare muta per sempre.
        unresolved.discard(entity_id)
        resolved.append((entity_id, automation_id))
    if not resolved:
        return written
    report = await ha_client.traces(
        list(dict.fromkeys(("automation", automation_id)
                           for _entity_id, automation_id in resolved)))
    # La casa di questo giro, per i nomi (A-18): letta una volta.
    house = House.read(app.get("home_space_store"), cache)
    if "errore" in report:
        # La raffica intera non e' partita: nessuna automazione si e' potuta
        # guardare, e nessun cursore si tocca.
        logger.warning("cervello: tracce delle automazioni segnate non lette "
                       "(%s) -- il giro si salta", report["errore"])
        return written
    for entity_id, automation_id in resolved:
        key = f"automation.{automation_id}"
        if key not in report["tracce"]:
            logger.warning(
                "cervello: tracce di %s (id di configurazione %s) non lette "
                "(%s) -- questa automazione si salta, le altre proseguono",
                entity_id, automation_id,
                report["non_letti"].get(key, "nessuna risposta"))
            continue
        already_seen = cursors.get(entity_id) or set()
        seen_this_round: set[str] = set()
        name = house.name("automazione", entity_id)
        title = None if name == entity_id else name
        for trace in report["tracce"][key]:
            if not isinstance(trace, dict):
                continue
            outcome = trace.get("script_execution")
            if not isinstance(outcome, str):
                # Ancora in corso (vedi il docstring): NON entra nel
                # cursore, o il suo esito vero non arriverebbe mai.
                continue
            run_id = trace.get("run_id")
            if not isinstance(run_id, str):
                continue
            seen_this_round.add(run_id)
            if run_id in already_seen:
                continue  # gia' processata in un giro precedente
            start_ts = instant_epoch((trace.get("timestamp") or {}).get("start"))
            if start_ts is not None and start_ts < boot_ts:
                continue  # prima dell'avvio: buco dichiarato, non si recupera
            if watcher.watch_automation_outcome(entity_id, outcome, title=title):
                written += 1
        cursors[entity_id] = seen_this_round
    return written


def tree_comparison_round(app, ha_client, count: int = AREAS_PER_ROUND):
    """Restituisce `giro()`: confronta un CAMPIONE di aree con Home Assistant
    e scrive l'esito in `app["tree_comparison"]`.

    **Cosa fa, in una riga.** `home_space/topology.hierarchy()` e' una replica che
    HIRIS costruisce dai registri, cioe' un'affermazione sulla casa che niente
    verificava. Qui la stessa domanda va all'originale --
    `HAClient.extract_from_target({"area_id": [...]}) `, che e' Home Assistant
    a risolvere -- e le due liste si mettono una accanto all'altra
    (`topology.compare_with_home_assistant`, pura).

    **OGNI QUANTO, e perche' non a ogni ricostruzione dell'anagrafe.** La
    strada ovvia sarebbe agganciarsi alla ricostruzione. Sarebbe anche il
    momento sbagliato: subito dopo una ricostruzione la replica e' fresca di
    secondi, cioe' esattamente quando una divergenza e' meno probabile. Il
    caso che questa verifica esiste per prendere e' l'opposto -- un evento di
    registro perso, un Home Assistant riavviato senza che HIRIS se ne
    accorgesse, una replica che INVECCHIA -- e per vederlo bisogna guardare
    mentre la copia invecchia, non appena e' stata rifatta. Quindi un lavoro
    periodico, indipendente dalla ricostruzione: quindici minuti (vedi la
    registrazione nello schedulatore), che con `AREAS_PER_ROUND` a rotazione
    coprono una casa da sedici aree in poco piu' di un'ora.

    **DOVE VIVE L'ESITO.** In RAM, in `app["tree_comparison"]`, accanto a
    `app["ha_problems"]` e per la stessa ragione, gia' scritta per esteso su
    `reread_ha_problems`: un confronto e' momentaneo -- la casa cambia e la
    replica si rifa' da sola al primo evento di registro -- e un archivio
    riletto di rado continuerebbe ad annunciare per ore una divergenza gia'
    rientrata. E' lo stesso ragionamento per cui `state` non entra nel sistema
    di riferimento della casa (`home_space.topology.reference_frame`).

    Si tiene SOLO l'ultimo giro, non un archivio di verdetti che si accumula:
    cosi' ogni verdetto che il nucleo legge e' vecchio al massimo quanto la
    cadenza, e nessuna area resta marchiata da una divergenza riparata mezz'ora
    fa. Il prezzo -- si vedono tre aree per volta -- e' dichiarato dentro
    l'esito stesso (`aree_totali`) e detto in ogni frase che il nucleo scrive.

    **Non solleva mai**: `extract_from_target` risponde gia' `{"errore": ...}`
    sui guasti, e un'area che non si e' potuta leggere e' un'informazione da
    portare al modello -- non un'eccezione da propagare in uno schedulatore, e
    soprattutto non un'area che combacia.

    Lo stato della rotazione (`dopo`) vive in una chiusura e non in `app`: e'
    un dettaglio di questo lavoro, non un fatto sulla casa, e nessun altro ha
    motivo di leggerlo. Stessa forma di `behavior_reader` e di
    `schedule_registry_rebuild`.
    """
    state: dict[str, str | None] = {"dopo": None}

    async def run_round() -> dict | None:
        if ha_client is None:
            return None
        reader = getattr(ha_client, "extract_from_target", None)
        if reader is None:
            # Un client vecchio o un finto di prova che non dichiara il
            # comando: non si scrive niente, cosi' la chiave resta assente e
            # il nucleo tace invece di affermare che l'albero e' verificato.
            return None
        store = app.get("home_space_store")
        if store is None:
            return None

        # Una lettura sola, e l'albero costruito una volta: il campione, le
        # domande a HA e il verdetto guardano tutti la STESSA fotografia della
        # replica. Ricostruirlo dopo le risposte vorrebbe dire confrontare un
        # albero con le risposte a domande fatte su un altro.
        home_space = store.read()
        piani = hierarchy(home_space, tuple(store.unavailable()))
        areas = tree_areas(piani)
        sample = choose_sample(areas, count, state["dopo"])

        answers: dict[str, dict] = {}
        for area in sample:
            try:
                answers[area["id"]] = await reader({"area_id": [area["id"]]})
            except Exception as exc:  # non previsto: il client cattura gia'
                logger.warning("confronto dell'area %s non riuscito: %s", area["id"], exc)
                answers[area["id"]] = {"errore": "Home Assistant non ha risposto"}
        if sample:
            state["dopo"] = sample[-1]["id"]

        report = compare_with_home_assistant(piani, home_space, answers)
        # La data la mette il chiamante: `compare_with_home_assistant` e'
        # pura, e una funzione pura che leggesse l'orologio non sarebbe piu'
        # confrontabile con se stessa. Serve a chi disegna l'albero
        # (`/api/home-space`) per dire quanto e' fresco il verdetto che sta
        # mostrando.
        report["letto_il"] = datetime.now(UTC).isoformat(timespec="seconds")
        app["tree_comparison"] = report
        divergenti = sum(1 for g in report["guardate"] if g.get("mancanti") or g.get("in_piu")
                         or g.get("assente_in_ha"))
        if divergenti:
            logger.warning("confronto dell'albero: %d aree su %d guardate divergono da "
                           "Home Assistant", divergenti, len(report["guardate"]))
        return report

    return run_round


#: Quanto tace il log per un giorno di `backfill_one_report` che non si fa, dopo
#: averlo detto una volta. Decisioni del proprietario, 17/09/2026: prima per la
#: cronaca che non si rifa', poi -- lo stesso giorno -- anche per il resoconto
#: che non si recupera (Home Assistant irraggiungibile). Il giro gira ogni
#: cinque minuti: senza, lo stesso warning uscirebbe a ogni giro, in entrambi i
#: rami. Il comportamento dei rami non cambia (il «manca» torna `None` e
#: riprova), cambia solo quante volte lo dicono.
#:
#: **I due rami condividono la voce del giorno**, di proposito: un giorno sta in
#: un ramo solo alla volta (un resoconto che manca non ha una cronaca da rifare),
#: e passa dal primo al secondo solo RIUSCENDO, cioe' togliendo la voce. Due
#: chiavi separate non direbbero niente di piu', e sarebbero due posti per lo
#: stesso fatto: «questo giorno non si riesce a fare».
#:
#: Lo stato vive in `app["backfill_quiet"]` (giorno ->
#: istante dell'ultimo warning), **creato vuoto da `_on_startup`**, prima che
#: aiohttp congeli l'app: il giro gira ad app avviata, e aggiungere una chiave a
#: quel punto e' «Changing state of started or joined application» (stessa
#: regola di `api/handlers_mcp.create_rounds_per_exchange`, M-2). Un riavvio lo
#: azzera, e il warning si riscrive una volta -- accettato.
#:
#: Una voce per giorno FALLITO; si toglie quando quel giorno riesce, e altrimenti
#: non si pota finche' il processo vive. Il conto e' limitato: un giorno uscito
#: dal grezzo non entra piu' in nessuno dei due rami, e i giorni del grezzo sono 22.
BACKFILL_QUIET_S = 4 * 3600


def _backfill_warning_due(app, day: str, clock: float) -> bool:
    """Se il warning di `day` va scritto adesso: si' la prima volta e dopo
    `BACKFILL_QUIET_S` dall'ultimo, e in quel caso segna l'istante. Una sola
    regola per i due rami di `backfill_one_report`."""
    quiet = app["backfill_quiet"]
    if clock - quiet.get(day, float("-inf")) < BACKFILL_QUIET_S:
        return False
    quiet[day] = clock
    return True


async def backfill_one_report(app, ha_client, *,
                              now=datetime.now) -> str | None:
    """Il resoconto di **un** giorno che manca o la cui cronaca e' nata con un
    altro giudizio. Torna quale, o `None`.

    **Perche' esiste, col numero.** Misurato sulla casa vera il 14/09/2026,
    appena il resoconto ha cominciato a nascere: esistevano quello del 12 e
    quello del 13, e basta. Il 7, l'8, il 9, il 10 e l'11 avevano oggetti e
    grezzo e **nessun resoconto** -- la riparazione d'avvio guarda solo gli
    ultimi due giorni pieni, e l'aggregazione notturna solo ieri. Nessuno dei
    due percorsi arriva indietro, e per l'analista quei giorni non esistono:
    una misura letta su due giorni non e' una serie.

    **Un giorno per giro.** Le statistiche di Home Assistant si chiedono una
    volta per giorno: ventidue richieste all'avvio ritarderebbero la partenza
    per un lavoro che non ha nessuna fretta. E' la stessa disciplina di
    `recipe_round` -- uno per volta, e in qualche ora si e' coperto tutto.

    **Dal piu' VECCHIO.** E' quello che sta per scadere: il suo grezzo sparisce
    per primo (22 giorni), e dopo non si rifa' piu'. Partire dal piu' recente
    vorrebbe dire perdere proprio i giorni per cui questo lavoro esiste.

    **Non oltre il grezzo.** Un giorno si rifa' solo finche' il suo grezzo
    esiste (spec §9). Andare piu' indietro scriverebbe resoconti VUOTI per
    giorni in cui era successo di tutto, e un resoconto vuoto dice «non e'
    successo niente»: una bugia archiviata, nell'archivio che esiste per non
    dirne.

    **Un giorno mancante si fa intero; uno gia' scritto non si sovrascrive
    mai per intero.** Le misure di un giorno scritto restano quelle: stessa
    asimmetria di `_write_missing_reports` e di `store._migration_8`.

    **Ma la sua cronaca si', quando e' nata con un altro giudizio** (dal
    17/09/2026, spec `docs/design/2026-09-16-il-giudizio-dei-tipi.md` §6):
    l'impronta del resoconto e' diversa da quella dell'istantanea corrente, o
    manca (`facts.chronicle_is_stale`). Allora `facts.rebuild_chronicle`
    sostituisce **solo** `cronaca` e `giudizio` -- nessuna lettura di Home
    Assistant, nessuna ricetta. Stesso giro, stesse regole: un giorno per
    giro, dal piu' vecchio, mai oltre il grezzo.

    **Il giorno a cavallo della potatura non si rifa'** (revisione del
    17/09/2026, eseguita): la potatura taglia a un istante e non a mezzanotte,
    quindi il giorno in cui cade il taglio ha perso le sue voci nate prima. Non
    si possono ricostruire, e rifarlo le cancellerebbe: quel giorno tiene la
    cronaca e l'impronta che ha. Solo per la cronaca: un giorno MANCANTE a cavallo si scrive
    ancora, com'era.

    **La condizione e' «nessuna riga di questo giorno puo' essere stata
    potata»**, cioe' l'inizio del giorno oltre il taglio della potatura
    (`adesso - READING_RETENTION_S`, dov'esso taglia: `mind/store.prune`) --
    **non** un confronto con la riga piu' vecchia dell'archivio (giro di
    correzioni 1, punto 1, riprodotto). Le due condizioni coincidono su una
    casa potata, dove la riga piu' vecchia E' il taglio, e divergono su una
    casa **giovane**: li' la riga piu' vecchia e' soltanto l'ora
    d'installazione, il primo giorno comincia a mezzanotte e con la vecchia
    condizione restava al giudizio vecchio per sempre, in silenzio.

    **Ogni giorno rifatto logga una riga con la durata**: e' la misura vera di
    quanto costa un giorno sull'host di Home Assistant, che la spec (§1,
    misura 12) non ha. Un giro che non ha niente da fare non logga niente.

    Non solleva: gira per sempre. **I due rami falliscono in modo diverso, e
    reagiscono in modo diverso.** Un giorno mancante che non si scrive torna
    `None` e si riprova al giro dopo dallo stesso giorno: i suoi errori sono
    la rete verso Home Assistant, e passano. Una cronaca che non si rifa' e'
    un difetto locale e deterministico -- fallirebbe a ogni giro -- e dal piu'
    vecchio fermerebbe per sempre ogni giorno dopo, al primo avvio tutti: si
    logga e si passa al giorno successivo nello stesso giro. **In entrambi i
    rami** il warning esce una volta per giorno ogni `BACKFILL_QUIET_S`, non a
    ogni giro, e una riuscita toglie la voce del giorno (Task 7b, decisioni del
    proprietario del 17/09/2026).
    """
    archivio = app["observations"]
    first_ts = archivio.oldest_reading_ts()
    if first_ts is None:
        return None
    timezone = house_timezone(app.get("home_space_store"))
    adesso = now(UTC)
    today = local_date(adesso.timestamp(), timezone)
    first_day = local_date(first_ts, timezone)
    # Il taglio della potatura, calcolato come lo calcola lei
    # (`mind/store.prune`: `quando_ts < now - READING_RETENTION_S`). Un giorno
    # che comincia da qui in poi non puo' aver perso nessuna riga, e si rifa'.
    oldest_intact_ts = adesso.timestamp() - READING_RETENTION_S

    day = first_day
    while day < today:
        as_text = day.strftime("%Y-%m-%d")
        written = archivio.report(as_text)
        if written is None:
            try:
                await write_day_report(app, ha_client, day=as_text, timezone=timezone)
            except Exception as error:
                if _backfill_warning_due(app, as_text, now(UTC).timestamp()):
                    logger.warning(
                        "cervello: resoconto di %s non recuperato (%s: %s) -- per questo "
                        "giorno il log tace per %d ore", as_text, type(error).__name__,
                        error, BACKFILL_QUIET_S // 3600)
                return None
            app["backfill_quiet"].pop(as_text, None)
            logger.info("cervello: recuperato il resoconto di %s", as_text)
            return as_text
        if (chronicle_is_stale(written, app["type_judgments"])
                and day_boundaries(as_text, timezone)[0] >= oldest_intact_ts):
            started = time.monotonic()
            try:
                rebuild_chronicle(store=archivio, day=as_text, timezone=timezone,
                                  judgments=app["type_judgments"],
                                  house=House.read(app.get("home_space_store"),
                                                   app.get("entity_cache")))
            except Exception as error:
                if _backfill_warning_due(app, as_text, now(UTC).timestamp()):
                    logger.warning(
                        "cervello: cronaca di %s non rifatta (%s: %s) -- per questo "
                        "giorno il log tace per %d ore", as_text, type(error).__name__,
                        error, BACKFILL_QUIET_S // 3600)
                day += timedelta(days=1)
                continue
            app["backfill_quiet"].pop(as_text, None)
            logger.info(
                "cervello: rifatta la cronaca di %s col giudizio %s in %.2f s",
                as_text, app["type_judgments"].chronicle_fingerprint(),
                time.monotonic() - started)
            return as_text
        day += timedelta(days=1)
    return None


async def _write_missing_reports(app, ha_client, days, timezone) -> list[str]:
    """Il resoconto dei giorni che **non ne hanno uno**, e solo quelli.

    La riparazione d'avvio ha quattro uscite anticipate, tutte per la regola
    *«chi SOSTITUISCE non tollera il parziale»*: scrivere oggetti poveri sopra
    oggetti ricchi e' un impoverimento, non una riparazione. La regola e'
    giusta per gli oggetti.

    **Per il resoconto e' il contrario, e si e' misurato dal vivo il
    14/09/2026**: sulla casa vera non esisteva nessun resoconto, perche' una
    di quelle uscite scattava a ogni avvio e l'unico altro scrittore e'
    l'aggregazione delle 00:20. Un resoconto sa dire cio' che non ha potuto
    calcolare -- «non calcolabile, e perche'», che e' il terzo innesco
    dell'analista; un resoconto che non c'e' non dice niente, e non si
    distingue da un giorno in cui non e' successo nulla.

    **Ma l'asimmetria resta, spostata**: si scrivono solo i giorni che un
    resoconto non ce l'hanno. Uno gia' scritto dalla notte ha anche le misure,
    e sostituirlo con una cronaca nuda perche' stamattina la rete era giu'
    sarebbe lo stesso impoverimento, su un altro strato. E' la stessa regola
    di `store._migration_8` per gli oggetti storici.

    Non solleva: e' una consolazione, non il lavoro principale, e non deve
    poter far fallire un avvio.
    """
    archivio = app["observations"]
    scritti: list[str] = []
    for day in days:
        try:
            if archivio.report(day) is not None:
                continue
            await write_day_report(app, ha_client, day=day, timezone=timezone)
            scritti.append(day)
        except Exception as error:
            logger.warning(
                "cervello: resoconto di %s non scritto durante la riparazione "
                "(%s: %s)", day, type(error).__name__, error)
    return scritti


async def reaggregate_last_two_days(app, ha_client, *, now=datetime.now) -> None:
    """La riparazione d'avvio, **che dice sempre com'e' andata**.

    Il corpo vero e' `_reaggregate_days` qui sotto: questa e' la sola cosa che
    gli sta attorno. Il corpo scrive il proprio esito in
    `app["ultima_riparazione"]` solo se arriva in fondo; **se solleva prima**,
    l'eccezione risale al chiamante, che la ingoia in un warning, e senza
    questo involucro `GET /api/health` resterebbe a `riparazione: null`. Cioe'
    «non e' girata»: falso, ed e' proprio la domanda a cui deve rispondere.

    **L'eccezione continua a propagare**: il contratto col chiamante non
    cambia, e' lui a decidere se contenerla. Qui si aggiunge solo la memoria
    di cio' che e' successo.
    """
    try:
        await _reaggregate_days(app, ha_client, now=now)
    except Exception as error:
        app["ultima_riparazione"] = {
            "oggetti": "sollevata",
            "perche": f"{type(error).__name__}: {error}",
            "giorni": [], "resoconti_scritti": []}
        raise


async def _reaggregate_days(app, ha_client, *, now=datetime.now) -> None:
    """All'avvio, scrive il resoconto degli ultimi due giorni pieni che non ce
    l'hanno (oggi escluso: non e' ancora finito).

    **Qui il resoconto non si sostituisce mai**: si scrive solo dove manca, ed
    e' `_write_missing_reports` a farlo. L'unica sostituzione e' la sola
    cronaca nata con un altro giudizio, e la fa il recupero
    (`backfill_one_report`).

    **Perche' esiste ancora, accanto al recupero periodico.** Il recupero
    (`backfill_one_report`) scrive un giorno ogni cinque minuti dal
    piu' vecchio: gli ultimi due arriverebbero per ultimi, ore dopo l'avvio.
    Questa li mette davanti subito, che e' cio' che il proprietario guarda
    quando riapre la pagina.

    **L'eccezione si lascia propagare**, come prima: e' il chiamante a
    decidere se contenerla.

    `now` e' iniettabile per i test: nella vita vera nessuno lo passa.
    """
    timezone = house_timezone(app.get("home_space_store"))
    today = local_date(now(UTC).timestamp(), timezone)
    days = [(today - timedelta(days=delta)).strftime("%Y-%m-%d") for delta in (2, 1)]
    written = await _write_missing_reports(app, ha_client, days, timezone)
    app["ultima_riparazione"] = {"oggetti": "fatta", "perche": None,
                                 "giorni": days, "resoconti_scritti": written}
    if written:
        logger.info("cervello: resoconti scritti all'avvio per %s",
                    ", ".join(written))

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


def mirror_reload_listener(client, entity_cache, watcher=lambda: None):
    """Restituisce l'ascoltatore di topologia che rilegge lo specchio.

    Spec «una porta sola» §6: il quarto avvisato, dopo anagrafe, servizi e
    plance. Gli altri eventi dell'anagrafe non lo toccano. `_ws_loop` emette
    «riconnessione» a ogni connessione riuscita DOPO la prima (Tappa 2, Task
    7, D2): alla prima l'avvio legge lo specchio una volta da se'
    (`entity_cache.load`), dopo essersi iscritto. Con la stessa fotografia
    l'osservatore si riallinea (`mind/realignment.py`).
    """
    def _mirror_on_reconnect(event_type: str) -> None:
        if event_type == "riconnessione":
            _spawn(reload_and_realign(client, entity_cache, watcher),
                   name="specchio-riconnessione")
    return _mirror_on_reconnect


def schedule_dashboards_reread(client, store, delay: float = 3.0):
    """Restituisce `trigger(event_data)`: rilegge le plance, una volta sola.

    Gemello di `schedule_registry_rebuild` — stesso antirimbalzo,
    stessa tolleranza ai guasti — ma per un innesco DIVERSO (DASHBOARD_EVENT,
    non i registri): le plance non stanno in `reader.TABLES` e non vanno confuse con
    l'anagrafe, che questa funzione non tocca.
    """
    state: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(delay)
            await reread_dashboards(client, store)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("rilettura delle plance fallita: %s", exc)

    def trigger(event_data: dict) -> None:
        pending = state["attesa"]
        if pending is not None and not pending.done():
            pending.cancel()
        state["attesa"] = _spawn(_fra_poco(), name="rilettura_plance")

    return trigger


async def reconsideration_round(app, ha_client) -> dict | None:
    """L'anello dell'osservatore: **«è ora di ripensare la casa? e allora
    fallo»**. Torna il resoconto del giro, o `None` se non c'era da farlo.

    I quattro inneschi della spec §5.1 -- il primo avvio, l'obiettivo cambiato,
    qualcosa di nuovo in casa, la cadenza di riconsiderazione -- li pone tutti
    `cadence.reason_to_reconsider`: qui non se ne decide nessuno, o sarebbero
    due posti da cui dimenticarne uno.

    **La domanda «è ora?» deve costare zero.** Questo giro scatta ogni
    minuto; misurare la memoria di Home Assistant a ogni passaggio sarebbe
    traffico speso per rispondere «no». Quindi si
    usa la cadenza **dell'ultimo giro**, scritta accanto a quello, e la finestra
    si **rimisura solo quando si gira davvero**: e' anche piu' giusta, perche'
    il proprietario puo' aver cambiato il recorder nel frattempo.

    **L'impronta si chiede sulle stesse entita' che si mostrano al modello.**
    L'osservatore non giudica le entita' di servizio e le nascoste (decisione
    del proprietario, 10/09/2026): nessuna di esse finisce mai nello scope,
    quindi chiederle all'impronta le farebbe risultare «nuove» a ogni giro --
    452 su questa casa -- e l'osservatore girerebbe a ogni passaggio, per
    sempre.

    **Il giro ha DUE tempi, e non e' una complicazione gratuita** (fetta
    «l'osservatore chiede a chi risponde davvero», 11/09/2026). Chi risponde
    lo decide `steering.who_answers`, la stessa funzione che lo decide per la
    chat e per le promesse; quando risponde «ponte», il turno si **accoda** e
    la risposta torna minuti dopo, da un altro processo. Quindi ogni
    passaggio prima guarda se c'e' una risposta da raccogliere, e solo dopo si
    chiede se sia ora di domandare ancora.

    Non solleva mai: gira per sempre, e un avvio a meta' -- il modello non
    ancora costruito, l'anagrafe non ancora letta -- non deve fermare lo
    schedulatore.
    """
    store = app.get("observations")
    home_space_store = app.get("home_space_store")
    if store is None or home_space_store is None:
        return None
    try:
        # La casa di questo giro (R13): l'anagrafe e lo specchio di adesso,
        # una volta. Vale il giro e basta.
        house = House.read(home_space_store, app.get("entity_cache"))
        collected, letto = _collect_scope_turn(app, store, house)
        if collected is not None:
            return collected
        if letto:
            # **Una raccolta fallita chiude il passaggio: non si richiede
            # subito.** Riaccodando nello stesso giro, un guasto stabile
            # produrrebbe un turno a ogni scadenza del ponte.
            # `count_exchanges_today` conta ogni specie contro il tetto
            # giornaliero del piano: un osservatore rotto lo svuoterebbe da
            # solo, e da li' in poi ogni turno -- chat compresa -- passerebbe
            # ai provider a pagamento.
            return None
        if turn_in_flight(app, SCOPE_TURN_KIND):
            # Questo giro scatta ogni minuto e un turno del piano ne dura
            # parecchi: senza questa guardia la casa accodarebbe un turno al
            # minuto, ciascuno col suo lotto di casa dentro, e il tetto
            # giornaliero del piano si svuoterebbe in mezz'ora.
            return None
        if _retry_hold(store, now=time.time()):
            return None

        # Chi l'osservatore guarda lo dice la casa (Task 12): la stessa
        # scelta di `observer.watched_ids`, non una seconda lettura.
        candidates = sorted(house.visible_entities())
        last = store.last_reconsideration()
        objective = store.objective()
        # **Una riconsiderazione e' una CAMPAGNA di piu' lotti.** La domanda
        # si spezza perche' 381 giudizi in un turno solo uccidono la CLI del
        # piano (misurato l'11/09/2026, vedi `SCOPE_BATCH`), e la campagna
        # prosegue ai giri successivi finche' la casa e' coperta -- **senza
        # riaspettare la cadenza**, che altrimenti sarebbe gia' soddisfatta e
        # i lotti dal secondo in poi non partirebbero mai.
        restano = _to_judge(store, candidates, last)
        in_corso = last is not None and bool(restano)
        if in_corso:
            why = (f"la campagna prosegue: restano {len(restano)} soggetti "
                   "da giudicare")
        else:
            why = reason_to_reconsider(
                last=last,
                cadence_s=last["cadenza_s"] if last else None,
                objective_ts=objective.get("scritto_ts"),
                undecided=store.undecided(candidates),
                now=time.time())
            if why is None:
                return None
            # La campagna comincia ADESSO: i soggetti da rigiudicare sono
            # tutti, e l'istante si prende PRIMA delle decisioni cosi' che
            # quelle del primo lotto risultino gia' dentro la campagna.
            restano = list(candidates)
        lotto = set(restano[:SCOPE_BATCH])

        # **La stessa domanda che si fanno la chat e le promesse, dalla stessa
        # funzione.** Fino all'11/09/2026 questo giro non se la faceva affatto
        # e andava dritto al router -- dove il ponte non e' un anello
        # (`providers.chain_members()`). Misurato sulla casa vera l'11/09
        # alle 11:00:44: l'osservatore cadeva su un modello OpenRouter
        # «batch-only» (404) e su una chiave Claude senza credito (400) mentre
        # l'abbonamento, li' accanto, serviva la chat. E' il difetto che
        # `steering.py` dichiara chiuso il 22/08 per le promesse, con la frase
        # «una terza porta che nascesse domani non potrebbe inventarsene una
        # terza senza accorgersene»: la terza porta era questa.
        # **Il passaggio dal forfait al consumo si annuncia ogni volta**
        # (decisione del proprietario, 13/08/2026, che `steering.py` dichiara
        # nel suo docstring): un prelievo silenzioso si scopre a fine mese. Lo
        # dichiara la partenza (`steering.start`). Il motivo e' una chiave di
        # `model_resolution._DOWNGRADE_REASONS`, e finisce anche nel
        # tentativo, cosi' la pagina puo' dire da quale porta e' passato quel
        # giro.
        route, downgrade, runner = start(app, OBSERVER_SPECIES)
        if route == "catena" and runner is None:
            # **Anche il silenzio si annota.** Senza token del piano e senza
            # nessun provider in catena l'osservatore taceva per sempre, con
            # la faccia di «nessuno ha ancora provato» (rilievo della review
            # indipendente, 11/09/2026).
            store.record_attempt(
                outcome="non_riuscito",
                detail=f"non c'era nessun modello a cui chiedere ({downgrade})"
                if downgrade else "non c'era nessun modello a cui chiedere",
                version=read_version())
            return None

        logger.info("osservatore: riconsidero la casa (%s), lotto di %d -- %s",
                    route, len(lotto), why)
        campagna_ts = time.time()
        # **La finestra si misura solo per il lotto che la annota** (A-19,
        # Tappa 2, Task 8): la riconsiderazione la scrive solo il primo lotto
        # della campagna (`apply_answer` con `record=True`, il turno del ponte
        # con `annota`). I lotti successivi la misuravano su tutte le entita'
        # -- dieci sonde, piu' sette se la memoria cade dentro la scala -- e
        # la buttavano.
        # **L'insieme e' quello del registratore, non quello dell'osservatore**
        # (Task 12): la memoria e' di Home Assistant, e la provano anche le
        # entita' che nessuno guarda. Ogni entita' del registro, come prima.
        window_s = None if in_corso else await measure_memory_window(
            ha_client, sorted(house.entity_ids()))
        if route == "ponte":
            return _enqueue_scope_turn(app, store, house, reason=why,
                                       window_s=window_s, lotto=lotto,
                                       annota=not in_corso,
                                       campagna_ts=campagna_ts)
        outcome = await observer_reconsider(
            runner, store, house, reason=why,
            window_s=window_s, cadence_s=cadence_from(window_s),
            only=lotto, record=not in_corso, campaign_ts=campagna_ts,
            measurements=app.get("usage"))
        _record_attempt(store, outcome, route="catena", downgrade=downgrade)
        logger.info("osservatore: giro finito -- %s", outcome)
        return outcome
    except Exception as exc:
        logger.warning("osservatore: giro di riconsiderazione fallito (%s: %s)",
                       type(exc).__name__, exc)
        return None


async def _report_ingredients(app, ha_client, *, giorno: str,
                                     timezone: str | None):
    """Le ricette, le serie e i nomi che servono al resoconto di un giorno.

    Torna `(ricette, serie, nomi, silent, mute)`: `silent` sono le entita'
    che non daranno una serie, ognuna col suo rifiuto -- frase e causa
    (`recipes.silent_entities`, B-26) -- o `None` se non si e' potuto
    chiedere; `mute` sono le ricette che non possono produrre perche' ogni
    loro entita' tace per una causa che non passa da sola
    (`recipes.muted_recipes`, piano degli attori, Task 1.5): escono da
    `ricette`, le loro serie non si chiedono, e il resoconto le dice con una
    riga per dispositivo. Ricette vuote -- nessun dispositivo ne ha
    una, o il sapere non e' collegato -- fanno un resoconto con la meta' delle
    misure vuota, ed e' un fatto vero su quella casa: si scrive.

    **Le statistiche si chiedono una volta per tutte le ricette**: le entita'
    che ogni ricetta nomina si raccolgono prima, invece di una richiesta per
    dispositivo. Quali di quelle entita' hanno statistiche lo dice
    `statistic_ids_for_round`, la lettura condivisa col giro delle ricette.
    """
    sapere = app.get("knowledge")
    casa = app.get("home_space_store")
    if sapere is None or casa is None:
        return {}, {}, {}, None, {}
    # I dispositivi e i loro nomi li dice la casa (Task 12): il nome,
    # altrimenti l'id (`House.name`).
    house = House.read(casa, app.get("entity_cache"))
    nomi = {device_id: house.name("dispositivo", device_id)
            for device_id in house.device_ids()}
    # Le ricette di tutti in una lettura (A-38), nell'ordine dell'anagrafe.
    scritte = recipe_turn.recipes(sapere)
    ricette = {device_id: scritte[device_id] for device_id in nomi
               if device_id in scritte}
    # Le ricette di un dispositivo che tace tutto non girano (G-02, G-03):
    # lo stato della fonte si chiede alla stessa casa del giro.
    mute = muted_recipes(house, ricette)
    ricette = {device_id: recipe for device_id, recipe in ricette.items()
               if device_id not in mute}
    if not ricette:
        return {}, {}, nomi, None, mute
    entita = sorted({e for r in ricette.values() for e in Recipe(r).entities()})
    da_ts, a_ts = day_boundaries(giorno, timezone)
    # **Quali di queste entita' non avranno MAI una serie** (spec §6, primo
    # «rifiuta se»). Una lettura sola per giro, come le statistiche: il
    # registro di Home Assistant e' un elenco di nomi, non una serie.
    # `None` -- non l'insieme vuoto -- se non si e' potuto leggere: affermare
    # «nessuna entita' ha statistiche» farebbe rifiutare tutto il resoconto.
    # Si legge PRIMA delle serie (dal 06/10/2026): dice anche le sorelle che
    # la regola del dato fermo chiede (`House.sibling_group`).
    with_statistics = await statistic_ids_for_round(app, ha_client)
    if isinstance(with_statistics, dict):  # la busta del guasto (D3)
        logger.warning("resoconto: elenco delle statistiche non letto (%s): %s",
                       with_statistics.get("causa"), with_statistics.get("errore"))
        list_read = False
        # Senza l'elenco si chiedono TUTTE le sorelle possibili -- dispositivo
        # e istanza -- e chi ha statistiche lo dice la risposta delle serie
        # (sotto). Il ripiego sullo `state_class` dello specchio perdeva i
        # termometri del 29/09 (G7-1, rimisura dello sprint su 413ce7a7,
        # 06/10/2026): nello specchio non lo portavano.
        lette = sorted({c for e in entita for c in house.possible_siblings(e)})
    else:
        list_read = True
        counted = house.with_statistics(with_statistics)
        lette = sorted({s for e in entita for s in counted.siblings(e) or [e]})
    # **Il giorno e la sua storia in UNA lettura, con le sorelle** (attori,
    # Task 1.3; proposta del 06/10/2026): la regola del dato fermo giudica il
    # gruppo di ogni entita' contro la stessa ora dei giorni prima
    # (`mind/flatline.py`). La finestra si allunga di `HISTORY_DAYS` e le
    # sorelle entrano nella stessa richiesta: nessuna richiesta in piu'.
    history_start_ts = da_ts - HISTORY_DAYS * 86400
    report = await ha_client.hourly_statistics(
        lette, datetime.fromtimestamp(history_start_ts, tz=UTC).isoformat(),
        datetime.fromtimestamp(a_ts, tz=UTC).isoformat())
    if "errore" in report:
        # **Un guasto delle statistiche non e' un resoconto senza misure.** Si
        # scrivono le ricette senza serie: ogni misura esce «non calcolabile»
        # dicendo che le statistiche non si sono potute leggere -- e l'analista
        # la vede sparire, che e' il suo terzo innesco. Fino al 04/10/2026
        # questo commento lo prometteva e la misura diceva invece «la serie
        # e' vuota» (trovato 7 del piano della Tappa 3, S-28).
        logger.warning("resoconto: statistiche non lette per %s (%s)",
                       giorno, report["errore"])
        refusal = unread_series(str(report["errore"]))
        return ricette, {}, nomi, {e: refusal for e in entita}, mute
    if not list_read:
        # **Chi ha statistiche, detto da Home Assistant.** `recorder/
        # statistics_during_period` risponde solo per gli id che hanno righe
        # nella finestra (`recorder/statistics.py::_sorted_statistics_to_dict`,
        # `seen_statistic_ids`, letto sul tag `2026.9.0` il 06/10/2026): la
        # risposta e' un elenco anche lei, quello della finestra letta. La
        # regola resta una, `House.has_statistics`; cambia solo da quale
        # risposta di Home Assistant viene l'elenco.
        counted = house.with_statistics(frozenset(
            e for e, punti in report["serie"].items() if punti))
    gruppi = {}
    for e in entita:
        for sorella in counted.siblings(e) or [e]:
            gruppi[sorella] = counted.sibling_group(sorella)
    finestra = {e: hourly_points(report["serie"].get(e) or []) for e in gruppi}
    serie = {e: split_at(finestra[e], da_ts)[1] for e in entita}
    # **Una misura su una fonte ferma si rifiuta** (D4): il 30/09/2026 il
    # resoconto ha scritto produzione 0 con copertura 1.0, e lo zero era
    # falso. I rifiuti entrano fra le entita' che tacciono, la strada che
    # `Recipe.run` conosce gia'.
    ferme = frozen_refusals(finestra, gruppi, day_start_ts=da_ts, entity_ids=entita,
                            zone=home_space_zone(timezone))
    if ferme:
        logger.info("resoconto: %d entita' ferme il %s -- le loro misure "
                    "diranno perche'", len(ferme), giorno)
    if not list_read:
        # Di quali entita' non abbiano statistiche non si afferma niente: una
        # serie vuota nella finestra non e' «nessuna statistica». Che una
        # fonte sia ferma si e' visto sulle serie, e resta (G7-1).
        return ricette, serie, nomi, ferme or None, mute
    # Il perche' di ognuna dalla FONTE (B-26; Tappa 3, Task 8): la
    # stessa casa del giro, con l'elenco appena letto -- nessuna seconda
    # lettura di `recorder/list_statistic_ids`.
    silent = silent_entities(counted, entita)
    if silent:
        logger.info(
            "resoconto: %d entita' su %d nominate dalle ricette non hanno "
            "statistiche in Home Assistant -- le loro misure diranno perche'",
            len(silent), len(entita))
    if silent is None:
        return ricette, serie, nomi, ferme or None, mute
    return ricette, serie, nomi, {**ferme, **silent}, mute


async def write_day_report(app, ha_client, *, day: str, timezone: str | None) -> int:
    """Scrive il resoconto di `day` e torna quante voci di cronaca porta.

    **L'unica strada del resoconto di un giorno** (D-36, 06/10/2026): gli
    ingredienti letti da Home Assistant (`_report_ingredients`) e poi
    `facts.aggregate_day` con l'istantanea viva dei giudizi e la casa di
    adesso -- che serve a chiudere gli episodi di cio' che Home Assistant non
    nomina piu' (`facts.build_episodes`). Fino a quel giorno la stessa coppia
    era scritta tre volte: la notte (`_aggrega_ieri`), il recupero
    (`backfill_one_report`) e la riparazione d'avvio
    (`_write_missing_reports`). Lo difende
    `tests/test_fonte_unica.py::test_d36_il_resoconto_di_un_giorno_ha_una_strada_sola`.

    **Sostituisce sempre** (`aggregate_day` e' idempotente): se un giorno gia'
    scritto si possa rifare lo decide chi chiama, e cosi' la politica sugli
    errori -- la notte li logga, il recupero li silenzia per giorno, la
    riparazione li conta giorno per giorno. Qui si solleva.
    """
    ricette, serie, nomi, silent, mute = await _report_ingredients(
        app, ha_client, giorno=day, timezone=timezone)
    return aggregate_day(
        store=app["observations"], day=day, timezone=timezone,
        recipes=ricette, series=serie, names=nomi,
        silent=silent, muted=mute,
        judgments=app["type_judgments"],
        house=House.read(app.get("home_space_store"), app.get("entity_cache")))


async def hold_watcher_statistic_ids(app, ha_client) -> None:
    """L'elenco delle entita' con statistiche consegnato al watcher (B-12,
    Tappa 3, Task 7, 04/10/2026), dalla stessa lettura condivisa dei giri
    (`statistic_ids_for_round`): il watcher decide su ogni evento se una
    lettura la tiene gia' Home Assistant, e non puo' chiederlo evento per
    evento. Lo fa il giro delle condizioni, ogni dieci minuti; prima del primo
    giro il watcher usa la regola del sorgente (`ha_vocabulary.has_statistics`).
    Una lettura fallita non tocca l'ultima buona (`Watcher.hold_statistic_ids`).
    """
    watcher = app.get("watcher")
    if watcher is None or ha_client is None:
        return
    watcher.hold_statistic_ids(await statistic_ids_for_round(app, ha_client))


# **I nomi dei dispositivi vivono in `mind/view.MindView.device_names`, e qui
# si chiedono.** Fino al 15/09/2026 ne esistevano due copie identiche, e quella
# di la' aveva scritto nel docstring «Un posto solo»: una ragione smentita dal
# file che citava. Trovata dalla revisione indipendente. La seconda fondamenta
# -- niente doppioni -- vale anche per otto righe.


async def analyst_round(app) -> dict | None:
    """L'anello dell'analista: **«leggi le misure di molti giorni e di' cosa si
    potrebbe fare»** (spec §10).

    Torna il resoconto del giro, o `None` se non c'era da farlo.

    **Una volta al giorno, e non e' prudenza generica.** Misurato sulla casa
    vera il 15/09/2026, con venti giorni archiviati e 146 serie: la domanda
    pesa **~35.000 token** -- tre volte il giro dell'osservatore. Farla a ogni
    giro dello schedulatore svuoterebbe il tetto giornaliero del piano da sola.
    Un giorno ha una analisi sola, e quando ce l'ha il giro non fa niente.

    **Il silenzio si archivia**, e non e' un giro sprecato: «ho guardato e non
    c'era niente da dire» e «non ho guardato» sono due cose diverse, ed e' la
    stessa legge del resoconto vuoto.

    **Dalla stessa porta dello scope e delle ricette**: chi risponde lo decide
    `steering.who_answers`.

    Non solleva mai: gira per sempre, e un giro andato storto non deve fermare
    lo schedulatore.
    """
    store = app.get("observations")
    if store is None:
        return None
    try:
        timezone = house_timezone(app.get("home_space_store"))
        today = historian.today(timezone).isoformat()

        collected = _collect_analyst_turn(app, store, today)
        # **Chiude il giro solo un'analisi SCRITTA** (06/10/2026). Fino a
        # qui bastava `risposta`: una risposta rifiutata non si archivia, il
        # turno restava l'ultimo della sua specie, e il giro lo rileggeva e
        # rifiutava a ogni passaggio senza accodarne mai uno nuovo -- dal
        # 05/10 13:32 al 06/10 14:05 sulla casa vera, su un turno fallito dal
        # ponte. Sesta occorrenza della forma del 22/09 (sopra
        # `_collect_analyst_turn`). Un rifiuto o un vuoto aspettano il freno
        # delle ricette, poi si richiede: accodato il turno nuovo, quello
        # vecchio non e' piu' l'ultimo e non si rilegge.
        if collected is not None and collected.get("analisi") is not None:
            return collected
        if collected is not None and too_soon_to_ask_again(
                app, analyst_turn.ANALYSIS_TURN_KIND):
            return collected
        # **Non «c'e' gia' un'analisi per oggi?», ma «ce n'e' gia' una su
        # QUESTO fondamento?»** (difetto trovato dal proprietario il
        # 20/09/2026). I resoconti che l'analista legge possono cambiare
        # durante la giornata -- un giorno recuperato da `backfill_one_report`,
        # o rifatto dopo una correzione di giudizio -- e col vecchio confronto
        # quel giorno non entrava in nessuna analisi, mai: l'analisi restava
        # quella delle 14:00 e l'indomani si analizzava l'indomani.
        #
        # Ventitre' giri su ventiquattro il fondamento e' identico e qui non
        # succede niente, come prima.
        fondamento = analyst_turn.fondamento(store.report_stamps(limit=ANALYST_DAYS))
        scritta = store.analysis(today)
        if scritta is not None and scritta.get("fondamento") == fondamento:
            return None
        if turn_in_flight(app, analyst_turn.ANALYSIS_TURN_KIND):
            return None

        from .api.handlers_mind import mind_view

        series = analyst.with_deviation(
            report.series_of_measures(store.reports(limit=ANALYST_DAYS),
                                      names=mind_view(app).device_names()))
        if not (series.get("serie") or []):
            return None

        previous = _analyst_memory(store, today, series)
        # I problemi della risposta di prima, se e' stata rifiutata (D10):
        # dal registro dei turni, la stessa riga sulle due strade.
        refused = refused_problems(app.get("usage"), ANALYST_SPECIES)
        route, _downgrade, runner = start(app, ANALYST_SPECIES)
        if route == "ponte":
            return _enqueue_analyst_turn(app, series, today, previous,
                                         refused=refused)
        if runner is None:
            logger.info("analista: nessun modello collegato, si riprova al giro dopo")
            return None

        # Gli strumenti e il guardiano li dice la dichiarazione del mestiere
        # (D5, Task 3.6): gli stessi che il ponte serve da `/api/mcp`. Il
        # guardiano porta la maschera dei nomi, che copre anche la domanda.
        declared = SPECIES[ANALYST_SPECIES]
        dispatcher = await declared.guard(app) if declared.guard else None
        presence = getattr(dispatcher, "presence", None)
        question = analyst_turn.build_question(series, previous, refused=refused,
                                               presence=presence)
        if question is None:
            return None
        answer, turn = await chain_turn(
            runner, ANALYST_SPECIES, usage=app.get("usage"),
            max_tokens=analyst_turn.MAX_ANSWER_TOKENS,
            user_message=question, system_prompt=analyst_turn.SYSTEM,
            tools=declared.catalog_for_turn() or None, dispatcher=dispatcher)
        esito = analyst_turn.apply_analysis(
            series, chain_answer(answer, turn), truncated=turn.truncated,
            previous=previous, tool_calls=turn.tool_calls, presence=presence)
        if _was_refused(esito) and not turn.truncated:
            declare_refused(app.get("usage"), turn.turn_id, esito["problemi"])
        write_analysis(app, store, today, esito)
        return esito
    except Exception as error:
        logger.warning("analista: giro fallito (%s: %s) -- si riprova al giro "
                       "dopo", type(error).__name__, error)
        return None


def _analyst_memory(store, today: str, series: dict) -> list[dict]:
    """Cio' che l'analista ha gia' detto nella sua finestra, dagli archivi
    (D4 del piano degli attori, `analyst.previous_observations`)."""
    return analyst.previous_observations(
        store.analyses(limit=ANALYST_DAYS), store.proposals(), today=today,
        series=series)


def _was_refused(esito: dict) -> bool:
    """Se il modello ha risposto e la risposta non e' passata (D10): non un
    silenzio, non un guasto del ponte -- un'analisi rifiutata coi suoi
    problemi."""
    return bool(esito.get("risposta")) and esito.get("analisi") is None


def _analyst_presence(app):
    """La maschera dei nomi sulla casa di adesso (decisione 12 estesa): quella
    che il raccoglitore rifa' per riportare i segnaposto agli id."""
    casa = app.get("home_space_store")
    return (PresenceMask(House.read(casa, app.get("entity_cache")))
            if casa is not None else None)


def _enqueue_analyst_turn(app, series: dict, day: str,
                          previous: list[dict] | None = None, *,
                          refused: list[str] | None = None) -> dict | None:
    """Accoda al piano la domanda dell'analista, e torna subito."""
    job = analyst_turn.bridge_turn(series, previous, refused=refused,
                                   presence=_analyst_presence(app))
    if job is None:
        return None
    # **Nella sveglia va il giorno**: il ponte risponde minuti dopo, da un
    # altro processo, e chi raccoglie deve sapere di QUALE giorno era la
    # domanda -- e con quali serie confrontarla.
    _job_id, deadline_min = enqueue_turn(app, ANALYST_SPECIES, {"giorno": day}, job)
    logger.info("analista: turno accodato al piano per %s (scadenza %d min)",
                day, deadline_min)
    return {"accodata": True, "giorno": day}


def _collect_analyst_turn(app, store, today: str) -> dict | None:
    """La risposta che il piano ha dato alla domanda dell'analista.

    **Un turno gia' letto non si rilegge**, e la traccia e' l'analisi stessa:
    se quel giorno ne ha gia' una, la risposta e' gia' stata applicata.

    **Le serie si rileggono adesso, non si conservano.** Il ponte risponde
    minuti dopo e potrebbe averlo fatto dopo un'aggregazione: i numeri che
    l'osservazione portera' devono essere quelli che l'archivio ha ORA, o
    direbbero una cosa che nessuno puo' piu' verificare.

    **I problemi di una risposta rifiutata si chiedono qui**: con `risposta`
    vera e `analisi` `None`, `esito["problemi"]` sono i motivi del rifiuto.
    Vivono nel turno stesso -- la risposta resta nella coda, e si rivalida a
    ogni lettura -- finche' quel turno e' l'ultimo della sua specie, cioe'
    fino all'accodamento del turno nuovo. Con `risposta` falsa (vuota, o un
    turno che il ponte ha fallito: `turn_answer`) non c'e' nessuna risposta da
    correggere.
    """
    queue = app.get("reasoning_queue")
    if queue is None:
        return None
    turn = queue.latest(analyst_turn.ANALYSIS_TURN_KIND)
    if not turn:
        return None
    # **Le due guardie che i fratelli avevano e questo no** (difetto misurato
    # sulla casa vera il 22/09/2026, sei giorni di silenzio).
    #
    # `status`: un turno ancora `pending` non ha niente da raccogliere, e
    # provarci produce l'esito finto «il modello non ha risposto» -- che a
    # valle si legge come un giro gia' fatto. `_collect_recipe_turn` pretende
    # `decided` da settimane.
    #
    # `giorno`: una risposta per un altro giorno non dice niente su oggi.
    # Il giro del proponente lo pretende da sempre.
    #
    # Perche' insieme costavano sei giorni: il turno del 17/09 era `decided`
    # con una risposta che la validazione **non poteva accettare**; una
    # risposta rifiutata non si archivia (giusto), quindi `analysis(giorno)`
    # restava `None` per sempre, quindi il raccoglitore la riapplicava a ogni
    # giro tornando `risposta: True` -- e `analyst_round` usciva li'. L'analisi
    # di oggi non veniva mai nemmeno tentata.
    #
    # **Quinta occorrenza della stessa forma**: la porta salta chi ha gia' una
    # risposta, anche quando la risposta e' rotta.
    if turn.get("status") != "decided":
        return None
    day = (turn.get("wake") or {}).get("giorno")
    if day != today or store.analysis(day) is not None:
        return None
    from .agent.runner import _bare_tool_name
    from .api.handlers_mind import mind_view

    decision = turn.get("decision") or {}
    reply = turn_answer(turn)
    # Le letture del turno, come sulla catena: `{tool, input}` col nome NUDO
    # -- il prefisso `mcp__hiris__` e' del trasporto, e si toglie al confine
    # (`runner._bare_tool_name`).
    calls = [{"tool": _bare_tool_name(c.get("tool")), "input": c.get("input")}
             for c in decision.get("tools_called") or [] if isinstance(c, dict)]
    series = analyst.with_deviation(
        report.series_of_measures(store.reports(limit=ANALYST_DAYS),
                                  names=mind_view(app).device_names()))
    # I segnaposto che il modello ha letto sul ponte tornano id dalla stessa
    # numerazione, sulla casa di adesso (come l'osservatore, decisione 12).
    esito = analyst_turn.apply_analysis(series, reply,
                                        previous=_analyst_memory(store, day, series),
                                        tool_calls=calls,
                                        presence=_analyst_presence(app))
    if _was_refused(esito):
        # L'esito sulla riga del turno del ponte (D10): il runner l'ha messa
        # nella decisione. Il raccoglitore rilegge lo stesso turno finche' non
        # ne parte un altro, e riscrivere lo stesso esito non cambia niente.
        declare_refused(app.get("usage"), decision.get("turn_id"), esito["problemi"])
    if not esito.get("risposta"):
        # Il ponte ha restituito una decisione vuota: non e' una risposta, e
        # non si scrive niente. Il giro successivo richiede.
        return esito
    write_analysis(app, store, day, esito)
    return esito


async def recipe_round(app) -> dict | None:
    """L'anello delle ricette: **«c'e' un dispositivo che pesa e non ho ancora
    capito come si misura? e allora chiedilo»** (spec §7).

    Torna il resoconto del giro, o `None` se non c'era da farlo.

    **Perche' esiste, col numero.** Il registro delle operazioni e il motore
    delle ricette sono arrivati con la fetta 4, ma nessuno scriveva ricette
    nuove: il repo ne portava una, quella del bilancio (uscita il
    01/10/2026, le ricette gia' seminate restano). Misurato sulla casa vera
    il 13/09/2026, il resoconto giornaliero avrebbe avuto **~6 misure al
    giorno** -- tutte dello stesso inverter -- contro ~28 fatti di cronaca, e
    tutti e tre gli inneschi dell'analista lavorano sulle misure.

    **Uno per volta, e non e' prudenza generica.** Trenta dispositivi che
    pesano sono trenta turni del modello: chiesti insieme, svuoterebbero da
    soli il tetto giornaliero del piano (`count_exchanges_today` contro
    `ponte.tetto_giornaliero`) e da li' in poi ogni turno -- chat compresa --
    passerebbe ai provider a pagamento. Uno per giro, ogni dieci minuti, copre trenta
    dispositivi in cinque ore e non si vede nella bolletta. E' anche la
    ragione per cui `devices_to_ask` guarda **tutti e due** i campi: un
    dispositivo che il modello non ha saputo leggere non si richiede mai piu'.

    **Dalla stessa porta dello scope**: chi risponde lo decide
    `steering.who_answers`, la stessa funzione che lo decide per la chat, per
    le promesse e per l'osservatore. Una quarta porta che nascesse domani non
    potrebbe inventarsene una quarta senza accorgersene.

    Non solleva mai: gira per sempre, e un avvio a meta' non deve fermare lo
    schedulatore.
    """
    store = app.get("observations")
    sapere = app.get("knowledge")
    home_space_store = app.get("home_space_store")
    if store is None or sapere is None or home_space_store is None:
        return None
    try:
        house = House.read(home_space_store, app.get("entity_cache"))
        collected = _collect_recipe_turn(app, sapere, house)
        if collected is not None and collected.get("risposta"):
            return collected
        # **Una risposta che non c'e' non chiude il giro**, e senza questa riga
        # la promessa scritta in `apply_recipe` -- «non consuma il colpo, il
        # giro successivo richiede» -- era falsa: il turno vecchio veniva
        # ri-raccolto ogni dieci minuti, sempre vuoto, e non se ne accodava mai
        # uno nuovo. Trovato dal vivo il 13/09/2026 alle 21:05, dieci minuti
        # dopo aver rilasciato la correzione che quella promessa la scriveva.
        if collected is not None and too_soon_to_ask_again(
                app, recipe_turn.RECIPE_TURN_KIND):
            return collected
        if turn_in_flight(app, recipe_turn.RECIPE_TURN_KIND):
            return None

        watched = {s for s, riga in (store.scope() or {}).items()
                   if riga.get("dentro")}
        to_ask = recipe_turn.devices_to_ask(sapere, house, watched)
        # **Niente da riparare ne' da chiedere: niente da leggere** (A-20,
        # Tappa 2, Task 8). Fino al 04/10/2026 l'elenco delle statistiche si
        # leggeva qui sotto a ogni passaggio, prima di sapere se servisse.
        if not to_ask and not recipe_turn.has_named_recipes(sapere, house):
            return None

        # **Quali entita' sanno produrre una serie**: serve due volte, e si
        # legge una sola (spec §6, primo «rifiuta se»), condivisa con gli
        # ingredienti del resoconto (`statistic_ids_for_round`). `None` se non
        # si e' potuto leggere, e allora non si dice niente al modello e non si
        # ripara niente.
        with_series = None
        cliente = app.get("ha_client")
        if cliente is not None:
            reading = await statistic_ids_for_round(app, cliente)
            if isinstance(reading, dict):  # la busta del guasto (D3)
                logger.info("ricette: elenco delle statistiche non letto (%s): %s",
                            reading.get("causa"), reading.get("errore"))
            else:
                with_series = reading

        # **La dashboard Energia** (piano degli attori, Task 2.2-2.3, D6, D8):
        # letta una volta per giro dell'anagrafe, e solo quando c'e' qualcosa
        # da chiedere o da riparare. Serve due volte: citata a parte nella
        # domanda, e per sapere se una ricetta e' stata scritta contro ruoli
        # che la dashboard non dichiara piu' (o non dichiarava ancora).
        dashboard = (await energy_dashboard(cliente, home_space_store, house,
                                            with_series=with_series)
                     if cliente is not None else None)

        # **La ricetta rotta si ripara QUI, nel suo giro** (attori, Task 1.6;
        # D2 del proprietario, 03/10/2026). Decide il codice, dalla causa
        # (`recipe_turn.recipes_to_repair`): un dispositivo che pesa e la cui
        # ricetta nomina un'entita' sparita, ricreata o senza statistiche, o
        # e' stata scritta contro un'altra dashboard Energia (Task 2.3), torna
        # fra quelli da chiedere, con la domanda che dice perche'. Fino al
        # 05/10/2026 la riparava solo l'attuatore, in pausa dal 01/10: nessuno.
        to_repair = {device_id: broken for device_id, broken
                     in recipe_turn.recipes_to_repair(
                         sapere, house, with_series=with_series,
                         energy=dashboard).items()
                     if set(house.entities_of(device_id)) & watched}
        if to_repair:
            logger.info("ricette: %d ricette da riparare -- %s", len(to_repair),
                        ", ".join(sorted(to_repair)))
            # Nell'ordine dell'anagrafe, su cui ruota `who_to_ask`.
            asked = set(to_ask) | set(to_repair)
            to_ask = [d for d in house.device_ids() if d in asked]
        if not to_ask:
            return None
        # A chi chiedere: **si ruota**, o un dispositivo che non risponde
        # affama tutti gli altri (vedi `recipe_turn.who_to_ask`).
        device_id, app["recipe_turn_cursor"] = recipe_turn.who_to_ask(
            to_ask, int(app.get("recipe_turn_cursor") or 0))
        if device_id is None:
            return None
        repair = to_repair.get(device_id)
        objective = store.objective()["testo"]

        route, downgrade, runner = start(app, RECIPES_SPECIES)
        if route == "ponte":
            return _enqueue_recipe_turn(app, house, device_id,
                                        objective=objective,
                                        with_series=with_series, energy=dashboard,
                                        repair=repair)
        if runner is None:
            logger.info("ricette: nessun modello a cui chiedere (%s)", downgrade)
            return None
        logger.info("ricette: chiedo come si misura «%s» (%s)%s", device_id, route,
                    " -- riparazione" if repair else "")
        esito = await recipe_turn.ask(
            runner, sapere, house, device_id, objective=objective,
            who=f"modello ({route})", when_ts=time.time(),
            with_series=with_series, energy=dashboard, repair=repair,
            measurements=app.get("usage"))
        logger.info("ricette: giro finito -- %s", esito)
        return esito
    except Exception as exc:
        logger.warning("ricette: giro fallito (%s: %s)", type(exc).__name__, exc)
        return None


def _enqueue_recipe_turn(app, house: House, device_id: str, *,
                         objective: str,
                         with_series: set[str] | None = None,
                         energy: dict | None = None,
                         repair: recipe_turn.Repair | None = None) -> dict | None:
    """Accoda al piano la domanda su un dispositivo, e torna subito."""
    job = recipe_turn.bridge_turn(objective, house, device_id,
                                  with_series=with_series, energy=energy,
                                  repair=repair)
    if job is None:
        return None
    _job_id, deadline_min = enqueue_turn(
        app, RECIPES_SPECIES,
        # **Nella sveglia va il dispositivo**: il ponte risponde minuti dopo,
        # da un altro processo, e chi raccoglie deve sapere di CHI era la
        # domanda. `submit` azzera il contesto e non la sveglia. E, per una
        # riparazione, le entita' che la risposta non puo' nominare (`None`:
        # non e' una riparazione; `[]`: lo e', per la dashboard), e la
        # dashboard contro cui la domanda e' scritta: chi raccoglie le applica
        # come la catena (`apply_recipe`, `repairing` e `written_against`).
        {"dispositivo": device_id,
         "riparare": None if repair is None else sorted(repair.silent),
         "scritta_contro": recipe_turn.written_against(house, device_id, energy)},
        job)
    logger.info("ricette: turno accodato al piano per «%s» (scadenza %d min)",
                device_id, deadline_min)
    return {"accodata": True, "dispositivo": device_id}


def _collect_recipe_turn(app, sapere, house: House) -> dict | None:
    """La risposta che il piano ha dato alla domanda su un dispositivo.

    **Un turno gia' letto non si rilegge**, e qui la traccia e' il sapere
    stesso: se il dispositivo ha gia' una ricetta o un rifiuto scritto dopo
    che il turno e' stato deciso, quella risposta e' gia' stata applicata.
    """
    queue = app.get("reasoning_queue")
    if queue is None:
        return None
    turn = queue.latest(recipe_turn.RECIPE_TURN_KIND)
    if turn is None or turn["status"] != "decided":
        return None
    device_id = (turn.get("wake") or {}).get("dispositivo")
    if not device_id:
        return None
    decided_ts = turn.get("decided_ts") or turn.get("created_ts") or 0
    # **Tutti e tre i campi**: dalla 3.46.0 una risposta puo' finire anche in
    # `ricetta_non_serve` (il rifiuto ragionato), e guardarne due su tre
    # avrebbe fatto riapplicare lo stesso turno del ponte una seconda volta.
    for campo in (recipe_turn.RECIPE_FIELD, recipe_turn.UNDERSTOOD_FIELD,
                  recipe_turn.DECLINED_FIELD):
        riga = sapere.get("dispositivo", device_id, campo)
        if riga is not None and riga.when_ts >= decided_ts:
            return None
    reply = turn_answer(turn)
    wake = turn.get("wake") or {}
    # Una sveglia di prima del 06/10/2026 porta `[]` anche fuori da una
    # riparazione: letta come riparazione, tiene la ricetta vecchia davanti a
    # una risposta storta, e un dispositivo chiesto la prima volta non ne ha.
    repairing = (None if wake.get("riparare") is None
                 else frozenset(wake["riparare"]))
    esito = recipe_turn.apply_recipe(sapere, house, device_id, reply,
                                     who="modello (ponte)", when_ts=time.time(),
                                     repairing=repairing,
                                     written_against=wake.get("scritta_contro"))
    if not esito.get("risposta"):
        # Il ponte ha restituito una decisione vuota: non e' una risposta, e
        # non si scrive niente. Il giro successivo richiede.
        return esito
    logger.info("ricette: risposta del piano applicata per «%s» -- %s",
                device_id, esito)
    return esito


#: **Gli archivi dismessi che si cancellano** (23/09/2026).
#:
#: Erano undici, dichiarati morti nel codice e annunciati a ogni avvio, e
#: restavano per sempre per una regola scritta: «mai dati utente in /data».
#: Ma quella regola era gia' stata contraddetta lo stesso giorno da noi --
#: `vault.db`, cancellato con la fetta 7 -- e il criterio vero non era mai
#: stato scritto.
#:
#: Eccolo: **un archivio che nessun codice legge piu' non e' un dato
#: dell'utente, e' un residuo.** E un residuo entra nei backup di Home
#: Assistant, che non sono cifrati se il proprietario non ci mette una
#: password: il reperto C-4 ne ha escluso il solo `claude`, e il C-6 ha
#: dichiarato la conservazione delle sette tabelle VIVE -- questi file non
#: sono tabelle di nessun archivio vivo, quindi non avevano ne' una
#: dichiarazione ne' un cancellatore.
#:
#: **`chatbots.json` NON e' in questo elenco**, per decisione del
#: proprietario: contiene il prompt personalizzato che aveva salvato sul bot
#: di default, e va guardato prima. Un residuo si cancella quando e' morto
#: **e** quando qualcuno ha deciso -- non per la sola prima meta'.
#:
#: L'elenco e' NOMINATO, mai un'euristica sul nome: un archivio vivo che
#: somigliasse a un residuo, o uno che nascera' domani, non deve poter
#: sparire per assonanza.
RESIDUI_DISMESSI = (
    "advisory.db",
    "dashboard_backups.json",
    "ha_health.json",
    "history.db",
    "history_policy.json",
    "hiris_memory.db",
    "knowledge.db",
    "portrait.db",
    "proposals.db",
    "sentinel.db",
    "tasks.json",
)


def cancella_residui(data_dir: str) -> None:
    """Cancella gli archivi dismessi, **dicendo quali e quanto erano grandi**.

    Cancellare dati di un utente in silenzio e' proibito dalle fondamenta di
    questo progetto: si dice il nome e la dimensione, non «ho fatto pulizia».

    **Un file che non c'e' non fa rumore.** La casa di chi installa oggi non
    ne ha nessuno, e una riga per ognuno a ogni avvio sarebbe rumore sano che
    seppellisce quello vero.

    Non solleva mai: e' igiene, non una condizione di funzionamento. Un
    permesso negato o un disco pieno non devono impedire a HIRIS di partire --
    stessa disciplina di `decidi_vault`.
    """
    for nome in RESIDUI_DISMESSI:
        percorso = os.path.join(data_dir, nome)
        try:
            if not os.path.exists(percorso):
                continue
            quanto = os.path.getsize(percorso)
            os.remove(percorso)
        except OSError as errore:
            logger.warning(
                "%s non si e' potuto cancellare (%s: %s): resta su disco",
                nome, type(errore).__name__, errore)
            continue
        logger.info(
            "%s cancellato (%d byte): nessun codice lo leggeva piu', e un "
            "archivio dismesso entra nei backup di Home Assistant come tutto "
            "il resto di /data.", nome, quanto)


def decidi_vault(data_dir: str) -> None:
    """Cancella `vault.db`, e dice cosa conteneva (reperto C-6, 23/09/2026).

    **Prima lo ANNUNCIAVA.** Una riga informativa all'avvio diceva che il file
    conteneva «DATI PERSONALI IN CHIARO» -- la mappa PII<->token della
    pseudonimizzazione, la cui cifratura a riposo fu rinviata e mai fatta --
    che nessun codice lo legge piu', e che cancellarlo era «una decisione
    tua». Ma una riga fra centinaia di righe di avvio non e' un modo di dire
    una cosa a una persona, e quella persona per decidere avrebbe dovuto
    aprire un file SQLite dentro il contenitore dell'add-on.

    Quindi decide HIRIS, ed e' la decisione facile: un file che nessuno legge,
    che nessuna interfaccia svuota e che contiene dati personali in chiaro e'
    solo un rischio -- tanto piu' da quando si sa che entrava nei backup.

    **Si dice cosa e' stato cancellato**, non «ho fatto pulizia»: cancellare
    dati di un utente in silenzio e' proibito dalle fondamenta di questo
    progetto. Un file vuoto se ne va senza avvisi: non c'era niente da
    raccontare, e il rumore sano seppellisce quello vero.

    Non solleva mai: e' igiene, non una condizione di funzionamento.
    """
    percorso = os.path.join(data_dir, "vault.db")
    if not os.path.exists(percorso):
        return
    righe = None
    try:
        conn = sqlite3.connect(percorso)
        try:
            righe = conn.execute("SELECT COUNT(*) FROM pii").fetchone()[0]
        finally:
            conn.close()
    except Exception as errore:
        # Corrotto, o senza la tabella che ci si aspetta: si cancella lo
        # stesso -- nessuno lo legge -- e si dice che non lo si e' potuto
        # contare, invece di affermare uno zero che nessuno ha misurato.
        logger.info("vault.db non si e' potuto leggere prima di cancellarlo "
                    "(%s: %s)", type(errore).__name__, errore)
    try:
        os.remove(percorso)
    except OSError as errore:
        logger.warning("vault.db non si e' potuto cancellare (%s: %s): resta "
                       "su disco, e contiene dati personali in chiaro",
                       type(errore).__name__, errore)
        return
    if righe:
        logger.warning(
            "vault.db cancellato: conteneva %d righe della mappa PII<->token "
            "della pseudonimizzazione, con la colonna `value` IN CHIARO (la "
            "cifratura a riposo fu rinviata e mai fatta). Nessun codice lo "
            "leggeva piu' da quando brain/privacy.py e' uscito, e nessuna "
            "interfaccia lo svuotava: restava solo a farsi copiare nei backup.",
            righe)


def _record_attempt(store, outcome: dict, *, route: str = "ponte",
                    downgrade: str = "") -> None:
    """Annota com'e' andato il tentativo, **riuscito o no**.

    Prima dell'11/09/2026 un giro fallito non lasciava traccia da nessuna
    parte: la pagina dello scope mostrava «non e' mai stata fatta», che era
    vero alla lettera -- nessuna riconsiderazione era avvenuta -- e falso come
    racconto, perche' ci si era provato quattro volte in quaranta minuti
    mentre HIRIS non registrava piu' una riga sulla casa. Un guasto non si
    appiattisce su un'assenza.

    Non si scrive in `reconsideration`: un tentativo fallito non e' una
    riconsiderazione, e metterlo li' farebbe scadere la cadenza come se la
    casa fosse stata ripensata davvero.
    """
    # **Da quale porta e' passato il giro**, e se e' stato un ripiego: senza,
    # la pagina non puo' distinguere un giro servito dal piano da uno pagato a
    # consumo, e il prelievo resta invisibile (rilievo della review
    # indipendente, 11/09/2026; regola del proprietario del 13/08/2026).
    porta = f" [{route}{', ripiego: ' + downgrade if downgrade else ''}]"
    error = outcome.get("errore")
    if error:
        store.record_attempt(outcome="non_riuscito", detail=error + porta,
                             version=read_version())
    else:
        # Il riassunto di un giro riuscito, nella lingua della pagina.
        summary = (f"{outcome.get('decise', 0)} decisioni su "
                   f"{outcome.get('candidate', 0)} entita' guardate")
        store.record_attempt(outcome="riuscito", detail=summary + porta,
                             version=read_version())


#: Quante entita' si chiedono in un turno solo. **Misurato dal vivo
#: l'11/09/2026**: 381 giudizi in una domanda sola producono ~30 KB di
#: risposta (~8.000 token) e la CLI del piano viene uccisa dal tetto di 300
#: secondi del sottoprocesso -- `claude non eseguibile: TimeoutExpired`, due
#: volte, l'ultima alle 15:44:12 esatte, 300 secondi netti dopo
#: l'accodamento. Nessun consumo registrato, perche' il turno non finisce mai.
#:
#: **Cento righe, misurate dal vivo l'11/09/2026 alle 18:13:27**: 15.852 token
#: in uscita e **2 minuti e 5 secondi** di CLI -- il primo turno
#: dell'osservatore arrivato in fondo su questa casa. Sono ~158 token a
#: entita', non i ~20 che avevo stimato: su 381 sarebbero stati ~60.000 token,
#: cioe' non un turno lento ma un muro. Il lotto non e' prudenza, e' la
#: condizione perche' la domanda abbia una risposta.
#:
#: Restano due minuti e mezzo di margine sul tetto. Non e' molto, e il numero
#: giusto dipende da quanto e' prolisso il modello: se una casa lo vedesse
#: scadere, questo e' il primo valore da abbassare.
SCOPE_BATCH = 100

#: Quanto si aspetta prima di riprovare, dopo un fallimento: `RETRY_BASE_S`,
#: che raddoppia a ogni fallimento di fila e si ferma a `RETRY_MAX_S` (vedi
#: `_retry_hold`).
RETRY_BASE_S = 600.0
RETRY_MAX_S = 6 * 3600.0


def _retry_hold(store, *, now: float) -> bool:
    """Se il freno e' tirato: **si e' appena fallito, e si aspetta**.

    Senza, un osservatore che fallisce stabilmente chiede al piano a ogni
    passaggio, per sempre -- e siccome `count_exchanges_today` conta ogni
    specie contro lo stesso tetto (`ponte.tetto_giornaliero`), **svuota
    da solo il tetto giornaliero**: da li' in poi anche la chat scende ai
    provider a pagamento. Il freno non spegne niente, rallenta: un guasto che
    passa da solo dev'essere comunque scoperto.

    Si legge dai tentativi, che sono gia' l'archivio di questo fatto: un
    contatore a parte sarebbe un doppione che il primo riavvio azzera.
    """
    # **Un aggiornamento e' un fatto nuovo.** I fallimenti di una versione
    # precedente riguardavano un altro programma, e contarli fa ritardare la
    # verifica della riparazione che li ha tolti: misurato l'11/09/2026,
    # quattro fallimenti sulla 3.27.0 hanno tenuto fermo l'osservatore per
    # ottanta minuti dopo l'aggiornamento alla 3.27.1. Le righe piu' vecchie
    # della colonna portano `None` e non contano: e' vero, non si sa su quale
    # versione siano avvenute.
    versione = read_version()
    attempts = [a for a in store.recent_attempts() if a["versione"] == versione]
    consecutive = 0
    for attempt in attempts:
        if attempt["esito"] == "accodata":
            continue
        if attempt["esito"] in ("non_riuscito", "scaduta"):
            consecutive += 1
            continue
        break
    if not consecutive:
        return False
    wait = min(RETRY_BASE_S * 2 ** (consecutive - 1), RETRY_MAX_S)
    return now - attempts[0]["quando_ts"] < wait


def _to_judge(store, candidates: list[str], last: dict | None) -> list[str]:
    """I soggetti che questa campagna deve ancora giudicare, **dal piu'
    vecchio**: prima quelli su cui nessuno ha mai deciso, poi quelli decisi
    prima che la campagna cominciasse.

    L'ordine non e' estetico: e' cio' che garantisce che quattro lotti da cento
    coprano la casa invece di ripescare sempre gli stessi.
    """
    scope = store.scope()
    mai = [c for c in candidates if c not in scope]
    vecchi = [c for c in candidates
              if c in scope and last is not None
              and (scope[c]["quando"] or 0) <= last["quando_ts"]]
    vecchi.sort(key=lambda c: scope[c]["quando"] or 0)
    return mai + vecchi


def _collect_scope_turn(app, store, house: House) -> tuple[dict | None, bool]:
    """La risposta che il piano ha dato al turno di scope, e **se si e'
    letta**: `(esito, letto)`.

    Il secondo valore non e' una comodita': distingue «non c'era niente da
    raccogliere» da «si e' raccolto e non si e' potuto usare». Il secondo caso
    chiude il passaggio -- si riprova al giro dopo, col freno -- e senza questa
    distinzione il chiamante riaccodarebbe subito, che e' il difetto che la
    review indipendente ha misurato in turni al giorno.

    **La misura viaggia nella sveglia del job.** La sonda della memoria di
    Home Assistant si cala quando la domanda parte; la riconsiderazione si
    scrive quando la risposta torna, e fra i due momenti ci sono minuti e un
    altro processo. `submit` azzera il contesto (che porta la casa intera) e
    **non** la sveglia: e' li' che il numero aspetta, invece di essere
    rimisurato -- pagando due volte una cosa che non e' cambiata -- o perso,
    lasciando una finestra «non misurata» indistinguibile da una casa che non
    ricorda niente.

    **Un turno gia' letto non si rilegge**, e il confronto e' con **due**
    tracce, non una: la riconsiderazione, che una raccolta riuscita scrive, e
    il tentativo, che si scrive in ogni caso. La seconda serve proprio quando
    la prima manca -- una risposta inservibile non produce nessuna
    riconsiderazione, quindi guardando solo quella lo stesso turno storto
    verrebbe riletto e riannotato a ogni giro, gonfiando il «sta fallendo da...»
    con tentativi fantasma tutti sulla stessa risposta (rilievo della review
    indipendente, 11/09/2026).
    """
    queue = app.get("reasoning_queue")
    if queue is None:
        return None, False
    turn = queue.latest(SCOPE_TURN_KIND)
    if turn is None or turn["status"] != "decided":
        return None, False
    last = store.last_reconsideration()
    if last is not None and last["quando_ts"] >= turn["created_ts"]:
        return None, False
    # Si guarda l'ultimo tentativo che **non** sia un accodamento: «accodata»
    # si scrive quando la domanda parte, cioe' sempre PRIMA della risposta, e
    # confrontarlo con l'istante della risposta direbbe sempre di no. Cio' che
    # risponde davvero a «questa risposta l'ho gia' letta?» e' l'esito della
    # lettura.
    decided_ts = turn.get("decided_ts")
    letti = [a for a in store.recent_attempts() if a["esito"] != "accodata"]
    if decided_ts is not None and letti and letti[0]["quando_ts"] >= decided_ts:
        return None, False
    reply = turn_answer(turn)
    wake = turn.get("wake") or {}
    lotto = wake.get("lotto")
    outcome = observer_apply_answer(
        store, house, reply,
        reason=wake.get("motivo") or "il piano ha risposto",
        window_s=wake.get("finestra_s"), cadence_s=wake.get("cadenza_s"),
        asked=set(lotto) if lotto else None,
        record=bool(wake.get("annota", True)),
        campaign_ts=wake.get("campagna_ts"))
    _record_attempt(store, outcome)
    # **Il registro degli esiti e' il solo posto in cui HIRIS osserva come si
    # comporta un fornitore davvero**, e la terza strada del piano non ci
    # finiva: la pagina Modelli non avrebbe mai saputo che l'abbonamento ha
    # servito -- o mancato -- un turno dell'osservatore (rilievo della review
    # indipendente, 11/09/2026). La chat lo fa in `_submit_chat_reply`, la
    # promessa nella rotta MCP.
    registry = app.get("occurrence_registry")
    if registry is not None:
        if "errore" in outcome:
            registry.fallimento(SUBSCRIPTION.id, family="altro", code=None,
                                message=outcome["errore"], durata_s=0.0)
        else:
            registry.successo(SUBSCRIPTION.id)
    if "errore" in outcome:
        logger.warning("osservatore: la risposta del piano non si e' potuta "
                       "usare (%s) -- si riprova al giro dopo", outcome["errore"])
        return None, True
    logger.info("osservatore: giro finito dal piano -- %s", outcome)
    return outcome, True


def _enqueue_scope_turn(app, store, house: House, *, reason: str,
                        window_s: float | None, lotto: set[str],
                        annota: bool, campagna_ts: float) -> dict:
    """Accoda al piano il turno dell'osservatore, e torna subito.

    La scadenza viene dall'ARCHIVIO (`ponte.scadenza_min`), come per la chat e
    per le promesse: quella che l'utente cambia dev'essere quella che il turno
    subisce, e una terza fonte per lo stesso numero sarebbe la terza che
    diverge.
    """
    now = time.time()
    _job_id, deadline_min = enqueue_turn(
        app, OBSERVER_SPECIES,
        # **La sveglia porta anche il LOTTO e se questo turno apre la
        # campagna.** Il ponte risponde minuti dopo, da un altro processo: chi
        # raccoglie deve sapere di che cosa era stata fatta la domanda, o non
        # potrebbe ne' accorgersi delle omissioni ne' decidere se annotare la
        # riconsiderazione. `submit` azzera il contesto e **non** la sveglia.
        {"motivo": reason, "finestra_s": window_s,
         "cadenza_s": cadence_from(window_s),
         "lotto": sorted(lotto), "annota": annota, "campagna_ts": campagna_ts},
        observer_bridge_turn(store, house, lotto, opening=annota), now=now)
    # **«Ho chiesto e sto aspettando» e' il terzo stato**, e la pagina deve
    # poterlo dire: senza, qualche minuto di attesa legittima e'
    # indistinguibili da un guasto -- che e' precisamente la confusione da cui
    # questa fetta nasce.
    store.record_attempt(when_ts=now, outcome="accodata",
                         detail=f"chiesto al piano: {reason}",
                         version=read_version())
    logger.info("osservatore: turno accodato al piano (scadenza %d min) -- %s",
                deadline_min, reason)
    return {"accodata": True}


def behavior_reader(client, mirror, home_space, ha_folder: Path | None, find_folder=None):
    """Restituisce `look()`: rilegge il comportamento da Home Assistant.

    `mirror` e' lo specchio dello stato: dice QUALI automazioni e script ci
    sono, e il loro stato (A-03, 03/10/2026); a Home Assistant si chiede solo
    il corpo.

    **Non c'e' piu' niente da sorvegliare, e per questo non e' piu' una
    sentinella.** Fino al 10/09/2026 il comportamento veniva dai due file, e
    l'unico segnale di cambiamento era il loro `mtime`: per gli script Home
    Assistant non emette ALCUN evento di ricarica, quindi due `stat()` per giro
    erano il modo piu' economico di non rileggere a vuoto. Adesso la fonte e'
    Home Assistant, e l'impronta di quei file non dice piu' niente su cio' che
    HA ha caricato -- un'automazione dentro un pacchetto non li tocca affatto.

    Quindi si rilegge e basta: **misurato il 10/09/2026, venti configurazioni
    costano 66 ms** su una connessione sola. A cinque minuti di cadenza sono
    venti secondi di traffico al giorno -- lo stesso rumore di fondo dei
    registri, che si rileggono per intero in 80 ms.

    **La cartella si cerca ancora, e per una ragione sola**: `secrets.yaml`.
    E' la dichiarazione del proprietario su cosa sia segreto, non la espone
    nessuna API, e senza di essa i corpi non si archiviano (vedi
    `home_space/redaction.py`). Finche' non c'e' la si ricerca a ogni giro:
    l'add-on puo' partire prima che il Supervisor l'abbia montata, e
    risolverla una volta sola all'avvio significherebbe restare convinti per
    sempre che non ci sia niente da leggere.

    Restituisce `True` se ha riletto, `False` se la rilettura e' fallita.
    """
    found: dict[str, Path | None] = {"folder": ha_folder}
    _find = find_folder if find_folder is not None else home_assistant_folder

    def _folder() -> Path | None:
        if found["folder"] is None:
            appeared = _find()
            if appeared:
                found["folder"] = Path(appeared)
                logger.info("cartella di Home Assistant comparsa dopo l'avvio: %s",
                            found["folder"])
        return found["folder"]

    async def look() -> bool:
        """I due inneschi -- la cadenza e l'evento di registro -- rileggono
        entrambi allo stesso modo: non c'e' un confronto da scavalcare."""
        try:
            await reread(client, mirror, home_space, _folder())
        except Exception as exc:
            logger.warning("rilettura del comportamento fallita: %s", exc)
            return False
        return True

    return look


def schedule_behavior_reread(look, delay: float = 3.0):
    """Restituisce `trigger(event_type)`: rilegge il comportamento, una
    volta sola per raffica.

    Gemello di `schedule_registry_rebuild` -- stesso antirimbalzo,
    stessa tolleranza ai guasti, stesso evento (TOPOLOGY_EVENTS, via
    `add_topology_listener`: nessun meccanismo nuovo). Aggiungere o togliere
    un'automazione cambia il registro delle entita', e questo innesco fa
    rileggere subito invece di aspettare i cinque minuti della cadenza. Non
    e' un doppione di quella: e' la differenza fra vedere la propria
    automazione nuova adesso e vederla fra cinque minuti.
    """
    state: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(delay)
            await look()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("rilettura forzata del comportamento fallita: %s", exc)

    def trigger(event_type: str) -> None:
        pending = state["attesa"]
        if pending is not None and not pending.done():
            pending.cancel()
        state["attesa"] = _spawn(_fra_poco(), name="rilettura_comportamento")

    return trigger


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
        # Adesso e' una credenziale che vive dieci minuti e vale solo per il
        # ponte. Il sottoprocesso la riceve dalle STESSE intestazioni (vedi
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
    # (`_reasoning_sweep`), l'instradamento (`steering.who_answers`), la
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


def _read_static_pages(app) -> None:
    """Sincrona di proposito: gira una volta sola all'avvio, prima che l'app
    serva qualcosa. Sta fuori dalla coroutine perche' `open()` dentro una
    funzione async e' un difetto anche quando qui non lo e' -- e una regola
    con un'eccezione «tanto lo so io» e' una regola che non vale piu'."""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    for fname, key in (("index.html", "html_index"), ("config.html", "html_config")):
        path = os.path.join(static_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                app[key] = f.read()
        except FileNotFoundError:
            logger.error("Static %s missing at %s", fname, path)
            app[key] = ""


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
FIRST_CONNECTION_CEILING_S = 10


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
        await asyncio.wait_for(ha_client.ws_ready.wait(), FIRST_CONNECTION_CEILING_S)
    if ha_client.ws_ready.is_set():
        return True
    logger.warning(
        "Home Assistant non ha confermato l'iscrizione entro %ss: leggo la casa "
        "lo stesso, e la rileggo alla prima connessione", FIRST_CONNECTION_CEILING_S)
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

    # fetta E5 Task 5: qui l'add-on installava la card Lovelace dentro Home
    # Assistant (copia in www/, file di ingress, risorsa registrata). La card
    # e' uscita dal prodotto: adesso quelle tre tracce si **tolgono**, una
    # volta, riconoscendo solo cio' che l'add-on stesso aveva messo. Vedi il
    # commento esteso su `disinstalla_card_lovelace`.
    # NON e' lo slug del Supervisor (`panel_visibility.read_own_slug`): e' il
    # nome della cartella con cui il vecchio installatore della card la copiava.
    hiris_slug = os.environ.get("HIRIS_SLUG", "hiris")
    await disinstalla_card_lovelace(
        ha_base_url,
        os.environ.get("SUPERVISOR_TOKEN", ""),
        hiris_slug,
    )

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
    # ricostruzione riscalda le parole degli stati (`prime_state_translations`
    # legge `app.get("state_translations")`: un avviso arrivato prima della
    # sua nascita, piu' sotto, lo dice e non solleva). Lo specchio si rilegge
    # alla riconnessione.
    ha_client.add_topology_listener(
        schedule_registry_rebuild(ha_client, home_space_store,
                                  then=lambda: prime_state_translations(app)))
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
    await prime_state_translations(app)

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

    # Silenzio dichiarato, stessa disciplina di advisory.db/sentinel.db/ecc.
    # (tests/test_startup_legacy_db_silence.py): un chatbots.json (o il suo
    # predecessore agents.json) di un'installazione precedente non ha piu'
    # nessun lettore/scrittore -- l'entita' Chatbot e la sua migrazione
    # (ChatbotEngine._load, chatbot_engine.py) sono uscite per intero con
    # questo task. Decisione utente (vedi il commit): il prompt
    # personalizzato eventualmente salvato sul bot di default NON viene
    # migrato in ChatSettings -- si riparte puliti, coi default nel
    # codice. I file restano su disco, intatti (mai dati utente cancellati
    # in /data).
    _chatbots_json_path = os.path.join(data_dir, "chatbots.json")
    _agents_json_path_legacy = os.path.join(data_dir, "agents.json")
    if os.path.exists(_chatbots_json_path) or os.path.exists(_agents_json_path_legacy):
        logger.info(
            "chatbots.json (o il suo predecessore agents.json) presente in %s "
            "da un'installazione precedente: da fetta E4 Task 4 nessun codice "
            "li legge ne' li scrive piu' (l'entita' Chatbot e' uscita, "
            "sostituita dalle impostazioni della chat). Il prompt "
            "personalizzato eventualmente salvato sul bot di default non "
            "viene migrato -- si riparte con i default nel codice. I file "
            "restano su disco, intatti.",
            data_dir,
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
    # Serve solo all'importazione una-tantum dei contatori di prima
    # (`usage/store.importa_legacy`): i runner non scrivono piu' su
    # questi file, e i file restano dov'erano.
    usage_path = os.environ.get("USAGE_DATA_PATH", "/data/usage.json")
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
    cancella_residui(data_dir)

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
        trigger="interval", minutes=60,
        id="hiris_mind_analyst", replace_existing=True,
        misfire_grace_time=1800,
    )

    # Il PROPONENTE (piano degli attori, Task 4.2): lo stesso battito
    # dell'analista, un giro per analisi. Il giro vive in
    # `mind/proposer_round.py`; qui c'e' solo l'iscrizione.
    scheduler.add_job(
        proposer_round, args=(app,),
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
            count = await write_day_report(app, ha_client, day=ieri, timezone=timezone)
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

    # La potatura del grezzo: senza, l'archivio dei cambi cresce per sempre.
    # Il numero di giorni non si scrive a mano -- si deriva dalla costante
    # dell'archivio (`mind/store.READING_RETENTION_S`, 22 giorni: 21
    # di promessa, il 22esimo la guardia che la rende vera al bordo), cosi'
    # la riga di log non puo' mentire quando la costante cambia
    # (task-5-correzioni.md, punto C).
    #
    # try/except proprio (task-5-fix-brief.md, punto 3): era l'unico dei tre
    # lavori del cervello senza una rete sua -- un guasto di SQLite alle tre
    # di notte finiva nel registro di apscheduler senza il prefisso
    # «cervello:», mentre i due fratelli (le condizioni, l'aggregazione) ce
    # l'hanno gia'.
    async def _prune_observations() -> None:
        try:
            count = app["observations"].prune(_time.time())
            if count:
                days = READING_RETENTION_S // 86400
                logger.info("cervello: %s cambi oltre i %s giorni sono usciti",
                            count, days)
        except Exception as error:
            logger.warning("cervello: potatura fallita (%s: %s)",
                           type(error).__name__, error)

    scheduler.add_job(
        _prune_observations,
        trigger="cron", hour=3, minute=0,
        id="hiris_mind_pruning", replace_existing=True,
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

    # Daily retention job (chat messages only -- knowledge/memory items no
    # longer expire, Task 6 "la memoria non evapora": handle_save_memory
    # stopped computing a valid_until, so purge_expired_chatbot had no more
    # work fed to it and was removed).
    #
    # Task 12: la fonte del numero di giorni non e' piu' il globale di modulo
    # `chat_store.HISTORY_RETENTION_DAYS` (uscito dal modulo) ma
    # `app["chat_settings"].retention_days` -- letto AD OGNI GIRO
    # dentro la chiusura, non catturato una volta sola all'avvio: un PUT su
    # /api/chat-settings riassegna quella chiave a caldo
    # (`handlers_settings.handle_save_settings`), e la potatura di
    # stanotte deve vedere il valore che l'utente ha scelto oggi, non quello
    # con cui l'add-on e' partito.
    from .chat_store import delete_old_messages as _delete_old_messages

    def _run_retention() -> None:
        days = app["chat_settings"].retention_days
        if days > 0:
            n = _delete_old_messages(data_dir, days)
            if n:
                logger.info("Retention: deleted %d old chat messages", n)

    scheduler.add_job(
        _run_retention,
        trigger="cron",
        hour=3,
        minute=0,
        id="hiris_retention",
        replace_existing=True,
        misfire_grace_time=3600,
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

    # ── Ponte push (Piano A): spazzata dei job scaduti senza risposta dal
    # runner remoto. Il ramo chat resta (Slice 4b): un job "chat" scaduto
    # resta semplicemente 'expired', esposto alla sua stessa route di poll.
    # fetta E3 Task 4: il ramo di fallback olistico (ragionava in locale via
    # _run_decision) e' uscito con `_holistic_reason`, l'unico produttore di
    # job kind="holistic" -- nessun job di quel tipo viene piu' accodato.
    # Silenzio dichiarato: un job kind="holistic" qui puo' arrivare SOLO da
    # un reasoning.db lasciato da un'installazione precedente questo
    # deploy -- nessun fallback locale lo ragiona piu', quindi non e' un
    # pass silenzioso: un log esplicito lo dichiara prima di lasciarlo
    # scadere (sweep_expired lo ha gia' marcato 'expired' sopra).
    async def _reasoning_sweep() -> None:
        # Lo STESSO VALORE dell'instradamento, non la stessa espressione: fino
        # alla 2.5.0 i due gate chiamavano `_bridge_active` ciascuno per conto
        # suo sugli stessi due ingressi, e il fail-safe «mai accodare in una
        # coda che nessuno spazza» reggeva sul fatto che le due chiamate
        # restassero identiche. Adesso il valore e' derivato UNA volta
        # (`_recompute_chain`) e qui si LEGGE: due letture dello stesso slot
        # non possono divergere nemmeno per distrazione. Ed e' anche cio' che
        # rende la spazzata sensibile al ponte spento dalla pagina, senza un
        # riavvio.
        if not app.get("bridge_active"):
            return
        for job in reasoning_queue.sweep_expired(_time.time()):
            if job.get("kind") == "promessa":
                # Fetta «le promesse seguono la catena» (22/08/2026): il turno
                # e' scaduto senza che il piano rispondesse. La promessa non
                # puo' restare `in_corso` -- sarebbe invisibile, e peggio di
                # una fallita: `risana()` la chiuderebbe solo al prossimo
                # riavvio, cioe' forse mai.
                _close_expired_promise(app, job)
                continue
            if job.get("kind") == SCOPE_TURN_KIND:
                # **Un turno dell'osservatore scaduto deve lasciare traccia**
                # (correzione della review indipendente, 11/09/2026). Senza,
                # l'ultimo tentativo resta «accodata» per sempre e la pagina
                # dice «in corso da N minuti» mentre il piano non rispondera'
                # mai: un worker fermo con un token buono diventa
                # indistinguibile da un'attesa legittima -- lo stesso guasto
                # appiattito su un'assenza che questa fetta esiste per togliere.
                # E' il gemello di `_close_expired_promise` qui sopra.
                store = app.get("observations")
                if store is not None:
                    attesa = max(0.0, job.get("deadline_ts", 0) - job.get("created_ts", 0))
                    store.record_attempt(
                        outcome="scaduta",
                        detail=f"il piano non ha risposto entro {attesa / 60:.0f} minuti",
                        version=read_version())
                logger.warning(
                    "osservatore: il turno %s e' scaduto senza risposta dal piano",
                    job.get("job_id"))
                continue
            if job.get("kind") == "chat":
                continue
            # Una specie dichiarata (`steering.JOB_SPECIES`) e' un turno che il
            # piano non ha fatto in tempo a servire, non un orfano: fino al
            # 06/10/2026 analisi, ricette e attuazione scadute finivano nel
            # registro come «orfano (ponte olistico rimosso)» (rapporto T0-T2
            # della Tappa 6). Orfano resta solo un tipo che nessuno dichiara
            # piu', come l'olistico di un archivio di prima della fetta E3.
            if job.get("kind") in JOB_SPECIES:
                logger.warning(
                    "reasoning sweep: il turno %s (%s) e' scaduto senza risposta "
                    "dal piano", job.get("job_id"), job.get("kind"))
            else:
                logger.warning(
                    "reasoning sweep: job %s di tipo %r orfano (ponte olistico rimosso, "
                    "fetta E3 Task 4), scartato",
                    job.get("job_id"), job.get("kind"))
        # fetta «la catena diventa l'unica verita'», Task 14. Lo sweep NON ruba
        # il lavoro al poll: `sweep_expired` guarda solo 'pending'/'claimed' e
        # non tocca i job in 'ripiego' -- e' cio' che rende sicura la
        # convivenza fra i due, visto che il ripiego vive nella rotta di poll
        # (ogni 3,5 s) e non qui (ogni 2 minuti).
        #
        # Ma un job rimasto in 'ripiego' oltre il DOPPIO della scadenza e' un
        # ripiego che si e' schiantato: il processo e' caduto mentre chiedeva
        # alla catena, e nessuno chiudera' piu' quel job. Non puo' restare in
        # volo per sempre -- `prune` cancella 'decided', 'expired' e 'failed',
        # mai 'ripiego' -- e finche' resta li' tiene anche la conversazione
        # bloccata sul 409 (`has_pending_chat` conta i ripieghi come in volo).
        # Il doppio, e non la scadenza secca, perche' il ripiego COMINCIA alla
        # scadenza: il margine e' il tempo che la catena ha per rispondere.
        reasoning_queue.fail_stuck_downgrades(
            _time.time() - 2 * 60 * bridge_deadline_min(app.get("models_config")))
        # **Le risposte consegnate si dimenticano** (reperto C-6,
        # 23/09/2026). La domanda si azzera alla consegna da sempre
        # (`submit`); la risposta restava fino alla potatura a sette giorni,
        # anche dopo che il proprietario aveva cancellato la conversazione.
        #
        # Un quarto d'ora di margine, e non zero: un ricaricamento della
        # pagina rifa' il poll sullo stesso lavoro, e una risposta svuotata
        # all'istante gli tornerebbe come «non e' arrivata in tempo». La
        # spazzata gira ogni due minuti, quindi il ritardo vero e' il margine.
        dimenticate = reasoning_queue.forget_delivered(
            before_ts=_time.time() - 15 * 60)
        if dimenticate:
            logger.info("coda del ragionamento: dimenticate %d risposte gia' "
                        "consegnate", dimenticate)
        reasoning_queue.prune(_time.time() - 7 * 86400)

    scheduler.add_job(
        _reasoning_sweep, trigger="interval", minutes=2,
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

    _usage_base, _usage_ext = os.path.splitext(usage_path)
    _usage_ext = _usage_ext or ".json"

    # I quattro contatori di prima entrano nell'archivio UNA volta sola, come
    # una riga «(prima del dettaglio)» per provider: il totale ereditato non si
    # puo' attribuire a un modello -- nessuno lo ha mai registrato -- e dirlo
    # e' meglio che spalmarlo. I file NON vengono cancellati.
    app["usage"].importa_legacy([
        usage_path,
        f"{_usage_base}_openai{_usage_ext}",
        f"{_usage_base}_openrouter{_usage_ext}",
        f"{_usage_base}_ollama{_usage_ext}",
    ], now=time.time())

    openai_runner = None
    if openai_api_key and _credentials[OPENAI.id]:
        openai_runner = OpenAICompatRunner(
            base_url="https://api.openai.com/v1",
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
    # La sincronia della voce di menu (`start_panel_sync`): puo' essere
    # ancora in attesa del nucleo. Non tiene niente da chiudere, quindi si
    # ferma e si aspetta senza tetto proprio.
    panel_sync = app.get("panel_sync_task")
    if panel_sync is not None:
        panel_sync.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await panel_sync
    if "reasoning_queue" in app:
        app["reasoning_queue"].close()
    if "home_space_store" in app:
        app["home_space_store"].close()
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


@web.middleware
async def _security_headers(request: web.Request, handler) -> web.Response:
    response = await handler(request)
    # Static assets are content-fingerprinted (?v=HASH via _inject_version), so a
    # changed file always gets a fresh URL. As defence-in-depth against the HA
    # Ingress proxy / heuristic browser caching serving a stale copy under an old
    # URL, force revalidation: "no-cache" allows storing but requires a
    # conditional request (304 when unchanged) before the cached copy is reused.
    if request.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-cache")
        # Task B8 punto 5: se il client chiede un asset con un ?v=<impronta>
        # che non corrisponde all'impronta ATTUALE di quel file, il server sa
        # in quel momento che quel client ha un guscio vecchio -- e' cosi'
        # che il difetto misurato (bottone del guscio HTML mancante mentre i
        # testi del backend erano gia' aggiornati) sarebbe stato diagnosticato
        # subito invece che scoperto un giorno dopo. Non cambia cosa viene
        # servito: il file resta quello, si aggiunge solo la riga di log.
        asked = request.query.get("v")
        if asked:
            rel_path = request.path.lstrip("/")  # "static/chat/main.js"
            attuale = _asset_fingerprint(rel_path, "")
            if attuale and asked != attuale:
                logger.warning(
                    "Asset richiesto con impronta stantia: %s (chiesta=%s, attuale=%s) "
                    "-- il client ha un guscio HTML vecchio",
                    rel_path, asked, attuale,
                )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # X-Frame-Options omesso: HA Ingress carica l'UI in un iframe
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        # **Chiusa verso l'esterno** (reperto D-7, 23/09/2026). I due domini
        # dei caratteri sono usciti insieme ai `<link>` che li chiamavano: un
        # permesso che non serve piu' e' debito, e finche' restava scritto
        # qui un foglio di stile poteva ancora arrivare da fuori.
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'self'",
    )
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


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
    app.on_startup.append(start_panel_sync)
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


_NO_CACHE = {"Cache-Control": "no-store"}

# Per-file content fingerprints for cache-busting. Keyed by asset path
# relative to the static dir; value is (mtime, short-sha1). Hashing a given
# file happens at most once per change (invalidated by mtime).
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_ASSET_FP_CACHE: dict[str, tuple[float, str]] = {}
# Matches local asset refs like  src="static/config/main.js"  /  href="static/hiris.css"
# External URLs (https://…) and query-stringed refs are left untouched.
_ASSET_REF_RE = re.compile(r'(src|href)="(static/[^"?]+\.(?:js|css))"')


def _asset_fingerprint(rel_path: str, fallback: str) -> str:
    """Return a short content hash for a static asset, cached by mtime.

    Because the fingerprint is derived from the file's actual bytes, ANY edit
    changes the query string and forces browsers (and the HA Ingress proxy) to
    re-fetch — no manual version bump required. Falls back to the app version
    string if the file can't be read (keeps old behaviour as a floor)."""
    # rel_path is like "static/config/main.js"; strip the "static/" mount prefix.
    abs_path = os.path.join(_STATIC_DIR, rel_path[len("static/"):])
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        return fallback
    cached = _ASSET_FP_CACHE.get(rel_path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        with open(abs_path, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        return fallback
    _ASSET_FP_CACHE[rel_path] = (mtime, digest)
    return digest


def _compute_build_stamp(static_dir: str) -> str:
    """Hash breve del contenuto di TUTTI gli asset frontend: cambia se e solo se
    un file del frontend cambia. Esposto in /api/health e mostrato in UI, cosi'
    si verifica CON CERTEZZA quale build sta girando davvero -- distingue
    "cache del browser/CDN" da "container addon non ricostruito" nel giro di
    live-verify (prima non c'era modo di saperlo). Deterministico: root e file
    in ordine, il path relativo entra nell'hash insieme al contenuto."""
    h = hashlib.sha1()
    try:
        for root, _dirs, files in sorted(os.walk(static_dir)):
            for name in sorted(files):
                p = os.path.join(root, name)
                rel = os.path.relpath(p, static_dir).replace(os.sep, "/")
                try:
                    with open(p, "rb") as f:
                        h.update(rel.encode("utf-8"))
                        h.update(hashlib.sha1(f.read()).digest())
                except OSError:
                    continue
    except OSError:
        return "unknown"
    return h.hexdigest()[:12]


def _inject_version(html: str, version: str, build_stamp: str = "") -> str:
    """Append a per-file content fingerprint (?v=HASH) to local static asset
    URLs so browsers bust cache whenever a file's content actually changes.

    Replaces the previous single global ?v=VERSION scheme, which only busted
    caches on a release version bump and left stale JS/CSS in place during any
    edit that didn't change config.yaml's version field.

    Task B8: se `build_stamp` e' dato, dichiara anche da quale build il guscio
    e' nato -- una `<meta name="hiris-build" content="...">` in `<head>`, col
    valore che l'app ha gia' (`app["build_stamp"]`, calcolato una sola volta in
    create_app()): questa funzione non lo ricalcola. E' la meta' che mancava
    perche' `static/chat/main.js` (e ora anche il boot della configurazione)
    potessero confrontare "da quale build sono nato" con "quale build gira
    davvero" (GET api/health) invece di limitarsi a mostrarli affiancati senza
    che nessuno li leggesse."""
    def _repl(m: "re.Match[str]") -> str:
        attr, path = m.group(1), m.group(2)
        return f'{attr}="{path}?v={_asset_fingerprint(path, version)}"'

    html = _ASSET_REF_RE.sub(_repl, html)
    if build_stamp:
        html = html.replace(
            "</head>",
            f'  <meta name="hiris-build" content="{build_stamp}">\n</head>',
            1,
        )
    return html


def _serve_shell(key: str):
    """Il gestore che serve un guscio HTML, letto all'avvio sotto `key`
    (`_read_static_pages`).

    **Una funzione per i due gusci** (C-29, Tappa 4): fino al 05/10/2026
    `_serve_index` e `_serve_config` erano la stessa funzione con la chiave
    cambiata -- due copie libere di divergere alla prima intestazione aggiunta
    a una sola."""
    async def serve(request: web.Request) -> web.Response:
        html = request.app.get(key) or ""
        if not html:
            return web.Response(text="UI not yet available", status=503)
        return web.Response(
            text=_inject_version(html, read_version(), request.app.get("build_stamp", "")),
            content_type="text/html",
            headers=_NO_CACHE,
        )
    return serve



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
