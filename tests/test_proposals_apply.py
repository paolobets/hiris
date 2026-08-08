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


@pytest.mark.asyncio
async def test_apply_ha_automation_without_ha_client_returns_503(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_automation",
                                "config": {"alias": "X"}})
    client = await aiohttp_client(_app(store))   # no ha_client registered
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 503
    assert store.applied == []


@pytest.mark.asyncio
async def test_apply_legacy_hiris_agent_falls_through_to_status_only(aiohttp_client, caplog):
    """fetta E3 Task 3: il ramo dedicato "hiris_agent" (materializzava un
    Agentbot) e' uscito insieme all'intero strato Agentbot. Una proposta
    "hiris_agent" gia' su disco da prima di questo task (upgrade da
    un'installazione precedente) non deve piu' tentare di materializzare
    nulla: cade nel ramo generico status-only, marcata applied SENZA alcun
    effetto, con un warning esplicito -- il silenzio e' dichiarato, non
    muto."""
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "hiris_agent",
                                "config": {"name": "vecchio agente"}})
    client = await aiohttp_client(_app(store))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    assert (await r.json()) == {"ok": True}
    assert store.applied == ["p1"]
    assert any("tipo non gestito" in rec.message for rec in caplog.records)
