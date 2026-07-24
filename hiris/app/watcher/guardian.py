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
                 get_user_lenses: Optional[Callable[[], list]] = None,
                 run_lens: Optional[Callable[[dict, dict], Awaitable]] = None) -> None:
        self._store = store
        self._get_policy = get_policy
        self._policy_override: dict | None = None
        self._on_wake = on_wake
        self._clock = clock
        self._today = today
        self._cooldown = cooldown_sec
        self._cap = daily_cap
        # Slice 5b / Task 4: EVENT-triggered user lenses, dispatched ALONGSIDE
        # (never instead of) the built-in DETECTORS loop below. `get_user_lenses`
        # returns the current enabled event-type lenses (server.py wires it to
        # `watcher.lenses.load_lenses(data_dir)` filtered accordingly); `run_lens`
        # is `app["run_lens"]` (the shared Task-3 flow). Both optional so every
        # existing built-in-only call site (and every built-in regression test)
        # keeps working unchanged with zero user-lens overhead.
        self._get_user_lenses = get_user_lenses or (lambda: [])
        self._run_lens = run_lens

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

            # Slice 5b / Task 4: EVENT-triggered user lenses. Same eid, same
            # `now`, same duration-timer gating as the built-ins above (the
            # store's timers table is keyed by string, so a `lens:<id>:<eid>`
            # key can't collide with a built-in `<kind>:<eid>` key) — but
            # cooldown/daily-cap gating for user lenses lives INSIDE
            # `run_lens` (its own `maybe_wake` call, per-lens `cap_scope`),
            # not here, so it is deliberately NOT re-done via
            # `self._maybe_wake` for this branch.
            if self._run_lens is not None:
                await self._dispatch_user_lenses(eid, old, new, now)
        except Exception:  # noqa: BLE001 — mai far crollare il listener
            log.exception("guardian on_state_changed failed")

    async def _dispatch_user_lenses(self, eid: str, old, new, now: float) -> None:
        try:
            lenses = self._get_user_lenses() or []
        except Exception:
            log.exception("guardian: get_user_lenses failed")
            return
        for lens in lenses:
            if not isinstance(lens, dict) or not lens.get("enabled"):
                continue  # review fix: never fire a disabled lens
            trigger = lens.get("trigger") or {}
            if trigger.get("type") != "event" or trigger.get("entity_id") != eid:
                continue
            lens_id = lens.get("id", "-")
            key = f"lens:{lens_id}:{eid}"
            try:
                sig = make_generic_detector(trigger)(eid, old, new, {}, now)
            except Exception:
                log.exception("guardian: user lens detector failed for lens %s", lens_id)
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
                # review fix: a broken lens (bad adapter, LLM hiccup, ...)
                # must never take down the rest of this dispatch batch.
                await self._run_lens(lens, sig.evidence)
            except Exception:
                log.exception("guardian: run_lens failed for lens %s", lens_id)
                continue

    async def _maybe_wake(self, key: str, sig, now: float) -> None:
        await maybe_wake(self._store, key, wake_from_signal(sig),
                          on_wake=self._on_wake, clock=lambda: now, today=self._today,
                          cooldown_sec=self._cooldown, daily_cap=self._cap, cap_scope="events")
