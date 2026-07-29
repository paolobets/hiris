import pytest
from aiohttp import web

from hiris.app.api.handlers_proposals import handle_apply_proposal
from hiris.app.watcher.agentbots import load_agentbots, validate_agentbot


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
        self.created = []
    async def create_automation(self, config, automation_id=None):
        self.created.append(config)
        return self._result


def _app(store, ha=None):
    app = web.Application()
    app["proposal_store"] = store
    if ha is not None:
        app["ha_client"] = ha
    app.router.add_post("/api/proposals/{proposal_id}/apply", handle_apply_proposal)
    return app


@pytest.mark.asyncio
async def test_apply_ha_automation_writes_to_ha(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_automation",
                                "config": {"alias": "X", "trigger": [], "action": []}})
    ha = _FakeHA({"ok": True, "id": "999"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    body = await r.json()
    assert body["ok"] is True and body["automation_id"] == "999"
    assert len(ha.created) == 1                 # actually written to HA
    assert store.applied == ["p1"]              # marked applied only after HA ok


@pytest.mark.asyncio
async def test_apply_forwards_config_id_to_ha_for_modify(aiohttp_client):
    """MODIFY end-to-end: a proposal whose config carries an id must reach
    ha.create_automation with that id intact (so HA overwrites, not duplicates)."""
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_automation",
                                "config": {"id": "555", "alias": "X", "trigger": [], "action": []}})
    ha = _FakeHA({"ok": True, "id": "555"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    assert ha.created[0].get("id") == "555"
    assert (await r.json())["automation_id"] == "555"


@pytest.mark.asyncio
async def test_apply_ha_automation_not_marked_when_ha_fails(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_automation",
                                "config": {"alias": "X"}})
    ha = _FakeHA({"error": "HA ha rifiutato la config (400): bad"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 502
    assert store.applied == []                  # NOT marked applied on HA failure


@pytest.mark.asyncio
async def test_apply_non_pending_returns_409(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "applied", "type": "ha_automation"})
    client = await aiohttp_client(_app(store, _FakeHA({"ok": True})))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 409


class _RegisterSpy:
    def __init__(self):
        self.calls = 0

    async def __call__(self, app):
        self.calls += 1


def _agent_app(store, tmp_path, *, register=None):
    app = web.Application()
    app["proposal_store"] = store
    app["data_dir"] = str(tmp_path)
    app["user_agentbots"] = []
    app["register_agentbot_schedules"] = register if register is not None else _RegisterSpy()
    app.router.add_post("/api/proposals/{proposal_id}/apply", handle_apply_proposal)
    return app


VALID_AGENT_CONFIG = {
    "name": "Umidita bagno",
    "trigger": {"type": "event", "entity_id": "sensor.bagno_umidita", "operator": ">", "threshold": 70},
    "reasoning": {"enabled": True, "model": "auto"},
    "action": {"type": "notify", "message": "Umidita alta in bagno"},
    "severity": "warn",
}


@pytest.mark.asyncio
async def test_apply_hiris_agent_creates_agentbot(aiohttp_client, tmp_path):
    """Approving a `hiris_agent` proposal must actually materialize the
    Agentbot (the old behaviour only flipped the proposal's status, leaving
    "Attiva" a button that activated nothing). The config also carries an
    LLM-authored `allowed_tools` -- not part of the Agentbot schema at all --
    proving `validate_agentbot`'s whitelist reconstruction strips it rather
    than letting it ride along into the persisted config."""
    config = {**VALID_AGENT_CONFIG, "allowed_tools": ["shell_exec", "http_request"]}
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "hiris_agent",
                                "config": config})
    spy = _RegisterSpy()
    app = _agent_app(store, tmp_path, register=spy)
    client = await aiohttp_client(app)
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    body = await r.json()
    assert body["ok"] is True
    assert store.applied == ["p1"]                     # marked applied only after creation

    persisted = load_agentbots(str(tmp_path))
    assert len(persisted) == 1
    agentbot = persisted[0]
    assert agentbot["name"] == "Umidita bagno"
    assert agentbot["action"]["type"] == "notify"
    assert "allowed_tools" not in agentbot              # never smuggled through
    assert validate_agentbot(agentbot) == agentbot      # persisted shape re-validates clean

    # schedules/caches refreshed exactly like the /api/agentbots create path
    assert spy.calls == 1
    assert app["user_agentbots"] == persisted


@pytest.mark.asyncio
async def test_apply_hiris_agent_invalid_config_not_created_stays_pending(aiohttp_client, tmp_path):
    """A malformed trigger (missing entity_id/operator/threshold) makes the
    whole Agentbot unsalvageable -- validate_agentbot returns None. Nothing
    must be created, the proposal must NOT be marked applied (stays pending
    so the user/Brain can retry with a fixed config), and the scheduler/cache
    must not be touched."""
    bad_config = {**VALID_AGENT_CONFIG, "trigger": {"type": "event"}}
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "hiris_agent",
                                "config": bad_config})
    spy = _RegisterSpy()
    app = _agent_app(store, tmp_path, register=spy)
    client = await aiohttp_client(app)
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 400
    assert "error" in (await r.json())
    assert store.applied == []
    assert load_agentbots(str(tmp_path)) == []
    assert spy.calls == 0

    # proposal is still there and still pending -> retryable
    p = await store.get("p1")
    assert p["status"] == "pending"


@pytest.mark.asyncio
async def test_apply_hiris_agent_without_data_dir_returns_503(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "hiris_agent",
                                "config": VALID_AGENT_CONFIG})
    app = web.Application()
    app["proposal_store"] = store
    app.router.add_post("/api/proposals/{proposal_id}/apply", handle_apply_proposal)
    client = await aiohttp_client(app)
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 503
    assert store.applied == []


@pytest.mark.asyncio
async def test_apply_ha_automation_without_ha_client_returns_503(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_automation",
                                "config": {"alias": "X"}})
    client = await aiohttp_client(_app(store))   # no ha_client registered
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 503
    assert store.applied == []
