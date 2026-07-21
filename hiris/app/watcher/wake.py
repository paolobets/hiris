"""Shared wake-gating logic: cooldown + daily cap + record.

Extracted from Guardian._maybe_wake so the situation evaluator can reuse the
same cooldown/cap semantics with its own `cap_scope`, backed by the same
per-scope daily counters in SentinelStore (schema v2)."""
from __future__ import annotations
from typing import Awaitable, Callable


async def maybe_wake(store, key: str, wake, *, on_wake: Callable[..., Awaitable],
                      clock: Callable[[], float], today: Callable[[], str],
                      cooldown_sec: int, daily_cap: int, cap_scope: str = "events") -> str:
    """Gate a candidate wake-up through cooldown then daily cap.

    Returns "woke" | "cooldown" | "cap". On "woke", records the wake
    (cooldown timestamp + scoped daily counter) and awaits `on_wake(wake)`.
    On "cap", records a "cap" outcome event for observability.
    """
    now = clock()
    last = store.last_wake(key)
    if last is not None and (now - last) < cooldown_sec:
        return "cooldown"
    day = today()
    if store.wakes_today(day, cap_scope) >= daily_cap:
        store.record_event({"ts": now, "kind": cap_scope, "entity_id": key,
                             "verdict": None, "severity": None, "outcome": "cap",
                             "message": "cap giornaliero raggiunto"})
        return "cap"
    store.mark_wake(key, now)
    store.incr_wakes_today(day, cap_scope)
    await on_wake(wake)
    return "woke"
