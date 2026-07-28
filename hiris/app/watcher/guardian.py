from __future__ import annotations
import logging, time
from datetime import datetime
from typing import Awaitable, Callable, Optional
from .detectors import DETECTORS, make_generic_detector
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
                 cooldown_sec: int = 1800, daily_cap: int = 20,
                 get_user_agentbots: Optional[Callable[[], list]] = None,
                 run_agentbot: Optional[Callable[[dict, dict], Awaitable]] = None) -> None:
        self._store = store
        self._get_policy = get_policy
        self._policy_override: dict | None = None
        self._on_wake = on_wake
        self._clock = clock
        self._today = today
        self._cooldown = cooldown_sec
        self._cap = daily_cap
        # Slice 5b / Task 4: EVENT-triggered user Agentbots (renamed from
        # "lens" in SP-4 Fase A Task 3), dispatched ALONGSIDE (never instead
        # of) the built-in DETECTORS loop below. `get_user_agentbots` returns
        # the current enabled event-type Agentbots (server.py wires it to
        # `watcher.lenses.load_agentbots(data_dir)` filtered accordingly);
        # `run_agentbot` is `app["run_agentbot"]` (the shared Task-3 flow).
        # Both optional so every existing built-in-only call site (and every
        # built-in regression test) keeps working unchanged with zero
        # user-Agentbot overhead.
        self._get_user_agentbots = get_user_agentbots or (lambda: [])
        self._run_agentbot = run_agentbot

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

            # Slice 5b / Task 4: EVENT-triggered user Agentbots. Same eid,
            # same `now`, same duration-timer gating as the built-ins above
            # (the store's timers table is keyed by string, so an
            # `agentbot:<id>:<eid>` key can't collide with a built-in
            # `<kind>:<eid>` key) — but cooldown/daily-cap gating for user
            # Agentbots lives INSIDE `run_agentbot` (its own `maybe_wake`
            # call, per-Agentbot `cap_scope`), not here, so it is
            # deliberately NOT re-done via `self._maybe_wake` for this
            # branch.
            if self._run_agentbot is not None:
                await self._dispatch_user_agentbots(eid, old, new, now)
        except Exception:  # noqa: BLE001 — mai far crollare il listener
            log.exception("guardian on_state_changed failed")

    async def _dispatch_user_agentbots(self, eid: str, old, new, now: float) -> None:
        try:
            agentbots = self._get_user_agentbots() or []
        except Exception:
            log.exception("guardian: get_user_agentbots failed")
            return
        for agentbot in agentbots:
            if not isinstance(agentbot, dict) or not agentbot.get("enabled"):
                continue  # review fix: never fire a disabled Agentbot
            trigger = agentbot.get("trigger") or {}
            if trigger.get("type") != "event" or trigger.get("entity_id") != eid:
                continue
            agentbot_id = agentbot.get("id", "-")
            key = f"agentbot:{agentbot_id}:{eid}"
            try:
                sig = make_generic_detector(trigger)(eid, old, new, {}, now)
            except Exception:
                log.exception("guardian: user Agentbot detector failed for agentbot %s", agentbot_id)
                continue
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
            try:
                # review fix: a broken Agentbot (bad adapter, LLM hiccup, ...)
                # must never take down the rest of this dispatch batch.
                await self._run_agentbot(agentbot, sig.evidence)
            except Exception:
                log.exception("guardian: run_agentbot failed for agentbot %s", agentbot_id)
                continue

    async def _maybe_wake(self, key: str, sig, now: float) -> None:
        await maybe_wake(self._store, key, wake_from_signal(sig),
                          on_wake=self._on_wake, clock=lambda: now, today=self._today,
                          cooldown_sec=self._cooldown, daily_cap=self._cap, cap_scope="events")
