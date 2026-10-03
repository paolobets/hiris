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
     `test_*_wiring.py` inspect-source convention -- test_mayan_wiring.py e
     test_sentinel_wiring.py, i due esempi citati qui in origine, sono usciti
     coi loro soggetti; la convenzione resta, vedi test_home_space_wiring.py e
     test_reasoning_wiring.py).

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
from pathlib import Path

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


def _is_create_task(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return ((isinstance(func, ast.Attribute) and func.attr == "create_task")
            or (isinstance(func, ast.Name) and func.id == "create_task"))


def _held_by_an_attribute(tree: ast.AST) -> set[int]:
    """Gli `id()` delle chiamate a `create_task` il cui risultato si tiene in un
    attributo (`self._ws_task = asyncio.create_task(...)`): un riferimento
    forte c'e', ed e' la stessa ragione per cui esiste `_spawn`."""
    held = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and _is_create_task(node.value)
                and all(isinstance(target, ast.Attribute) for target in node.targets)):
            held.add(id(node.value))
    return held


def test_only_spawn_itself_calls_asyncio_create_task():
    """No call site in the PRODUCT may call asyncio.create_task(...) and drop
    the result -- every fire-and-forget task must go through server._spawn()
    so it gets a strong reference. A task kept in an attribute
    (`self._ws_task = ...`, the HA websocket loop) already has one.
    AST-based (not text/grep-based) so comments mentioning
    'asyncio.create_task' in prose don't produce false positives.

    Since 03/10/2026 (Tappa 1 of «Una fonte sola di verita'») the gate
    looks at all of `hiris/app`, not at server.py alone: code moving out of
    server.py would otherwise leave the gate green and blind.
    Mutation EXECUTED: a bare `asyncio.create_task(...)` in
    `api/handlers_chat.py` -- red (it was green before)."""
    app_dir = Path(server.__file__).resolve().parent
    offending = []
    for path in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if path.name == "server.py" and path.parent == app_dir:
            spawn_def = _find_spawn_def(tree)
            allowed = range(spawn_def.lineno, spawn_def.end_lineno + 1)
        else:
            allowed = range(0)
        held = _held_by_an_attribute(tree)
        for node in ast.walk(tree):
            if _is_create_task(node) and node.lineno not in allowed and id(node) not in held:
                offending.append(f"{path.relative_to(app_dir).as_posix()}:{node.lineno}")

    assert offending == [], (
        f"asyncio.create_task(...) called outside _spawn() at: {offending} -- "
        "route these through _spawn() so the task gets a strong reference "
        "(review C/#15)."
    )


def test_the_create_task_gate_still_sees_the_product():
    """The derivation did not break: it finds the one call inside _spawn and
    the one held by the HA client. An empty walk would be a green gate that
    looks at nothing."""
    app_dir = Path(server.__file__).resolve().parent
    found = []
    for path in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found += [path.name for node in ast.walk(tree) if _is_create_task(node)]
    assert "server.py" in found and "ha_client.py" in found, found


# Qui stava `test_spawn_body_adds_to_background_tasks_and_wires_done_callback`,
# che cercava `_background_tasks.add(`, `add_done_callback(` e
# `_background_tasks.discard` nel sorgente di `_spawn`. E' uscita il
# 03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'»): lo stesso lo
# guarda, eseguendo `_spawn`, la prima prova di questo file
# (`test_spawn_keeps_strong_ref_while_pending_and_discards_on_done`).
# Mutazioni ESEGUITE su quella: tolto `_background_tasks.add(task)` -- rossa;
# tolto `task.add_done_callback(...)` -- rossa.
