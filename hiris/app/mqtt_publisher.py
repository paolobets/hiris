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

    # MQTT v5 reason codes that indicate a permanent auth/config failure
    _AUTH_CODES = frozenset({
        4,    # MQTT v3: Connection Refused, Bad Username or Password
        5,    # MQTT v3: Connection Refused, Not Authorized
        133,  # MQTT v5 0x85: Client Identifier Not Valid
        134,  # MQTT v5 0x86: Bad User Name or Password
        135,  # MQTT v5 0x87: Not Authorized
        151,  # MQTT v5 0x97: Quota Exceeded (broker-side block)
    })

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        msg = str(exc)
        for code in MQTTPublisher._AUTH_CODES:
            if f"[code:{code}]" in msg or f"code={code}" in msg:
                return True
        return False

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
                logger.info(
                    "MQTT connecting to %s:%d (user=%r, password_len=%d)",
                    self._host, self._port, self._user, len(self._password),
                )
                async with aiomqtt.Client(**kwargs) as client:
                    self._connected = True
                    backoff = 1
                    logger.info("MQTT connected to %s:%d", self._host, self._port)

                    # No inbound command topics to subscribe to (Slice 5 Task
                    # 2): the `enabled`/`run_now` command callback was retired
                    # in Task 1 (no scheduler/autonomous execution left to
                    # enable or trigger) — this publisher is outbound-only
                    # (discovery + state) now, so draining the outbound queue
                    # is the only thing keeping this connection busy.
                    try:
                        await self._publish_drain(client)
                    finally:
                        self._connected = False

            except asyncio.CancelledError:
                self._connected = False
                break
            except Exception as exc:
                self._connected = False
                if self._is_auth_error(exc):
                    # Auth errors won't resolve by retrying quickly — use max backoff
                    logger.error(
                        "MQTT auth error connecting to %s:%d as user=%r — "
                        "verifica credenziali nel broker Mosquitto. "
                        "Prossimo tentativo in %ds. (%s)",
                        self._host, self._port, self._user, _RECONNECT_MAX, exc,
                    )
                    await asyncio.sleep(_RECONNECT_MAX)
                else:
                    logger.warning("MQTT disconnected: %s. Reconnecting in %ds", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _RECONNECT_MAX)

    async def _publish_drain(self, client) -> None:
        """Drain ``self._pending`` onto the broker until cancelled.

        Cancellation propagates from ``stop()`` cancelling the outer
        ``_connect_loop`` task — no separate teardown needed here.
        """
        while True:
            topic, payload = await self._pending.get()
            await client.publish(topic, payload, retain=True)
            self._pending.task_done()

    # ── Discovery ──────────────────────────────────────────────────────────────

    def _build_discovery_payload(self, agent, metric: str, component: str) -> dict:
        payload: dict = {
            "unique_id": f"hiris_{agent.id}_{metric}",
            "name": metric.replace("_", " ").title(),
            "device": {
                "identifiers": [f"hiris_{agent.id}"],
                "name": f"HIRIS {agent.name}",
                "manufacturer": "HIRIS",
                # Slice 5 Task 2 dropped Agent.type — every persona is the
                # chat entity now, so there is no per-agent "model" variant
                # left to report here.
                "model": "Persona",
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

    # Task 1 removed the MQTT command callback (no scheduler/autonomous
    # execution left to enable or manually trigger), so the "enabled" switch
    # and "run_now" button this used to (re)discover were dead controls in
    # HA — pressing/flipping them did nothing. We stop advertising them and
    # publish an empty config on their old discovery topics so HA drops any
    # already-discovered entity from an install upgrading from an older
    # release, instead of leaving it visible-but-inert.
    _RETIRED_COMMAND_ENTITIES = (("enabled", "switch"), ("run_now", "button"))

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
            # Read-only now (was a "switch" with a dead command_topic): still
            # worth surfacing whether a persona is enabled, just not as a
            # control.
            ("enabled", "sensor"),
        ]
        for metric, component in metrics:
            payload = self._build_discovery_payload(agent, metric, component)
            topic = f"{_DISCOVERY_PREFIX}/{component}/hiris_{agent.id}_{metric}/config"
            await self._pending.put((topic, json.dumps(payload)))
        for metric, component in self._RETIRED_COMMAND_ENTITIES:
            topic = f"{_DISCOVERY_PREFIX}/{component}/hiris_{agent.id}_{metric}/config"
            await self._pending.put((topic, ""))

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
