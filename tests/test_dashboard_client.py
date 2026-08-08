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


# Review finale fetta E2, I-2: `list_dashboards` e' uscito da ha_client.py
# (orfano, nessun chiamante di produzione dal Task 7). I due test che lo
# esercitavano sono usciti con lui.


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
