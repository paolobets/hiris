from __future__ import annotations
from datetime import date, timedelta


def due_obligations_to_notify(store, *, today: date, horizon_days: int = 7) -> list[dict]:
    """Obligations due within `horizon_days` from `today` (overdue included)."""
    before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    return store.upcoming_obligations(before=before)


async def run_due_reminders(store, notify, *, today: date, horizon_days: int = 7) -> int:
    """Compute due obligations (off the event loop) and call `notify(item)` for each.

    `notify` is an async callable that receives a single obligation dict.
    Returns the number of items notified.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(
        None,
        lambda: due_obligations_to_notify(store, today=today, horizon_days=horizon_days),
    )
    for it in items:
        await notify(it)
    return len(items)
