"""Tests for review C/#15: fire-and-forget asyncio.create_task(...) results
were discarded across server.py (no stored reference). Per asyncio's
documented weak-reference semantics, a task with no external referrer can be
garbage-collected mid-execution.

Fix: a module-level `_background_tasks` strong-reference set plus a
`_spawn()` helper that adds each created task to it and wires a done-callback
to discard it on completion. Every previously-bare `asyncio.create_task(...)`
call site in server.py must now go through `_spawn()`.

GC itself is not directly testable/deterministic here, so this file verifies:
  1. `_spawn()` behavior: the returned task is added to `_background_tasks`
     while pending and removed once it completes (via the done-callback).
  2. Source-level wiring: no bare `asyncio.create_task(...)` call remains in
     server.py outside `_spawn()`'s own body (mirrors the existing
     `test_*_wiring.py` inspect-source convention, e.g. test_mayan_wiring.py /
     test_sentinel_wiring.py).

Fetta E2 Task 5 ("escono le conferme del gateway"): point 3 originally here
asserted that the HA notification-action listener (the phone-tap
Approve/Reject wiring for the gateway's pending/OTP store) routed through
`_spawn(...)`. That listener registration -- and `add_action_listener` /
`_action_listeners` on HAClient entirely -- is removed with it: the pending
store it drove was dead by construction (see handlers_gateway_pending.py's
removal), so there is nothing left to phone-tap. The test asserting that
wiring is gone with its subject, not moved.
"""
import ast
import asyncio
import inspect

import pytest

from hiris.app import server


# ── 1. _spawn() behavior ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_keeps_strong_ref_while_pending_and_discards_on_done():
    gate = asyncio.Event()

    async def _work():
        await gate.wait()
        return "done"

    task = server._spawn(_work(), name="test_spawn_task")

    # Strong ref held while pending -- this is the whole point of the fix:
    # nothing else in the caller holds `task`, so without _background_tasks
    # the task would be eligible for GC right here.
    assert task in server._background_tasks
    assert not task.done()

    gate.set()
    result = await task

    assert result == "done"
    # Done-callback must discard it once finished, or the set would grow
    # unbounded across the process lifetime.
    assert task not in server._background_tasks


@pytest.mark.asyncio
async def test_spawn_discards_on_exception_too():
    async def _boom():
        raise ValueError("boom")

    task = server._spawn(_boom(), name="test_spawn_boom")
    assert task in server._background_tasks

    with pytest.raises(ValueError):
        await task

    assert task not in server._background_tasks


@pytest.mark.asyncio
async def test_spawn_returns_asyncio_task_with_name():
    async def _noop():
        return None

    task = server._spawn(_noop(), name="my_named_task")
    assert isinstance(task, asyncio.Task)
    assert task.get_name() == "my_named_task"
    await task


# ── 2. Source-level wiring: every create_task(...) site goes through _spawn ─


def _find_spawn_def(tree: ast.Module) -> ast.FunctionDef:
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_spawn"
    )


def test_only_spawn_itself_calls_asyncio_create_task():
    """No other call site in server.py may call asyncio.create_task(...)
    directly -- every fire-and-forget task must go through _spawn() so it
    gets a strong reference. AST-based (not text/grep-based) so comments
    mentioning 'asyncio.create_task' in prose don't produce false positives."""
    source = inspect.getsource(server)
    tree = ast.parse(source)
    spawn_def = _find_spawn_def(tree)
    spawn_line_range = range(spawn_def.lineno, spawn_def.end_lineno + 1)

    offending_lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_create_task_call = (
            (isinstance(func, ast.Attribute) and func.attr == "create_task")
            or (isinstance(func, ast.Name) and func.id == "create_task")
        )
        if is_create_task_call and node.lineno not in spawn_line_range:
            offending_lines.append(node.lineno)

    assert offending_lines == [], (
        f"asyncio.create_task(...) called outside _spawn() at line(s): "
        f"{offending_lines} -- route these through _spawn() so the task "
        f"gets a strong reference (review C/#15)."
    )


def test_spawn_body_adds_to_background_tasks_and_wires_done_callback():
    """Sanity-check _spawn()'s own implementation does what the docstring/
    comment claims, so the AST check above isn't the only thing standing
    between us and a regression (e.g. someone 'fixing' _spawn to no longer
    track the task)."""
    source = inspect.getsource(server._spawn)
    assert "_background_tasks.add(" in source
    assert "add_done_callback(" in source
    assert "_background_tasks.discard" in source
