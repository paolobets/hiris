# hiris/app/server.py
import os

from aiohttp import web

from .action.installation import start_installation
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
from .api.shell import _STATIC_DIR, _compute_build_stamp, _security_headers, _serve_shell
from .chat_thread import SyncTurnsInFlight
from .provider_occurrences import OccurrenceRegistry
from .startup import _on_cleanup, _on_startup


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

    static_path = _STATIC_DIR
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



