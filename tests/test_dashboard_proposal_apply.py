import pytest
from hiris.app.api.handlers_proposals import handle_apply_proposal


class FakeStore:
    def __init__(self, proposal):
        self.proposal = proposal
        self.applied = None

    async def get(self, pid):
        return self.proposal

    async def apply(self, pid):
        self.applied = pid
        return True


class FakeHA:
    def __init__(self):
        self.saved = None

    async def get_lovelace_config(self, url_path):
        return {"views": [{"title": "VECCHIA"}]}

    async def save_dashboard_config(self, url_path, config):
        self.saved = (url_path, config)
        return {"ok": True, "url_path": url_path}


class FakeRequest:
    def __init__(self, app, pid="p1"):
        self.app = app
        self.match_info = {"proposal_id": pid}


@pytest.mark.asyncio
async def test_apply_replace_proposal_writes_snapshot(tmp_path):
    from hiris.app.proxy.dashboard_backups import latest_backup
    new_cfg = {"views": [{"title": "NUOVA"}]}
    store = FakeStore({
        "id": "p1", "status": "pending", "type": "ha_dashboard",
        "config": {"kind": "dashboard", "mode": "replace",
                   "slug": "casa-mia", "ha_config": new_cfg},
    })
    ha = FakeHA()
    app = {"proposal_store": store, "ha_client": ha, "data_dir": str(tmp_path)}
    resp = await handle_apply_proposal(FakeRequest(app))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", new_cfg)
    assert store.applied == "p1"
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "VECCHIA"}]}
