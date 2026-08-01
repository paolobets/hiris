import pytest
from hiris.app.proxy.supervisor_client import SupervisorClient


class FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Registra le GET e risponde con code preimpostate per path."""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers_seen = []

    def get(self, url, **kw):
        self.calls.append(url)
        self.headers_seen.append(kw.get("headers") or {})
        for path, resp in self.routes.items():
            if url.endswith(path):
                return resp
        return FakeResp(404, {})


def _client(session):
    c = SupervisorClient.__new__(SupervisorClient)
    c._token = "tok"
    c._base = "http://supervisor"
    c._session = session
    return c


@pytest.mark.asyncio
async def test_get_addons_estrae_i_campi_utili():
    session = FakeSession({"/addons": FakeResp(200, {"result": "ok", "data": {"addons": [
        {"slug": "core_mosquitto", "name": "Mosquitto", "state": "started",
         "version": "6.4", "update_available": False, "irrilevante": 1},
    ]}})})
    out = await _client(session).get_addons()
    assert out == [{"slug": "core_mosquitto", "name": "Mosquitto", "state": "started",
                    "version": "6.4", "update_available": False}]


@pytest.mark.asyncio
async def test_autenticazione_bearer():
    session = FakeSession({"/addons": FakeResp(200, {"data": {"addons": []}})})
    await _client(session).get_addons()
    assert session.headers_seen[0]["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_get_host_info_riporta_lo_spazio_disco():
    session = FakeSession({"/host/info": FakeResp(200, {"data": {
        "disk_total": 32.0, "disk_used": 20.0, "disk_free": 12.0, "altro": "x"}})})
    out = await _client(session).get_host_info()
    assert out == {"disk_total": 32.0, "disk_used": 20.0, "disk_free": 12.0}


@pytest.mark.asyncio
async def test_get_available_updates():
    session = FakeSession({"/available_updates": FakeResp(200, {"data": {"available_updates": [
        {"name": "Home Assistant Core", "update_type": "core", "version_latest": "2026.8.0"},
    ]}})})
    out = await _client(session).get_available_updates()
    assert out == [{"name": "Home Assistant Core", "update_type": "core",
                    "version_latest": "2026.8.0"}]


@pytest.mark.asyncio
async def test_supervisor_non_disponibile_degrada_a_vuoto():
    """Installazione senza Supervisor: 404 su tutto, nessuna eccezione."""
    client = _client(FakeSession({}))
    assert await client.get_addons() == []
    assert await client.get_host_info() == {}
    assert await client.get_available_updates() == []


@pytest.mark.asyncio
async def test_errore_di_rete_degrada_a_vuoto():
    class BoomSession:
        def get(self, url, **kw):
            raise OSError("connessione rifiutata")
    assert await _client(BoomSession()).get_addons() == []


@pytest.mark.asyncio
async def test_payload_malformato_degrada_a_vuoto():
    session = FakeSession({"/addons": FakeResp(200, {"data": "non-un-dict"})})
    assert await _client(session).get_addons() == []
