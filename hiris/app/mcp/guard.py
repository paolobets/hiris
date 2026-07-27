from __future__ import annotations
import logging
from collections import deque

logger = logging.getLogger(__name__)


class McpGuard:
    """Kill-switch + audit in-memory per l'MCP interno (item I2). Il semaforo
    HIRIS resta il gate delle azioni; questo aggiunge stop d'emergenza + traccia.

    Non thread-safe: assume esecuzione su un unico event loop asyncio. Una
    futura attivazione del kill-switch da un thread separato deve rivedere
    questa assunzione (serve un lock o comunicazione cross-thread sicura)."""

    def __init__(self, audit_max: int = 200) -> None:
        self._killed = False
        self.audit: deque = deque(maxlen=audit_max)

    def is_killed(self) -> bool:
        return self._killed

    def set_killed(self, value: bool) -> None:
        self._killed = bool(value)
        logger.warning("MCP kill-switch %s", "ON" if self._killed else "OFF")

    def record(self, tool: str, outcome: str, latency_ms: int) -> None:
        self.audit.append({"tool": tool, "outcome": outcome, "latency_ms": latency_ms})
