import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.chatbot_engine import ChatbotEngine, Chatbot


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha, tmp_path):
    return ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))


def test_create_agent_stores_agent(engine):
    agent = engine.create_chatbot({
        "name": "Energy Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Monitor energy",
        "allowed_tools": ["get_entity_states"],
        "enabled": True,
    })
    assert agent.id in engine.list_chatbots()


def test_list_agents_returns_dict(engine):
    engine.create_chatbot({
        "name": "Test Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 10},
        "system_prompt": "test",
        "allowed_tools": [],
        "enabled": False,
    })
    agents = engine.list_chatbots()
    assert len(agents) == 1
    first = list(agents.values())[0]
    assert first["name"] == "Test Agent"


def test_delete_agent_removes_agent(engine):
    agent = engine.create_chatbot({
        "name": "To Delete",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "",
        "allowed_tools": [],
        "enabled": False,
    })
    engine.delete_chatbot(agent.id)
    assert agent.id not in engine.list_chatbots()


@pytest.mark.asyncio
async def test_run_agent_skips_when_already_running(engine):
    """Per-agent concurrency guard: a trigger that arrives while the agent is
    already in flight is skipped, not run concurrently.

    Without this, the scheduler (interval+cron), state-change reactions and the
    manual API can overlap the same agent — double-executing actions and racing
    on the shared ClaudeRunner state.
    """
    agent = engine.create_chatbot({
        "name": "Busy", "type": "agent",
        "triggers": [], "system_prompt": "x",
        "allowed_tools": [], "enabled": False,
    })
    runner = MagicMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    engine.set_claude_runner(runner)

    # Simulate the agent already in flight from another trigger source.
    engine._running_chatbots.add(agent.id)
    result = await engine.run_chatbot(agent)

    assert "already running" in result
    runner.chat.assert_not_called()
    runner.run_with_actions.assert_not_called()


def test_create_agent_with_new_fields(engine):
    agent = engine.create_chatbot({
        "name": "Climate Manager",
        "type": "preventive",
        "trigger": {"type": "preventive", "cron": "0 15 * * 1-5"},
        "system_prompt": "Gestisci il clima",
        "allowed_tools": ["get_entity_states", "call_ha_service"],
        "enabled": True,
        "strategic_context": "Famiglia rientra alle 16:00. Temp preferita 21°C.",
        "allowed_entities": ["climate.*", "person.*"],
        "allowed_services": ["climate.set_temperature", "notify.*"],
    })
    assert agent.strategic_context == "Famiglia rientra alle 16:00. Temp preferita 21°C."
    assert agent.allowed_entities == ["climate.*", "person.*"]
    assert agent.allowed_services == ["climate.set_temperature", "notify.*"]


def test_create_agent_new_fields_default_empty(engine):
    agent = engine.create_chatbot({
        "name": "Minimal Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "",
        "allowed_tools": [],
        "enabled": False,
    })
    assert agent.strategic_context == ""
    assert agent.allowed_entities == []
    assert agent.allowed_services == []


def test_create_agent_thinking_budget_default_zero(engine):
    """thinking_budget defaults to 0 (extended thinking disabled)."""
    agent = engine.create_chatbot({
        "name": "X", "type": "chat",
        "triggers": [], "system_prompt": "", "allowed_tools": [],
    })
    assert agent.thinking_budget == 0


def test_create_agent_thinking_budget_persists(engine):
    """thinking_budget is stored from create payload."""
    agent = engine.create_chatbot({
        "name": "Reasoner", "type": "agent",
        "triggers": [], "system_prompt": "",
        "allowed_tools": [],
        "thinking_budget": 4096,
    })
    assert agent.thinking_budget == 4096


def test_update_agent_thinking_budget(engine):
    """thinking_budget can be updated."""
    agent = engine.create_chatbot({
        "name": "X", "type": "chat",
        "triggers": [], "system_prompt": "", "allowed_tools": [],
    })
    updated = engine.update_chatbot(agent.id, {"thinking_budget": 2048})
    assert updated.thinking_budget == 2048


def test_create_agent_thinking_budget_negative_clamped_to_zero(engine):
    """Negative thinking_budget is clamped to 0 by create_agent (defensive)."""
    agent = engine.create_chatbot({
        "name": "X", "type": "chat",
        "triggers": [], "system_prompt": "", "allowed_tools": [],
        "thinking_budget": -1,
    })
    assert agent.thinking_budget == 0


def test_update_agent_new_fields(engine):
    agent = engine.create_chatbot({
        "name": "Test Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 10},
        "system_prompt": "test",
        "allowed_tools": [],
        "enabled": False,
    })
    updated = engine.update_chatbot(agent.id, {
        "strategic_context": "Nuovo contesto",
        "allowed_entities": ["sensor.*"],
        "allowed_services": [],
    })
    assert updated.strategic_context == "Nuovo contesto"
    assert updated.allowed_entities == ["sensor.*"]
    assert updated.allowed_services == []


def test_list_agents_includes_new_fields(engine):
    engine.create_chatbot({
        "name": "Export Test",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "",
        "allowed_tools": [],
        "enabled": False,
        "strategic_context": "contesto",
        "allowed_entities": ["light.*"],
        "allowed_services": [],
    })
    agents = list(engine.list_chatbots().values())
    assert "strategic_context" in agents[0]
    assert "allowed_entities" in agents[0]
    assert "allowed_services" in agents[0]
    assert agents[0]["strategic_context"] == "contesto"
    assert agents[0]["allowed_entities"] == ["light.*"]


@pytest.mark.asyncio
async def test_run_agent_injects_strategic_context(engine):
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    engine.set_claude_runner(mock_runner)
    agent = engine.create_chatbot({
        "name": "Climate Agent",
        "type": "agent",
        "triggers": [{"type": "cron", "cron": "0 6 * * *"}],
        "system_prompt": "Analizza il clima.",
        "allowed_tools": [],
        "enabled": False,
        "strategic_context": "Famiglia: 2 adulti. Temp preferita 21°C.",
        "allowed_entities": [],
        "allowed_services": [],
    })
    await engine.run_chatbot(agent)
    call_kwargs = mock_runner.chat.call_args
    system_prompt_used = call_kwargs.kwargs.get("system_prompt", "")
    assert "---" in system_prompt_used
    assert "Famiglia: 2 adulti." in system_prompt_used
    assert "Analizza il clima." in system_prompt_used
    assert system_prompt_used.index("Famiglia: 2 adulti.") < system_prompt_used.index("Analizza il clima.")


@pytest.mark.asyncio
async def test_run_agent_no_strategic_context_plain_prompt(engine):
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    engine.set_claude_runner(mock_runner)
    agent = engine.create_chatbot({
        "name": "Simple Agent",
        "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Semplice monitor.",
        "allowed_tools": [],
        "enabled": False,
    })
    await engine.run_chatbot(agent)
    call_kwargs = mock_runner.chat.call_args
    system_prompt_used = call_kwargs.kwargs.get("system_prompt", "")
    assert "---" not in system_prompt_used
    assert system_prompt_used == "Semplice monitor."


def test_create_agent_persists_to_file(engine, tmp_path):
    engine.create_chatbot({
        "name": "Persist Test", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "test", "allowed_tools": [], "enabled": False,
    })
    path = tmp_path / "agents.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["schema_version"] == 4
    assert any(a["name"] == "Persist Test" for a in data["chatbots"])


def test_delete_agent_removes_from_file(engine, tmp_path):
    agent = engine.create_chatbot({
        "name": "ToDelete", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    engine.delete_chatbot(agent.id)
    data = json.loads((tmp_path / "agents.json").read_text())
    assert not any(a["id"] == agent.id for a in data["chatbots"])


def test_load_agents_from_existing_file(mock_ha, tmp_path):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "agents": [{
            "id": "loaded-001",
            "name": "Loaded Agent",
            "type": "monitor",
            "trigger": {"type": "schedule", "interval_minutes": 10},
            "system_prompt": "loaded",
            "allowed_tools": [],
            "enabled": False,
            "is_default": False,
            "last_run": None,
            "last_result": None,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }]
    }))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    assert "loaded-001" in eng._chatbots
    assert eng._chatbots["loaded-001"].name == "Loaded Agent"


def test_load_missing_file_is_noop(mock_ha, tmp_path):
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "nonexistent.json"))
    eng._load()  # must not raise
    assert len(eng._chatbots) == 0


def test_load_agent_with_legacy_tool_names_maps_to_current_names(mock_ha, tmp_path):
    """Fix 4 (Important, whole-branch review): a Chatbot persisted BEFORE the
    memoria-unica merge (Task 2) may still name the retired
    recall_knowledge/save_knowledge tools in allowed_tools (they were two
    separate checkboxes). claude_runner.py's allowed_tools filter matches by
    exact name (ALL_TOOL_DEFS lookup) -- an unmapped legacy name silently
    drops second-brain access from a bot whose base system prompt now orders
    it to call save_memory unconditionally. Loading must rewrite the old
    names to the current recall_memory/save_memory."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 4,
        "chatbots": [{
            "id": "legacy-001",
            "name": "Legacy Bot",
            "system_prompt": "legacy",
            "allowed_tools": ["get_home_status", "recall_knowledge", "save_knowledge"],
            "enabled": True,
            "is_default": False,
        }]
    }))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    loaded = eng._chatbots["legacy-001"]
    assert loaded.allowed_tools == ["get_home_status", "recall_memory", "save_memory"]


def test_load_agent_with_both_legacy_and_current_names_dedupes(mock_ha, tmp_path):
    """A config that (however it happened) carries BOTH the legacy and the
    current name for the same tool must not end up with a duplicate --
    normalize_tool_names is idempotent and de-duplicates on the mapped name,
    preserving first-seen order."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 4,
        "chatbots": [{
            "id": "legacy-002",
            "name": "Legacy Bot 2",
            "system_prompt": "legacy",
            "allowed_tools": ["recall_knowledge", "recall_memory", "save_knowledge"],
            "enabled": True,
            "is_default": False,
        }]
    }))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    loaded = eng._chatbots["legacy-002"]
    assert loaded.allowed_tools == ["recall_memory", "save_memory"]


def test_update_agent_persists_to_file(engine, tmp_path):
    agent = engine.create_chatbot({
        "name": "Update Me", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "original", "allowed_tools": [], "enabled": False,
    })
    engine.update_chatbot(agent.id, {"system_prompt": "updated"})
    data = json.loads((tmp_path / "agents.json").read_text())
    entry = next(a for a in data["chatbots"] if a["id"] == agent.id)
    assert entry["system_prompt"] == "updated"


@pytest.mark.asyncio
async def test_default_agent_seeded_after_load(mock_ha, tmp_path):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_chatbot()
    assert DEFAULT_CHATBOT_ID in eng._chatbots
    assert eng._chatbots[DEFAULT_CHATBOT_ID].is_default is True
    assert not hasattr(eng._chatbots[DEFAULT_CHATBOT_ID], "type")
    eng._scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_default_agent_not_seeded_if_already_present(mock_ha, tmp_path):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"schema_version": 1, "agents": [{
        "id": DEFAULT_CHATBOT_ID, "name": "Custom HIRIS", "type": "chat",
        "trigger": {"type": "manual"}, "system_prompt": "custom",
        "allowed_tools": [], "enabled": True, "is_default": True,
        "last_run": None, "last_result": None, "strategic_context": "",
        "allowed_entities": [], "allowed_services": [],
    }]}))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_chatbot()
    assert eng._chatbots[DEFAULT_CHATBOT_ID].name == "Custom HIRIS"
    eng._scheduler.shutdown(wait=False)


def test_delete_default_agent_returns_false(engine):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS",
        system_prompt="",
        allowed_tools=[], enabled=True, is_default=True,
    )
    result = engine.delete_chatbot(DEFAULT_CHATBOT_ID)
    assert result is False
    assert DEFAULT_CHATBOT_ID in engine._chatbots


def test_get_agent_returns_correct(engine):
    agent = engine.create_chatbot({
        "name": "Find Me", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert engine.get_chatbot(agent.id) is agent
    assert engine.get_chatbot("nonexistent") is None


def test_get_default_agent(engine):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS",
        system_prompt="",
        allowed_tools=[], enabled=True, is_default=True,
    )
    assert engine.get_default_chatbot() is engine._chatbots[DEFAULT_CHATBOT_ID]


def test_agent_model_defaults_to_auto(engine):
    agent = engine.create_chatbot({
        "name": "Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.model == "auto"
    # Every persona is a chat entity now (Slice 5 Task 2 dropped the
    # non-chat "agent"/"monitor" type) — new personas default to the chat
    # ceiling (16000), not the old non-chat default (4096).
    assert agent.max_tokens == 16000
    assert agent.restrict_to_home is False


def test_agent_per_agent_config_persists(engine):
    agent = engine.create_chatbot({
        "name": "Haiku Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "restrict_to_home": True,
    })
    engine2 = ChatbotEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_chatbot(agent.id)
    assert loaded.model == "claude-haiku-4-5-20251001"
    assert loaded.max_tokens == 1024
    assert loaded.restrict_to_home is True


def test_agent_update_model_and_max_tokens(engine):
    agent = engine.create_chatbot({
        "name": "Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    updated = engine.update_chatbot(agent.id, {"model": "claude-sonnet-4-6", "max_tokens": 2048})
    assert updated.model == "claude-sonnet-4-6"
    assert updated.max_tokens == 2048


@pytest.mark.asyncio
async def test_run_agent_passes_per_agent_config_to_runner(engine):
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="result")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_chatbot({
        "name": "Config Test", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Test prompt", "allowed_tools": [], "enabled": False,
        "model": "claude-haiku-4-5-20251001", "max_tokens": 512, "restrict_to_home": True,
    })
    await engine._run_chatbot(agent)

    call_kwargs = mock_runner.chat.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 512
    # Every persona is the chat entity now (Slice 5 Task 2 dropped `type`).
    assert call_kwargs["agent_type"] == "chat"
    assert call_kwargs["restrict_to_home"] is True


@pytest.mark.asyncio
async def test_run_agent_passes_require_confirmation_to_runner(engine):
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    # require_confirmation is a chat-agent feature; use type="chat" to hit that branch
    agent = engine.create_chatbot({
        "name": "Conf Agent", "type": "chat",
        "triggers": [],
        "system_prompt": "do stuff", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    await engine.run_chatbot(agent)
    call_kwargs = mock_runner.chat.call_args.kwargs
    assert call_kwargs["require_confirmation"] is True


def test_agent_require_confirmation_defaults_false(engine):
    agent = engine.create_chatbot({
        "name": "Default", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.require_confirmation is False


def test_update_agent_require_confirmation(engine):
    agent = engine.create_chatbot({
        "name": "Flip", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    updated = engine.update_chatbot(agent.id, {"require_confirmation": True})
    assert updated.require_confirmation is True


def test_agent_require_confirmation_persists(engine):
    agent = engine.create_chatbot({
        "name": "Persist Conf", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    engine2 = ChatbotEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_chatbot(agent.id)
    assert loaded.require_confirmation is True


@pytest.mark.asyncio
async def test_run_agent_appends_execution_log_record(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = [{"tool": "get_home_status", "input": {}}]
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0

    async def run_side_effect(**kwargs):
        mock_runner.total_input_tokens += 120
        mock_runner.total_output_tokens += 30
        return "Tutto ok, niente da fare."
    mock_runner.chat = AsyncMock(side_effect=run_side_effect)
    engine.set_claude_runner(mock_runner)

    agent = engine.create_chatbot({
        "name": "Log Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_chatbot(agent)

    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    # No more `agent.triggers` to source a default from (Slice 5 Task 2
    # removed the field) — every manual run logs "manual" now.
    assert rec["trigger"] == "manual"
    assert rec["tool_calls"] == ["get_home_status"]
    assert rec["input_tokens"] == 120
    assert rec["output_tokens"] == 30
    assert rec["result_summary"].startswith("Tutto ok")
    assert rec["success"] is True
    assert rec["timestamp"] == agent.last_run


@pytest.mark.asyncio
async def test_run_agent_execution_log_caps_at_20(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.chat = AsyncMock(return_value="ok")
    engine.set_claude_runner(mock_runner)

    agent = engine.create_chatbot({
        "name": "Cap Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    for _ in range(25):
        await engine.run_chatbot(agent)
    assert len(agent.execution_log) == 20


@pytest.mark.asyncio
async def test_run_agent_execution_log_marks_error(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.chat = AsyncMock(side_effect=RuntimeError("boom"))
    engine.set_claude_runner(mock_runner)

    agent = engine.create_chatbot({
        "name": "Err Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_chatbot(agent)
    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    assert rec["success"] is False
    assert rec["result_summary"].startswith("Error:")


@pytest.mark.asyncio
async def test_run_agent_degrades_gracefully_on_runner_backend_error(engine):
    """Review C/#13: the runner (bypassed here directly, as ChatbotEngine
    always is -- it calls .chat() rather than going through the router's
    fallback) now RAISES RunnerBackendError on an API failure instead of
    returning a friendly string. _run_agent must catch it at the call site
    and reproduce the exact same degraded-string behavior as before (no
    crash, no generic "Error: " prefix from the catch-all except, and the
    upstream-failure detection below still sees a plain string) -- not let
    it fall into the generic `except Exception` branch, which would lose the
    rate-limit bookkeeping this specific branch relies on."""
    from hiris.app.claude_runner import RunnerBackendError

    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.chat = AsyncMock(
        side_effect=RunnerBackendError("Errore temporaneo del servizio AI. Riprova tra poco.")
    )
    engine.set_claude_runner(mock_runner)

    agent = engine.create_chatbot({
        "name": "Backend Err Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    result = await engine.run_chatbot(agent)

    assert result == "Errore temporaneo del servizio AI. Riprova tra poco."
    assert not result.startswith("Error:")
    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    assert rec["success"] is False
    assert rec["result_summary"] == "Errore temporaneo del servizio AI. Riprova tra poco."


def test_execution_log_not_in_updatable_fields(engine):
    assert "execution_log" not in ChatbotEngine.UPDATABLE_FIELDS


def test_execution_log_persists_across_reload(engine):
    agent = engine.create_chatbot({
        "name": "Persist Log", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    agent.execution_log = [{
        "timestamp": "2026-04-20T10:00:00+00:00",
        "trigger": "schedule",
        "tool_calls": ["get_home_status"],
        "input_tokens": 50,
        "output_tokens": 10,
        "result_summary": "ok",
        "success": True,
    }]
    engine._save()
    engine2 = ChatbotEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_chatbot(agent.id)
    assert len(loaded.execution_log) == 1
    assert loaded.execution_log[0]["trigger"] == "schedule"


# ---------------------------------------------------------------------------
# Backward-compatibility / no-regression tests (Cycle 3 → v0.1.1)
# These tests codify the contracts that must hold for users upgrading from
# v0.1.0 agents.json files that do not contain the new Cycle 3 fields.
# ---------------------------------------------------------------------------

def test_load_old_json_without_cycle3_fields_defaults_safely(mock_ha, tmp_path):
    """agents.json from v0.1.0 (no require_confirmation / execution_log) loads without error."""
    data_path = str(tmp_path / "agents.json")
    old_payload = {
        "schema_version": 1,
        "agents": [{
            "id": "legacy-001",
            "name": "Legacy Agent",
            "type": "monitor",
            "trigger": {"type": "schedule", "interval_minutes": 10},
            "system_prompt": "do stuff",
            "allowed_tools": [],
            "enabled": False,
            "last_run": None,
            "last_result": None,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
            "is_default": False,
            "model": "auto",
            "max_tokens": 4096,
            "restrict_to_home": False,
            # NO require_confirmation, NO execution_log  ← v0.1.0 file
        }],
    }
    with open(data_path, "w") as f:
        json.dump(old_payload, f)

    eng = ChatbotEngine(ha_client=mock_ha, data_path=data_path)
    eng._load()
    agent = eng.get_chatbot("legacy-001")
    assert agent is not None
    assert agent.require_confirmation is False
    assert agent.execution_log == []


def test_update_agent_without_require_confirmation_preserves_existing_value(engine):
    """PUT payload missing require_confirmation leaves the existing value untouched."""
    agent = engine.create_chatbot({
        "name": "Keep Me", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    updated = engine.update_chatbot(agent.id, {"name": "Keep Me Updated"})
    assert updated.require_confirmation is True  # unchanged


def test_create_agent_without_require_confirmation_defaults_false(engine):
    """POST /api/agents payload without require_confirmation must default to False."""
    agent = engine.create_chatbot({
        "name": "No Conf", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        # no require_confirmation key
    })
    assert agent.require_confirmation is False


def test_update_agent_with_require_confirmation_false_from_ui(engine):
    """buildPayload() always sends require_confirmation:false — must not break existing agents."""
    agent = engine.create_chatbot({
        "name": "UI Save", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "original", "allowed_tools": [], "enabled": False,
    })
    # Simulate UI saving the agent (sends require_confirmation even if user never touched it)
    updated = engine.update_chatbot(agent.id, {"system_prompt": "updated", "require_confirmation": False})
    assert updated.system_prompt == "updated"
    assert updated.require_confirmation is False


def test_execution_log_initialises_empty_for_new_agents(engine):
    """Newly created agents have an empty execution_log — no stale data."""
    agent = engine.create_chatbot({
        "name": "Fresh", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.execution_log == []


def _make_entity_cache(entities):
    cache = MagicMock()
    cache.get_all_useful.return_value = entities
    return cache


def test_set_entity_cache_stores_cache(engine):
    cache = _make_entity_cache([])
    engine.set_entity_cache(cache)
    assert engine._entity_cache is cache


def test_build_entity_context_with_allowed_entities(engine):
    cache = _make_entity_cache([
        {"id": "light.soggiorno", "state": "on",   "name": "Luce Soggiorno", "unit": ""},
        {"id": "sensor.temp",     "state": "22.5", "name": "Temperatura",    "unit": "°C"},
        {"id": "switch.pompa",    "state": "off",  "name": "Pompa",          "unit": ""},
    ])
    engine.set_entity_cache(cache)
    agent = engine.create_chatbot({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Monitor",
        "allowed_tools": [],
        "allowed_entities": ["light.*", "sensor.*"],
        "enabled": False,
    })
    ctx = engine._build_entity_context(agent)
    assert "[CONTESTO ENTITÀ]" in ctx
    assert "Luce Soggiorno: on" in ctx
    assert "Temperatura: 22.5 °C" in ctx
    # switch.pompa is not in allowed_entities → must not appear
    assert "Pompa" not in ctx


def test_build_entity_context_no_allowed_entities_uses_useful(engine):
    entities = [
        {"id": f"light.l{i}", "state": "on", "name": f"Luce {i}", "unit": ""}
        for i in range(60)
    ]
    cache = _make_entity_cache(entities)
    engine.set_entity_cache(cache)
    agent = engine.create_chatbot({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule"},
        "system_prompt": "test",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    ctx = engine._build_entity_context(agent)
    # cap at 50 entities even without filter
    lines = [l for l in ctx.splitlines() if l.startswith("- ")]
    assert len(lines) == 50


def test_build_entity_context_returns_empty_without_cache(engine):
    # no cache set → empty string
    agent = engine.create_chatbot({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule"},
        "system_prompt": "test",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    ctx = engine._build_entity_context(agent)
    assert ctx == ""


@pytest.mark.asyncio
async def test_run_agent_never_injects_entity_context(engine):
    """Slice 5 Task 2: the entity-context injection that used to be gated on
    `agent.type == "agent"` is gone along with the `type` field itself — a
    persona's manual run never builds/injects `_build_entity_context` output
    into `user_message`, regardless of `allowed_entities`. (`_build_entity_context`
    itself is kept and still directly tested — see the tests above — it's
    just no longer called from `_run_agent`.)"""
    cache = _make_entity_cache([
        {"id": "sensor.temp", "state": "21.0", "name": "Temp", "unit": "°C"},
    ])
    engine.set_entity_cache(cache)

    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.last_tool_calls = []
    runner.total_input_tokens = 0
    runner.total_output_tokens = 0
    engine.set_claude_runner(runner)

    agent = engine.create_chatbot({
        "name": "Monitor",
        "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Analizza",
        "allowed_tools": [],
        "allowed_entities": ["sensor.*"],
        "enabled": False,
    })
    await engine._run_chatbot(agent)

    call_args = runner.chat.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "[CONTESTO ENTITÀ]" not in user_msg
    assert "Temp: 21.0 °C" not in user_msg


@pytest.mark.asyncio
async def test_execution_log_result_summary_truncated_at_1000(tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.chatbot_engine import ChatbotEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_chatbot({
        "name": "Log Test", "type": "agent",
        "triggers": [{"type": "manual"}],
    })

    long_result = "x" * 1500
    mock_runner = MagicMock()
    mock_runner.chat = AsyncMock(return_value=long_result)
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    await engine.run_chatbot(agent)
    assert len(agent.execution_log[0]["result_summary"]) == 1000

    await engine.stop()


@pytest.mark.asyncio
async def test_run_agent_does_not_inject_for_chat(engine):
    cache = _make_entity_cache([
        {"id": "sensor.temp", "state": "21.0", "name": "Temp", "unit": "°C"},
    ])
    engine.set_entity_cache(cache)

    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.last_tool_calls = []
    runner.total_input_tokens = 0
    runner.total_output_tokens = 0
    engine.set_claude_runner(runner)

    agent = engine.create_chatbot({
        "name": "Chat",
        "type": "chat",
        "trigger": {"type": "manual"},
        "system_prompt": "Chat",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    await engine._run_chatbot(agent)

    call_args = runner.chat.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "[CONTESTO ENTITÀ]" not in user_msg


@pytest.mark.asyncio
async def test_agent_not_auto_disabled_regardless_of_usage(tmp_path):
    """Slice 5 Task 2 removed `budget_eur_limit` and the
    `_check_budget_auto_disable` method that consumed it — a stray
    `budget_eur_limit` key in the create payload is silently ignored
    (create_agent never reads it), and no amount of reported usage disables
    a persona anymore; that was the whole point of the field's removal."""
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.chatbot_engine import ChatbotEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_chatbot({
        "name": "Budget Test", "type": "agent",
        "triggers": [{"type": "manual"}],
        "budget_eur_limit": 0.001,  # stray key — ignored, no such field anymore
    })
    assert not hasattr(agent, "budget_eur_limit")

    mock_runner = MagicMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    # Usage that would have blown past even a generous limit under the old
    # (now-removed) auto-disable check.
    mock_runner.get_chatbot_usage = MagicMock(return_value={
        "input_tokens": 5_000_000, "output_tokens": 2_000_000,
        "requests": 1, "cost_usd": 500.0,
        "last_run": "2026-04-21T10:00:00Z",
    })
    engine.set_claude_runner(mock_runner)

    await engine.run_chatbot(agent)

    assert agent.enabled is True  # never auto-disabled — the feature is gone

    await engine.stop()


# ---------------------------------------------------------------------------
# Slice 5 removed _migrate_agent_raw (v1→v2 schema migration), the AZIONI-line
# parser (_parse_azioni_lines), and the action/rules execution machinery
# entirely — agents.json is v2-only going forward, and no agent (any type)
# executes actions anymore. See test_run_agent_uses_chat_not_run_with_actions
# below for the replacement contract: every agent type now goes through
# ClaudeRunner.chat(), never run_with_actions().
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_uses_chat_not_run_with_actions(engine):
    """Slice 5: no agent type executes actions anymore — _run_agent always
    calls chat() (plain text), regardless of agent.type, and never touches
    run_with_actions. fetta E3 Task 8: `run_with_actions` non esiste piu'
    affatto su ClaudeRunner (era Sentinella-only, invocato direttamente da
    `_llm_reason`, uscita a sua volta col Task 7) -- l'assert_not_called()
    sotto resta comunque un guard valido sul comportamento di ChatbotEngine
    verso QUALUNQUE oggetto le passi come runner, mock incluso."""
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Analisi OK.")
    mock_runner.run_with_actions = AsyncMock(return_value=("should not be used", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_chatbot({
        "name": "New Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Monitor everything.",
        "allowed_tools": [], "enabled": False,
    })
    result = await engine.run_chatbot(agent)

    assert result == "Analisi OK."
    mock_runner.chat.assert_called_once()
    mock_runner.run_with_actions.assert_not_called()


# ---------------------------------------------------------------------------
# Regression: per-agent rate-limit backoff (v0.9.10)
# When an agent on an OpenRouter :free model gets rate-limited by the upstream
# provider repeatedly, ChatbotEngine pauses scheduled runs for a cooldown so we
# don't burn the daily quota on triggers that will all fail.
# ---------------------------------------------------------------------------

import time as _time
from hiris.app.chatbot_engine import (
    _RATE_LIMIT_THRESHOLD, _RATE_LIMIT_WINDOW_SEC, _RATE_LIMIT_COOLDOWN_SEC,
)


def test_is_rate_limited_detects_upstream_message():
    eng = ChatbotEngine(ha_client=AsyncMock())
    msg = (
        "Il modello qwen/qwen3-next-80b-a3b-instruct:free ha esaurito il "
        "rate limit upstream. Riprova tra qualche minuto..."
    )
    assert eng._is_rate_limited(msg) is True


def test_is_rate_limited_does_not_match_normal_text():
    eng = ChatbotEngine(ha_client=AsyncMock())
    assert eng._is_rate_limited("Tutto ok, nessun problema.") is False
    assert eng._is_rate_limited("") is False
    assert eng._is_rate_limited(None) is False


def test_record_failures_below_threshold_does_not_pause():
    eng = ChatbotEngine(ha_client=AsyncMock())
    for _ in range(_RATE_LIMIT_THRESHOLD - 1):
        eng._record_rate_limit_failure("ag-x")
    assert eng._is_in_rate_limit_pause("ag-x") is False


def test_record_failures_at_threshold_triggers_pause():
    eng = ChatbotEngine(ha_client=AsyncMock())
    for _ in range(_RATE_LIMIT_THRESHOLD):
        eng._record_rate_limit_failure("ag-x")
    assert eng._is_in_rate_limit_pause("ag-x") is True


def test_pause_auto_clears_after_cooldown(monkeypatch):
    eng = ChatbotEngine(ha_client=AsyncMock())
    # Start time t0; record failures
    t = [1000.0]
    monkeypatch.setattr("hiris.app.chatbot_engine.time.monotonic", lambda: t[0])
    for _ in range(_RATE_LIMIT_THRESHOLD):
        eng._record_rate_limit_failure("ag-x")
    assert eng._is_in_rate_limit_pause("ag-x") is True
    # Advance past the cooldown
    t[0] += _RATE_LIMIT_COOLDOWN_SEC + 1
    assert eng._is_in_rate_limit_pause("ag-x") is False


def test_old_failures_outside_window_do_not_count(monkeypatch):
    eng = ChatbotEngine(ha_client=AsyncMock())
    t = [1000.0]
    monkeypatch.setattr("hiris.app.chatbot_engine.time.monotonic", lambda: t[0])
    # First failure
    eng._record_rate_limit_failure("ag-x")
    # Advance past the window
    t[0] += _RATE_LIMIT_WINDOW_SEC + 1
    # Now record _RATE_LIMIT_THRESHOLD - 1 more — should NOT trigger pause
    for _ in range(_RATE_LIMIT_THRESHOLD - 1):
        eng._record_rate_limit_failure("ag-x")
    assert eng._is_in_rate_limit_pause("ag-x") is False


def test_clear_failures_after_success(monkeypatch):
    """A successful run between failures resets the counter."""
    eng = ChatbotEngine(ha_client=AsyncMock())
    eng._record_rate_limit_failure("ag-x")
    eng._record_rate_limit_failure("ag-x")
    eng._clear_rate_limit_failures("ag-x")
    eng._record_rate_limit_failure("ag-x")
    assert eng._is_in_rate_limit_pause("ag-x") is False


def test_agent_knowledge_access_default_and_update(engine):
    a = engine.create_chatbot({
        "name": "Chat", "type": "chat", "triggers": [],
        "system_prompt": "x", "allowed_tools": [], "enabled": True,
    })
    assert a.knowledge_access == {"allow_sensitive": False, "kinds": "all"}
    engine.update_chatbot(a.id, {"knowledge_access": {"allow_sensitive": True, "kinds": "all"}})
    assert engine.get_chatbot(a.id).knowledge_access["allow_sensitive"] is True


@pytest.mark.asyncio
async def test_run_agent_short_circuits_during_pause():
    """When an agent is in rate-limit cooldown, _run_agent must skip
    immediately without invoking the runner — preserves OpenRouter quota."""
    eng = ChatbotEngine(ha_client=AsyncMock())
    runner = MagicMock()
    runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    runner.chat = AsyncMock(return_value="ok")
    eng.set_claude_runner(runner)

    agent = eng.create_chatbot({
        "name": "Energy",
        "type": "agent",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "...",
        "allowed_tools": [],
    })
    # Force pause
    for _ in range(_RATE_LIMIT_THRESHOLD):
        eng._record_rate_limit_failure(agent.id)

    result = await eng._run_chatbot(agent)
    assert "skipped" in result.lower()
    assert "cooldown" in result.lower()
    runner.run_with_actions.assert_not_called()
    runner.chat.assert_not_called()


# ---------------------------------------------------------------------------
# SP-4 Fase A Task 1: one-time agents.json -> chatbots.json migration
# ---------------------------------------------------------------------------

def test_load_migrates_legacy_agents_json_to_chatbots_json(mock_ha, tmp_path):
    """When chatbots.json is absent but a legacy agents.json sits next to it,
    _load() must migrate it once (rename the key, bump schema_version, write
    chatbots.json) and load the chatbots from the migrated file — idempotent,
    non-fatal, no data loss."""
    legacy_path = tmp_path / "agents.json"
    legacy_path.write_text(json.dumps({
        "schema_version": 3,
        "agents": [{
            "id": "legacy-chat-001",
            "name": "Legacy Chatbot",
            "system_prompt": "hello",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    chatbots_path = tmp_path / "chatbots.json"
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng._load()

    # Migrated file now exists on disk, in the new shape.
    assert chatbots_path.exists()
    migrated = json.loads(chatbots_path.read_text())
    assert migrated["schema_version"] == 4
    assert any(c["id"] == "legacy-chat-001" for c in migrated["chatbots"])
    assert "agents" not in migrated

    # And the engine loaded the chatbot from the migrated file.
    chatbot = eng.get_chatbot("legacy-chat-001")
    assert chatbot is not None
    assert chatbot.name == "Legacy Chatbot"
    assert chatbot.system_prompt == "hello"


def test_load_migration_is_idempotent_and_non_fatal(mock_ha, tmp_path):
    """A second _load() call after migration must not re-migrate (chatbots.json
    already exists) and must not touch/require the legacy file any further."""
    legacy_path = tmp_path / "agents.json"
    legacy_path.write_text(json.dumps({
        "schema_version": 3,
        "agents": [{
            "id": "legacy-chat-002",
            "name": "Legacy Chatbot 2",
            "system_prompt": "",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    chatbots_path = tmp_path / "chatbots.json"
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng._load()
    first_migrated_mtime = chatbots_path.stat().st_mtime_ns

    # Delete the legacy file to prove the second _load() does not depend on it.
    legacy_path.unlink()
    eng2 = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng2._load()  # must not raise even though agents.json is now gone

    assert eng2.get_chatbot("legacy-chat-002") is not None
    # chatbots.json was not rewritten by the second _load() (no re-migration).
    assert chatbots_path.stat().st_mtime_ns == first_migrated_mtime


def test_load_no_migration_when_chatbots_json_already_present(mock_ha, tmp_path):
    """If chatbots.json already exists, a sibling agents.json (however stale)
    must be ignored entirely — no migration, no overwrite."""
    (tmp_path / "agents.json").write_text(json.dumps({
        "schema_version": 3,
        "agents": [{
            "id": "should-not-load",
            "name": "Stale",
            "system_prompt": "",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))
    chatbots_path = tmp_path / "chatbots.json"
    chatbots_path.write_text(json.dumps({
        "schema_version": 4,
        "chatbots": [{
            "id": "current-chat",
            "name": "Current",
            "system_prompt": "",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng._load()

    assert eng.get_chatbot("current-chat") is not None
    assert eng.get_chatbot("should-not-load") is None
