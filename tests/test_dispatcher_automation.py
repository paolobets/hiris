import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.get_automation_config_calls = []

    async def get_automation_config(self, automation_id):
        self.get_automation_config_calls.append(automation_id)
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


# --- review A/#4 (SSRF/path-injection): get_automation_config must validate
# automation_id BEFORE reaching ha_client, mirroring trigger/toggle's
# _AUTOMATION_ID_RE check, so a hostile id never reaches the HA client at all.

@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    "automation.x/../../config/core/config",
    "x/../../config/core/config",
    "automation.x y",
    "automation.http://evil.com",
    "../../../api/config/core/config",
    "automation.foo?x=1",
])
async def test_dispatch_get_automation_config_rejects_traversal(payload):
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_automation_config", {"automation_id": payload})
    assert "error" in out
    assert ha.get_automation_config_calls == []  # no request ever built downstream


@pytest.mark.asyncio
async def test_dispatch_get_automation_config_valid_id_reaches_ha_client():
    ha = _FakeHA()
    d = ToolDispatcher(ha, notify_config={})
    out = await d.dispatch("get_automation_config", {"automation_id": "automation.my_id"})
    assert out["alias"] == "Test"
    assert ha.get_automation_config_calls == ["automation.my_id"]


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
    # light tier green so the semaforo gate itself allows through, isolating
    # the per-agent whitelist's own broadcast-without-target fail-closed check.
    d = ToolDispatcher(_FakeHASvc(), notify_config={},
                       execute_policy={"tiers": {"light": "green"}})
    out = await d.dispatch("call_ha_service",
                           {"domain": "light", "service": "turn_on"},
                           allowed_services=["light.*"], allowed_entities=["light.*"])
    assert "error" in out               # no target entity under active whitelist -> blocked


@pytest.mark.asyncio
async def test_call_ha_service_with_target_ok():
    ha = _FakeHASvc()
    d = ToolDispatcher(ha, notify_config={}, execute_policy={"tiers": {"light": "green"}})
    out = await d.dispatch("call_ha_service",
                           {"domain": "light", "service": "turn_on",
                            "data": {"entity_id": "light.sala"}},
                           allowed_services=["light.*"], allowed_entities=["light.*"])
    assert ha.calls == [("light", "turn_on", {"entity_id": "light.sala"})]


# --- list_tasks MCP dispatcher fallback (Task 4 / Fase 1 review, gap 1):
# dispatcher.py resolves the filter as inputs.get("agent_id") or
# inputs.get("chatbot_id") so an external MCP client still using the old
# "chatbot_id" key keeps getting a FILTERED list instead of silently falling
# back to the unfiltered one. These exercise dispatch() end-to-end (not just
# the tool schema) and record what the task engine actually received.

class _ListTasksEngine:
    def __init__(self):
        self.calls = []

    def list_tasks(self, agent_id=None, status=None):
        self.calls.append({"agent_id": agent_id, "status": status})
        return []


@pytest.mark.asyncio
async def test_list_tasks_dispatch_filters_by_new_key():
    d = ToolDispatcher(_FakeHASvc(), notify_config={})
    eng = _ListTasksEngine()
    d.set_task_engine(eng)
    await d.dispatch("list_tasks", {"agent_id": "agent-x"})
    assert eng.calls == [{"agent_id": "agent-x", "status": None}]


@pytest.mark.asyncio
async def test_list_tasks_dispatch_falls_back_to_legacy_chatbot_id_key():
    d = ToolDispatcher(_FakeHASvc(), notify_config={})
    eng = _ListTasksEngine()
    d.set_task_engine(eng)
    await d.dispatch("list_tasks", {"chatbot_id": "agent-x"})
    assert eng.calls == [{"agent_id": "agent-x", "status": None}]


@pytest.mark.asyncio
async def test_list_tasks_dispatch_new_key_wins_when_both_present():
    d = ToolDispatcher(_FakeHASvc(), notify_config={})
    eng = _ListTasksEngine()
    d.set_task_engine(eng)
    await d.dispatch("list_tasks", {"agent_id": "new-agent", "chatbot_id": "old-agent"})
    assert eng.calls == [{"agent_id": "new-agent", "status": None}]
