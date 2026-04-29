import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.agent_engine import AgentEngine, Agent


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha, tmp_path):
    return AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))


def test_create_agent_stores_agent(engine):
    agent = engine.create_agent({
        "name": "Energy Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Monitor energy",
        "allowed_tools": ["get_entity_states"],
        "enabled": True,
    })
    assert agent.id in engine.list_agents()


def test_list_agents_returns_dict(engine):
    engine.create_agent({
        "name": "Test Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 10},
        "system_prompt": "test",
        "allowed_tools": [],
        "enabled": False,
    })
    agents = engine.list_agents()
    assert len(agents) == 1
    first = list(agents.values())[0]
    assert first["name"] == "Test Agent"


def test_delete_agent_removes_agent(engine):
    agent = engine.create_agent({
        "name": "To Delete",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "",
        "allowed_tools": [],
        "enabled": False,
    })
    engine.delete_agent(agent.id)
    assert agent.id not in engine.list_agents()


@pytest.mark.asyncio
async def test_state_changed_triggers_reactive_agent(engine, mock_ha):
    agent = engine.create_agent({
        "name": "Garage Watcher",
        "type": "agent",
        "triggers": [{"type": "state_changed", "entity_id": "binary_sensor.garage_door"}],
        "system_prompt": "Watch the garage",
        "allowed_tools": ["send_notification"],
        "enabled": True,
    })

    with patch.object(engine, "_run_agent", new=AsyncMock()) as mock_run:
        engine._on_state_changed({
            "entity_id": "binary_sensor.garage_door",
            "new_state": {"state": "on"},
        })
        await asyncio.sleep(0.05)
        mock_run.assert_called_once()


def test_create_agent_with_new_fields(engine):
    agent = engine.create_agent({
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
    agent = engine.create_agent({
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


def test_update_agent_new_fields(engine):
    agent = engine.create_agent({
        "name": "Test Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 10},
        "system_prompt": "test",
        "allowed_tools": [],
        "enabled": False,
    })
    updated = engine.update_agent(agent.id, {
        "strategic_context": "Nuovo contesto",
        "allowed_entities": ["sensor.*"],
        "allowed_services": [],
    })
    assert updated.strategic_context == "Nuovo contesto"
    assert updated.allowed_entities == ["sensor.*"]
    assert updated.allowed_services == []


def test_list_agents_includes_new_fields(engine):
    engine.create_agent({
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
    agents = list(engine.list_agents().values())
    assert "strategic_context" in agents[0]
    assert "allowed_entities" in agents[0]
    assert "allowed_services" in agents[0]
    assert agents[0]["strategic_context"] == "contesto"
    assert agents[0]["allowed_entities"] == ["light.*"]


@pytest.mark.asyncio
async def test_run_agent_injects_strategic_context(engine):
    mock_runner = AsyncMock()
    mock_runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    engine.set_claude_runner(mock_runner)
    agent = engine.create_agent({
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
    await engine.run_agent(agent)
    call_kwargs = mock_runner.run_with_actions.call_args
    system_prompt_used = call_kwargs.kwargs.get("system_prompt", "")
    assert "---" in system_prompt_used
    assert "Famiglia: 2 adulti." in system_prompt_used
    assert "Analizza il clima." in system_prompt_used
    assert system_prompt_used.index("Famiglia: 2 adulti.") < system_prompt_used.index("Analizza il clima.")


@pytest.mark.asyncio
async def test_run_agent_no_strategic_context_plain_prompt(engine):
    mock_runner = AsyncMock()
    mock_runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    engine.set_claude_runner(mock_runner)
    agent = engine.create_agent({
        "name": "Simple Agent",
        "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Semplice monitor.",
        "allowed_tools": [],
        "enabled": False,
    })
    await engine.run_agent(agent)
    call_kwargs = mock_runner.run_with_actions.call_args
    system_prompt_used = call_kwargs.kwargs.get("system_prompt", "")
    assert "---" not in system_prompt_used
    assert system_prompt_used == "Semplice monitor."


def test_create_agent_persists_to_file(engine, tmp_path):
    engine.create_agent({
        "name": "Persist Test", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "test", "allowed_tools": [], "enabled": False,
    })
    path = tmp_path / "agents.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["schema_version"] == 2
    assert any(a["name"] == "Persist Test" for a in data["agents"])


def test_delete_agent_removes_from_file(engine, tmp_path):
    agent = engine.create_agent({
        "name": "ToDelete", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    engine.delete_agent(agent.id)
    data = json.loads((tmp_path / "agents.json").read_text())
    assert not any(a["id"] == agent.id for a in data["agents"])


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
    eng = AgentEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    assert "loaded-001" in eng._agents
    assert eng._agents["loaded-001"].name == "Loaded Agent"


def test_load_missing_file_is_noop(mock_ha, tmp_path):
    eng = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "nonexistent.json"))
    eng._load()  # must not raise
    assert len(eng._agents) == 0


def test_update_agent_persists_to_file(engine, tmp_path):
    agent = engine.create_agent({
        "name": "Update Me", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "original", "allowed_tools": [], "enabled": False,
    })
    engine.update_agent(agent.id, {"system_prompt": "updated"})
    data = json.loads((tmp_path / "agents.json").read_text())
    entry = next(a for a in data["agents"] if a["id"] == agent.id)
    assert entry["system_prompt"] == "updated"


@pytest.mark.asyncio
async def test_default_agent_seeded_after_load(mock_ha, tmp_path):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID
    eng = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_agent()
    assert DEFAULT_AGENT_ID in eng._agents
    assert eng._agents[DEFAULT_AGENT_ID].is_default is True
    assert eng._agents[DEFAULT_AGENT_ID].type == "chat"
    eng._scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_default_agent_not_seeded_if_already_present(mock_ha, tmp_path):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"schema_version": 1, "agents": [{
        "id": DEFAULT_AGENT_ID, "name": "Custom HIRIS", "type": "chat",
        "trigger": {"type": "manual"}, "system_prompt": "custom",
        "allowed_tools": [], "enabled": True, "is_default": True,
        "last_run": None, "last_result": None, "strategic_context": "",
        "allowed_entities": [], "allowed_services": [],
    }]}))
    eng = AgentEngine(ha_client=mock_ha, data_path=str(path))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_agent()
    assert eng._agents[DEFAULT_AGENT_ID].name == "Custom HIRIS"
    eng._scheduler.shutdown(wait=False)


def test_delete_default_agent_returns_false(engine):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        triggers=[], system_prompt="",
        allowed_tools=[], enabled=True, is_default=True,
    )
    result = engine.delete_agent(DEFAULT_AGENT_ID)
    assert result is False
    assert DEFAULT_AGENT_ID in engine._agents


def test_get_agent_returns_correct(engine):
    agent = engine.create_agent({
        "name": "Find Me", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert engine.get_agent(agent.id) is agent
    assert engine.get_agent("nonexistent") is None


def test_get_default_agent(engine):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        triggers=[], system_prompt="",
        allowed_tools=[], enabled=True, is_default=True,
    )
    assert engine.get_default_agent() is engine._agents[DEFAULT_AGENT_ID]


def test_agent_model_defaults_to_auto(engine):
    agent = engine.create_agent({
        "name": "Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.model == "auto"
    assert agent.max_tokens == 4096
    assert agent.restrict_to_home is False


def test_agent_per_agent_config_persists(engine):
    agent = engine.create_agent({
        "name": "Haiku Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "restrict_to_home": True,
    })
    engine2 = AgentEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_agent(agent.id)
    assert loaded.model == "claude-haiku-4-5-20251001"
    assert loaded.max_tokens == 1024
    assert loaded.restrict_to_home is True


def test_agent_update_model_and_max_tokens(engine):
    agent = engine.create_agent({
        "name": "Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    updated = engine.update_agent(agent.id, {"model": "claude-sonnet-4-6", "max_tokens": 2048})
    assert updated.model == "claude-sonnet-4-6"
    assert updated.max_tokens == 2048


@pytest.mark.asyncio
async def test_run_agent_passes_per_agent_config_to_runner(engine):
    mock_runner = AsyncMock()
    mock_runner.run_with_actions = AsyncMock(return_value=("result", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Config Test", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Test prompt", "allowed_tools": [], "enabled": False,
        "model": "claude-haiku-4-5-20251001", "max_tokens": 512, "restrict_to_home": True,
    })
    await engine._run_agent(agent)

    call_kwargs = mock_runner.run_with_actions.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 512
    assert call_kwargs["agent_type"] == "agent"
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
    agent = engine.create_agent({
        "name": "Conf Agent", "type": "chat",
        "triggers": [],
        "system_prompt": "do stuff", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    await engine.run_agent(agent)
    call_kwargs = mock_runner.chat.call_args.kwargs
    assert call_kwargs["require_confirmation"] is True


def test_agent_require_confirmation_defaults_false(engine):
    agent = engine.create_agent({
        "name": "Default", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.require_confirmation is False


def test_update_agent_require_confirmation(engine):
    agent = engine.create_agent({
        "name": "Flip", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    updated = engine.update_agent(agent.id, {"require_confirmation": True})
    assert updated.require_confirmation is True


def test_agent_require_confirmation_persists(engine):
    agent = engine.create_agent({
        "name": "Persist Conf", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    engine2 = AgentEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_agent(agent.id)
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
        return ("Tutto ok, niente da fare.", {})
    mock_runner.run_with_actions = AsyncMock(side_effect=run_side_effect)
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Log Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_agent(agent)

    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    assert rec["trigger"] == "schedule"
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
    mock_runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Cap Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    for _ in range(25):
        await engine.run_agent(agent)
    assert len(agent.execution_log) == 20


@pytest.mark.asyncio
async def test_run_agent_execution_log_marks_error(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.run_with_actions = AsyncMock(side_effect=RuntimeError("boom"))
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Err Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_agent(agent)
    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    assert rec["success"] is False
    assert rec["result_summary"].startswith("Error:")


def test_execution_log_not_in_updatable_fields(engine):
    assert "execution_log" not in AgentEngine.UPDATABLE_FIELDS


def test_execution_log_persists_across_reload(engine):
    agent = engine.create_agent({
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
    engine2 = AgentEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_agent(agent.id)
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

    eng = AgentEngine(ha_client=mock_ha, data_path=data_path)
    eng._load()
    agent = eng.get_agent("legacy-001")
    assert agent is not None
    assert agent.require_confirmation is False
    assert agent.execution_log == []


def test_update_agent_without_require_confirmation_preserves_existing_value(engine):
    """PUT payload missing require_confirmation leaves the existing value untouched."""
    agent = engine.create_agent({
        "name": "Keep Me", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    updated = engine.update_agent(agent.id, {"name": "Keep Me Updated"})
    assert updated.require_confirmation is True  # unchanged


def test_create_agent_without_require_confirmation_defaults_false(engine):
    """POST /api/agents payload without require_confirmation must default to False."""
    agent = engine.create_agent({
        "name": "No Conf", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        # no require_confirmation key
    })
    assert agent.require_confirmation is False


def test_update_agent_with_require_confirmation_false_from_ui(engine):
    """buildPayload() always sends require_confirmation:false — must not break existing agents."""
    agent = engine.create_agent({
        "name": "UI Save", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "original", "allowed_tools": [], "enabled": False,
    })
    # Simulate UI saving the agent (sends require_confirmation even if user never touched it)
    updated = engine.update_agent(agent.id, {"system_prompt": "updated", "require_confirmation": False})
    assert updated.system_prompt == "updated"
    assert updated.require_confirmation is False


def test_execution_log_initialises_empty_for_new_agents(engine):
    """Newly created agents have an empty execution_log — no stale data."""
    agent = engine.create_agent({
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
    agent = engine.create_agent({
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
    agent = engine.create_agent({
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
    agent = engine.create_agent({
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
async def test_run_agent_injects_context_for_monitor(engine):
    cache = _make_entity_cache([
        {"id": "sensor.temp", "state": "21.0", "name": "Temp", "unit": "°C"},
    ])
    engine.set_entity_cache(cache)

    runner = AsyncMock()
    runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    runner.last_tool_calls = []
    runner.total_input_tokens = 0
    runner.total_output_tokens = 0
    engine.set_claude_runner(runner)

    agent = engine.create_agent({
        "name": "Monitor",
        "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Analizza",
        "allowed_tools": [],
        "allowed_entities": ["sensor.*"],
        "enabled": False,
    })
    await engine._run_agent(agent)

    call_args = runner.run_with_actions.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "[CONTESTO ENTITÀ]" in user_msg
    assert "Temp: 21.0 °C" in user_msg


@pytest.mark.asyncio
async def test_execution_log_result_summary_truncated_at_1000(tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_agent({
        "name": "Log Test", "type": "agent",
        "triggers": [{"type": "manual"}],
    })

    long_result = "x" * 1500
    mock_runner = MagicMock()
    mock_runner.run_with_actions = AsyncMock(return_value=(long_result, {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    await engine.run_agent(agent)
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

    agent = engine.create_agent({
        "name": "Chat",
        "type": "chat",
        "trigger": {"type": "manual"},
        "system_prompt": "Chat",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    await engine._run_agent(agent)

    call_args = runner.chat.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "[CONTESTO ENTITÀ]" not in user_msg


@pytest.mark.asyncio
async def test_agent_auto_disabled_when_budget_exceeded(tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_agent({
        "name": "Budget Test", "type": "agent",
        "triggers": [{"type": "manual"}],
        "budget_eur_limit": 0.001,  # €0.001 — very low, will be exceeded
    })

    mock_runner = MagicMock()
    mock_runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    # Simulate usage exceeding budget
    mock_runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 5000, "output_tokens": 2000,
        "requests": 1, "cost_usd": 0.005,  # 0.005 * 0.92 = €0.0046 > €0.001 limit
        "last_run": "2026-04-21T10:00:00Z",
    })
    engine.set_claude_runner(mock_runner)

    await engine.run_agent(agent)

    # Agent should be auto-disabled after budget exceeded
    assert agent.enabled is False

    await engine.stop()


@pytest.mark.asyncio
async def test_agent_not_disabled_when_budget_not_exceeded(tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_agent({
        "name": "No Budget Test", "type": "agent",
        "triggers": [{"type": "manual"}],
        "budget_eur_limit": 10.0,  # high limit — will not be exceeded
    })

    mock_runner = MagicMock()
    mock_runner.run_with_actions = AsyncMock(return_value=("ok", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 100, "output_tokens": 50,
        "requests": 1, "cost_usd": 0.0001,
        "last_run": "2026-04-21T10:00:00Z",
    })
    engine.set_claude_runner(mock_runner)

    await engine.run_agent(agent)

    assert agent.enabled is True  # not disabled

    await engine.stop()


# ---------------------------------------------------------------------------
# Migration tests (v1 schema → v2 schema)
# ---------------------------------------------------------------------------

def test_migrate_agent_raw_monitor_to_agent():
    from hiris.app.agent_engine import _migrate_agent_raw
    raw = {
        "id": "x", "name": "M", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 10},
        "system_prompt": "", "allowed_tools": [], "enabled": True,
    }
    result = _migrate_agent_raw(raw)
    assert result["type"] == "agent"
    assert result["triggers"] == [{"type": "schedule", "interval_minutes": 10}]
    assert "trigger" not in result


def test_migrate_agent_raw_preventive_trigger_renamed():
    from hiris.app.agent_engine import _migrate_agent_raw
    raw = {
        "id": "x", "name": "P", "type": "preventive",
        "trigger": {"type": "preventive", "cron": "0 7 * * *"},
        "system_prompt": "", "allowed_tools": [], "enabled": True,
    }
    result = _migrate_agent_raw(raw)
    assert result["type"] == "agent"
    assert result["triggers"][0]["type"] == "cron"
    assert result["triggers"][0]["cron"] == "0 7 * * *"


def test_migrate_agent_raw_reactive_state_changed():
    from hiris.app.agent_engine import _migrate_agent_raw
    raw = {
        "id": "x", "name": "R", "type": "reactive",
        "trigger": {"type": "state_changed", "entity_id": "binary_sensor.door"},
        "system_prompt": "", "allowed_tools": [], "enabled": True,
    }
    result = _migrate_agent_raw(raw)
    assert result["type"] == "agent"
    assert result["triggers"] == [{"type": "state_changed", "entity_id": "binary_sensor.door"}]


def test_migrate_agent_raw_chat_gets_empty_triggers():
    from hiris.app.agent_engine import _migrate_agent_raw
    raw = {
        "id": "x", "name": "C", "type": "chat",
        "trigger": {"type": "manual"},
        "system_prompt": "", "allowed_tools": [], "enabled": True,
    }
    result = _migrate_agent_raw(raw)
    assert result["type"] == "chat"
    assert result["triggers"] == []


def test_migrate_agent_raw_actions_to_rules():
    from hiris.app.agent_engine import _migrate_agent_raw
    raw = {
        "id": "x", "name": "A", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": True,
        "trigger_on": ["ANOMALIA"],
        "actions": [{"type": "notify", "channel": "ha_push", "message": "Alert!"}],
    }
    result = _migrate_agent_raw(raw)
    assert result["rules"] == [
        {"states": ["ANOMALIA"], "actions": [{"type": "notify", "channel": "ha_push", "message": "Alert!"}]}
    ]
    assert result["action_mode"] == "configured"
    assert "actions" not in result
    assert "trigger_on" not in result


def test_migrate_agent_raw_is_idempotent():
    from hiris.app.agent_engine import _migrate_agent_raw
    raw = {
        "id": "x", "name": "M", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 10}],
        "rules": [], "action_mode": "automatic",
        "system_prompt": "", "allowed_tools": [], "enabled": True,
    }
    result1 = _migrate_agent_raw(dict(raw))
    result2 = _migrate_agent_raw(dict(result1))
    assert result1 == result2


def test_load_v1_json_migrates_on_load(mock_ha, tmp_path):
    """Old v1 agents.json migrates to v2 schema at load time without errors."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "agents": [{
            "id": "old-001", "name": "Old Monitor", "type": "monitor",
            "trigger": {"type": "schedule", "interval_minutes": 15},
            "trigger_on": ["ANOMALIA"],
            "actions": [{"type": "notify", "channel": "ha_push", "message": "Alert"}],
            "system_prompt": "check", "allowed_tools": [], "enabled": False,
            "is_default": False, "last_run": None, "last_result": None,
            "strategic_context": "", "allowed_entities": [], "allowed_services": [],
        }]
    }))
    eng = AgentEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    agent = eng.get_agent("old-001")
    assert agent is not None
    assert agent.type == "agent"
    assert agent.triggers == [{"type": "schedule", "interval_minutes": 15}]
    assert agent.rules == [{"states": ["ANOMALIA"], "actions": [{"type": "notify", "channel": "ha_push", "message": "Alert"}]}]
    assert agent.action_mode == "configured"


# ---------------------------------------------------------------------------
# _parse_azioni_lines tests
# ---------------------------------------------------------------------------

def test_parse_azioni_lines_basic_commands():
    from hiris.app.agent_engine import AgentEngine
    lines = [
        "turn_on switch.water_heater",
        "wait 60",
        "turn_off switch.water_heater",
        "notify ha_push Scaldabagno spento",
    ]
    result = AgentEngine._parse_azioni_lines(lines)
    assert result[0] == {"type": "turn_on", "entity_id": "switch.water_heater"}
    assert result[1] == {"type": "wait", "minutes": 60}
    assert result[2] == {"type": "turn_off", "entity_id": "switch.water_heater"}
    assert result[3] == {"type": "notify", "channel": "ha_push", "message": "Scaldabagno spento"}


def test_parse_azioni_lines_set_value():
    from hiris.app.agent_engine import AgentEngine
    result = AgentEngine._parse_azioni_lines(["set_value climate.soggiorno 21"])
    assert result[0] == {"type": "set_value", "entity_id": "climate.soggiorno", "value": "21"}


def test_parse_azioni_lines_call_service():
    from hiris.app.agent_engine import AgentEngine
    result = AgentEngine._parse_azioni_lines(["call_service light.turn_on light.soggiorno"])
    assert result[0] == {"type": "call_service", "domain": "light", "service": "turn_on", "entity_id": "light.soggiorno"}


def test_parse_azioni_lines_skips_blank():
    from hiris.app.agent_engine import AgentEngine
    result = AgentEngine._parse_azioni_lines(["", "  ", "turn_on switch.x"])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# run_with_actions integration — agent type uses structured output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_type_uses_run_with_actions(engine):
    """Agents with type='agent' must call run_with_actions, not chat."""
    mock_runner = AsyncMock()
    mock_runner.run_with_actions = AsyncMock(return_value=(
        "Analisi OK.",
        {"valutazione": "OK", "notifica": "Tutto bene.", "params": {}, "azioni": []},
    ))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "New Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "Monitor everything.",
        "allowed_tools": [], "enabled": False,
    })
    await engine.run_agent(agent)

    mock_runner.run_with_actions.assert_called_once()
    mock_runner.chat.assert_not_called()


@pytest.mark.asyncio
async def test_run_agent_execution_log_includes_structured_fields(engine):
    """Execution log for type='agent' includes valutazione and notifica."""
    mock_runner = AsyncMock()
    mock_runner.run_with_actions = AsyncMock(return_value=(
        "Analisi.",
        {"valutazione": "ANOMALIA", "notifica": "Consumo alto.", "params": {}, "azioni": []},
    ))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Struct Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_agent(agent)

    rec = agent.execution_log[0]
    assert rec["eval_status"] == "ANOMALIA"
    assert rec["notifica"] == "Consumo alto."
