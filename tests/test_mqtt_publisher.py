import pytest
from hiris.app.mqtt_publisher import MQTTPublisher
from hiris.app.agent_engine import Agent


def _make_agent(**kwargs):
    defaults = dict(
        id="test-001", name="Test Agent", type="chat",
        trigger={"type": "manual"}, system_prompt="",
        allowed_tools=[], enabled=True, last_run=None,
        budget_eur_limit=5.0,
    )
    defaults.update(kwargs)
    return Agent(**defaults)


@pytest.mark.asyncio
async def test_start_disabled_when_host_empty():
    pub = MQTTPublisher()
    await pub.start(host="", port=1883, user="", password="")
    assert not pub.is_connected


@pytest.mark.asyncio
async def test_stop_without_start_does_not_raise():
    pub = MQTTPublisher()
    await pub.stop()


def test_build_discovery_payload_sensor():
    pub = MQTTPublisher()
    agent = _make_agent()
    p = pub._build_discovery_payload(agent, "status", "sensor")
    assert p["unique_id"] == "hiris_test-001_status"
    assert p["state_topic"] == "hiris/agents/test-001/status"
    assert p["device"]["name"] == "HIRIS Test Agent"
    assert "command_topic" not in p


def test_build_discovery_payload_switch():
    pub = MQTTPublisher()
    agent = _make_agent()
    p = pub._build_discovery_payload(agent, "enabled", "switch")
    assert "command_topic" in p
    assert p["command_topic"] == "hiris/agents/test-001/enabled/set"


def test_build_state_topics_idle_enabled():
    pub = MQTTPublisher()
    agent = _make_agent()
    topics = pub._build_state_topics(agent, budget_eur=0.12, status="idle")
    assert topics["hiris/agents/test-001/status"] == "idle"
    assert topics["hiris/agents/test-001/enabled"] == "ON"
    assert topics["hiris/agents/test-001/budget_eur"] == "0.12"


def test_build_state_topics_disabled():
    pub = MQTTPublisher()
    agent = _make_agent(enabled=False)
    topics = pub._build_state_topics(agent, budget_eur=0.0, status="idle")
    assert topics["hiris/agents/test-001/enabled"] == "OFF"


@pytest.mark.asyncio
async def test_publish_noop_when_not_connected():
    pub = MQTTPublisher()
    agent = _make_agent()
    await pub.publish_agent_state(agent, budget_eur=0.0, status="idle")  # must not raise
    await pub.publish_discovery(agent)  # must not raise
