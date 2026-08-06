import pytest
from hiris.app.proxy.ha_client import HAClient


class FakeWS:
    """Registra i comandi WS e risponde con code preimpostate."""
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def command(self, cmd, payload=None):
        self.calls.append((cmd, payload or {}))
        return self.responses.get(cmd, {"success": True, "result": None})


def _client(ws):
    c = HAClient.__new__(HAClient)          # niente __init__: serve solo il WS
    c._ws_command = ws.command
    return c


@pytest.mark.asyncio
async def test_list_dashboards_returns_raw_entries():
    """Il client riferisce cio' che HA dice (compresi id/icon/require_admin/
    show_in_sidebar), il consumatore sceglie cosa tenere — stesso principio
    gia' applicato a get_config_entries. Prima potava a {url_path, title,
    mode}: qui si verifica che NON lo faccia piu'."""
    voce = {"id": "1", "url_path": "casa-mia", "title": "Casa Mia", "mode": "storage",
            "icon": "mdi:home", "require_admin": False, "show_in_sidebar": True}
    ws = FakeWS({"lovelace/dashboards/list": {"success": True, "result": [voce]}})
    out = await _client(ws).list_dashboards()
    assert out == [voce]
    assert ws.calls[0][0] == "lovelace/dashboards/list"


@pytest.mark.asyncio
async def test_list_dashboards_error_is_returned_not_raised():
    ws = FakeWS({"lovelace/dashboards/list": {"success": False, "error": {"message": "boom"}}})
    out = await _client(ws).list_dashboards()
    assert isinstance(out, dict) and "error" in out


@pytest.mark.asyncio
async def test_save_dashboard_config_sends_url_path_and_config():
    ws = FakeWS({"lovelace/config/save": {"success": True}})
    cfg = {"views": [{"title": "Home", "cards": []}]}
    out = await _client(ws).save_dashboard_config("casa-mia", cfg)
    assert out == {"ok": True, "url_path": "casa-mia"}
    assert ws.calls[0] == ("lovelace/config/save", {"url_path": "casa-mia", "config": cfg})


@pytest.mark.asyncio
async def test_save_dashboard_config_accepts_strategy_config():
    """HA ammette anche le config a strategia ({"strategy": {...}}, senza
    'views'): sono le plance generate da template. Il client deve accettarle,
    altrimenti il ripristino di uno snapshot di quel tipo (pulsante Annulla)
    fallirebbe con 502 pur avendo lo snapshot su disco."""
    ws = FakeWS({"lovelace/config/save": {"success": True}})
    cfg = {"strategy": {"type": "areas"}}
    out = await _client(ws).save_dashboard_config("casa-mia", cfg)
    assert out == {"ok": True, "url_path": "casa-mia"}
    assert ws.calls[0] == ("lovelace/config/save", {"url_path": "casa-mia", "config": cfg})


@pytest.mark.asyncio
async def test_save_dashboard_config_rejects_config_without_views_or_strategy():
    ws = FakeWS({})
    out = await _client(ws).save_dashboard_config("casa-mia", {"nope": 1})
    assert "error" in out
    assert ws.calls == [], "config invalida: non deve partire alcun comando WS"


@pytest.mark.asyncio
async def test_save_dashboard_config_rejects_non_dict():
    ws = FakeWS({})
    out = await _client(ws).save_dashboard_config("casa-mia", ["views"])
    assert "error" in out
    assert ws.calls == [], "config invalida: non deve partire alcun comando WS"
