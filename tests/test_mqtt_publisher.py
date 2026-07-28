import pytest
from hiris.app.mqtt_publisher import MQTTPublisher
from hiris.app.chatbot_engine import Chatbot


def _make_chatbot(**kwargs):
    defaults = dict(
        id="test-001", name="Test Agent",
        system_prompt="",
        allowed_tools=[], enabled=True, last_run=None,
    )
    defaults.update(kwargs)
    return Chatbot(**defaults)


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
    chatbot = _make_chatbot()
    p = pub._build_discovery_payload(chatbot, "status", "sensor")
    assert p["unique_id"] == "chatbot_test-001_status"
    assert p["state_topic"] == "hiris/chatbots/test-001/status"
    assert p["device"]["name"] == "HIRIS Test Agent"
    assert "command_topic" not in p


def test_build_discovery_payload_switch():
    pub = MQTTPublisher()
    chatbot = _make_chatbot()
    p = pub._build_discovery_payload(chatbot, "enabled", "switch")
    assert "command_topic" in p
    assert p["command_topic"] == "hiris/chatbots/test-001/enabled/set"


def test_build_state_topics_idle_enabled():
    pub = MQTTPublisher()
    chatbot = _make_chatbot()
    topics = pub._build_state_topics(chatbot, budget_eur=0.12, status="idle")
    assert topics["hiris/chatbots/test-001/status"] == "idle"
    assert topics["hiris/chatbots/test-001/enabled"] == "ON"
    assert topics["hiris/chatbots/test-001/budget_eur"] == "0.12"


def test_build_state_topics_disabled():
    pub = MQTTPublisher()
    chatbot = _make_chatbot(enabled=False)
    topics = pub._build_state_topics(chatbot, budget_eur=0.0, status="idle")
    assert topics["hiris/chatbots/test-001/enabled"] == "OFF"


@pytest.mark.asyncio
async def test_publish_noop_when_not_connected():
    pub = MQTTPublisher()
    chatbot = _make_chatbot()
    await pub.publish_chatbot_state(chatbot, budget_eur=0.0, status="idle")  # must not raise
    await pub.publish_discovery(chatbot)  # must not raise


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
    chatbot = _make_chatbot()
    await pub.publish_discovery(chatbot)
    topics = await _drain(pub)

    switch_topic = "homeassistant/switch/chatbot_test-001_enabled/config"
    button_topic = "homeassistant/button/chatbot_test-001_run_now/config"
    assert switch_topic in topics
    assert topics[switch_topic] == ""  # empty payload → HA drops the entity
    assert button_topic in topics
    assert topics[button_topic] == ""


@pytest.mark.asyncio
async def test_publish_discovery_keeps_enabled_as_read_only_sensor():
    pub = MQTTPublisher()
    pub._enabled = True
    chatbot = _make_chatbot()
    await pub.publish_discovery(chatbot)
    topics = await _drain(pub)

    sensor_topic = "homeassistant/sensor/chatbot_test-001_enabled/config"
    assert sensor_topic in topics
    import json
    payload = json.loads(topics[sensor_topic])
    assert payload["state_topic"] == "hiris/chatbots/test-001/enabled"
    assert "command_topic" not in payload  # read-only now, not a control


@pytest.mark.asyncio
async def test_publish_discovery_does_not_crash_without_agent_type():
    """Regression: `_build_discovery_payload` used to read `agent.type` for
    the device "model" field — Chatbot no longer has that attribute."""
    pub = MQTTPublisher()
    pub._enabled = True
    chatbot = _make_chatbot()
    await pub.publish_discovery(chatbot)  # must not raise AttributeError


# ---------------------------------------------------------------------------
# SP-4 Fase A Task 1 — MQTT wire rename (hiris/agents -> hiris/chatbots,
# hiris_<id> -> chatbot_<id>) + one-time legacy discovery cleanup.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_legacy_discovery_publishes_empty_payload_on_old_topics():
    pub = MQTTPublisher()
    pub._enabled = True
    metrics = ["status", "last_run", "last_result", "budget_eur",
               "budget_remaining_eur", "tokens_used_today", "enabled"]

    await pub.cleanup_legacy_discovery(["chat-a", "chat-b"], metrics)
    topics = await _drain(pub)

    for cid in ("chat-a", "chat-b"):
        for metric in metrics:
            topic = f"homeassistant/sensor/hiris_{cid}_{metric}/config"
            assert topic in topics
            assert topics[topic] == ""  # empty retained payload -> HA drops the entity


@pytest.mark.asyncio
async def test_cleanup_legacy_discovery_noop_when_disabled():
    pub = MQTTPublisher()  # _enabled stays False (start() never called)
    await pub.cleanup_legacy_discovery(["chat-a"], ["status"])
    topics = await _drain(pub)
    assert topics == {}


@pytest.mark.asyncio
async def test_cleanup_legacy_discovery_does_not_touch_new_scheme_topics():
    """The old-scheme cleanup must only ever publish to hiris_<id> topics —
    never collide with the new chatbot_<id> discovery scheme."""
    pub = MQTTPublisher()
    pub._enabled = True
    await pub.cleanup_legacy_discovery(["chat-a"], ["status"])
    topics = await _drain(pub)
    assert all("chatbot_" not in topic for topic in topics)
    assert all(topic.startswith("homeassistant/sensor/hiris_") for topic in topics)
