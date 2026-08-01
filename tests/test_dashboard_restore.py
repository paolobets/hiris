import pytest

from hiris.app.api.handlers_dashboards import handle_restore_dashboard
from hiris.app.proxy.dashboard_backups import save_backup
from hiris.app.proxy.ha_client import HAClient


class FakeHA:
    def __init__(self, result=None):
        self.result = result or {"ok": True, "url_path": "casa-mia"}
        self.saved = None

    async def save_dashboard_config(self, url_path, config):
        self.saved = (url_path, config)
        return self.result


class FakeRequest:
    def __init__(self, app, url_path="casa-mia"):
        self.app = app
        self.match_info = {"url_path": url_path}


@pytest.mark.asyncio
async def test_restore_reapplies_latest_snapshot(tmp_path):
    old = {"views": [{"title": "VECCHIA"}]}
    save_backup(str(tmp_path), "casa-mia", old)
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", old)


@pytest.mark.asyncio
async def test_restore_without_backup_is_404(tmp_path):
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 404
    assert ha.saved is None


@pytest.mark.asyncio
async def test_restore_of_strategy_snapshot_succeeds(tmp_path):
    """Sequenza reale che si rompeva: replace su una plancia a strategia ->
    snapshot salvato -> Annulla -> save_dashboard_config con uno snapshot senza
    'views'. Qui usiamo il VERO HAClient (solo il WS e' finto) perche' il bug
    stava nella sua validazione, non nell'handler."""
    old = {"strategy": {"type": "areas"}}
    save_backup(str(tmp_path), "casa-mia", old)
    calls = []

    async def fake_ws(cmd, payload=None):
        calls.append((cmd, payload or {}))
        return {"success": True}

    ha = HAClient.__new__(HAClient)   # niente __init__: serve solo il WS
    ha._ws_command = fake_ws
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert calls == [("lovelace/config/save",
                      {"url_path": "casa-mia", "config": old})]


@pytest.mark.asyncio
async def test_restore_reports_ha_failure(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": []})
    ha = FakeHA(result={"error": "boom"})
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 502
