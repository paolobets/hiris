import pytest

from hiris.app.api.handlers_dashboards import handle_restore_dashboard
from hiris.app.proxy.dashboard_backups import save_backup


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
async def test_restore_reports_ha_failure(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": []})
    ha = FakeHA(result={"error": "boom"})
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 502
