import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

_DISCOVERY_PREFIX = "homeassistant"
_STATE_PREFIX = "hiris/agents"
_RECONNECT_MAX = 60

# Topics HIRIS subscribes to for inbound commands
_CMD_TOPICS = (
    f"{_STATE_PREFIX}/+/enabled/set",
    f"{_STATE_PREFIX}/+/run_now/set",
)

_CommandCallback = Callable[[str, str, str], Coroutine[Any, Any, None]]


class MQTTPublisher:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._enabled = False   # True once start() is called with a non-empty host
        self._host = ""
        self._port = 1883
        self._user = ""
        self._password = ""
        self._pending: asyncio.Queue = asyncio.Queue()
        self._command_callback: Optional[_CommandCallback] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_command_callback(self, cb: _CommandCallback) -> None:
        self._command_callback = cb

    async def start(self, host: str, port: int = 1883, user: str = "", password: str = "") -> None:
        if not host:
            logger.info("MQTT host not configured — publisher disabled")
            return
        self._host = host.strip()
        self._port = port
        self._user = user.strip()
        self._password = password.strip()
        self._enabled = True
        self._task = asyncio.create_task(self._connect_loop(), name="mqtt_publisher")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False

    async def _connect_loop(self) -> None:
        try:
            import aiomqtt
        except ImportError:
            logger.error("aiomqtt not installed — run: pip install aiomqtt>=2.0.0")
            return

        backoff = 1
        while True:
            try:
                kwargs: dict = {
                    "hostname": self._host,
                    "port": self._port,
                    "identifier": "hiris",
                }
                if self._user:
                    kwargs["username"] = self._user
                if self._password:
                    kwargs["password"] = self._password
                logger.debug(
                    "MQTT connecting to %s:%d user=%r password_len=%d",
                    self._host, self._port, self._user, len(self._password),
                )
                async with aiomqtt.Client(**kwargs) as client:
                    self._connected = True
                    backoff = 1
                    logger.info("MQTT connected to %s:%d", self._host, self._port)

                    for topic in _CMD_TOPICS:
                        await client.subscribe(topic)
                    logger.debug("MQTT subscribed to command topics")

                    # Run publish drain and subscribe loop concurrently
                    async def _publish_drain() -> None:
                        while True:
                            topic, payload = await self._pending.get()
                            await client.publish(topic, payload, retain=True)
                            self._pending.task_done()

                    publish_task = asyncio.create_task(_publish_drain(), name="mqtt_publish_drain")
                    try:
                        async for message in client.messages:
                            asyncio.create_task(
                                self._on_command(str(message.topic), message.payload.decode()),
                                name="mqtt_cmd",
                            )
                    finally:
                        self._connected = False
                        publish_task.cancel()
                        try:
                            await publish_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                self._connected = False
                break
            except Exception as exc:
                self._connected = False
                logger.warning("MQTT disconnected: %s. Reconnecting in %ds", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RECONNECT_MAX)

    async def _on_command(self, topic: str, payload: str) -> None:
        # Expected topic: hiris/agents/{agent_id}/{command}/set
        parts = topic.split("/")
        if len(parts) != 5 or parts[0] != "hiris" or parts[1] != "agents" or parts[4] != "set":
            logger.debug("MQTT: unexpected command topic %s", topic)
            return
        agent_id = parts[2]
        command = parts[3]
        if self._command_callback:
            try:
                await self._command_callback(agent_id, command, payload.strip())
            except Exception as exc:
                logger.warning("MQTT command callback error (agent=%s cmd=%s): %s", agent_id, command, exc)

    # ── Discovery ──────────────────────────────────────────────────────────────

    def _build_discovery_payload(self, agent, metric: str, component: str) -> dict:
        payload: dict = {
            "unique_id": f"hiris_{agent.id}_{metric}",
            "name": metric.replace("_", " ").title(),
            "device": {
                "identifiers": [f"hiris_{agent.id}"],
                "name": f"HIRIS {agent.name}",
                "manufacturer": "HIRIS",
                "model": agent.type,
            },
        }
        if component == "button":
            payload["command_topic"] = f"{_STATE_PREFIX}/{agent.id}/{metric}/set"
            payload["payload_press"] = "PRESS"
        else:
            payload["state_topic"] = f"{_STATE_PREFIX}/{agent.id}/{metric}"
            if component == "switch":
                payload["command_topic"] = f"{_STATE_PREFIX}/{agent.id}/{metric}/set"
                payload["payload_on"] = "ON"
                payload["payload_off"] = "OFF"
            elif metric == "budget_eur":
                payload["unit_of_measurement"] = "EUR"
                payload["device_class"] = "monetary"
            elif metric == "budget_remaining_eur":
                # No device_class=monetary: value can be "unlimited" (non-numeric)
                payload["unit_of_measurement"] = "EUR"
            elif metric == "tokens_used_today":
                payload["unit_of_measurement"] = "tokens"
        return payload

    def _build_state_topics(
        self,
        agent,
        budget_eur: float = 0.0,
        status: str = "idle",
        budget_remaining_eur: str | float = "unlimited",
        tokens_used_today: int = 0,
    ) -> dict:
        remaining = (
            budget_remaining_eur
            if isinstance(budget_remaining_eur, str)
            else str(round(budget_remaining_eur, 4))
        )
        return {
            f"{_STATE_PREFIX}/{agent.id}/status": status,
            f"{_STATE_PREFIX}/{agent.id}/enabled": "ON" if agent.enabled else "OFF",
            f"{_STATE_PREFIX}/{agent.id}/budget_eur": str(round(budget_eur, 4)),
            f"{_STATE_PREFIX}/{agent.id}/last_run": agent.last_run or "",
            f"{_STATE_PREFIX}/{agent.id}/last_result": (agent.last_result or "")[:255],
            f"{_STATE_PREFIX}/{agent.id}/budget_remaining_eur": remaining,
            f"{_STATE_PREFIX}/{agent.id}/tokens_used_today": str(tokens_used_today),
        }

    async def publish_discovery(self, agent) -> None:
        if not self._enabled:
            return
        metrics = [
            ("status", "sensor"),
            ("last_run", "sensor"),
            ("last_result", "sensor"),
            ("budget_eur", "sensor"),
            ("budget_remaining_eur", "sensor"),
            ("tokens_used_today", "sensor"),
            ("enabled", "switch"),
            ("run_now", "button"),
        ]
        for metric, component in metrics:
            payload = self._build_discovery_payload(agent, metric, component)
            topic = f"{_DISCOVERY_PREFIX}/{component}/hiris_{agent.id}_{metric}/config"
            await self._pending.put((topic, json.dumps(payload)))

    async def publish_agent_state(
        self,
        agent,
        budget_eur: float = 0.0,
        status: str = "idle",
        budget_remaining_eur: str | float = "unlimited",
        tokens_used_today: int = 0,
    ) -> None:
        if not self._connected:
            return
        for topic, payload in self._build_state_topics(
            agent,
            budget_eur=budget_eur,
            status=status,
            budget_remaining_eur=budget_remaining_eur,
            tokens_used_today=tokens_used_today,
        ).items():
            await self._pending.put((topic, payload))
