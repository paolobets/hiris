"""L'**avvio** e la **chiusura** dell'add-on: cio' che `create_app` aggancia a
`on_startup` e `on_cleanup`, e i due pezzi d'avvio con nome (il sapere, la
prima connessione a Home Assistant).

Spostato da `server.py` senza una riga di logica cambiata (Chiusura dello
sprint, F8 passo 1, 14/10/2026): `server.py` registra e avvia, non ospita.
"""
import asyncio
import contextlib
import logging
import os
import time
from functools import partial
from pathlib import Path

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .action.actuator import ACTUATOR_KEY, ActionActuator
from .action.construction.revisions import CONSTRUCTIONS_KEY, ConstructionStore
from .action.construction.workshop import WORKSHOP_KEY, Workshop
from .action.installation import INSTALLATION_TASK_KEY
from .action.journal import JOURNAL_KEY, Journal
from .action.registry import SERVICE_REGISTRY_KEY, ServiceRegistry
from .agent.bridge_governor import (
    AGENT_WORKER_TASK_KEY,
    RECOMPUTE_CHAIN_KEY,
    _bridge_notices,
    _recompute_chain,
)
from .api.handlers_config import THEME_KEY
from .api.middleware_internal_auth import INGRESS_CIDRS_KEY
from .api.servizi import SERVICES_KEY
from .api.shell import _read_static_pages
from .chat_settings import CHAT_SETTINGS_KEY, ChatSettings, file_lacks_retention_days
from .chat_store import CHAT_STORE_KEY
from .chat_store import open_store as open_chat_store
from .claude_runner import CLAUDE_RUNNER_KEY
from .conservazione import (
    accantona_archivi,
    cancella_residui,
    decidi_vault,
    nightly,
    reasoning_sweep,
)
from .home_space import historian
from .home_space.behavior import reread_dashboards
from .home_space.historian import house_timezone
from .home_space.house_history import STATISTIC_IDS_HELD_KEY, STATISTIC_IDS_LOCK_KEY
from .home_space.reader import HOME_SPACE_KEY, HomeSpace, house_timezone_of
from .home_space.redaction import home_assistant_folder
from .home_space.registry_follower import schedule_registry_rebuild
from .home_space.rounds import (
    HA_INTEGRATIONS_KEY,
    HA_PROBLEMS_KEY,
    TREE_COMPARISON_KEY,
    behavior_reader,
    integration_follower,
    reload_entity_inventory,
    reread_ha_problems,
    schedule_behavior_reread,
    schedule_dashboards_reread,
    tree_comparison_round,
)
from .home_space.topology import rebuild
from .home_space.type_vocabulary import REPO_JUDGMENTS
from .keeper.delivery import NOTICES_WRITTEN_KEY, forget_written
from .keeper.exchange import interpreta_promise
from .keeper.store import AGENDA_KEY, AgendaStore
from .keeper.sweeper import SWEEPER_KEY, Sweeper, _promise_delivery
from .live_value import LiveValue
from .llm_router import LLM_ROUTER_KEY
from .memory.store import MEMORY_STORE_KEY, MemoryStore
from .mind import automate_turn, proposer_round, report
from .mind.analyst_round import analyst_round
from .mind.conditions_round import (
    TRACE_CURSORS_KEY,
    TRACE_UNRESOLVED_KEY,
    TRACES_BOOT_TS_KEY,
    watch_automation_outcomes,
    watch_system_conditions,
)
from .mind.day_report import (
    BACKFILL_QUIET_KEY,
    LAST_REPAIR_KEY,
    backfill_one_report,
    reaggregate_last_two_days,
    write_day_report,
)
from .mind.judgments import TYPE_JUDGMENTS_KEY, TYPE_JUDGMENTS_STATUS_KEY, build_judgments
from .mind.knowledge import KNOWLEDGE_KEY, KnowledgeStore
from .mind.observer_round import hold_watcher_statistic_ids, reconsideration_round
from .mind.proposal_redo import CHAIN_IN_FLIGHT
from .mind.proposer_round import proposer_beat
from .mind.realignment import disconnection_recorder, mirror_reload_listener
from .mind.recipe_round import RECIPE_CURSOR_KEY, recipe_round
from .mind.reconciliation import after_rebuild
from .mind.seed import REPO_PRIORITY, attribute_seed, judgment_seed, meaning_seed
from .mind.state_words import prime_state_translations
from .mind.store import OBSERVATIONS_KEY, ObservationsStore
from .mind.watcher import WATCHER_KEY, Watcher
from .models_store import MODELS_CONFIG_KEY
from .provider_occurrences import OCCURRENCES_KEY
from .providers import (
    CLAUDE,
    CLAUDE_CREDENTIAL_KEY,
    LOCAL_MODEL_URL_KEY,
    OLLAMA,
    OPENAI,
    OPENAI_CREDENTIAL_KEY,
    OPENROUTER,
    OPENROUTER_CREDENTIAL_KEY,
    SUBSCRIPTION,
    can_answer_at_startup,
    credentials_present,
    outside_chain,
    providers_in_chain,
)
from .proxy.entity_cache import ENTITY_CACHE_KEY, EntityCache
from .proxy.ha_client import HA_CLIENT_KEY, HAClient
from .proxy.state_translations import STATE_TRANSLATIONS_KEY, StateTranslations
from .reasoning.consegna import SUBMIT_CHAT_REPLY_KEY, _chat_reply_submitter
from .reasoning.queue import REASONING_QUEUE_KEY
from .steering import BRIDGE_ACTIVE_KEY, MODEL_CHAIN_KEY
from .storage import DATA_DIR_KEY
from .usage.store import USAGE_KEY

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
SCHEDULER_KEY = web.AppKey("scheduler")

logger = logging.getLogger(__name__)


def _open_knowledge(app, data_dir: str) -> None:
    """Apre il sapere, lo semina e costruisce l'istantanea dei giudizi.

    **Il file e' `sapere.db`, NON `knowledge.db`**: quel nome era occupato
    su disco da un archivio documentale morto, che oggi l'avvio cancella
    (`conservazione.RESIDUI_DISMESSI`). Vedi il docstring di `mind/knowledge.py`.

    Il seme del repo scrive solo cio' che ancora non c'e': la casa scrive
    sopra, e un riavvio non cancella cio' che ha imparato.

    **Se aprire o seminare solleva, l'add-on parte lo stesso** (decisione del
    proprietario, 17/09/2026; spec 2026-09-16 §8): l'errore si logga, l'archivio
    aperto a meta' si chiude, `app[KNOWLEDGE_KEY]` resta `None` e l'istantanea
    si costruisce dal solo seme, col `perche` che porta l'errore vero -- e
    `/api/health` lo mostra. Ogni lettore di `app[KNOWLEDGE_KEY]` regge `None`:
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
        app[KNOWLEDGE_KEY] = None
        judgments, status = build_judgments(None, unavailable_reason=reason)
        app[TYPE_JUDGMENTS_KEY].set(judgments)
        app[TYPE_JUDGMENTS_STATUS_KEY].set(status)
        return
    if seeded:
        logger.info("sapere: %d righe del seme scritte (le altre c'erano gia')", seeded)
    app[KNOWLEDGE_KEY] = knowledge
    judgments, status = build_judgments(knowledge)
    app[TYPE_JUDGMENTS_KEY].set(judgments)
    app[TYPE_JUDGMENTS_STATUS_KEY].set(status)


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


def mark_triggered_automation(app, event_data: dict) -> None:
    if not isinstance(event_data, dict):
        return
    entity_id = event_data.get("entity_id")
    if isinstance(entity_id, str):
        app[WATCHER_KEY].mark_automation(entity_id)


async def reload_inventory_job(app, ha_client) -> None:
    await reload_entity_inventory(app.get(ENTITY_CACHE_KEY), ha_client)


async def reread_problems_job(app, ha_client) -> None:
    await reread_ha_problems(app, ha_client)


async def reread_state_translations_job(app) -> None:
    await prime_state_translations(app)


async def conditions_job(app, ha_client) -> None:
    try:
        await watch_system_conditions(app, ha_client)
        await hold_watcher_statistic_ids(app, ha_client)
    except Exception as exc:
        logger.warning(
            "cervello: giro delle condizioni di sistema fallito (%s: %s)",
            type(exc).__name__, exc)


async def automation_traces_job(app, ha_client) -> None:
    try:
        await watch_automation_outcomes(app, ha_client)
    except Exception as exc:
        logger.warning(
            "cervello: giro delle tracce di automazione fallito (%s: %s)",
            type(exc).__name__, exc)


async def reconsideration_job(app, ha_client) -> None:
    await reconsideration_round(app, ha_client)


async def recipes_job(app) -> None:
    await recipe_round(app)


async def report_backfill_job(app, ha_client) -> None:
    try:
        await backfill_one_report(app, ha_client)
    except Exception as error:
        logger.warning(
            "cervello: recupero dei resoconti fallito (%s: %s) -- "
            "si riprova al giro dopo", type(error).__name__, error)


async def analyst_job(app) -> None:
    await analyst_round(app)


async def nightly_aggregation_job(app, ha_client) -> None:
    try:
        # `timezone`/`ieri` DENTRO il try: se il loro calcolo sollevasse
        # FUORI da qui il warning contestualizzato non partirebbe --
        # l'eccezione finirebbe nel registro di apscheduler senza il
        # prefisso «cervello:», e la notte salterebbe in silenzio.
        timezone = house_timezone_of(app)
        ieri = historian.resolve_day("ieri", timezone)
        # **IL RESOCONTO** (spec §9), per la strada unica: la notte
        # rifa' ieri anche se c'e' gia'.
        count = await write_day_report(app, ha_client, day=ieri, timezone=timezone,
                                       when_ts=time.time())
        logger.info("cervello: %s voci di cronaca per %s", count, ieri)
    except Exception as error:
        logger.warning("cervello: aggregazione notturna fallita (%s: %s)",
                       type(error).__name__, error)


async def sweeper_interpret(app, promise: dict) -> dict:
    return await interpreta_promise(app, promise)


async def keeper_heartbeat_job(app) -> None:
    await app[SWEEPER_KEY].batti(time.time())


# Il modello per provider, come LETTURA e non come valore. È la metà
# nascosta del difetto peggiore trovato dal progetto: fino alla 2.4.1 qui
# si leggeva `provider_models` UNA volta e lo si passava ai runner come
# argomento di costruzione, mentre `api/handlers_chat._enqueue_chat_job`
# rilegge `app[MODELS_CONFIG_KEY]` a OGNI turno -- quindi lo stesso valore
# aveva effetto immediato sul ponte e solo al riavvio sull'API, e la pagina
# ne dichiarava uno solo (invariante 4: «un valore si applica in un modo
# solo»). La lettura chiude su `app`, non su un valore: `models_config` è
# SOSTITUITO a ogni PUT (`handle_save_models_config`, col `set` del suo
# `LiveValue`), quindi la lettura vede sempre l'ultimo archivio, e la
# sostituzione del dizionario intero è ciò che rende la lettura atomica --
# un turno non può mai vedere metà di un salvataggio.
def model_reader(app, provider: str):
    def read() -> str:
        return (app[MODELS_CONFIG_KEY].value
                .get("provider_models", {}).get(provider, ""))
    return read


def local_model(app) -> str:
    """Il modello di Ollama non vive in `provider_models` (è un fantasma
    lì: `_clean_provider_models` lo scarta in lettura e in scrittura): la
    sua unica casa è `models_config["ollama"]["modello"]`."""
    return app[MODELS_CONFIG_KEY].value.get(OLLAMA.id, {}).get("modello", "")


def reapply_chain(app) -> None:
    _recompute_chain(app)


def live_values() -> dict:
    """Cio' che le rotte, i giri e il ponte cambiano dopo l'avvio, appena nato:
    `create_app` lo mette nell'app mentre si compone (X-31, Chiusura dello
    sprint).

    aiohttp congela l'app quando l'avvio finisce, e da li' scrivere in
    `app[...]` e' deprecato (un errore in aiohttp 4). Fino al 14/10/2026
    queste chiavi si riscrivevano a richiesta servita o a giro gia' partito:
    adesso l'app porta dall'inizio un `LiveValue` (o il contenitore che si
    modifica sul posto), e chi le cambia chiama `set` -- anche l'avvio, che
    ci mette i valori letti da disco. Il valore iniziale e' quello che i
    lettori davano all'assenza della chiave. Ogni chiamata ne fa di nuovi:
    due app non condividono mai un contenitore."""
    values = {key: LiveValue(initial) for key, initial in (
        (MODELS_CONFIG_KEY, {}), (CHAT_SETTINGS_KEY, ChatSettings()),
        (TYPE_JUDGMENTS_KEY, REPO_JUDGMENTS), (TYPE_JUDGMENTS_STATUS_KEY, None),
        (BRIDGE_ACTIVE_KEY, False), (MODEL_CHAIN_KEY, []), (AGENT_WORKER_TASK_KEY, None),
        (HA_PROBLEMS_KEY, None), (HA_INTEGRATIONS_KEY, None), (TREE_COMPARISON_KEY, None),
        (automate_turn.IN_FLIGHT, None), (proposer_round.IN_FLIGHT, False),
        (RECIPE_CURSOR_KEY, 0), (LAST_REPAIR_KEY, None), (STATISTIC_IDS_HELD_KEY, None))}
    values[STATISTIC_IDS_LOCK_KEY] = asyncio.Lock()
    values[TRACE_CURSORS_KEY] = {}
    values[NOTICES_WRITTEN_KEY] = {}
    values[TRACE_UNRESOLVED_KEY] = set()
    values[CHAIN_IN_FLIGHT] = set()
    return values


async def _on_startup(app: web.Application) -> None:
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
    app[DATA_DIR_KEY] = data_dir
    # La pulizia totale del 23/10/2026 (`conservazione.accantona_archivi`):
    # QUI, prima che qualunque archivio si apra -- `sapere.db` si apre poche
    # righe sotto. Codice a scadenza: esce nella release dopo.
    accantona_archivi(
        data_dir, attiva=os.environ.get("HIRIS_PULIZIA_TOTALE", "") == "true")
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
    app[INGRESS_CIDRS_KEY] = [str(r) for r in _reti]
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
    app[HA_CLIENT_KEY] = ha_client

    # Cosa Home Assistant sa fare, in questa casa. Costruito vuoto: si carica
    # al primo uso (`ensure_fresh`), non all'avvio -- un caricamento qui
    # allungherebbe il boot per una cosa che potrebbe non servire in questa
    # sessione, e fallirebbe in silenzio se HA non fosse ancora pronto.
    app[SERVICE_REGISTRY_KEY] = ServiceRegistry()

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
    app[ENTITY_CACHE_KEY] = entity_cache

    # L'anagrafe nasce qui, vuota, e non piu' accanto alla sua prima
    # lettura (piu' sotto): l'iscrizione alle integrazioni le consegna le
    # voci appena il websocket si apre, e l'ascoltatore deve esserci prima.
    # Finche' la prima ricostruzione non e' riuscita le tiene solo in
    # `app[HA_INTEGRATIONS_KEY]` (`HomeSpace.hold_integrations`).
    home_space_store = HomeSpace(data_dir, mirror=entity_cache)
    app[HOME_SPACE_KEY] = home_space_store
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
        mirror_reload_listener(ha_client, entity_cache, lambda: app.get(WATCHER_KEY)))
    ha_client.add_disconnection_listener(disconnection_recorder(lambda: app.get(WATCHER_KEY)))
    ha_client.add_disconnection_listener(forget_written(app))
    # L'ultimo riavvio di Home Assistant, accanto a ogni `ultimo_cambio`.
    ha_client.add_disconnection_listener(home_space_store.hold_restart)
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
    _service_registry = app[SERVICE_REGISTRY_KEY]
    ha_client.add_service_listener(lambda _type: _service_registry.invalidate())

    await _open_websocket(ha_client)

    try:
        await entity_cache.load(ha_client)
    except Exception as exc:
        logger.warning("EntityCache load failed: %s", exc)

    # Come si RENDE uno stato di Home Assistant (fetta «lo stato»,
    # 07/09/2026). Costruito vuoto, come il registro dei servizi qui sopra, e
    # **scaldato piu' sotto** (`prime_state_translations`, subito dopo
    # `app[HOME_SPACE_KEY]`, che e' dove la lingua della casa diventa
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
    app[STATE_TRANSLATIONS_KEY] = StateTranslations(ha_client)

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
    app[OBSERVATIONS_KEY] = ObservationsStore(
        os.path.join(data_dir, "osservazioni.db"))
    # La quiete del recupero delle cronache (`BACKFILL_QUIET_S`): nasce qui,
    # prima che aiohttp congeli l'app, perche' il giro la usa ad app avviata.
    app[BACKFILL_QUIET_KEY] = {}
    # Il sapere e' nato piu' sopra, prima della cache delle entita'.
    # L'osservatore riceve il sapere: da li' legge **quali attributi valga la
    # pena tenere** per un tipo (spec §5.4). Senza, scriverebbe come prima e
    # l'esempio fondativo del cervello -- «il riscaldamento parte alle 15:30,
    # la casa e' calda alle 16:30» -- resterebbe non rispondibile.
    app[WATCHER_KEY] = Watcher(app[OBSERVATIONS_KEY], knowledge=app[KNOWLEDGE_KEY])
    # Rilegge dall'archivio le condizioni di sistema gia' aperte prima di
    # QUESTO avvio (task-5-correzioni.md, punto B): senza, ogni riavvio
    # dell'add-on -- che succede a ogni aggiornamento -- riscriverebbe
    # "aperto" per ogni guasto gia' aperto, come se fosse nato in quel
    # momento, e l'oggetto «guasto» perderebbe la sua unica informazione
    # utile: da quando dura. **Prima** del primo giro delle condizioni, qui
    # sotto. Non solleva mai (vedi il suo docstring).
    app[WATCHER_KEY].rebuild_conditions()
    # LO STESSO rubinetto che alimenta lo specchio, non un secondo: due
    # sorgenti degli stessi eventi sarebbero due cose che possono divergere.
    # Si aggancia DOPO lo specchio: se un giorno l'ordine contasse, conta che
    # lo specchio sia aggiornato prima.
    ha_client.add_state_listener(app[WATCHER_KEY].watch_reading)

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
    app[TRACES_BOOT_TS_KEY] = time.time()

    # L'evento delle automazioni (Task 4 di «le tracce e il log»,
    # AUTOMATION_TRIGGERED_EVENT in `proxy/ha_client.py`): segna soltanto,
    # non scrive -- vedi il docstring di `Watcher.mark_automation` per il
    # perche'. Il glue e' qui e non un metodo di `Watcher` apposta:
    # l'interfaccia che questo task produce e' `mark_automation(entity_id)`
    # -- estrarre `entity_id` dal dizionario grezzo dell'evento e' cablaggio
    # di questo file, non un giudizio dell'osservatore. Il nome che l'evento
    # porta non si tiene (A-18): lo dice la casa all'esito.
    ha_client.add_automation_listener(partial(mark_triggered_automation, app))

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
    app[JOURNAL_KEY] = Journal(os.path.join(data_dir, "azioni.db"))

    # L'archivio delle promesse (`keeper/store.py`): l'unica casa di
    # «cosa e quando». Nasce qui, accanto alla cronaca -- i due archivi nuovi
    # di questo cablaggio. La legge sia la chat (via
    # `create_tool_dispatcher`, per `promise`/`agenda`/`cancel`)
    # sia lo schedulatore -- l'orologio, montato piu' sotto insieme al
    # battito, perche' gli serve prima lo scheduler, costruito piu' avanti in
    # questa funzione.
    app[AGENDA_KEY] = AgendaStore(os.path.join(data_dir, "promesse.db"))

    # L'unico punto del prodotto che esegue qualcosa su Home Assistant
    # (`action/actuator.py`). Sta QUI, e non accanto a `service_registry` piu'
    # sopra, per l'ordine: la porta ha bisogno dello specchio dello stato
    # (`entity_cache`) per rileggere dopo aver agito, e sopra la cache non
    # esiste ancora -- `app.get("entity_cache")` avrebbe dato `None` e la
    # porta avrebbe rifiutato OGNI azione con «non vedo lo stato di questa
    # casa», per sempre. Costruita una volta e condivisa: la chat la usa oggi
    # via `create_tool_dispatcher`, lo schedulatore e il brain
    # domani, senza che ne nasca una seconda.
    app[ACTUATOR_KEY] = ActionActuator(ha_client, app[SERVICE_REGISTRY_KEY],
                                      app.get(ENTITY_CACHE_KEY), app[JOURNAL_KEY],
                                      home_space_store=app.get(HOME_SPACE_KEY))

    # L'archivio delle costruzioni e l'officina (fetta «costruire»,
    # docs/design/2026-08-22-costruire-in-home-assistant.md). Nascono QUI e non
    # piu' in alto per l'ordine: l'officina riceve la cronaca (che nasce sopra)
    # e il canale HA. Non riceve la porta e non la usa: sono due canali di
    # scrittura diversi -- «un canale, una porta», spec §2.1 -- e l'officina
    # non chiama mai un servizio.
    app[CONSTRUCTIONS_KEY] = ConstructionStore(
        os.path.join(data_dir, "costruzioni.db"))

    app[WORKSHOP_KEY] = Workshop(
        ha_client, app[CONSTRUCTIONS_KEY], app[JOURNAL_KEY],
        read_timezone=lambda: house_timezone_of(app))

    # L'archivio dei modelli si legge prima di costruire `LLMRouter`, piu' sotto:
    # la catena si compone da `chain_order`.
    from .models_store import load_models_config
    # Qui c'era la semina delle opzioni dell'add-on (`options_migration.seed`):
    # copiava nell'archivio, una volta sola, sette valori che arrivavano
    # dall'ambiente. Dalla 3.0.0 `run.sh` non li esporta piu', e sulla casa la
    # copia e' avvenuta da tempo (misurato il 02/10/2026: `seminato` vero).
    # L'archivio e' la sola fonte, e i campi che non ha partono dai
    # predefiniti di `load_models_config`.
    app[MODELS_CONFIG_KEY].set(load_models_config(data_dir))

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
    # **QUI, dopo `app[HOME_SPACE_KEY]` e dopo `rebuild`**: la riparazione
    # chiede all'anagrafe il fuso della casa e i dispositivi di cui cercare le
    # ricette. Chiamata prima lavorerebbe in UTC e su una casa vuota, mentre
    # l'aggregazione notturna (`nightly_aggregation_job`, qui sopra nel modulo) lavora col fuso
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

    app[USAGE_KEY] = UsageStore(
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
    app[MEMORY_STORE_KEY] = memory_store

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
    app[CHAT_SETTINGS_KEY].set(chat_settings)
    # L'archivio della chat, come gli altri (D-27): la finestra la legge dalle
    # impostazioni a ogni potatura, perche' la pagina la cambia a caldo.
    app[CHAT_STORE_KEY] = open_chat_store(
        data_dir, read_retention_days=lambda: app[CHAT_SETTINGS_KEY].value.retention_days)

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
    app[SCHEDULER_KEY] = scheduler

    app[THEME_KEY] = os.environ.get("THEME", "auto")

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
    app[CLAUDE_CREDENTIAL_KEY] = api_key
    app[OPENAI_CREDENTIAL_KEY] = openai_api_key
    app[OPENROUTER_CREDENTIAL_KEY] = openrouter_api_key
    app[LOCAL_MODEL_URL_KEY] = local_model_url

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
    # `app[BRIDGE_ACTIVE_KEY]` poteva dire True mentre `ponte.attivo`, cioe' cio'
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
    scheduler.add_job(
        reload_inventory_job, args=(app, ha_client),
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
    scheduler.add_job(
        reread_problems_job, args=(app, ha_client),
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
    scheduler.add_job(
        reread_state_translations_job, args=(app,),
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
    # problemi li prende da `app[HA_PROBLEMS_KEY]`, che `hiris_ha_problems` qui
    # sopra rilegge ogni cinque minuti (A-02).
    scheduler.add_job(
        conditions_job, args=(app, ha_client),
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
    scheduler.add_job(
        automation_traces_job, args=(app, ha_client),
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
    scheduler.add_job(
        reconsideration_job, args=(app, ha_client),
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
    scheduler.add_job(
        recipes_job, args=(app,),
        trigger="interval", minutes=10,
        id="hiris_mind_recipes", replace_existing=True,
        misfire_grace_time=600,
    )

    # L'anello dell'analista: legge le misure di molti giorni e dice cosa si
    # potrebbe fare (spec §10). Ogni ora, non ogni dieci minuti: la domanda
    # pesa ~35.000 token -- misurato sulla casa vera il 15/09/2026, venti
    # giorni e 146 serie -- e un giorno ha UNA analisi sola. Quando ce l'ha,
    # il giro non fa niente e non lo dice.
    scheduler.add_job(
        analyst_job, args=(app,),
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
    scheduler.add_job(
        report_backfill_job, args=(app, ha_client),
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
    scheduler.add_job(
        nightly_aggregation_job, args=(app, ha_client),
        trigger="cron", hour=report.NIGHTLY_HOUR, minute=report.NIGHTLY_MINUTE,
        id="hiris_mind_aggregation", replace_existing=True,
        misfire_grace_time=3600,
    )

    # La conservazione: un lavoro solo, alle 03:00, per tutti gli archivi
    # (`conservazione.nightly`).
    scheduler.add_job(
        nightly, args=(app,),
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
        app[AGENDA_KEY].risana(now=time.time())
    except Exception as exc:
        logger.warning("risanamento delle promesse in sospeso fallito: %s", exc)

    # Fetta «costruire»: le proposte rimaste `in_corso` da un riavvio a meta'.
    # Come per le promesse, si chiude PRIMA che qualcuno possa applicarne una
    # nuova -- una riga rivendicata e mai conclusa non e' piu' toccabile da
    # nessuna `apply`, e resterebbe un fantasma fino alla potatura.
    try:
        app[CONSTRUCTIONS_KEY].risana(now=time.time())
    except Exception as exc:
        logger.warning("risanamento delle costruzioni in sospeso fallito: %s", exc)

    # L'orologio (`keeper/sweeper.py`): non conosce ne' la chat ne' il
    # modello, riceve solo `execute` (la porta unica, costruita sopra) e
    # `interpreta` (il turno di `chiedi`, `keeper/exchange.py`).
    # `interpreta_promise` prende DUE argomenti (`app`, `promessa`); l'orologio
    # chiama `interpreta(promessa)` con uno solo -- `partial(sweeper_interpret,
    # app)` gli lega il primo.
    # Fetta «il seguito delle chat divise» (spec 2026-09-26 §2.4): l'esito
    # torna a chi l'ha chiesta -- il recapito, la riga nel filo e il soffitto
    # riletto al risveglio (`_promise_delivery`, qui sopra nel modulo).
    app[SWEEPER_KEY] = Sweeper(
        app[AGENDA_KEY],
        execute=app[ACTUATOR_KEY].execute,
        interpreta=partial(sweeper_interpret, app),
        **_promise_delivery(app),
    )

    # Quindici secondi, battito FISSO: la verita' e' la tabella, non un timer
    # per promessa. Un battito fisso non si perde se l'ora di sistema salta
    # (NTP, ora legale), e `misfire_grace_time` corto perche' un battito perso
    # lo rimpiazza quello dopo: e' la tolleranza dello SCHEDULATORE (120 s,
    # spec §7, `TOLLERANZA_S`) a decidere cosa e' troppo tardi, non APScheduler.
    scheduler.add_job(
        keeper_heartbeat_job, args=(app,),
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
    app[REASONING_QUEUE_KEY] = reasoning_queue

    app[SUBMIT_CHAT_REPLY_KEY] = _chat_reply_submitter(app, data_dir)

    # La spazzata della coda del ponte: `conservazione.reasoning_sweep`.
    scheduler.add_job(
        reasoning_sweep, args=(app,), trigger="interval", minutes=2,
        id="hiris_reasoning_sweep", replace_existing=True, misfire_grace_time=120)

    # Il punto di cablaggio -- da qui `handle_chat` sa se instradare il turno
    # sul ponte -- NON e' piu' qui: e' `_recompute_chain`, l'unica riga del
    # prodotto che scrive `app[BRIDGE_ACTIVE_KEY]`, e viene chiamata sia all'avvio
    # (`reapply_chain`, piu' sotto) sia a ogni salvataggio della pagina
    # Modelli. Doveva spostarsi: il valore viene adesso dall'archivio, che la
    # pagina riscrive, e un cablaggio fatto una volta all'avvio avrebbe
    # riprodotto per il ponte il difetto che il Task 10 ha chiuso per la
    # catena -- salvataggio accettato con 200, effetto solo al riavvio.
    #
    # `steering._bridge_on` verifica soltanto che `app[REASONING_QUEUE_KEY]`
    # sia agganciata -- e in produzione lo e' sempre, perche' la coda si crea
    # incondizionatamente piu' su -- quindi da sola non dice che
    # qualcuno reclami o spazzi quei job. E' `app[BRIDGE_ACTIVE_KEY]` a dirlo:
    # tenere il gate li', invece di insegnare l'archivio a `_bridge_on`, lascia
    # ai test la possibilita' di agganciare o sganciare la
    # coda senza toccare la configurazione.

    # Il modello di Ollama, dalla SUA UNICA CASA. Fino alla 2.4.1 veniva da
    # `LOCAL_MODEL_NAME`, cioè da un'opzione dell'add-on: era il modello messo
    # dove si custodiscono le credenziali invece che dove si prendono le
    # decisioni, e `provider_models["ollama"]` restava un fantasma
    # (`_PROVIDER_MODEL_KEYS` non lo contiene, `_clean_provider_models` lo
    # scarta in lettura E in scrittura -- e resta così: NON è un doppione da
    # far rivivere).
    _ollama_model = (app[MODELS_CONFIG_KEY].value.get(OLLAMA.id) or {}).get("modello", "")
    _risponde = can_answer_at_startup(_credentials, app[MODELS_CONFIG_KEY].value)

    claude_runner = None
    if api_key and _credentials[CLAUDE.id]:
        claude_runner = ClaudeRunner(
            api_key=api_key,
            read_model=model_reader(app, CLAUDE.id),
            log_usage=app[USAGE_KEY].log,
        )

    # I quattro contatori di prima entrano nell'archivio UNA volta sola, come
    # una riga «(prima del dettaglio)» per provider: il totale ereditato non si
    # puo' attribuire a un modello -- nessuno lo ha mai registrato -- e dirlo
    # e' meglio che spalmarlo. Stanno nella cartella dei dati: fino
    # all'08/10/2026 il primo si leggeva da `USAGE_DATA_PATH`, una variabile
    # che `run.sh` non esportava (D6 della Tappa 8).
    app[USAGE_KEY].importa_legacy([
        os.path.join(data_dir, name)
        for name in ("usage.json", "usage_openai.json", "usage_openrouter.json",
                     "usage_ollama.json")
    ], now=time.time())
    # I residui si cancellano DOPO l'importazione: un contatore registrato
    # come importato e' un residuo come gli altri (D6).
    cancella_residui(data_dir, imported=app[USAGE_KEY].legacy_imported())

    openai_runner = None
    if openai_api_key and _credentials[OPENAI.id]:
        openai_runner = OpenAICompatRunner(
            base_url=OPENAI.api_base,
            api_key=openai_api_key,
            read_model=model_reader(app, OPENAI.id),
            log_usage=app[USAGE_KEY].log,
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
            timeout_s=(app[MODELS_CONFIG_KEY].value.get(OLLAMA.id) or {}).get(
                "timeout_s", OLLAMA.reply_timeout_s),
            read_model=partial(local_model, app),
            log_usage=app[USAGE_KEY].log,
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
            read_model=model_reader(app, OPENROUTER.id),
            log_usage=app[USAGE_KEY].log,
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
    # `app[MODEL_CHAIN_KEY]` qui NON si scrive: lo scrive `_recompute_chain`,
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
    _chain = providers_in_chain(app[MODELS_CONFIG_KEY].value.get("chain_order") or [], _risponde)
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
            registry=app[OCCURRENCES_KEY],
        )
        app[CLAUDE_RUNNER_KEY] = claude_runner  # backward compat (may be None)
        app[LLM_ROUTER_KEY] = router
    else:
        app[CLAUDE_RUNNER_KEY] = None
        app[LLM_ROUTER_KEY] = None

    # ── Rimettere in vigore, a caldo ──────────────────────────────────────
    # Fuori da entrambi i rami, e con UNA implementazione sola: il ramo `else`
    # (nessun provider configurato) è il PRIMO gesto di chi installa HIRIS, e
    # senza `app[RECOMPUTE_CHAIN_KEY]` la prima PUT solleverebbe
    # `TypeError: 'NoneType' object is not callable`.
    #
    # Si chiama anche QUI, all'avvio. Non serve a mettere in vigore niente di
    # nuovo -- `_chain` è appena entrata nel router -- ma fa sì che la strada
    # che rimette in vigore sia la STESSA che mette in vigore la prima volta:
    # se le due derivazioni potessero divergere, divergerebbero all'avvio,
    # dove ogni prova le guarda, invece che al primo salvataggio di un utente.
    app[RECOMPUTE_CHAIN_KEY] = partial(reapply_chain, app)
    reapply_chain(app)

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
    # `reapply_chain(app)` ha gia' chiamato poche righe sopra: l'avvio e il
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
    for _notice in _bridge_notices(bool(app[BRIDGE_ACTIVE_KEY].value),
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
    aw = app[AGENT_WORKER_TASK_KEY].value
    if aw is not None:
        aw.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(aw, timeout=5)
    # L'installazione (`start_installation`): puo' essere
    # ancora in attesa del nucleo. Non tiene niente da chiudere, quindi si
    # ferma e si aspetta senza tetto proprio.
    installation = app.get(INSTALLATION_TASK_KEY)
    if installation is not None:
        installation.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await installation
    if REASONING_QUEUE_KEY in app:
        app[REASONING_QUEUE_KEY].close()
    if MEMORY_STORE_KEY in app:
        app[MEMORY_STORE_KEY].close()
    # I due archivi del Task 7 (keeper): stessa disciplina dei due qui
    # sopra -- senza chiuderli un riavvio lascerebbe il file sqlite bloccato.
    if AGENDA_KEY in app:
        app[AGENDA_KEY].close()
    if JOURNAL_KEY in app:
        app[JOURNAL_KEY].close()
    # Fetta «costruire» (Task 8): l'archivio delle proposte/versioni
    # dell'officina (`action/construction/revisions.py`), costruito in
    # `_on_startup` accanto a `app[JOURNAL_KEY]`. Stessa disciplina dei due
    # archivi qui sopra: senza chiuderlo il file sqlite resterebbe bloccato
    # al riavvio.
    if CONSTRUCTIONS_KEY in app:
        app[CONSTRUCTIONS_KEY].close()
    # I CONSUMI e i SERVIZI accoppiati. Tutti e due mancavano da qui -- `usage`
    # da mesi, `servizi` dal giorno in cui e' nato (22/09/2026) -- e nessuna
    # delle prove accanto poteva accorgersene, perche' ognuna nominava a mano
    # l'archivio che il suo autore ricordava. Li ha trovati il cancello
    # derivato `tests/test_archivi_chiusi.py`, che da oggi li chiede al codice.
    if USAGE_KEY in app:
        app[USAGE_KEY].close()
    if SERVICES_KEY in app:
        app[SERVICES_KEY].close()
    # Fetta «l'osservatore» (Task 5): l'archivio dei cambi e degli oggetti
    # del cervello (`mind/store.py`), costruito in `_on_startup`
    # accanto a `app[JOURNAL_KEY]`. Stessa disciplina degli archivi qui sopra:
    # senza chiuderlo il file sqlite resterebbe bloccato al riavvio.
    if OBSERVATIONS_KEY in app:
        app[OBSERVATIONS_KEY].close()
    # Il sapere (`mind/knowledge.py`, fetta «il sapere e le ricette»): stessa
    # disciplina dell'archivio qui sopra, con una differenza sola -- la chiave
    # puo' esserci e valere `None`, quando all'avvio il sapere non si e' aperto
    # (`_open_knowledge`, Task 7b). Per questo si guarda il valore, non la
    # presenza della chiave.
    if app.get(KNOWLEDGE_KEY) is not None:
        app[KNOWLEDGE_KEY].close()
    # `wait=False`: non si aspettano i job in corso al momento dello shutdown.
    if SCHEDULER_KEY in app:
        app[SCHEDULER_KEY].shutdown(wait=False)
    await app[HA_CLIENT_KEY].stop()
    close_all_stores()
