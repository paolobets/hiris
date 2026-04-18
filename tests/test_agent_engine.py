import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.agent_engine import AgentEngine, Agent


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha):
    return AgentEngine(ha_client=mock_ha)


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
