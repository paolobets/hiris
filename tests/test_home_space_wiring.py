"""Il cablaggio dell'anagrafe: antirimbalzi, smistamento degli eventi, specchio.

Home Assistant, dove lo si interroga, e' il client vero sulla casa finta
(`scripts/casa_finta.py::CasaFinta`, Tappa 2, Task 12): fino ad allora era un
`AsyncMock()` senza spec, o una classe che imitava `get_services`, o un tipo
costruito al volo con `get_states`. Cio' che il codice ha chiesto si legge in
`house.calls`.

Restano sul trasporto finto le prove dello SMISTAMENTO degli eventi
(`_FintoWSEventi` dato come sessione a `_ws_loop`): la connessione di lunga
vita della casa finta (`SilentConnection`) tace per costruzione -- una casa
congelata non manda eventi -- e non sa ne' consegnarne ne' cadere.
"""
import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import aiohttp
import pytest

from hiris.app.home_space.reader import HomeSpace
from hiris.app.proxy.entity_cache import EntityCache
from hiris.app.proxy.ha_client import HAClient
from hiris.app.server import (
    mirror_reload_listener,
    schedule_behavior_reread,
    schedule_registry_rebuild,
)
from tests._casa_sintetica import synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

# La config minima che Home Assistant restituisce a `get_config`: da questa
# fetta la ricostruzione dell'anagrafe legge anche il sistema di riferimento
# della casa (unita', fuso, valuta). Una casa che non la dichiara e' un HA che
# non ha risposto -- e infatti `non_disponibili` lo direbbe. Che sia questo il
# comportamento e' provato a parte, in tests/test_home_space_reference.py.
_CONFIG = {"time_zone": "Europe/Rome", "currency": "EUR", "language": "it",
           "unit_system": {"temperature": "C", "length": "km"}}


_VUOTI = {"piani": [], "aree": [], "dispositivi": [], "entita": [],
          "etichette": [], "categorie": [], "integrazioni": []}

#: Il primo comando di `read_registries`, chiesto alla sua tabella: una
#: ricostruzione lo manda una volta, quindi contarlo conta le ricostruzioni.
_FIRST_REGISTRY = HAClient._REGISTRIES[0][1]


def _empty_house() -> CasaFinta:
    """Una casa con i registri vuoti e il sistema di riferimento."""
    return CasaFinta({"registries": dict(_VUOTI), "ha_config": _CONFIG})


def _rebuilds(house: CasaFinta) -> int:
    return sum(1 for command, _ in house.calls if command == _FIRST_REGISTRY)


def _state_reads(house: CasaFinta) -> int:
    return sum(1 for path, _ in house.calls if path == "/api/states")


def _specchio_caricato():
    """Uno specchio dello stato VERO gia' caricato: senza `loaded`, `rebuild`
    dichiara `specchio_vivo` fra i non disponibili (vedi il suo docstring)."""
    cache = EntityCache()
    cache._states = {}
    cache._loaded = True
    return cache


@pytest.fixture
def archivio(tmp_path):
    a = HomeSpace(str(tmp_path))
    yield a
    a.close()


@pytest.mark.asyncio
async def test_una_raffica_di_eventi_ricostruisce_una_volta_sola(archivio):
    house = _empty_house()
    innesca = schedule_registry_rebuild(house, archivio, _specchio_caricato(), delay=0.05)
    for _ in range(10):
        innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert _rebuilds(house) == 1


@pytest.mark.asyncio
async def test_due_raffiche_distanti_ricostruiscono_due_volte(archivio):
    house = _empty_house()
    innesca = schedule_registry_rebuild(house, archivio, _specchio_caricato(), delay=0.05)
    innesca("floor_registry_updated")
    await asyncio.sleep(0.2)
    innesca("floor_registry_updated")
    await asyncio.sleep(0.2)
    assert _rebuilds(house) == 2
    # Contare le chiamate non basta: `_fra_poco` ingoia ogni eccezione per non
    # uccidere l'ascoltatore, quindi due ricostruzioni FALLITE darebbero lo
    # stesso conteggio. Solo l'archivio scritto prova che sono riuscite.
    assert archivio.updated_at() is not None


@pytest.mark.asyncio
async def test_una_ricostruzione_fallita_non_uccide_l_ascoltatore(archivio, monkeypatch):
    """Fino alla Tappa 2 il guasto era `read_registries` che SOLLEVAVA
    `OSError("HA giu'")`: il client vero non solleva (D3), un Home Assistant
    giu' gli rende registri «non disponibili». Cio' che puo' ancora sollevare
    dentro la ricostruzione e' l'archivio -- un disco pieno, un database
    bloccato --, ed e' quello il guasto che l'ascoltatore deve reggere.

    Limite misurato il 03/10/2026: restringere l'`except Exception` di
    `_fra_poco` a `except RuntimeError` lascia questa prova VERDE (come la
    lasciava verde la finta di prima): ogni innesco fa nascere un compito
    nuovo, e il guasto del precedente non lo tocca. La prova difende che la
    seconda ricostruzione parta e riesca, non l'`except`."""
    house = _empty_house()
    hold = archivio.hold_registries
    failures = iter([sqlite3.OperationalError("database is locked")])

    def _hold_failing_once(*args, **kwargs):
        error = next(failures, None)
        if error is not None:
            raise error
        return hold(*args, **kwargs)

    monkeypatch.setattr(archivio, "hold_registries", _hold_failing_once)
    innesca = schedule_registry_rebuild(house, archivio, _specchio_caricato(), delay=0.05)
    innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert archivio.updated_at() is None   # la prima e' fallita davvero
    innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert _rebuilds(house) == 2
    assert archivio.updated_at() is not None


@pytest.mark.asyncio
async def test_una_raffica_di_eventi_rilegge_il_comportamento_una_volta_sola():
    """Important (6): stesso antirimbalzo di
    `test_una_raffica_di_eventi_ricostruisce_una_volta_sola`, ma per il
    comportamento -- riusa TOPOLOGY_EVENTS (nessun meccanismo nuovo)."""
    guarda_finta = AsyncMock(return_value=True)
    innesca = schedule_behavior_reread(guarda_finta, delay=0.05)
    for _ in range(10):
        innesca("entity_registry_updated")
    await asyncio.sleep(0.2)
    assert guarda_finta.await_count == 1
    # FORZA la rilettura: l'mtime dei file puo' non essere cambiato affatto
    # (un'automazione tolta/aggiunta in un pacchetto), ed e' proprio il
    # punto di questo innesco.
    guarda_finta.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_una_rilettura_del_comportamento_fallita_non_uccide_l_ascoltatore():
    guarda_finta = AsyncMock(side_effect=[OSError("HA giu'"), True])
    innesca = schedule_behavior_reread(guarda_finta, delay=0.05)
    innesca("entity_registry_updated")
    await asyncio.sleep(0.2)
    innesca("entity_registry_updated")
    await asyncio.sleep(0.2)
    assert guarda_finta.await_count == 2


class _MsgFinto:
    """Un messaggio TEXT del WebSocket di HA che porta un evento."""

    def __init__(self, event_type: str, data: dict):
        self.type = aiohttp.WSMsgType.TEXT
        self._payload = {"type": "event", "event": {"event_type": event_type, "data": data}}

    def json(self):
        return self._payload


class _FintoWSEventi:
    """Consegna auth_required/auth_ok, poi la sequenza di eventi data, poi si
    blocca -- il test cancella il task invece di aspettare una fine che in
    produzione non arriva mai. Stessa forma di _FakeWS in test_ha_client_invio.py."""

    def __init__(self, eventi: list[tuple[str, dict]]):
        self._auth = [{"type": "auth_required"}, {"type": "auth_ok"}]
        self._eventi = list(eventi)
        self.comandi: list[dict] = []

    async def receive_json(self):
        return self._auth.pop(0)

    async def send_json(self, payload):
        self.comandi.append(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._eventi:
            event_type, data = self._eventi.pop(0)
            return _MsgFinto(event_type, data)
        await asyncio.sleep(3600)  # nessun altro evento: si blocca finche' il test non cancella


class _FintaSessioneEventi:
    def __init__(self, ws: _FintoWSEventi):
        self._ws = ws

    def ws_connect(self, url):
        return self._ws


@pytest.mark.asyncio
async def test_lo_smistamento_degli_eventi_ws_raggiunge_gli_ascoltatori_giusti():
    """Sostituisce la tautologia che confrontava TOPOLOGY_EVENTS con se stessa.
    Cancellando il blocco `if event_type in TOPOLOGY_EVENTS` o il ciclo di
    sottoscrizione, questo test si accorge -- quello vecchio no.

    Un floor_registry_updated deve chiamare l'ascoltatore dell'anagrafe. Un
    entity_registry_updated deve chiamarlo anche lui, SENZA filtro su
    action -- create e update entrano entrambi.

    Fino alla fetta E3 (2.0) qui si verificava anche il meccanismo storico
    verso `add_registry_listener` (filtrato su action=="create"): e' uscito
    con la context map, il suo unico chiamante di produzione (vedi
    task-2-report.md) -- il caso resta, l'assert sul registro no.
    """
    ws = _FintoWSEventi([
        ("floor_registry_updated", {}),
        ("entity_registry_updated", {"action": "create", "entity_id": "light.nuova"}),
        ("entity_registry_updated", {"action": "update", "entity_id": "light.rinominata"}),
    ])
    client = HAClient(base_url="http://ha.test", token="t")
    client._session = _FintaSessioneEventi(ws)

    anagrafe_chiamate: list[str] = []
    client.add_topology_listener(lambda tipo: anagrafe_chiamate.append(tipo))

    task = asyncio.create_task(client._ws_loop("ws://ha.test/api/websocket"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # "riconnessione" (fix Task 6, punto 2) apre la lista: ogni connessione
    # riuscita rifa' l'anagrafe, non solo gli eventi ricevuti mentre era su.
    assert anagrafe_chiamate == [
        "riconnessione", "floor_registry_updated",
        "entity_registry_updated", "entity_registry_updated",
    ]


@pytest.mark.asyncio
async def test_lovelace_updated_raggiunge_solo_l_ascoltatore_delle_plance():
    """Task 5: DASHBOARD_EVENT ha un ascoltatore proprio, separato
    dall'anagrafe. Cancellare la sua sottoscrizione o il suo smistamento (e
    lasciare solo quello dell'anagrafe) farebbe cadere questo test da solo --
    a differenza di un confronto TOPOLOGY_EVENTS-con-se-stesso, che non si
    accorgerebbe di niente."""
    ws = _FintoWSEventi([("lovelace_updated", {"url_path": "cucina"})])
    client = HAClient(base_url="http://ha.test", token="t")
    client._session = _FintaSessioneEventi(ws)

    anagrafe_chiamate: list[str] = []
    plance_chiamate: list[dict] = []
    client.add_topology_listener(lambda tipo: anagrafe_chiamate.append(tipo))
    client.add_dashboard_listener(lambda dati: plance_chiamate.append(dati))

    task = asyncio.create_task(client._ws_loop("ws://ha.test/api/websocket"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # "riconnessione" (stesso principio del Task 6 per l'anagrafe): una
    # disconnessione perde per sempre un DASHBOARD_EVENT emesso nel frattempo.
    assert plance_chiamate == [{}, {"url_path": "cucina"}]
    # DASHBOARD_EVENT non deve innescare la ricostruzione dei REGISTRI: solo
    # "riconnessione" tocca l'ascoltatore dell'anagrafe qui.
    assert anagrafe_chiamate == ["riconnessione"]

    tipi_sottoscritti = {
        c.get("event_type") for c in ws.comandi if c.get("type") == "subscribe_events"
    }
    assert "lovelace_updated" in tipi_sottoscritti


# --- I servizi si rinfrescano su EVENTO, non a scadenza --------------------
#
# `ServiceRegistry` si ricarica solo se ha piu' di 300 secondi
# (`action/registry.py`). Conseguenza misurata da una review: per cinque minuti
# dopo aver installato un'integrazione, HIRIS rifiuta i suoi servizi dicendo
# «non esiste in questa casa» -- una frase FALSA detta con sicurezza, che e'
# peggio di un «non lo so».
#
# Home Assistant emette `service_registered` e `service_removed` con `domain` e
# `service` (verificato su home-assistant.io/docs/configuration/events/).


@pytest.mark.asyncio
async def test_gli_eventi_dei_servizi_raggiungono_il_loro_ascoltatore():
    """Terza famiglia di eventi, accanto ad anagrafe e plance -- e separata per
    la stessa ragione: innescano una rilettura diversa."""
    ws = _FintoWSEventi([
        ("service_registered", {"domain": "luce_nuova", "service": "accendi"}),
        ("service_removed", {"domain": "vecchia", "service": "spegni"}),
    ])
    client = HAClient(base_url="http://ha.test", token="t")
    client._session = _FintaSessioneEventi(ws)

    servizi_chiamate: list[str] = []
    anagrafe_chiamate: list[str] = []
    client.add_service_listener(lambda tipo: servizi_chiamate.append(tipo))
    client.add_topology_listener(lambda tipo: anagrafe_chiamate.append(tipo))

    task = asyncio.create_task(client._ws_loop("ws://ha.test/api/websocket"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # "riconnessione" apre la lista per la stessa ragione dell'anagrafe: gli
    # eventi emessi mentre la connessione era giu' non tornano piu', e un
    # registro stantio direbbe «non esiste» di un servizio che esiste.
    assert servizi_chiamate == [
        "riconnessione", "service_registered", "service_removed"]
    # E NON devono finire nell'anagrafe: un servizio nuovo non cambia la casa.
    assert anagrafe_chiamate == ["riconnessione"]


@pytest.mark.asyncio
async def test_automation_triggered_reaches_only_the_automation_listener():
    """Task 4 di «le tracce e il log»: quarta famiglia di eventi, accanto ad
    anagrafe/plance/servizi -- e separata per la stessa ragione, un'
    automazione scattata non cambia la casa ne' i servizi.

    Nessuna "riconnessione" sintetica per questa famiglia (a differenza di
    anagrafe/plance/servizi qui sopra): `mark_automation` non ha bisogno di
    "recuperare" un evento perso durante una disconnessione -- un'automazione
    gia' segnata resta segnata per sempre (vedi il docstring di
    `Watcher._marked_automations`, ora un dizionario entity_id->nome, non
    piu' un insieme, ma con la stessa sorte: solo aggiunte, mai tolte), e
    una segnata perso durante il distacco tornera' a segnarsi da sola al
    primo scatto successivo. Verificato qui guardando che l'elenco NON
    contenga "riconnessione", a differenza degli altri tre.

    Mutazione provata a mano: cancellare il ramo
    `elif event_type == AUTOMATION_TRIGGERED_EVENT` nello smistamento fa
    arrossire `assert automation_calls == [...]` (tornerebbe `[]`)."""
    ws = _FintoWSEventi([
        ("automation_triggered", {"name": "Luci sera", "entity_id": "automation.luci_sera"}),
    ])
    client = HAClient(base_url="http://ha.test", token="t")
    client._session = _FintaSessioneEventi(ws)

    automation_calls: list[dict] = []
    anagrafe_chiamate: list[str] = []
    client.add_automation_listener(lambda dati: automation_calls.append(dati))
    client.add_topology_listener(lambda tipo: anagrafe_chiamate.append(tipo))

    task = asyncio.create_task(client._ws_loop("ws://ha.test/api/websocket"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert automation_calls == [
        {"name": "Luci sera", "entity_id": "automation.luci_sera"}]
    # E NON deve finire nell'anagrafe, ne' innescare la "riconnessione"
    # sintetica delle altre tre famiglie -- vedi il docstring sopra.
    assert anagrafe_chiamate == ["riconnessione"]

    subscribed_types = {
        c.get("event_type") for c in ws.comandi if c.get("type") == "subscribe_events"
    }
    assert "automation_triggered" in subscribed_types


@pytest.mark.asyncio
async def test_invalidare_il_registro_lo_fa_ricaricare_prima_della_scadenza():
    """Il cuore della fetta. Senza `invalidate()`, `ensure_fresh` guarda solo
    l'eta' e torna subito: l'evento non servirebbe a niente."""
    from hiris.app.action.registry import ServiceRegistry

    house = CasaFinta(synthetic_inputs())

    def letture():
        return sum(1 for path, _ in house.calls if path == "/api/services")

    r = ServiceRegistry()
    await r.ensure_fresh(house)
    assert letture() == 1
    assert r.service("light", "turn_on") is not None   # la lettura e' arrivata

    # Senza invalidare: nessuna seconda lettura, l'eta' e' minima.
    await r.ensure_fresh(house)
    assert letture() == 1

    r.invalidate()
    await r.ensure_fresh(house)
    assert letture() == 2, (
        "dopo un `service_registered` il registro deve rileggere, altrimenti "
        "HIRIS continua a dire «non esiste in questa casa» per 5 minuti")


def test_invalidare_non_svuota_cio_che_si_sapeva():
    """`invalidate()` dice «rileggi appena serve», non «dimentica». Se svuotasse,
    fra l'evento e la rilettura HIRIS non potrebbe verificare NIENTE -- e un
    registro assente e' peggio di uno vecchio (e' la ragione scritta in
    `ensure_fresh`)."""
    from hiris.app.action.registry import ServiceRegistry

    r = ServiceRegistry()
    r._per_domain = {"light": {"turn_on": {}}}
    r._caricato_a = 1.0
    r.invalidate()
    assert r.service("light", "turn_on") is not None
    assert not r.empty()


class _FintoWSCheCade(_FintoWSEventi):
    """La connessione si rompe subito dopo l'handshake: `_ws_loop` ne apre
    un'altra (la riconnessione)."""

    async def __anext__(self):
        raise ConnectionError("giu'")


class _FintaSessioneDueConnessioni:
    def __init__(self, *connessioni):
        self._connessioni = list(connessioni)

    def ws_connect(self, url):
        return self._connessioni.pop(0)


@pytest.mark.asyncio
async def test_alla_seconda_connessione_lo_specchio_si_rilegge(monkeypatch):
    """Spec «una porta sola» §6. Ogni connessione emette «riconnessione», la
    PRIMA compresa (all'avvio, dopo il `load`, segue quindi un `reload` in
    piu', innocuo). Qui la prima connessione cade e ne segue una seconda:
    `get_states` deve girare una volta PER CONNESSIONE, cioe' due -- la
    seconda e' la rilettura dopo la riconnessione.

    Mutazione ESEGUITA: non registrare `mirror_reload_listener` sul client --
    rossa (nessuna chiamata a `get_states`). Che l'avvio lo registri davvero
    lo prova l'app avviata
    (`tests/test_cablaggio_dell_avvio.py::test_a_reconnection_rereads_the_state_mirror`)."""
    vero_sleep = asyncio.sleep

    async def _backoff_istantaneo(_secondi):
        await vero_sleep(0)   # il backoff di 10s fra due connessioni

    monkeypatch.setattr("hiris.app.proxy.ha_client.asyncio.sleep", _backoff_istantaneo)

    client = HAClient(base_url="http://ha.test", token="t")
    client._session = _FintaSessioneDueConnessioni(
        _FintoWSCheCade([]), _FintoWSEventi([]))
    # Il client che rilegge lo specchio e' la casa finta; quello che ascolta
    # gli eventi resta sul trasporto finto (vedi il docstring del modulo).
    house = CasaFinta(synthetic_inputs())
    cache = _specchio_caricato()
    client.add_topology_listener(mirror_reload_listener(house, cache))

    task = asyncio.create_task(client._ws_loop("ws://ha.test/api/websocket"))
    await vero_sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # una per connessione: la prima all'avvio, la seconda alla riconnessione
    assert _state_reads(house) == 2
    # E la rilettura e' arrivata nello specchio, che prima era vuoto.
    assert {e["id"] for e in cache.all_states()} == {
        s["entity_id"] for s in synthetic_inputs()["states"]}


@pytest.mark.asyncio
async def test_gli_altri_eventi_dell_anagrafe_non_rileggono_lo_specchio():
    """Mutazione ESEGUITA: togliere il `if event_type == "riconnessione"` --
    rossa (ogni evento di registro rilegge tutti gli stati)."""
    house = CasaFinta(synthetic_inputs())
    ascoltatore = mirror_reload_listener(house, _specchio_caricato())
    ascoltatore("floor_registry_updated")
    ascoltatore("entity_registry_updated")
    await asyncio.sleep(0.05)
    assert _state_reads(house) == 0
