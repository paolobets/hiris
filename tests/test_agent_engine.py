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
        "type": "reactive",
        "trigger": {"type": "state_changed", "entity_id": "binary_sensor.garage_door"},
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
    mock_runner.chat = AsyncMock(return_value="ok")
    engine.set_claude_runner(mock_runner)
    agent = engine.create_agent({
        "name": "Climate Agent",
        "type": "preventive",
        "trigger": {"type": "preventive", "cron": "0 6 * * *"},
        "system_prompt": "Analizza il clima.",
        "allowed_tools": [],
        "enabled": False,
        "strategic_context": "Famiglia: 2 adulti. Temp preferita 21°C.",
        "allowed_entities": [],
        "allowed_services": [],
    })
    await engine.run_agent(agent)
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
    agent = engine.create_agent({
        "name": "Simple Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Semplice monitor.",
        "allowed_tools": [],
        "enabled": False,
    })
    await engine.run_agent(agent)
    call_kwargs = mock_runner.chat.call_args
    system_prompt_used = call_kwargs.kwargs.get("system_prompt", "")
    assert "---" not in system_prompt_used
    assert system_prompt_used == "Semplice monitor."


def test_create_agent_persists_to_file(engine, tmp_path):
    engine.create_agent({
        "name": "Persist Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "test", "allowed_tools": [], "enabled": False,
    })
    path = tmp_path / "agents.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert any(a["name"] == "Persist Test" for a in data["agents"])


def test_delete_agent_removes_from_file(engine, tmp_path):
    agent = engine.create_agent({
        "name": "ToDelete", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
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
        trigger={"type": "manual"}, system_prompt="",
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
        trigger={"type": "manual"}, system_prompt="",
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
