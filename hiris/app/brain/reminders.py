from __future__ import annotations
from datetime import date, timedelta


def due_obligations_to_notify(store, *, today: date, horizon_days: int = 7) -> list[dict]:
    """Obligations due within `horizon_days` from `today` (overdue included)."""
    before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    return store.upcoming_obligations(before=before)
