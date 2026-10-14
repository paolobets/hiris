"""Il **governo del ponte**: se il ponte e' acceso, se il suo lavoratore deve
girare, e la catena che la pagina Modelli rimette in vigore a caldo.

Spostato da `server.py` senza una riga di logica cambiata (Chiusura dello
sprint, F8 passo 6, 14/10/2026): `server.py` registra e avvia, non ospita.
"""
import asyncio
import logging
import os
import time

from ..background import spawn as _spawn
from ..providers import (
    OLLAMA,
    SUBSCRIPTION,
    can_answer_now,
    providers_in_chain,
    subscription_has_token,
)
from ..usage.bridge_loads import _registra_turno_ponte

logger = logging.getLogger(__name__)


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
        from ..usage.bridge_loads import BRIDGE_LOADS_KEY
        from . import runner as _agent_runner

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
        from ..api.credenziali import credenziale_ponte_viva
        from ..reasoning.consegna import consegna

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
        from ..api.credenziali import revoca

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
