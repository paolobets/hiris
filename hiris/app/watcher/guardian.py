from __future__ import annotations
import logging, time
from datetime import datetime
from typing import Awaitable, Callable
from .detectors import DETECTORS
from .signals import wake_from_signal, WakeEvent
from .wake import maybe_wake

log = logging.getLogger(__name__)

def _default_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

class Guardian:
    def __init__(self, store, get_policy: Callable[[], dict],
                 on_wake: Callable[[WakeEvent], Awaitable],
                 *, clock: Callable[[], float] = time.time,
                 today: Callable[[], str] = _default_today,
                 cooldown_sec: int = 1800, daily_cap: int = 20) -> None:
        self._store = store
        self._get_policy = get_policy
        self._policy_override: dict | None = None
        self._on_wake = on_wake
        self._clock = clock
        self._today = today
        self._cooldown = cooldown_sec
        self._cap = daily_cap

    def set_policy(self, policy: dict) -> None:
        """Apply a policy override live (e.g. right after the UI saves new
        detector config), bypassing the next disk read via ``get_policy``."""
        self._policy_override = policy

    async def on_state_changed(self, event: dict) -> None:
        try:
            data = event or {}
            eid = data.get("entity_id")
            if not eid:
                return
            old, new = data.get("old_state"), data.get("new_state")
            source = self._policy_override if self._policy_override is not None else (self._get_policy() or {})
            pol = source.get("detectors", {})
            now = self._clock()
            for kind, fn in DETECTORS.items():
                dcfg = pol.get(kind) or {}
                if not dcfg.get("enabled"):
                    continue
                if eid not in (dcfg.get("entities") or []):
                    continue
                sig = fn(eid, old, new, dcfg, now)
                key = f"{kind}:{eid}"
                if sig is None:
                    self._store.clear_timer(key)   # condizione rientrata
                    continue
                if sig.evidence.get("needs_duration"):
                    self._store.open_timer(key, now)
                    started = self._store.timer_started_at(key)
                    thr = float(sig.evidence.get("threshold_min", 10)) * 60.0
                    if started is None or (now - started) < thr:
                        continue
                    sig.evidence["minutes"] = round((now - started) / 60.0, 1)
                await self._maybe_wake(key, sig, now)
        except Exception:  # noqa: BLE001 — mai far crollare il listener
            log.exception("guardian on_state_changed failed")

    async def _maybe_wake(self, key: str, sig, now: float) -> None:
        await maybe_wake(self._store, key, wake_from_signal(sig),
                          on_wake=self._on_wake, clock=lambda: now, today=self._today,
                          cooldown_sec=self._cooldown, daily_cap=self._cap, cap_scope="events")
