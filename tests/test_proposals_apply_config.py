import pytest
from aiohttp import web
from hiris.app.api.handlers_proposals import handle_apply_proposal


class _FakeProposalStore:
    def __init__(self, proposal):
        self._p = proposal
        self.applied = []
    async def get(self, pid):
        return dict(self._p) if self._p and self._p.get("id") == pid else None
    async def apply(self, pid):
        self.applied.append(pid)
        return True


class _FakeHA:
    def __init__(self, result):
        self._result = result
        self.calls = []
    async def create_script(self, object_id, config):
        self.calls.append(("script", object_id)); return self._result
    async def create_scene(self, scene_id, config):
        self.calls.append(("scene", scene_id)); return self._result
    async def create_dashboard(self, url_path, title, config, icon=None, show_in_sidebar=True):
        self.calls.append(("dashboard", url_path)); return self._result


def _app(store, ha=None):
    app = web.Application()
    app["proposal_store"] = store
    if ha is not None:
        app["ha_client"] = ha
    app.router.add_post("/api/proposals/{proposal_id}/apply", handle_apply_proposal)
    return app


def _script_proposal():
    return {"id": "p1", "status": "pending", "type": "ha_script",
            "config": {"kind": "script", "slug": "luci_sera", "name": "Luci sera",
                       "icon": None, "show_in_sidebar": None, "ha_config": {"sequence": []}}}


@pytest.mark.asyncio
async def test_apply_script_writes_to_ha(aiohttp_client):
    store = _FakeProposalStore(_script_proposal())
    ha = _FakeHA({"ok": True, "id": "luci_sera"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    assert ha.calls == [("script", "luci_sera")]
    assert store.applied == ["p1"]


@pytest.mark.asyncio
async def test_apply_script_not_marked_when_ha_fails(aiohttp_client):
    store = _FakeProposalStore(_script_proposal())
    ha = _FakeHA({"error": "HA ha rifiutato la config (400): bad"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 502
    assert store.applied == []


@pytest.mark.asyncio
async def test_apply_dashboard_proposal(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_dashboard",
        "config": {"kind": "dashboard", "slug": "casa-mia", "name": "Casa Mia",
                   "icon": "mdi:home", "show_in_sidebar": True,
                   "ha_config": {"views": []}}})
    ha = _FakeHA({"ok": True, "url_path": "casa-mia"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    assert ha.calls == [("dashboard", "casa-mia")]


@pytest.mark.asyncio
async def test_apply_config_without_ha_client_returns_503(aiohttp_client):
    store = _FakeProposalStore(_script_proposal())
    client = await aiohttp_client(_app(store))   # no ha_client
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 503
    assert store.applied == []


@pytest.mark.asyncio
async def test_apply_script_proposal_missing_kind_returns_502(aiohttp_client):
    # Simulates a proposal created via create_automation_proposal (chat tool), which
    # does NOT run inputs through normalize_config_inputs: type matches _CONFIG_TYPES
    # but config lacks "kind". Must not raise KeyError inside apply_ha_config.
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_script",
        "config": {"slug": "luci_sera", "ha_config": {"sequence": []}}})
    ha = _FakeHA({"ok": True, "id": "luci_sera"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 502
    assert ha.calls == []
    assert store.applied == []
