"""Il websocket di lunga vita del client: la prima connessione, le cadute,
l'autenticazione rifiutata, l'iscrizione alle integrazioni (Tappa 2, Task 7).

Gira il codice VERO di `HAClient._ws_loop` sulla connessione della casa finta
(`scripts/casa_finta.py::SilentConnection`), che parla nella forma dei
messaggi di Home Assistant letta al tag `2026.9.4` (vedi il suo docstring).

**Cosa difende.**

- *La prima connessione non rilegge* (D2 del piano, «prima l'iscrizione»):
  l'avvio si iscrive e POI legge la casa una volta; l'avviso «riconnessione»
  parte solo dalla seconda connessione in poi -- o dalla prima, se l'avvio ha
  letto prima che Home Assistant rispondesse (`reread_after_first_connection`).
- *`ws_ready` dice la verita'*: acceso quando Home Assistant ha confermato
  l'iscrizione agli stati, spento quando la connessione cade (S-04).
- *Un gettone rifiutato non spegne i sensi per sempre* (S-04): fino al
  03/10/2026 `_ws_loop` faceva `return` e l'add-on restava sordo fino al
  riavvio.
- *Le integrazioni si seguono per evento* (aggiunta di Paolo al Task 7,
  «avviso»): l'elenco iniziale e i cambi arrivano agli ascoltatori cosi' come
  Home Assistant li manda.
"""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casa_finta
from casa_finta import CasaFinta

from hiris.app.proxy import ha_client as ha_client_module
from hiris.app.proxy.ha_client import HAClient
from tests._casa_sintetica import synthetic_inputs

#: Il tetto delle attese: una connessione finta non fa I/O.
CEILING_S = 2


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    """Le attese fra un tentativo e il successivo, a zero: si prova la
    sequenza, non l'orologio. Le attese vere sono provate a parte."""
    monkeypatch.setattr(ha_client_module, "RECONNECT_DELAY_S", 0)
    monkeypatch.setattr(ha_client_module, "AUTH_RETRY_FIRST_S", 0)


def _client(connection=None) -> tuple[HAClient, casa_finta.SilentConnection]:
    client = HAClient("http://casa.invalid", "gettone")
    client._session = connection or casa_finta.SilentConnection()
    return client, client._session


async def _until(condition, what: str) -> None:
    async def poll():
        while not condition():
            await asyncio.sleep(0)
    try:
        await asyncio.wait_for(poll(), CEILING_S)
    except TimeoutError:
        raise AssertionError(f"non e' successo: {what}") from None


async def _settle() -> None:
    """Lascia girare il ciclo finche' i messaggi in coda sono smistati."""
    for _ in range(20):
        await asyncio.sleep(0)


async def _stop(client: HAClient) -> None:
    client._ws_task.cancel()
    try:
        await client._ws_task
    except asyncio.CancelledError:
        pass


# ── la prima connessione ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_la_prima_connessione_non_avvisa_la_seconda_si():
    client, connection = _client()
    heard: list[str] = []
    client.add_topology_listener(heard.append)
    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "prima connessione in ascolto")
    assert heard == []
    connection.drop()
    await _until(lambda: connection.listening == 2, "seconda connessione in ascolto")
    assert heard == ["riconnessione"]
    await _stop(client)


@pytest.mark.asyncio
async def test_chi_ha_letto_prima_della_connessione_si_fa_avvisare_anche_dalla_prima():
    """Home Assistant giu' all'avvio: l'avvio ha letto (e fallito) prima che il
    websocket si aprisse, e la prima connessione e' quella che deve far
    rileggere."""
    client, connection = _client()
    heard: list[str] = []
    client.add_topology_listener(heard.append)
    client.reread_after_first_connection()
    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "prima connessione in ascolto")
    assert heard == ["riconnessione"]
    await _stop(client)


@pytest.mark.asyncio
async def test_se_la_prima_connessione_e_gia_avvenuta_l_avviso_parte_subito():
    """La corsa: l'avvio smette di aspettare proprio mentre la connessione
    arriva. Chiedere l'avviso a connessione gia' avvenuta lo da' subito,
    invece di perderlo."""
    client, connection = _client()
    heard: list[str] = []
    client.add_topology_listener(heard.append)
    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "prima connessione in ascolto")
    client.reread_after_first_connection()
    assert heard == ["riconnessione"]
    await _stop(client)


# ── ws_ready ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ws_ready_si_accende_alla_conferma_e_si_spegne_alla_caduta():
    client, connection = _client()
    assert not client.ws_ready.is_set()
    await client.start_websocket()
    await asyncio.wait_for(client.ws_ready.wait(), CEILING_S)
    # Acceso solo DOPO che Home Assistant ha confermato l'iscrizione agli
    # stati: chi legge la casa dopo `ws_ready` non perde un cambio.
    states = next(m for m in connection.sent if m.get("event_type") == "state_changed")
    assert states["type"] == "subscribe_events"
    connection.drop()
    await _until(lambda: not client.ws_ready.is_set() or connection.listening == 2,
                 "la caduta spegne ws_ready")
    await _stop(client)
    assert not client.ws_ready.is_set()


@pytest.mark.asyncio
async def test_ws_ready_aspetta_la_conferma_dell_iscrizione_agli_stati():
    """Senza la conferma di Home Assistant `ws_ready` resta spento: la
    connessione e' aperta, ma l'iscrizione non e' ancora sicura."""
    class Unconfirmed(casa_finta.SilentConnection):
        def _confirm(self, subscription: int) -> None:
            return None

    client, connection = _client(Unconfirmed())
    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "connessione in ascolto")
    await _settle()
    assert not client.ws_ready.is_set()
    await _stop(client)


# ── l'autenticazione rifiutata (S-04) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_un_gettone_rifiutato_si_riprova_e_la_seconda_connessione_accende_i_sensi(caplog):
    client, connection = _client()
    connection.refuse_next_auth()
    await client.start_websocket()
    await asyncio.wait_for(client.ws_ready.wait(), CEILING_S)
    assert connection.opened == 2
    assert connection.listening == 1
    # Il motivo che Home Assistant ha scritto arriva nel registro.
    assert casa_finta.INVALID_TOKEN in caplog.text
    await _stop(client)


@pytest.mark.asyncio
async def test_l_attesa_dopo_un_rifiuto_cresce_fino_al_tetto(monkeypatch):
    """Ogni rifiuto e' un «Login attempt failed» fra le notifiche di Home
    Assistant (`http/ban.py`, `process_wrong_login`): l'attesa raddoppia, fino
    al tetto, e torna alla prima dopo un'autenticazione riuscita."""
    waited: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        # `asyncio.sleep` e' uno solo: anche l'attesa della prova passa di
        # qui, con zero. Contano le attese del ciclo.
        if seconds:
            waited.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(ha_client_module, "AUTH_RETRY_FIRST_S", 10)
    monkeypatch.setattr(ha_client_module, "AUTH_RETRY_CEILING_S", 35)
    monkeypatch.setattr(ha_client_module.asyncio, "sleep", sleep)
    client, connection = _client()
    for _ in range(4):
        connection.refuse_next_auth()
    await client.start_websocket()
    await _until(lambda: connection.listening == 1, "connessione accettata")
    assert waited[:4] == [10, 20, 35, 35]
    await _stop(client)


# ── le integrazioni ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_l_elenco_iniziale_e_i_cambi_arrivano_come_li_manda_home_assistant():
    rows = synthetic_inputs()["registries"]["integrazioni"]
    house = CasaFinta(synthetic_inputs())
    heard: list = []
    topology: list[str] = []
    house.add_integration_listener(heard.append)
    house.add_topology_listener(topology.append)
    await house.start_websocket()
    await _until(lambda: heard, "l'elenco iniziale")
    assert heard == [[{"type": None, "entry": row} for row in rows]]
    changed = {**rows[0], "state": "setup_error"}
    assert house._session.push_config_entry_change("updated", changed)
    # Un evento di stato DOPO quello delle integrazioni: il ciclo e' vivo.
    assert house._session.push_event("floor_registry_updated", {})
    await _until(lambda: topology, "l'evento successivo")
    assert heard[-1] == [{"type": "updated", "entry": changed}]
    # Il messaggio delle integrazioni porta una LISTA in `event`: smistarlo
    # come un evento del bus faceva cadere la connessione.
    assert house._session.opened == 1
    await _stop(house)


@pytest.mark.asyncio
async def test_alla_riconnessione_l_elenco_iniziale_torna():
    house = CasaFinta(synthetic_inputs())
    heard: list = []
    house.add_integration_listener(heard.append)
    await house.start_websocket()
    await _until(lambda: len(heard) == 1, "il primo elenco")
    house._session.drop()
    await _until(lambda: len(heard) == 2, "l'elenco dopo la riconnessione")
    assert all(change["type"] is None for change in heard[1])
    subscriptions = [m for m in house._session.sent if m["type"] == "config_entries/subscribe"]
    assert len(subscriptions) == 2
    await _stop(house)


@pytest.mark.asyncio
async def test_un_iscrizione_alle_integrazioni_rifiutata_si_dice(caplog):
    class Refusing(casa_finta.SilentConnection):
        async def send_json(self, payload):
            if payload.get("type") == "config_entries/subscribe":
                self.sent.append(payload)
                self._inbox.put_nowait({
                    "id": payload["id"], "type": "result", "success": False,
                    "error": {"code": "unauthorized", "message": "Unauthorized"}})
                return None
            return await super().send_json(payload)

    client, _connection = _client(Refusing())
    heard: list = []
    client.add_integration_listener(heard.append)
    await client.start_websocket()
    await asyncio.wait_for(client.ws_ready.wait(), CEILING_S)
    await _settle()
    assert heard == []
    assert "config_entries/subscribe" in caplog.text and "Unauthorized" in caplog.text
    await _stop(client)
