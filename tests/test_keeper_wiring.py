"""Il montaggio dello schedulatore in `server.py` (Task 7 SDD schedulatore):
gli oggetti nuovi esistono, il battito e' registrato, le prese a meta' si
risanano PRIMA che il battito possa girare, e tutto si chiude in
`_on_cleanup`.

Dal 03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'») l'avvio
gira davvero (`tests/_avvio.py`): prima i blocchi si ritagliavano dal testo di
`_on_startup` e si eseguivano isolati, perche' «nessun test avvia il boot
vero». Il montaggio della fotografia delle porte lo fa, su una casa congelata.

`_on_cleanup`, al contrario, e' una funzione piccola e senza I/O di rete: la
si chiama per davvero, come fa implicitamente ogni altro test che passa da
`client` (`tests/test_api.py`) chiudendo il server a fine test.
"""
from __future__ import annotations

import os
import time as _time_module
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.action.actuator import ActionActuator
from hiris.app.action.journal import Journal
from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.chat_thread import ChatThread
from hiris.app.keeper.store import AgendaStore
from hiris.app.keeper.sweeper import Sweeper

# ── L'avvio vero, con gli `add_job` registrati ─────────────────────────────
#
# Fino al 03/10/2026 i blocchi dell'avvio (costruzione di cronaca, promesse e
# porta; risanamento, orologio e battito; la chiusura `_battito`) si
# ritagliavano dal testo di `_on_startup` e si eseguivano isolati, con doppi
# al posto dello schedulatore. Adesso l'app si avvia davvero
# (`tests/_avvio.py::started_with`): lo schedulatore e' quello vero, e una
# spia che AVVOLGE `AsyncIOScheduler.add_job` ne ricorda gli argomenti --
# `replace_existing` non resta scritto sul lavoro, e la prova di prima lo
# guardava.


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def recorded_startup(tmp_path_factory):
    """`(app, lavori)`: l'app avviata, e `{id: argomenti di add_job}`."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from tests._avvio import started_with

    jobs: dict[str, dict] = {}
    real = AsyncIOScheduler.add_job

    def add_job(self, func, *args, id=None, **kwargs):  # noqa: A002
        jobs[id] = {"args": args, **kwargs}
        return real(self, func, *args, id=id, **kwargs)

    with mock.patch.object(AsyncIOScheduler, "add_job", add_job):
        async with started_with(tmp_path_factory.mktemp("custode")) as app:
            yield app, jobs


@pytest.mark.asyncio(loop_scope="module")
async def test_l_avvio_monta_cronaca_e_promesse_e_li_passa_alla_porta(recorded_startup):
    """La porta deve aver ricevuto la STESSA cronaca appena costruita, non
    `None` (il difetto che questo test esiste per impedire: una porta
    costruita a tre argomenti scriverebbe di nuovo solo nel log), e lo stesso
    registro dei servizi e la stessa casa che l'app tiene.

    Mutazione ESEGUITA (03/10/2026): `ActionActuator(...)` costruita con
    `None` al posto di `app["journal"]` -- rossa (`None is <Journal>`)."""
    app, _jobs = recorded_startup
    assert isinstance(app["journal"], Journal)
    assert isinstance(app["agenda"], AgendaStore)
    porta = app["action_actuator"]
    assert isinstance(porta, ActionActuator)
    assert porta._journal is app["journal"]
    assert porta._ha is app["ha_client"]
    assert porta._registry is app["service_registry"]


@pytest.mark.asyncio(loop_scope="module")
async def test_il_battito_e_registrato_come_lavoro(recorded_startup):
    """Mutazione ESEGUITA (03/10/2026): `seconds=15` -> `seconds=60` nel
    lavoro del battito -- rossa."""
    app, jobs = recorded_startup
    assert isinstance(app["sweeper"], Sweeper)
    assert app["scheduler"].get_job("hiris_keeper_heartbeat") is not None, (
        f"il battito non e' registrato -- lavori: {sorted(jobs)}")
    battito = jobs["hiris_keeper_heartbeat"]
    assert battito["trigger"] == "interval"
    assert battito["seconds"] == 15
    assert battito["replace_existing"] is True
    assert battito["misfire_grace_time"] == 30


@pytest.mark.asyncio
async def test_al_riavvio_le_promesse_in_corso_vengono_risanate(tmp_path):
    """Una promessa lasciata `in_corso` da un add-on morto non deve ripartire
    (spec §7, «mai due volte»): al prossimo avvio deve leggersi `fallita`.

    L'archivio si prepara sul disco PRIMA dell'avvio, nella `data_dir` che
    l'avvio apre; la porta vera e' avvolta perche' si veda che nessuno l'ha
    chiamata.

    Mutazione ESEGUITA (03/10/2026): tolta la chiamata
    `app["agenda"].risana(...)` dall'avvio -- rossa (`'in_corso' ==
    'fallita'`)."""
    from tests._avvio import started_with

    promesse = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    try:
        # `quando_ts` entro il tetto dei 30 giorni da `adesso` (spec §9.1.6,
        # `promessa.ORIZZONTE_S`): una data fissa lontana farebbe rifiutare
        # `create()` invece di crearla.
        adesso = _time_module.time()
        ident = promesse.create({
            "specie": "fai", "frase": "x", "quando_ts": adesso + 3600.0,
            "chiamata": {"servizio": "light.turn_on",
                         "bersaglio": {"entita": ["light.x"]}},
        }, thread=ChatThread("persona:paolo", "pannello"), now=adesso)["promessa"]["id"]
        promesse.prendi(ident, now=adesso + 100.0)
        assert promesse.read(ident)["stato"] == "in_corso"  # precondizione
    finally:
        promesse.close()

    with mock.patch.object(ActionActuator, "execute", AsyncMock()) as execute:
        async with started_with(tmp_path) as app:
            assert app["agenda"].read(ident)["stato"] == "fallita"
    # E nessuno l'ha eseguita: risana() deve finire prima che qualunque cosa
    # la prenda di nuovo in mano.
    execute.assert_not_awaited()


# ── L'ultimo anello: il lavoro del battito chiama DAVVERO `orologio.batti` ──
#
# Review Task 7, Rilievo 2: la registrazione del lavoro non prova che il suo
# CORPO faccia la cosa giusta quando lo schedulatore lo chiama, quindici
# secondi dopo. E' l'unico anello fra il lavoro e l'orologio: se dicesse
# `orologio.batti()` a vuoto (o chiamasse un altro metodo), nessuna promessa
# scatterebbe mai in produzione. Qui si chiama il lavoro VERO dello
# schedulatore, con l'orologio dell'app sostituito per la durata della prova.


@pytest.mark.asyncio(loop_scope="module")
async def test_la_chiusura_del_battito_chiama_orologio_batti_con_un_istante(recorded_startup):
    """Mutazione ESEGUITA (03/10/2026): `_battito` chiama
    `app["sweeper"].batti()` senza l'istante -- rossa."""
    app, _jobs = recorded_startup
    battito = app["scheduler"].get_job("hiris_keeper_heartbeat").func
    with mock.patch.object(app["sweeper"], "batti", AsyncMock()) as batti:
        await battito()

    batti.assert_awaited_once()
    # "CON un istante", non a vuoto: una chiusura che chiamasse
    # `orologio.batti()` senza argomenti supererebbe un `assert_awaited()`
    # generico ma non `Sweeper.batti(self, adesso)`, che lo richiede -- il
    # doppio qui non lo impone, quindi lo impone il test.
    args, kwargs = batti.await_args
    assert len(args) == 1 and isinstance(args[0], float), (
        "la chiusura deve passare un istante (`_time.time()`), non chiamare "
        "`batti` a vuoto")
    assert not kwargs


# ── _on_cleanup chiude i due archivi nuovi ──────────────────────────────────


@pytest.mark.asyncio
async def test_il_cleanup_chiude_promesse_e_cronaca():
    """`_on_cleanup` non fa I/O di rete oltre a fermare `ha_client` (gia'
    finto qui): si puo' chiamare per davvero, senza estrazioni."""
    promesse_finte = MagicMock()
    cronaca_finta = MagicMock()
    app = {
        "ha_client": AsyncMock(stop=AsyncMock()),
        "agenda": promesse_finte,
        "journal": cronaca_finta,
    }

    await server._on_cleanup(app)

    promesse_finte.close.assert_called_once()
    cronaca_finta.close.assert_called_once()


@pytest.mark.asyncio
async def test_il_cleanup_non_solleva_senza_promesse_ne_cronaca():
    """Un'app di test che non li ha montati (i tanti test esistenti che
    costruiscono l'app a mano, vedi `tests/test_api.py::client`) non deve
    rompersi al cleanup: stessa disciplina di `archivio_casa`/
    `archivio_memoria` qui sotto."""
    app = {"ha_client": AsyncMock(stop=AsyncMock())}
    await server._on_cleanup(app)  # non deve sollevare


@pytest.mark.asyncio
async def test_il_cleanup_chiude_casa_e_memoria_con_lo_stesso_metodo():
    """`app["home_space_store"]` (`HomeSpaceStore`, ambito `casa`) e
    `app["memory_store"]` (`MemoryStore`, Task 5) esponevano due nomi
    diversi per la stessa azione -- `.chiudi()` contro `.close()` -- perche'
    i due sottosistemi erano a meta' del passaggio all'inglese in due
    momenti diversi. La fetta «la rinomina» (Task 8) chiude quel divario:
    ora entrambi espongono `.close()`, e questo test verifica che
    `_on_cleanup` chiami quel nome su entrambi, non che ne usi due diversi.

    Trovato dalla review del Task 5 per mutazione, quando l'asimmetria era
    ancora vera: rimettere `.chiudi()` su `archivio_memoria` lasciava la
    suite verde (nessun altro test lo copriva), e HIRIS sarebbe uscito verde
    di cancello e di suite per poi sollevare `AttributeError` allo
    SPEGNIMENTO, lasciando il file sqlite bloccato -- esattamente il guasto
    che il commento sopra `if "memory_store" in app` descrive. La
    guardia resta valida oggi nella direzione opposta: se una delle due
    tornasse a `.chiudi()` da sola, questo test lo direbbe."""
    archivio_casa_finto = MagicMock()
    archivio_memoria_finto = MagicMock()
    app = {
        "ha_client": AsyncMock(stop=AsyncMock()),
        "home_space_store": archivio_casa_finto,
        "memory_store": archivio_memoria_finto,
    }

    await server._on_cleanup(app)

    archivio_casa_finto.close.assert_called_once()
    archivio_memoria_finto.close.assert_called_once()
    archivio_casa_finto.chiudi.assert_not_called()
    archivio_memoria_finto.chiudi.assert_not_called()


# ── Il dispatcher riceve DUE parametri nuovi, non uno ────────────────────────


def test_costruisci_dispatcher_strumenti_riceve_registro_e_promesse():
    """Punto 1 del task: non basta `promesse=` -- serve anche `registro=`,
    preso dallo STESSO oggetto dell'app che alimenta la porta
    (`app["service_registry"]`), non una seconda costruzione."""
    registro_sentinella = object()
    promesse_sentinella = object()
    app = {"service_registry": registro_sentinella, "agenda": promesse_sentinella}

    dispatcher = create_tool_dispatcher(app)

    assert dispatcher._registry is registro_sentinella
    assert dispatcher._agenda is promesse_sentinella


@pytest.mark.asyncio
async def test_l_orologio_montato_consegna_l_esito_nella_chat_vera(tmp_path):
    """Task 3: i collaboratori del montaggio vero (`_promise_delivery`)
    scrivono nella cronologia della cartella dell'add-on, rifiutano un filo
    assente, e rileggono il soffitto -- non sono finte che il montaggio
    dimentica."""
    from hiris.app.chat_store import close_all_stores, load_history

    paolo = ChatThread("persona:paolo", "pannello")
    app = {"data_dir": str(tmp_path), "ha_client": None, "servizi": None,
           "ruoli": {"quando": 0.0, "per_id": {}}}
    try:
        collaboratori = server._promise_delivery(app)
        assert set(collaboratori) == {"recipients", "write_to_thread", "ceiling",
                                      "owner_thread"}
        assert collaboratori["write_to_thread"](paolo, "Esito della promessa «x»: y") is True
        assert collaboratori["write_to_thread"](None, "nessun filo") is False
        assert load_history(str(tmp_path), thread=paolo) == [
            {"role": "assistant", "content": "Esito della promessa «x»: y"}]
        # Un servizio senza archivio non comanda a scadenza (fail closed).
        soffitto = await collaboratori["ceiling"]({"specie": "luogo", "id": "p"})
        assert soffitto["comandare"] is False
        # Senza Home Assistant nessun proprietario: un'orfana resta orfana.
        assert await collaboratori["owner_thread"]() is None

        class _Utenti:
            async def users(self):
                return {"utenti": [{"id": "marta", "proprietario": False},
                                   {"id": "paolo", "proprietario": True}]}

        app["ha_client"] = _Utenti()
        assert await collaboratori["owner_thread"]() == paolo
    finally:
        close_all_stores()
