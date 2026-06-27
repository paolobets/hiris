import time

import pytest
from aiohttp import web

from hiris.app.api.handlers_gateway_pending import (
    approve,
    build_actions,
    create_pending,
    list_pending,
    on_notification_action,
    parse_action,
    reject,
    take_pending,
)


def _entry(tmp_path, tier="yellow"):
    return create_pending(str(tmp_path), tool="call_ha_service",
                          inputs={"domain": "climate", "service": "set_temperature",
                                  "data": {"entity_id": "climate.soggiorno"}},
                          tier=tier, origin="mcp-gateway", label="climate.set_temperature")


def test_create_and_list_pending(tmp_path):
    e = _entry(tmp_path)
    assert e["status"] == "pending" and e["id"]
    pend = list_pending(str(tmp_path))
    assert len(pend) == 1 and pend[0]["id"] == e["id"]


def test_take_pending_is_single_use(tmp_path):
    e = _entry(tmp_path)
    assert take_pending(str(tmp_path), e["id"]) is not None
    assert take_pending(str(tmp_path), e["id"]) is None      # second take rejected
    assert list_pending(str(tmp_path)) == []                 # no longer pending


def test_take_pending_expired(tmp_path):
    e = _entry(tmp_path)
    # force expiry
    import json
    p = str(tmp_path / "gateway_pending.json")
    data = json.load(open(p))
    data[e["id"]]["expires"] = time.time() - 1
    json.dump(data, open(p, "w"))
    assert take_pending(str(tmp_path), e["id"]) is None
    assert list_pending(str(tmp_path)) == []


def test_parse_and_build_actions():
    acts = build_actions("abc123")
    approve_action = acts[0]["action"]
    assert parse_action(approve_action) == ("approve", "abc123")
    assert parse_action("HIRIS_GW:reject:xyz") == ("reject", "xyz")
    assert parse_action("garbage") is None
    assert parse_action("HIRIS_GW:delete:x") is None     # only approve/reject


class _FakeDispatcher:
    def __init__(self):
        self.calls = []

    async def dispatch(self, name, inputs, allowed_services=None, allowed_entities=None,
                       agent_id=None, cloud=True, **kw):
        self.calls.append((name, inputs, allowed_services))
        return {"ok": name}


def _app(tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["tool_dispatcher"] = _FakeDispatcher()
    return app


@pytest.mark.asyncio
async def test_approve_executes_once_and_scopes_whitelist(tmp_path):
    app = _app(tmp_path)
    e = _entry(tmp_path)
    res = await approve(app, e["id"])
    assert res["ok"] is True
    name, inputs, allowed = app["tool_dispatcher"].calls[0]
    assert name == "call_ha_service"
    assert allowed == ["climate.*"]                       # scoped to the held action
    # second approve fails (single-use)
    res2 = await approve(app, e["id"])
    assert res2["ok"] is False


@pytest.mark.asyncio
async def test_reject_does_not_execute(tmp_path):
    app = _app(tmp_path)
    e = _entry(tmp_path)
    assert reject(app, e["id"])["ok"] is True
    assert app["tool_dispatcher"].calls == []


@pytest.mark.asyncio
async def test_on_notification_action_approves(tmp_path):
    app = _app(tmp_path)
    e = _entry(tmp_path)
    await on_notification_action(app, {"action": f"HIRIS_GW:approve:{e['id']}"})
    assert len(app["tool_dispatcher"].calls) == 1
    assert list_pending(str(tmp_path)) == []
