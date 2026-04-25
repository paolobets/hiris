import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DISCOVERY_PREFIX = "homeassistant"
_STATE_PREFIX = "hiris/agents"
_RECONNECT_MAX = 60


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

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self, host: str, port: int = 1883, user: str = "", password: str = "") -> None:
        if not host:
            logger.info("MQTT host not configured — publisher disabled")
            return
        self._host = host
        self._port = port
        self._user = user
        self._password = password
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
                kwargs: dict = {"hostname": self._host, "port": self._port}
                if self._user:
                    kwargs["username"] = self._user
                if self._password:
                    kwargs["password"] = self._password
                async with aiomqtt.Client(**kwargs) as client:
                    self._connected = True
                    backoff = 1
                    logger.info("MQTT connected to %s:%d", self._host, self._port)
                    while True:
                        topic, payload = await self._pending.get()
                        await client.publish(topic, payload, retain=True)
                        self._pending.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._connected = False
                logger.warning("MQTT disconnected: %s. Reconnecting in %ds", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RECONNECT_MAX)

    def _build_discovery_payload(self, agent, metric: str, component: str) -> dict:
        payload: dict = {
            "unique_id": f"hiris_{agent.id}_{metric}",
            "name": metric.replace("_", " ").title(),
            "state_topic": f"{_STATE_PREFIX}/{agent.id}/{metric}",
            "device": {
                "identifiers": [f"hiris_{agent.id}"],
                "name": f"HIRIS {agent.name}",
                "manufacturer": "HIRIS",
                "model": agent.type,
            },
        }
        if component == "switch":
            payload["command_topic"] = f"{_STATE_PREFIX}/{agent.id}/{metric}/set"
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
        elif metric == "budget_eur":
            payload["unit_of_measurement"] = "EUR"
            payload["device_class"] = "monetary"
        return payload

    def _build_state_topics(self, agent, budget_eur: float = 0.0, status: str = "idle") -> dict:
        return {
            f"{_STATE_PREFIX}/{agent.id}/status": status,
            f"{_STATE_PREFIX}/{agent.id}/enabled": "ON" if agent.enabled else "OFF",
            f"{_STATE_PREFIX}/{agent.id}/budget_eur": str(round(budget_eur, 4)),
            f"{_STATE_PREFIX}/{agent.id}/last_run": agent.last_run or "",
        }

    async def publish_discovery(self, agent) -> None:
        # Enqueue even when not yet connected so discovery config survives
        # the initial MQTT backoff period (messages drain once connected).
        if not self._enabled:
            return
        metrics = [
            ("status", "sensor"),
            ("last_run", "sensor"),
            ("budget_eur", "sensor"),
            ("enabled", "switch"),
        ]
        for metric, component in metrics:
            payload = self._build_discovery_payload(agent, metric, component)
            topic = f"{_DISCOVERY_PREFIX}/{component}/hiris_{agent.id}_{metric}/config"
            await self._pending.put((topic, json.dumps(payload)))

    async def publish_agent_state(self, agent, budget_eur: float = 0.0, status: str = "idle") -> None:
        if not self._connected:
            return
        for topic, payload in self._build_state_topics(agent, budget_eur=budget_eur, status=status).items():
            await self._pending.put((topic, payload))
