"""I compiti senza padrone: l'unico posto del prodotto che ne crea uno.

Spostato da `server.py` il 06/10/2026 (attori, strato 4, Task 4.5), senza
cambiare una riga di logica: «Rendila automatica» fa girare il suo turno sulla
catena in un compito, e un modulo di `mind/` non importa `server.py`.
"""
from __future__ import annotations

import asyncio

# review C/#15: asyncio only holds a WEAK reference to a task with no other
# referrer -- a bare `asyncio.create_task(...)` whose result is discarded can
# be garbage-collected mid-execution (see the asyncio docs' "Important" note
# on create_task). Several fire-and-forget spots in server.py discarded the
# result, including the HA notification-action listener that drives the
# step-up APPROVAL flow (a human's phone-tap Approve/Reject awaits HTTP calls
# to HA and must not be silently dropped mid-flight). background_tasks keeps
# a strong reference until each task finishes; spawn() is the one place that
# creates a background task, so every fire-and-forget site goes through it.
background_tasks: set[asyncio.Task] = set()


def spawn(coro, *, name: str | None = None) -> asyncio.Task:
    """Create a fire-and-forget task and keep a strong reference to it.

    Use this instead of a bare `asyncio.create_task(...)` for any task whose
    result is not awaited/stored by the caller -- otherwise nothing prevents
    the event loop from garbage-collecting it before it completes.
    """
    task = asyncio.create_task(coro, name=name)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task
