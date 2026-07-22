from __future__ import annotations
import logging, time
from datetime import datetime
from typing import Awaitable, Callable
from .snapshot import interpret_presence
from .signals import WakeEvent
from .wake import maybe_wake

log = logging.getLogger(__name__)

def _default_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

async def is_evening(deps: dict, cfg: dict) -> bool:
    sun_entity = cfg.get("sun_entity", "sun.sun")
    try:
        rows = await deps["get_states"]([sun_entity])
        by = {r.get("entity_id"): r for r in (rows or []) if isinstance(r, dict)}
        if sun_entity in by:
            return by[sun_entity].get("state") == "below_horizon"
    except Exception:
        log.debug("is_evening: sun read failed, falling back to hour")
    try:
        return deps["now_hour"]() >= cfg.get("after_hour", 18)
    except Exception:
        return False

class ArrivalWatcher:
    def __init__(self, store, get_config: Callable[[], dict], *, deps: dict,
                 on_arrival: Callable[..., Awaitable],
                 clock: Callable[[], float] = time.time,
                 today: Callable[[], str] = _default_today,
                 cooldown_sec: int = 1800, daily_cap: int = 20) -> None:
        self._store = store
        self._get_config = get_config
        self._deps = deps
        self._on_arrival = on_arrival
        self._clock = clock
        self._today = today
        self._cooldown = cooldown_sec
        self._cap = daily_cap

    async def on_state_changed(self, event) -> None:
        try:
            cfg = self._get_config() or {}
            ea = ((cfg.get("preparation") or {}).get("evening_arrival") or {})
            if not ea.get("enabled"):
                return
            presence_entity = (cfg.get("situations") or {}).get("presence_entity")
            data = event or {}
            if not presence_entity or data.get("entity_id") != presence_entity:
                return
            old = (data.get("old_state") or {}).get("state")
            new = (data.get("new_state") or {}).get("state")
            if not (interpret_presence(old) is False and interpret_presence(new) is True):
                return
            if not await is_evening(self._deps, ea):
                return
            target = ea.get("target_entity")
            if not target:
                return
            domain = target.split(".", 1)[0] if "." in target else "scene"
            suggested = {"domain": domain, "service": "turn_on", "entity_id": target, "data": {}}
            wake = WakeEvent(signal_kind="evening_arrival", entity_id=presence_entity,
                             severity_hint="info", evidence={"target": target}, ts=self._clock())
            await maybe_wake(self._store, f"arrival:{presence_entity}", wake,
                             on_wake=lambda w, s=suggested: self._on_arrival(w, s),
                             clock=self._clock, today=self._today,
                             cooldown_sec=self._cooldown, daily_cap=self._cap, cap_scope="arrival")
        except Exception:
            log.exception("arrival on_state_changed failed")
