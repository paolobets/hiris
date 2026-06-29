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
