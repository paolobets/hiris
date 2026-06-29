import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    async def get_automation_config(self, automation_id):
        return {"id": "123", "alias": "Test", "trigger": [], "action": [],
                "_got": automation_id}


@pytest.mark.asyncio
async def test_dispatch_get_automation_config():
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_automation_config", {"automation_id": "automation.foo"})
    assert out["alias"] == "Test"
    assert out["_got"] == "automation.foo"


@pytest.mark.asyncio
async def test_dispatch_get_automation_config_ignores_whitelist():
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_automation_config", {"automation_id": "foo"},
                           allowed_entities=["light.*"])
    assert out["alias"] == "Test"      # read, not blocked


class _FakeHASvc:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return True


@pytest.mark.asyncio
async def test_create_task_rejects_unknown_action_type():
    class _Eng:  # minimal task engine stand-in; should NOT be reached
        pass
    d = ToolDispatcher(_FakeHASvc(), notify_config={})
    d.set_task_engine(_Eng())
    out = await d.dispatch("create_task", {"label": "x", "trigger": {}, "actions": [
        {"type": "scene", "entity_id": "scene.evil"}]})
    assert "error" in out and "not permitted" in out["error"]


@pytest.mark.asyncio
async def test_call_ha_service_failclosed_broadcast_without_target():
    d = ToolDispatcher(_FakeHASvc(), notify_config={})
    out = await d.dispatch("call_ha_service",
                           {"domain": "light", "service": "turn_on"},
                           allowed_services=["light.*"], allowed_entities=["light.*"])
    assert "error" in out               # no target entity under active whitelist -> blocked


@pytest.mark.asyncio
async def test_call_ha_service_with_target_ok():
    ha = _FakeHASvc()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("call_ha_service",
                           {"domain": "light", "service": "turn_on",
                            "data": {"entity_id": "light.sala"}},
                           allowed_services=["light.*"], allowed_entities=["light.*"])
    assert ha.calls == [("light", "turn_on", {"entity_id": "light.sala"})]
