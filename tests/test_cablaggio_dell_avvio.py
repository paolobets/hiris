"""Il cablaggio dell'avvio, chiesto all'app avviata.

Fino al 03/10/2026 queste prove cercavano nel testo di `server.py` una riga
(`app["workshop"] = Workshop(`) o l'ordine fra due righe
(`sorgente.index(A) < sorgente.index(B)`). Un cablaggio spostato in un'altra
funzione o in un altro modulo le rompeva senza che niente cambiasse, e una riga
commentata, o scritta dentro un ramo mai preso, le teneva verdi (Tappa 1 dello
sprint «Una fonte sola di verita'», Task 4).

Adesso l'app si avvia davvero (`tests/_avvio.py`) e si guardano quattro cose:

- le IDENTITA': l'officina tiene la stessa cronaca che l'app tiene, non «una
  cronaca costruita prima»;
- gli ASCOLTATORI: la casa (`RecordingHouse`) ricorda chi l'avvio ha iscritto
  ai suoi eventi, e in che ordine; le prove li chiamano;
- l'ORDINE dei passi d'avvio, registrato mentre l'avvio gira
  (`startup_steps`): chi viene chiamato, e cosa c'e' gia' in `app` in quel
  momento;
- lo SPEGNIMENTO: dopo l'uscita dall'app, gli archivi sono chiusi davvero.
"""
import contextlib
import inspect
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest
import pytest_asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from hiris.app import server
from hiris.app.action.actuator import ActionActuator
from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.registry import ServiceRegistry
from hiris.app.home_space import historian, registry_follower
from hiris.app.mind import realignment
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.entity_cache import EntityCache
from tests._avvio import RecordingHouse, router_routes, started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

pytestmark = pytest.mark.asyncio(loop_scope="module")


# --------------------------------------------------------------------------
# I passi dell'avvio, registrati mentre l'avvio gira
# --------------------------------------------------------------------------

def _recorded(steps: list, label: str, real, *, app_keys: bool = False):
    """`real`, che prima di girare scrive `label` in `steps`. Con
    `app_keys=True` scrive anche le chiavi che `app` (il primo argomento) ha
    IN QUEL MOMENTO: e' cosi' che si vede se un collaboratore esiste gia'."""
    def note(args):
        steps.append((label, frozenset(args[0]) if app_keys else None))

    if inspect.iscoroutinefunction(real):
        async def recorded(*args, **kwargs):
            note(args)
            return await real(*args, **kwargs)
    else:
        def recorded(*args, **kwargs):
            note(args)
            return real(*args, **kwargs)
    return recorded


def _recorded_job(steps: list):
    real = AsyncIOScheduler.add_job

    # `id` e' il nome che APScheduler da' alla parola chiave: si riceve per
    # nome, invece di pescarlo da `kwargs` con una chiave scritta a mano.
    def add_job(self, func, *args, id=None, **kwargs):  # noqa: A002
        steps.append((f"add_job:{id}", None))
        return real(self, func, *args, id=id, **kwargs)
    return add_job


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def startup_steps(tmp_path_factory):
    """`[(passo, chiavi di app in quel momento | None)]`, nell'ordine in cui
    l'avvio vero li ha fatti. Le spie avvolgono le funzioni vere, non le
    sostituiscono: l'avvio fa esattamente cio' che fa senza di loro."""
    steps: list[tuple[str, frozenset | None]] = []
    spies = (
        mock.patch.object(server, "_open_knowledge",
                          _recorded(steps, "knowledge", server._open_knowledge)),
        mock.patch.object(EntityCache, "load",
                          _recorded(steps, "entity_cache", EntityCache.load)),
        mock.patch.object(Watcher, "rebuild_conditions",
                          _recorded(steps, "rebuild_conditions",
                                    Watcher.rebuild_conditions)),
        mock.patch.object(server, "watch_system_conditions",
                          _recorded(steps, "watch_system_conditions",
                                    server.watch_system_conditions)),
        mock.patch.object(server, "reaggregate_last_two_days",
                          _recorded(steps, "reaggregate",
                                    server.reaggregate_last_two_days, app_keys=True)),
        mock.patch.object(ConstructionStore, "risana",
                          _recorded(steps, "constructions_risana",
                                    ConstructionStore.risana)),
        mock.patch.object(AsyncIOScheduler, "add_job", _recorded_job(steps)),
    )
    data_dir = str(tmp_path_factory.mktemp("passi"))
    with contextlib.ExitStack() as stack:
        for spy in spies:
            stack.enter_context(spy)
        async with fotografia_porte.mounted(synthetic_inputs(), data_dir,
                                            RecordingHouse):
            pass
    yield steps


def _first(steps, label: str) -> int:
    names = [name for name, _ in steps]
    assert label in names, f"l'avvio non ha mai fatto «{label}»: {names}"
    return names.index(label)


async def test_the_steps_are_really_recorded(startup_steps):
    """Se le spie non prendessero niente, ogni confronto d'ordine qui sotto
    fallirebbe su un passo mancante -- ma un «non trovato» che diventasse un
    `-1` farebbe sembrare vero qualunque ordine. Si guarda che ci siano
    tutti."""
    names = {name for name, _ in startup_steps}
    assert {"knowledge", "entity_cache", "rebuild_conditions",
            "watch_system_conditions", "reaggregate", "constructions_risana",
            "add_job:hiris_keeper_heartbeat"} <= names, sorted(names)


async def test_knowledge_opens_before_the_entity_cache(startup_steps):
    """La spec 2026-09-16 §8 prescrive che il sapere, il suo seme e
    l'istantanea dei giudizi nascano prima della cache delle entita'. Oggi
    nessun lettore vivo della cache lo pretende (spec §2, §3): e' un ordine
    dichiarato, e si guarda come tale.

    Mutazione ESEGUITA: `_open_knowledge(app, data_dir)` spostata sotto
    `app["entity_cache"] = entity_cache` -- rossa."""
    assert _first(startup_steps, "knowledge") < _first(startup_steps, "entity_cache")


async def test_conditions_are_rebuilt_before_the_first_round(startup_steps):
    """Senza la ricostruzione, a ogni riavvio dell'add-on -- che succede a
    ogni aggiornamento -- i guasti gia' aperti verrebbero riscritti come nati
    adesso, e l'oggetto «guasto» perderebbe la sua unica informazione utile:
    da quando dura. Quindi PRIMA del primo giro delle condizioni.

    Mutazione ESEGUITA: `app["watcher"].rebuild_conditions()` spostata dopo il
    primo `watch_system_conditions` -- rossa. Tolta del tutto -- rossa."""
    assert (_first(startup_steps, "rebuild_conditions")
            < _first(startup_steps, "watch_system_conditions"))


async def test_the_startup_repair_finds_its_collaborators_already_built(startup_steps):
    """La riparazione d'avvio degli ultimi due giorni gira dopo la
    ricostruzione delle condizioni, e trova gia' in `app` cio' di cui ha
    bisogno: il sapere (da li' legge le direzioni: senza, il suo `except` largo
    inghiottirebbe un `KeyError` e due giorni di oggetti non si rifarebbero) e
    l'anagrafe (il fuso della casa e i dispositivi: chiamata prima lavorerebbe
    in UTC e su una casa vuota).

    La prova vecchia guardava l'ordine di due stringhe e NON sapeva dire se
    l'anagrafe esistesse gia' (lo diceva il suo docstring): questa lo vede.

    Mutazione ESEGUITA: `_open_knowledge(app, data_dir)` spostata sotto la
    riparazione -- rossa («knowledge» non c'e'). Mutazione ESEGUITA: la
    riparazione spostata sopra `app["home_space_store"] = ...` -- rossa."""
    position = _first(startup_steps, "reaggregate")
    assert _first(startup_steps, "rebuild_conditions") < position
    present = startup_steps[position][1]
    assert "knowledge" in present
    assert "home_space_store" in present


async def test_unfinished_constructions_heal_before_the_heartbeat(startup_steps):
    """Se il risanamento delle proposte `in_corso` scattasse DOPO che il
    battito dello schedulatore e' registrato, un giro potrebbe partire prima
    e toccare una riga che `risana()` avrebbe dovuto dichiarare incerta --
    riaprendo lo stato fantasma che il risanamento chiude.

    Mutazione ESEGUITA: il blocco `app["constructions"].risana(...)` spostato
    dopo `scheduler.add_job(_battito, ...)` -- rossa."""
    assert (_first(startup_steps, "constructions_risana")
            < _first(startup_steps, "add_job:hiris_keeper_heartbeat"))


async def test_a_failing_startup_repair_does_not_stop_startup(tmp_path, caplog):
    """La riparazione d'avvio sta in un `try/except` che non deve bloccare
    l'avvio: un cervello che non riparte perche' non e' riuscito a rifare
    l'altro ieri sarebbe peggio del buco che sta chiudendo. La prova vecchia
    cercava `try:` e `except Exception` in una finestra di 280 caratteri;
    qui la riparazione SOLLEVA, e l'avvio deve arrivare in fondo (l'ultimo
    passo dell'avvio pubblica `recompute_chain`).

    E il registro porta QUEL preciso errore, col prefisso «cervello:»: un
    errore diverso catturato per sbaglio dallo stesso `except` non si
    distinguerebbe dal solo prefisso. (Questa meta' la guardava
    `test_mind_wiring.py::test_se_la_riaggregazione_solleva_l_avvio_prosegue`,
    uscita il 03/10/2026 perche' ritagliava il blocco dal testo.)

    Mutazione ESEGUITA: tolto il `try/except` intorno alla chiamata -- rossa
    (l'avvio solleva `RuntimeError`). Mutazione ESEGUITA (03/10/2026): il
    `logger.warning` del ramo d'errore tolto -- rossa."""
    import logging

    from tests._avvio import SERVER_LOGGER

    async def broken(app, ha_client, **kwargs):
        raise RuntimeError("riparazione rotta")

    with mock.patch.object(server, "reaggregate_last_two_days", broken), \
            caplog.at_level(logging.WARNING, logger=SERVER_LOGGER):
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path),
                                            RecordingHouse) as app:
            assert callable(app["recompute_chain"])
    lines = [r.getMessage() for r in caplog.records if r.name == SERVER_LOGGER]
    assert any(line.startswith("cervello:")
               and "RuntimeError: riparazione rotta" in line for line in lines), lines


# --------------------------------------------------------------------------
# Le identita': chi tiene cosa
# --------------------------------------------------------------------------

async def test_the_workshop_holds_the_app_store_journal_and_house(started_app):
    """L'officina riceve il canale verso la casa, l'archivio delle costruzioni
    e la cronaca: QUELLI dell'app, non altri. Una cronaca costruita dopo
    l'officina la lascerebbe senza riga di registro, in silenzio.

    Mutazione ESEGUITA: `Workshop(ha_client, app["constructions"],
    Journal(...))` (una cronaca sua) -- rossa."""
    workshop = started_app["workshop"]
    assert isinstance(workshop, Workshop)
    assert isinstance(started_app["constructions"], ConstructionStore)
    assert workshop._ha is started_app["ha_client"]
    assert workshop._store is started_app["constructions"]
    assert workshop._journal is started_app["journal"]


async def test_the_workshop_does_not_hold_the_service_door(started_app):
    """«Un canale, una porta» (spec 2026-08-22 §2.1): l'officina scrive la
    configurazione, la porta esegue i servizi -- due canali di scrittura
    diversi che non devono confondersi. La prova vecchia confrontava il testo
    INTERO della chiamata; questa guarda cio' che l'officina tiene davvero.

    Mutazione ESEGUITA: passato `app["action_actuator"]` all'officina come
    attributo -- rossa."""
    actuator = started_app["action_actuator"]
    held = vars(started_app["workshop"]).values()
    assert not any(value is actuator for value in held)


async def test_the_workshop_reads_the_house_timezone(started_app):
    """La data dell'anteprima di ripristino e' nel fuso della CASA, letto
    dall'anagrafe a ogni chiamata (non quello del container, non quello
    dell'avvio).

    Mutazione ESEGUITA: `read_timezone` tolto dalla costruzione -- rossa."""
    expected = historian.house_timezone(started_app["home_space_store"])
    assert expected is not None
    assert started_app["workshop"]._read_timezone() == expected


async def test_the_watcher_holds_its_store_and_the_knowledge(started_app):
    """L'osservatore scrive nel SUO archivio e legge dal sapere quali
    attributi tenere (spec §5.4). Nasce dopo tutti e due: se nascesse prima,
    l'avvio prenderebbe `KeyError`.

    Mutazione ESEGUITA: `app["watcher"] = Watcher(...)` spostata sopra
    `_open_knowledge(app, data_dir)` -- rossa (l'avvio solleva `KeyError`)."""
    watcher = started_app["watcher"]
    assert isinstance(watcher, Watcher)
    assert isinstance(started_app["observations"], ObservationsStore)
    assert watcher._store is started_app["observations"]
    assert started_app["knowledge"] is not None
    assert watcher._knowledge is started_app["knowledge"]


async def test_the_service_door_holds_the_state_mirror(started_app):
    """La porta dei servizi rilegge lo stato dallo specchio dopo aver agito.
    Costruita prima dello specchio avrebbe `cache=None` e rifiuterebbe OGNI
    azione con «non vedo lo stato di questa casa» (guardia (b) di
    `action/actuator.py`) -- per sempre, e senza che nulla sollevi.

    Mutazione ESEGUITA: la porta costruita sopra `app["entity_cache"] = ...` --
    rossa (`_cache` e' `None`)."""
    actuator = started_app["action_actuator"]
    assert isinstance(actuator, ActionActuator)
    assert actuator._cache is started_app["entity_cache"]
    assert actuator._journal is started_app["journal"]


async def test_the_service_registry_is_the_one_the_door_uses(started_app):
    """Senza il registro nell'app HIRIS resta cieco su cio' che Home Assistant
    sa fare: deve esserci, ed essere lo stesso che la porta consulta.

    Mutazione ESEGUITA: tolto `app["service_registry"] = ServiceRegistry()` --
    rossa (l'avvio solleva `KeyError`)."""
    registry = started_app["service_registry"]
    assert isinstance(registry, ServiceRegistry)
    assert started_app["action_actuator"]._registry is registry


async def test_backfill_quiet_is_born_at_startup(started_app):
    """La quiete del recupero delle cronache nasce nell'avvio, prima che
    aiohttp congeli l'app: crearla al primo giro, ad app avviata, emette
    «Changing state of started or joined application» (con aiohttp 4 un
    errore). Il giro su un'app congelata lo prova
    `test_mind_wiring.py::test_la_quiete_NON_cambia_lo_stato_di_un_app_aiohttp_avviata`;
    qui si prova che l'avvio la crea.

    Mutazione ESEGUITA: tolta `app["backfill_quiet"] = {}` da `_on_startup` --
    rossa."""
    assert isinstance(started_app["backfill_quiet"], dict)


# --------------------------------------------------------------------------
# Gli ascoltatori: chi l'avvio iscrive agli eventi della casa
# --------------------------------------------------------------------------

async def test_the_watcher_listens_to_the_same_tap_as_the_mirror_and_after_it(started_app):
    """Non si apre un secondo rubinetto: lo stesso `add_state_listener` che
    alimenta lo specchio, e dopo di lui -- se un giorno l'ordine contasse,
    conta che lo specchio sia aggiornato prima.

    Mutazione ESEGUITA: scambiate le due iscrizioni -- rossa."""
    listeners = started_app["ha_client"].registered("state")
    mirror = started_app["entity_cache"].on_state_changed
    watcher = started_app["watcher"].watch_reading
    assert mirror in listeners and watcher in listeners, listeners
    assert listeners.index(mirror) < listeners.index(watcher)


async def test_the_automation_event_marks_the_automation(started_app):
    """Senza questo cablaggio `Watcher.mark_automation` non ha nessun
    chiamante: l'evento arriverebbe e nessuna automazione verrebbe segnata.
    Si manda l'evento a chi l'avvio ha iscritto, e si guarda l'osservatore.

    Mutazione ESEGUITA: commentata
    `ha_client.add_automation_listener(_mark_triggered_automation)` -- rossa."""
    entity_id = "automation.prova_cablaggio_avvio"
    for listener in started_app["ha_client"].registered("automation"):
        listener({"entity_id": entity_id, "name": "Prova di cablaggio"})
    watcher = started_app["watcher"]
    assert entity_id in watcher.marked_automations()


async def test_a_service_event_makes_the_registry_reread(started_app):
    """I servizi si rinfrescano su EVENTO, non a scadenza: senza
    l'ascoltatore, per cinque minuti HIRIS rifiuterebbe i servizi di
    un'integrazione appena installata dicendo «non esiste in questa casa».
    Si porta il registro fresco, si manda l'evento a chi l'avvio ha iscritto, e
    si guarda che la lettura dopo torni a chiedere i servizi alla casa.

    Mutazione ESEGUITA: tolta `ha_client.add_service_listener(...)` -- rossa.
    Mutazione ESEGUITA: l'ascoltatore che non chiama `invalidate()` -- rossa."""
    house = started_app["ha_client"]
    registry = started_app["service_registry"]
    with mock.patch.object(house, "get_services",
                           mock.AsyncMock(wraps=house.get_services)) as asked:
        await registry.ensure_fresh(house)
        asked.reset_mock()
        await registry.ensure_fresh(house)
        assert asked.await_count == 0, "un registro fresco non deve rileggere"
        for listener in house.registered("service"):
            listener("service_registered")
        await registry.ensure_fresh(house)
    assert asked.await_count == 1


async def test_a_reconnection_rereads_the_state_mirror(started_app):
    """Alla riconnessione del WebSocket lo specchio dello stato si rilegge:
    gli eventi persi mentre la connessione era giu' non arriveranno piu'.
    Provare `mirror_reload_listener` non prova che l'avvio lo iscriva: qui si
    manda «riconnessione» agli ascoltatori di topologia iscritti, e si guarda
    che lo specchio DELL'APP chieda di essere riletto dalla casa dell'app.

    Il lavoro si cattura invece di girare: gli altri ascoltatori di topologia
    rimandano una ricostruzione di qualche secondo, e lasciarla partire in
    un'app condivisa dal file sarebbe uno stato che passa fra le prove.

    Mutazione ESEGUITA: tolta
    `ha_client.add_topology_listener(mirror_reload_listener(...))` -- rossa."""
    spawned = []

    def capture(coroutine, *, name=None):
        spawned.append(coroutine)

    house = started_app["ha_client"]
    # Due moduli creano i compiti degli ascoltatori di topologia: lo specchio
    # in `server.py`, la ricostruzione in `home_space/registry_follower.py`.
    with (mock.patch.object(server, "_spawn", capture),
          mock.patch.object(registry_follower, "_spawn", capture)):
        for listener in house.registered("topology"):
            listener("riconnessione")
    try:
        # Dal riallineamento dell'osservatore (06/10/2026) la rilettura gira
        # in `mind/realignment.py`, che con la stessa fotografia riallinea: si
        # riconosce dalla funzione e da cio' che porta con se'.
        rereads = [c for c in spawned
                   if c.cr_code is realignment.reload_and_realign.__code__
                   and c.cr_frame.f_locals.get("entity_cache") is started_app["entity_cache"]
                   and c.cr_frame.f_locals.get("client") is house]
        assert len(rereads) == 1, [c.cr_code.co_qualname for c in spawned]
        # E l'osservatore che riallinea e' quello dell'app, chiesto all'avviso
        # e non fissato all'iscrizione: l'ascoltatore nasce prima di lui.
        # Mutazione ESEGUITA: `lambda: None` al posto di `app.get("watcher")`
        # nell'iscrizione -- rossa.
        assert started_app.get("watcher") is not None
        assert rereads[0].cr_frame.f_locals["watcher"]() is started_app["watcher"]
    finally:
        for coroutine in spawned:
            coroutine.close()


async def test_a_closed_disconnection_window_reaches_the_app_watcher(started_app):
    """La finestra di scollegamento, chiusa quando Home Assistant si dichiara
    avviato, arriva all'osservatore DELL'APP: l'avvio iscrive il suo
    ascoltatore. La finestra si consegna a un osservatore finto messo al posto
    di quello dell'app, e lo si rimette subito.

    Mutazione ESEGUITA: tolta
    `ha_client.add_disconnection_listener(disconnection_recorder(...))` --
    rossa."""
    house = started_app["ha_client"]
    real = started_app["watcher"]
    windows = []

    class Osservatore:
        def record_disconnection(self, window):
            windows.append(window)

    started_app["watcher"] = Osservatore()
    try:
        for listener in house.registered("disconnection"):
            listener({"da": 1.0, "a": 2.0})
    finally:
        started_app["watcher"] = real
    assert windows == [{"da": 1.0, "a": 2.0}]


async def test_a_reference_change_rereads_the_state_words(started_app):
    """A-14: il proprietario cambia la lingua della casa e Home Assistant
    manda `core_config_updated`. L'anagrafe si ricostruisce e legge la
    cornice nuova; le parole degli stati -- e il sapere che ne nasce -- si
    rileggono SUBITO DOPO, nella lingua nuova. Fino alla Tappa 2 aspettavano
    il giro dei cinque minuti, e per quel tempo il nucleo parlava la lingua
    vecchia.

    Il lavoro si cattura come nella prova qui sopra; la ricostruzione catturata
    si fa girare senza la sua attesa, con le parole degli stati sostituite da
    una registrazione."""
    spawned = []

    def capture(coroutine, *, name=None):
        spawned.append(coroutine)

    house = started_app["ha_client"]
    with (mock.patch.object(server, "_spawn", capture),
          mock.patch.object(registry_follower, "_spawn", capture)):
        for listener in house.registered("topology"):
            listener("core_config_updated")
    primed = mock.AsyncMock(return_value={"lette": True})
    try:
        rebuilds = [c for c in spawned if c.cr_code.co_name == "_fra_poco"
                    and "rebuild" in c.cr_code.co_names]
        assert len(rebuilds) == 1, [c.cr_code.co_qualname for c in spawned]
        with (mock.patch.object(server, "prime_state_translations", primed),
              mock.patch("asyncio.sleep", mock.AsyncMock())):
            await rebuilds[0]
    finally:
        for coroutine in spawned:
            coroutine.close()
    primed.assert_awaited_once_with(started_app)


# --------------------------------------------------------------------------
# Le rotte dell'officina, dal router
# --------------------------------------------------------------------------

async def test_the_five_construction_routes_are_registered():
    """La registrazione di `/reject` non era pinnata da nessuno, e le altre
    quattro solo per sottostringa, che una riga commentata lascia passare. Il
    router vero non contiene rotte commentate.

    Mutazione ESEGUITA: commentata la registrazione di `.../reject` -- rossa."""
    routes = router_routes()
    assert {
        "GET /api/constructions": "handle_get_constructions",
        "GET /api/constructions/{id}": "handle_get_construction",
        "POST /api/constructions/{id}/confirm": "handle_confirm_construction",
        "POST /api/constructions/{id}/restore": "handle_restore_construction",
        "POST /api/constructions/{id}/reject": "handle_reject_construction",
    }.items() <= routes.items()


# --------------------------------------------------------------------------
# La catena: rimessa in vigore dalla stessa strada, con o senza provider
# --------------------------------------------------------------------------

async def test_the_chain_can_be_recomputed_without_any_provider(started_app):
    """Il ramo senza provider e' il PRIMO gesto di chi installa HIRIS: senza
    `app["recompute_chain"]` la prima PUT della pagina Modelli solleverebbe
    `TypeError: 'NoneType' object is not callable`. E la catena dev'essere
    vuota: senza backend non risponde nessuno.

    Mutazione ESEGUITA: `app["recompute_chain"] = ...` spostata dentro il ramo
    con i provider -- rossa (`KeyError`)."""
    assert started_app["llm_router"] is None, "la casa sintetica non ha provider"
    started_app["recompute_chain"]()
    assert started_app["model_chain"] == []


async def test_startup_and_the_page_take_the_same_road(tmp_path, monkeypatch):
    """Con un provider, l'avvio mette in vigore la catena passando dalla
    STESSA funzione che la pagina Modelli richiama a ogni salvataggio: se le
    due derivazioni potessero divergere, divergerebbero all'avvio, dove ogni
    prova le guarda.

    Mutazione ESEGUITA: tolta la chiamata `_rimetti_in_vigore()` dall'avvio --
    rossa (nessun ricalcolo all'avvio). Mutazione ESEGUITA:
    `app["recompute_chain"] = ...` spostata dentro il ramo `else` -- rossa."""
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-prova-cablaggio")
    recomputed = []
    real = server._recompute_chain

    def spy(app):
        recomputed.append(app)
        return real(app)

    with mock.patch.object(server, "_recompute_chain", spy):
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path),
                                            RecordingHouse) as app:
            assert app["llm_router"] is not None
            assert recomputed == [app], "l'avvio non ha ricalcolato la catena"
            app["recompute_chain"]()
            assert recomputed == [app, app]


# --------------------------------------------------------------------------
# Lo spegnimento
# --------------------------------------------------------------------------

def _connections(app) -> dict[str, sqlite3.Connection]:
    """`{chiave di app: connessione}` per ogni oggetto dell'app che tiene una
    connessione SQLite: gli archivi, chiesti all'app e non elencati."""
    found = {}
    for key, value in app.items():
        for attribute in getattr(value, "__dict__", {}).values():
            if isinstance(attribute, sqlite3.Connection):
                found[key] = attribute
    return found


async def test_every_store_is_closed_after_shutdown(tmp_path):
    """Un archivio SQLite lasciato aperto non si rompe subito: il file resta
    bloccato, e il difetto compare al riavvio successivo -- che su un add-on
    succede a ogni aggiornamento. Si spegne l'app vera e si prova a usare ogni
    connessione che teneva.

    `tests/test_archivi_chiusi.py` guarda che gli archivi costruiti come
    `app["x"] = XStore(...)` ricevano `close` allo spegnimento; questa prova
    guarda, per ogni connessione che l'app tiene comunque sia nata, che non
    si possa piu' usare.

    Mutazione ESEGUITA: tolta `app["observations"].close()` da `_on_cleanup` --
    rossa. Tolta `app["constructions"].close()` -- rossa."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path),
                                        RecordingHouse) as app:
        connections = _connections(app)
        for connection in connections.values():
            connection.execute("SELECT 1")
    # La derivazione non si e' svuotata: i due archivi di cui le prove vecchie
    # parlavano per nome ci sono.
    assert {"observations", "constructions"} <= set(connections), sorted(connections)
    still_open = []
    for key, connection in connections.items():
        try:
            connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            continue
        still_open.append(key)
    assert not still_open, f"archivi rimasti aperti dopo lo spegnimento: {still_open}"
