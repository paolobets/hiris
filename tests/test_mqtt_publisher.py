import pytest
from hiris.app.mqtt_publisher import MQTTPublisher
from hiris.app.agent_engine import Agent


def _make_agent(**kwargs):
    defaults = dict(
        id="test-001", name="Test Agent",
        system_prompt="",
        allowed_tools=[], enabled=True, last_run=None,
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


def test_is_auth_error_detects_known_codes():
    pub = MQTTPublisher()
    assert pub._is_auth_error(Exception("[code:135] Not authorized"))
    assert pub._is_auth_error(Exception("[code:134] Bad user name or password"))
    assert pub._is_auth_error(Exception("[code:5] Connection Refused, Not Authorized"))
    assert pub._is_auth_error(Exception("[code:4] Connection Refused, Bad Username"))


def test_is_auth_error_ignores_network_errors():
    pub = MQTTPublisher()
    assert not pub._is_auth_error(Exception("[code:1] Unacceptable protocol version"))
    assert not pub._is_auth_error(Exception("Connection refused: server unavailable"))
    assert not pub._is_auth_error(Exception("TimeoutError"))


# ---------------------------------------------------------------------------
# Slice 5 Task 2 — MQTT residue: the "enabled" switch and "run_now" button
# had a command_topic with no listener (Task 1 removed the command
# callback). publish_discovery must stop advertising them as live controls
# and instead publish a removal (empty payload) on their old discovery
# topics so HA drops any already-discovered entity.
# ---------------------------------------------------------------------------

async def _drain(pub):
    topics = {}
    while not pub._pending.empty():
        topic, payload = pub._pending.get_nowait()
        topics[topic] = payload
    return topics


@pytest.mark.asyncio
async def test_publish_discovery_removes_stale_command_entities():
    pub = MQTTPublisher()
    pub._enabled = True
    agent = _make_agent()
    await pub.publish_discovery(agent)
    topics = await _drain(pub)

    switch_topic = "homeassistant/switch/hiris_test-001_enabled/config"
    button_topic = "homeassistant/button/hiris_test-001_run_now/config"
    assert switch_topic in topics
    assert topics[switch_topic] == ""  # empty payload → HA drops the entity
    assert button_topic in topics
    assert topics[button_topic] == ""


@pytest.mark.asyncio
async def test_publish_discovery_keeps_enabled_as_read_only_sensor():
    pub = MQTTPublisher()
    pub._enabled = True
    agent = _make_agent()
    await pub.publish_discovery(agent)
    topics = await _drain(pub)

    sensor_topic = "homeassistant/sensor/hiris_test-001_enabled/config"
    assert sensor_topic in topics
    import json
    payload = json.loads(topics[sensor_topic])
    assert payload["state_topic"] == "hiris/agents/test-001/enabled"
    assert "command_topic" not in payload  # read-only now, not a control


@pytest.mark.asyncio
async def test_publish_discovery_does_not_crash_without_agent_type():
    """Regression: `_build_discovery_payload` used to read `agent.type` for
    the device "model" field — Agent no longer has that attribute."""
    pub = MQTTPublisher()
    pub._enabled = True
    agent = _make_agent()
    await pub.publish_discovery(agent)  # must not raise AttributeError
