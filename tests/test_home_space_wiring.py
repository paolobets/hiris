import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest

from hiris.app.home_space.store import HomeSpaceStore
from hiris.app.proxy.ha_client import HAClient
from hiris.app.server import schedule_behavior_reread, schedule_registry_rebuild

# La config minima che Home Assistant restituisce a `get_config`: da questa
# fetta la ricostruzione dell'anagrafe legge anche il sistema di riferimento
# della casa (unita', fuso, valuta). Un finto che non la dichiara e' un HA che
# non ha risposto -- e infatti `non_disponibili` lo direbbe. Che sia questo il
# comportamento e' provato a parte, in tests/test_home_space_reference.py.
_CONFIG = {"time_zone": "Europe/Rome", "currency": "EUR", "language": "it",
           "unit_system": {"temperature": "C", "length": "km"}}


_VUOTI = {"piani": [], "aree": [], "dispositivi": [], "entita": [],
          "etichette": [], "categorie": [], "integrazioni": []}


@pytest.fixture
def archivio(tmp_path):
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    yield a
    a.close()


@pytest.mark.asyncio
async def test_una_raffica_di_eventi_ricostruisce_una_volta_sola(archivio):
    client = AsyncMock()
    client.read_registries = AsyncMock(return_value=(_VUOTI, []))
    client.get_config = AsyncMock(return_value=_CONFIG)
    innesca = schedule_registry_rebuild(client, archivio, delay=0.05)
    for _ in range(10):
        innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert client.read_registries.await_count == 1


@pytest.mark.asyncio
async def test_due_raffiche_distanti_ricostruiscono_due_volte(archivio):
    client = AsyncMock()
    client.read_registries = AsyncMock(return_value=(_VUOTI, []))
    client.get_config = AsyncMock(return_value=_CONFIG)
    innesca = schedule_registry_rebuild(client, archivio, delay=0.05)
    innesca("floor_registry_updated")
    await asyncio.sleep(0.2)
    innesca("floor_registry_updated")
    await asyncio.sleep(0.2)
    assert client.read_registries.await_count == 2
    # Contare le chiamate non basta: `_fra_poco` ingoia ogni eccezione per non
    # uccidere l'ascoltatore, quindi due ricostruzioni FALLITE darebbero lo
    # stesso conteggio. Solo l'archivio scritto prova che sono riuscite.
    assert archivio.updated_at() is not None


@pytest.mark.asyncio
async def test_una_ricostruzione_fallita_non_uccide_l_ascoltatore(archivio):
    client = AsyncMock()
    client.read_registries = AsyncMock(side_effect=[OSError("HA giu'"), (_VUOTI, [])])
    client.get_config = AsyncMock(return_value=_CONFIG)
    innesca = schedule_registry_rebuild(client, archivio, delay=0.05)
    innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert client.read_registries.await_count == 2


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
    guarda_finta.assert_awaited_once_with(force=True)


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
    produzione non arriva mai. Stessa forma di _FintoWS in test_ws_batch.py."""

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
async def test_invalidare_il_registro_lo_fa_ricaricare_prima_della_scadenza():
    """Il cuore della fetta. Senza `invalidate()`, `ensure_fresh` guarda solo
    l'eta' e torna subito: l'evento non servirebbe a niente."""
    from hiris.app.action.registry import ServiceRegistry

    class _Ha:
        def __init__(self):
            self.letture = 0

        async def get_services(self):
            self.letture += 1
            return [{"domain": "light", "services": {"turn_on": {}}}]

    ha = _Ha()
    r = ServiceRegistry()
    await r.ensure_fresh(ha)
    assert ha.letture == 1

    # Senza invalidare: nessuna seconda lettura, l'eta' e' minima.
    await r.ensure_fresh(ha)
    assert ha.letture == 1

    r.invalidate()
    await r.ensure_fresh(ha)
    assert ha.letture == 2, (
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


def test_l_avvio_CABLA_davvero_l_ascoltatore_dei_servizi():
    """Senza questa prova, `invalidate()` e la famiglia di eventi sarebbero un
    meccanismo che nessuno collega -- e in produzione il registro continuerebbe
    a rinfrescarsi solo a scadenza, con la suite tutta verde.

    Si legge il blocco dal sorgente vero di `_on_startup`, come fa
    `tests/test_websocket_startup.py` e per la stessa ragione: provare la
    funzione non dimostra che qualcuno la chiami."""
    import inspect

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert "add_service_listener" in src, (
        "nessuno registra l'ascoltatore dei servizi: gli eventi arrivano e "
        "non invalidano niente")
    assert ".invalidate()" in src, (
        "l'ascoltatore c'e' ma non invalida: il registro resta vecchio")
