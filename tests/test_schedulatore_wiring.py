"""Il montaggio dello schedulatore in `server.py` (Task 7 SDD schedulatore):
gli oggetti nuovi esistono, il battito e' registrato, le prese a meta' si
risanano PRIMA che il battito possa girare, e tutto si chiude in
`_on_cleanup`.

Nessun test qui avvia `_on_startup` per intero -- e' la stessa disciplina
gia' scritta in `tests/test_avvio_websocket.py` ("review finale E3: nessun
test avvia il boot vero", perche' `_on_startup` tocca il Supervisor, il
websocket di Home Assistant, e una lunga catena di migrazioni una-tantum che
non hanno niente a che fare con lo schedulatore). Chi ha scritto questo file
lo ha verificato di persona: `server.create_app()` non accetta un parametro
`data_dir` (a differenza di quanto ipotizzava il brief del task), e nessun
test esistente chiama mai `server._on_startup(app)` per davvero -- l'unica
convenzione che lo fa (`test_avvio_websocket.py`) ESTRAE dal sorgente vero il
solo blocco che le serve e lo esegue isolato, con doppi al posto di Home
Assistant/scheduler. Questo file adotta la STESSA tecnica per i due blocchi
nuovi di questo task (costruzione di cronaca/promesse/porta, e
risana+orologio+battito), invece di inventarne una seconda maniera.

`_on_cleanup`, al contrario, e' una funzione piccola e senza I/O di rete: la
si chiama per davvero, come fa implicitamente ogni altro test che passa da
`client` (`tests/test_api.py`) chiudendo il server a fine test.
"""
from __future__ import annotations

import inspect
import os
import textwrap
import time as _time_module
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app import server
from hiris.app.api.handlers_chat import costruisci_dispatcher_strumenti
from hiris.app.azione.cronaca import Cronaca
from hiris.app.azione.porta import PortaAzione
from hiris.app.schedulatore.archivio import ArchivioPromesse
from hiris.app.schedulatore.orologio import Orologio
from hiris.app.schedulatore.turno import interpreta_promessa


# ── Estrazione 1: cronaca + promesse + porta (con cronaca) ──────────────────


def _load_costruzione_archivi():
    """Estrae dal sorgente vero di `_on_startup` il blocco che costruisce
    `app["cronaca"]`, `app["promesse"]` e passa la cronaca alla porta -- da
    `app["cronaca"] = Cronaca(` fino (incluso) alla chiamata a `PortaAzione`.
    """
    src = inspect.getsource(server._on_startup)
    start = src.index('    app["cronaca"] = Cronaca(')
    end_marker = 'app.get("entity_cache"), app["cronaca"])'
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "async def _check(app, data_dir, os, ha_client, Cronaca, "
        "ArchivioPromesse, PortaAzione):\n" + textwrap.indent(body, "    ")
    )
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup costruzione archivi>", "exec"), namespace)
    return namespace["_check"]


@pytest.mark.asyncio
async def test_l_avvio_monta_cronaca_e_promesse_e_li_passa_alla_porta(tmp_path):
    check = _load_costruzione_archivi()
    app: dict = {"registro_servizi": object()}  # sentinella: la porta la deve
    # ricevere TALE E QUALE, non ricalcolata.
    ha_client = object()  # PortaAzione non lo chiama alla costruzione (solo lo
    # conserva): un oggetto qualunque basta a dimostrare che e' quello passato.

    await check(app, str(tmp_path), os, ha_client, Cronaca, ArchivioPromesse,
                PortaAzione)

    assert isinstance(app["cronaca"], Cronaca)
    assert isinstance(app["promesse"], ArchivioPromesse)
    try:
        porta = app["porta_azione"]
        assert isinstance(porta, PortaAzione)
        # La porta deve aver ricevuto la STESSA cronaca appena costruita, non
        # `None` (il difetto che questo test esiste per impedire: una porta
        # costruita a tre argomenti scriverebbe di nuovo solo nel log).
        assert porta._cronaca is app["cronaca"]
        assert porta._ha is ha_client
        assert porta._registro is app["registro_servizi"]
    finally:
        app["cronaca"].close()
        app["promesse"].close()


# ── Estrazione 2: risana + orologio + battito ────────────────────────────────


def _load_battito_avvio():
    """Estrae dal sorgente vero di `_on_startup` il blocco che risana le
    promesse a meta', monta l'orologio e registra il battito -- dal `try:`
    del risanamento fino (incluso) alla chiusura di `scheduler.add_job(...)`
    del battito."""
    src = inspect.getsource(server._on_startup)
    start = src.index('    try:\n        app["promesse"].risana(')
    end_marker = '        misfire_grace_time=30,\n    )'
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "async def _check(app, scheduler, _time, logger, Orologio, "
        "interpreta_promessa):\n" + textwrap.indent(body, "    ")
    )
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup battito>", "exec"), namespace)
    return namespace["_check"]


class _SchedulerRegistratore:
    """Registra ogni `add_job(...)` senza schedulare nulla per davvero --
    stesso principio del `_SchedulerFinto` di `test_avvio_websocket.py`, solo
    che qui serve leggere GLI ARGOMENTI della chiamata, non l'ordine."""

    def __init__(self) -> None:
        self.chiamate: list[dict] = []

    def add_job(self, func, **kwargs):
        self.chiamate.append({"func": func, **kwargs})


@pytest.fixture()
def promesse(tmp_path):
    a = ArchivioPromesse(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


@pytest.fixture()
def porta_finta():
    """Un doppio minimo della porta: solo `esegui`, mai chiamato in questi
    test (nessuna promessa e' scaduta)."""
    finta = MagicMock()
    finta.esegui = AsyncMock(return_value={"eseguito": True})
    return finta


@pytest.mark.asyncio
async def test_il_battito_e_registrato_come_lavoro(promesse, porta_finta):
    check = _load_battito_avvio()
    app = {"promesse": promesse, "porta_azione": porta_finta}
    scheduler = _SchedulerRegistratore()

    await check(app, scheduler, _time_module, server.logger, Orologio,
                interpreta_promessa)

    assert isinstance(app["orologio"], Orologio)
    battiti = [c for c in scheduler.chiamate if c.get("id") == "hiris_schedulatore_battito"]
    assert len(battiti) == 1, (
        "il battito deve essere registrato UNA volta, con questo id -- "
        f"lavori registrati: {[c.get('id') for c in scheduler.chiamate]}")
    battito = battiti[0]
    assert battito["trigger"] == "interval"
    assert battito["seconds"] == 15
    assert battito["replace_existing"] is True
    assert battito["misfire_grace_time"] == 30


@pytest.mark.asyncio
async def test_al_riavvio_le_promesse_in_corso_vengono_risanate(promesse, porta_finta):
    """Una promessa lasciata `in_corso` da un add-on morto non deve ripartire
    (spec §7, «mai due volte»): al prossimo avvio deve leggersi `fallita`."""
    # `quando_ts` entro il tetto dei 30 giorni da `adesso` (spec §9.1.6,
    # `promessa.ORIZZONTE_S`): una data fissa lontana avrebbe fatto rifiutare
    # `crea()` con "non tengo promesse oltre 30 giorni" invece di crearla --
    # lo stesso difetto di date-a-mano gia' documentato in
    # `test_schedulatore_strumenti.py::_fra`.
    ident = promesse.crea({
        "specie": "fai", "frase": "x", "quando_ts": 1_000.0 + 3600.0,
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.x"]}},
    }, adesso=1_000.0)["promessa"]["id"]
    promesse.prendi(ident, adesso=1_100.0)
    assert promesse.leggi(ident)["stato"] == "in_corso"  # precondizione del test

    check = _load_battito_avvio()
    app = {"promesse": promesse, "porta_azione": porta_finta}
    scheduler = _SchedulerRegistratore()

    await check(app, scheduler, _time_module, server.logger, Orologio,
                interpreta_promessa)

    assert promesse.leggi(ident)["stato"] == "fallita"
    # E il battito NON deve averla toccata: risana() deve essere finita
    # prima che qualunque cosa la prenda di nuovo in mano.
    porta_finta.esegui.assert_not_awaited()


# ── L'ultimo anello: la chiusura `_battito` chiama DAVVERO `orologio.batti` ──
#
# Review Task 7, Rilievo 2 (Minor, richiesto lo stesso): nessuno dei test qui
# sopra invoca la chiusura `_battito` -- `_load_battito_avvio()` prova che
# viene REGISTRATA su APScheduler con l'id/trigger giusti, non che il suo
# CORPO faccia la cosa giusta quando lo scheduler la chiama davvero, quindici
# secondi dopo. E' l'unico anello fra il job e l'orologio: se dicesse
# `orologio.batti()` a vuoto (o chiamasse un altro metodo), l'intera fetta
# sarebbe verde e nessuna promessa scatterebbe mai in produzione -- nessun
# test degli altri file se ne accorgerebbe, perche' il resto della catena e'
# provato a pezzi separati (Orologio per conto suo in
# `test_schedulatore_orologio.py`, la registrazione del job qui sopra).


def _load_battito_closure():
    """Estrae SOLO la chiusura `_battito` (non l'intero blocco di
    `_load_battito_avvio`) dal sorgente vero di `_on_startup`, e la
    restituisce pronta per essere chiamata con un `app` e un `_time` finti.
    Stessa tecnica delle altre estrazioni di questo file (e di
    `test_avvio_websocket.py`): il corpo vero, non una sua imitazione."""
    src = inspect.getsource(server._on_startup)
    start = src.index('    async def _battito() -> None:')
    end_marker = 'await app["orologio"].batti(_time.time())'
    end = src.index(end_marker, start) + len(end_marker)
    body = textwrap.dedent(src[start:end])
    func_src = (
        "async def _wrap(app, _time):\n" + textwrap.indent(body, "    ")
        + "\n    return _battito\n"
    )
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup battito closure>", "exec"), namespace)
    return namespace["_wrap"]


@pytest.mark.asyncio
async def test_la_chiusura_del_battito_chiama_orologio_batti_con_un_istante():
    orologio_finto = MagicMock()
    orologio_finto.batti = AsyncMock()
    app = {"orologio": orologio_finto}

    wrap = _load_battito_closure()
    battito = await wrap(app, _time_module)
    await battito()

    orologio_finto.batti.assert_awaited_once()
    # "CON un istante", non a vuoto: una chiusura che chiamasse
    # `orologio.batti()` senza argomenti supererebbe un `assert_awaited()`
    # generico ma non `Orologio.batti(self, adesso)`, che lo richiede -- il
    # doppio qui non lo impone (e' un MagicMock), quindi lo impone il test.
    args, kwargs = orologio_finto.batti.await_args
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
        "promesse": promesse_finte,
        "cronaca": cronaca_finta,
    }

    await server._on_cleanup(app)

    promesse_finte.close.assert_called_once()
    cronaca_finta.close.assert_called_once()


@pytest.mark.asyncio
async def test_il_cleanup_non_solleva_senza_promesse_ne_cronaca():
    """Un'app di test che non li ha montati (i tanti test esistenti che
    costruiscono l'app a mano, vedi `tests/test_api.py::client`) non deve
    rompersi al cleanup: stessa disciplina di `archivio_casa`/
    `archivio_memoria` qui sopra."""
    app = {"ha_client": AsyncMock(stop=AsyncMock())}
    await server._on_cleanup(app)  # non deve sollevare


# ── Il dispatcher riceve DUE parametri nuovi, non uno ────────────────────────


def test_costruisci_dispatcher_strumenti_riceve_registro_e_promesse():
    """Punto 1 del task: non basta `promesse=` -- serve anche `registro=`,
    preso dallo STESSO oggetto dell'app che alimenta la porta
    (`app["registro_servizi"]`), non una seconda costruzione."""
    registro_sentinella = object()
    promesse_sentinella = object()
    app = {"registro_servizi": registro_sentinella, "promesse": promesse_sentinella}

    dispatcher = costruisci_dispatcher_strumenti(app)

    assert dispatcher._registro is registro_sentinella
    assert dispatcher._promesse is promesse_sentinella
