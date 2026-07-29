import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DISCOVERY_PREFIX = "homeassistant"
_STATE_PREFIX = "hiris/chatbots"
_RECONNECT_MAX = 60


class MQTTPublisher:
    # Pre-rename (SP-4 Fase A Task 1) discovery/state scheme — kept only so
    # cleanup_legacy_discovery() can retract the orphaned discovery configs
    # AND the stale retained state messages published under it. Never used
    # to publish new state/discovery.
    _OLD_STATE_PREFIX = "hiris/agents"
    _OLD_ID_FMT = "hiris_{id}"

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

    def _build_discovery_payload(self, chatbot, metric: str, component: str) -> dict:
        payload: dict = {
            "unique_id": f"chatbot_{chatbot.id}_{metric}",
            "name": metric.replace("_", " ").title(),
            "device": {
                "identifiers": [f"chatbot_{chatbot.id}"],
                "name": f"HIRIS {chatbot.name}",
                "manufacturer": "HIRIS",
                # Slice 5 Task 2 dropped Agent.type — every persona is the
                # chat entity now, so there is no per-chatbot "model" variant
                # left to report here. Review finale pre-1.0, finding m8:
                # this device is built per-Chatbot (unique_id/identifiers are
                # "chatbot_{id}_..."), and "Persona" is the retired Slice-5
                # name for that same entity -- the current model (CLAUDE.md
                # "The current model — three AI entities") calls it
                # "Chatbot" everywhere else, so every HIRIS MQTT device was
                # showing model "Persona" in HA instead of "Chatbot".
                "model": "Chatbot",
            },
        }
        if component == "button":
            payload["command_topic"] = f"{_STATE_PREFIX}/{chatbot.id}/{metric}/set"
            payload["payload_press"] = "PRESS"
        else:
            payload["state_topic"] = f"{_STATE_PREFIX}/{chatbot.id}/{metric}"
            if component == "switch":
                payload["command_topic"] = f"{_STATE_PREFIX}/{chatbot.id}/{metric}/set"
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
        chatbot,
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
            f"{_STATE_PREFIX}/{chatbot.id}/status": status,
            f"{_STATE_PREFIX}/{chatbot.id}/enabled": "ON" if chatbot.enabled else "OFF",
            f"{_STATE_PREFIX}/{chatbot.id}/budget_eur": str(round(budget_eur, 4)),
            f"{_STATE_PREFIX}/{chatbot.id}/last_run": chatbot.last_run or "",
            f"{_STATE_PREFIX}/{chatbot.id}/last_result": (chatbot.last_result or "")[:255],
            f"{_STATE_PREFIX}/{chatbot.id}/budget_remaining_eur": remaining,
            f"{_STATE_PREFIX}/{chatbot.id}/tokens_used_today": str(tokens_used_today),
        }

    # Task 1 removed the MQTT command callback (no scheduler/autonomous
    # execution left to enable or manually trigger), so the "enabled" switch
    # and "run_now" button this used to (re)discover were dead controls in
    # HA — pressing/flipping them did nothing. We stop advertising them and
    # publish an empty config on their old discovery topics so HA drops any
    # already-discovered entity from an install upgrading from an older
    # release, instead of leaving it visible-but-inert.
    _RETIRED_COMMAND_ENTITIES = (("enabled", "switch"), ("run_now", "button"))

    # Metric list mirrored by cleanup_legacy_discovery() below — keep the two
    # in sync (this is the real list published for every chatbot, read off
    # the live code rather than assumed).
    _DISCOVERY_METRICS = (
        "status", "last_run", "last_result", "budget_eur",
        "budget_remaining_eur", "tokens_used_today", "enabled",
    )

    async def publish_discovery(self, chatbot) -> None:
        if not self._enabled:
            return
        metrics = [(m, "sensor") for m in self._DISCOVERY_METRICS]
        for metric, component in metrics:
            payload = self._build_discovery_payload(chatbot, metric, component)
            topic = f"{_DISCOVERY_PREFIX}/{component}/chatbot_{chatbot.id}_{metric}/config"
            await self._pending.put((topic, json.dumps(payload)))
        for metric, component in self._RETIRED_COMMAND_ENTITIES:
            topic = f"{_DISCOVERY_PREFIX}/{component}/chatbot_{chatbot.id}_{metric}/config"
            await self._pending.put((topic, ""))

    async def publish_chatbot_state(
        self,
        chatbot,
        budget_eur: float = 0.0,
        status: str = "idle",
        budget_remaining_eur: str | float = "unlimited",
        tokens_used_today: int = 0,
    ) -> None:
        if not self._connected:
            return
        for topic, payload in self._build_state_topics(
            chatbot,
            budget_eur=budget_eur,
            status=status,
            budget_remaining_eur=budget_remaining_eur,
            tokens_used_today=tokens_used_today,
        ).items():
            await self._pending.put((topic, payload))

    # ── Legacy discovery cleanup (SP-4 Fase A Task 1) ──────────────────────
    # The Agent -> Chatbot rename changed the discovery unique_id/device
    # scheme from "hiris_<id>" to "chatbot_<id>" and the state topic prefix
    # from "hiris/agents" to "hiris/chatbots". Home Assistant does not drop
    # the old entities on its own — they'd sit orphaned in the registry
    # forever unless we explicitly retract them (empty retained payload on
    # their old discovery config topics). Called once at boot (server.py),
    # guarded by a marker file, after chatbots are loaded and before any
    # new-scheme publish_discovery() runs for them.
    #
    # NOTE: the plan's reference snippet used a stored `self._client.publish`
    # — this class has no such attribute (the aiomqtt client is local to
    # `_connect_loop`; every other publish method here goes through the
    # `_pending` queue drained by `_publish_drain`). Reusing that same queue
    # keeps this consistent with publish_discovery/publish_chatbot_state
    # instead of introducing a second, parallel publish path.
    async def cleanup_legacy_discovery(self, chatbot_ids: list[str], metrics: list[str]) -> None:
        """Remove HA entities discovered under the pre-rename id scheme
        (``hiris_<id>``) by publishing an empty retained payload on each old
        discovery topic — HA drops the entity (and, once all its entities
        are gone, the device) when it sees an empty config payload.

        Also retracts the old retained STATE topics (``hiris/agents/<id>/
        <metric>``, the pre-rename ``_OLD_STATE_PREFIX``): an empty retained
        publish clears the broker's retained message so a client subscribing
        fresh no longer receives the stale value, mirroring the discovery
        retraction above so no piece of the old scheme is left behind.

        Task 3 (SP-4 Fase B): also retracts the old-scheme COMMAND entities
        (``switch``/``button``) — previously only ``publish_discovery()``
        retracted them, and only under the NEW id scheme, so the old-scheme
        ``homeassistant/switch/hiris_<id>_enabled/config`` and
        ``homeassistant/button/hiris_<id>_run_now/config`` topics were never
        touched, leaving two dead entities per chatbot in HA."""
        if not self._enabled:
            return
        for cid in chatbot_ids:
            old_id = self._OLD_ID_FMT.format(id=cid)
            for metric in metrics:
                topic = f"{_DISCOVERY_PREFIX}/sensor/{old_id}_{metric}/config"
                try:
                    await self._pending.put((topic, ""))
                except Exception:
                    logger.warning("legacy discovery cleanup failed for %s", topic, exc_info=True)
            for metric, component in self._RETIRED_COMMAND_ENTITIES:
                topic = f"{_DISCOVERY_PREFIX}/{component}/{old_id}_{metric}/config"
                try:
                    await self._pending.put((topic, ""))
                except Exception:
                    logger.warning("legacy discovery cleanup failed for %s", topic, exc_info=True)
            for metric in metrics:
                state_topic = f"{self._OLD_STATE_PREFIX}/{cid}/{metric}"
                try:
                    await self._pending.put((state_topic, ""))
                except Exception:
                    logger.warning("legacy state cleanup failed for %s", state_topic, exc_info=True)

    async def wait_drained(self, timeout: float = 30.0) -> bool:
        """Block until every item currently on the outbound ``_pending``
        queue has been published (or the wait times out).

        Used by server.py's one-time legacy-discovery-cleanup marker: that
        marker must only be written once the retraction publishes enqueued
        by ``cleanup_legacy_discovery`` have actually reached the broker —
        writing it right after they're merely *enqueued* would permanently
        skip the retraction if the broker happens to be unreachable at boot
        (routine: HA host and add-ons start together). Returns True if the
        queue drained within ``timeout`` seconds, False on timeout (caller
        must then NOT write the marker, so the next boot retries)."""
        try:
            await asyncio.wait_for(self._pending.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
