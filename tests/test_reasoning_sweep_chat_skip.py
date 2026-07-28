"""Slice 4b Task 2, Fix 1: the ponte-push fallback sweep (server.py's
``_reasoning_sweep``, scheduled as ``hiris_reasoning_sweep``) must NOT treat
an expired ``kind="chat"`` job as a holistic-reasoning job. Before this fix
every expired job -- chat or holistic -- was wrapped in a ``WakeEvent`` and
fed to ``_run_decision`` with ``SITUATION_HOLISTIC_SYSTEM``: a spurious
holistic cycle over an (empty) chat job's context, AND the user's question
silently discarded instead of being surfaced as an error (Fix 2's job).

``_reasoning_sweep`` is a closure defined inside ``server._on_startup``
(same reason test_reasoning_wiring.py mirrors ``_execute_decision``'s verdict
logic rather than instantiating the whole app -- full startup wires
Supervisor/MQTT/etc and every existing fixture calls
``app.on_startup.clear()`` before use). Rather than hand-maintaining a
mirror copy that could silently drift from the shipped code, this test
extracts the REAL function source via ``inspect.getsource`` and executes it
against test doubles for its two free variables (``reasoning_queue``,
``_run_decision``) -- everything else it references (``os``, ``_time``,
``logger``, ``WakeEvent``, ``SITUATION_HOLISTIC_SYSTEM``) is a plain
importable symbol in server.py, not per-instance closure state, so binding
the real ones is exact, not a guess.
"""
import inspect
import logging
import os
import textwrap
import time as _time

import pytest

from hiris.app import server
from hiris.app.reasoning.queue import ReasoningQueue
from hiris.app.watcher.reasoner import SITUATION_HOLISTIC_SYSTEM
from hiris.app.watcher.signals import WakeEvent


def _load_real_reasoning_sweep(reasoning_queue, run_decision):
    src = inspect.getsource(server._on_startup)
    start = src.index("    async def _reasoning_sweep() -> None:")
    end_marker = "reasoning_queue.prune(_time.time() - 7 * 86400)"
    end = src.index(end_marker, start) + len(end_marker)
    func_src = textwrap.dedent(src[start:end])

    namespace = {
        "os": os,
        "_time": _time,
        "logger": logging.getLogger("test_reasoning_sweep_chat_skip"),
        "WakeEvent": WakeEvent,
        "SITUATION_HOLISTIC_SYSTEM": SITUATION_HOLISTIC_SYSTEM,
        "reasoning_queue": reasoning_queue,
        "_run_decision": run_decision,
        # SP-2 tech-debt: _reasoning_sweep now reads BRIDGE_ENABLED via the
        # shared env_util.env_bool helper (module-level import in server.py);
        # the extracted-source exec namespace must provide it too.
        "env_bool": server.env_bool,
    }
    exec(compile(func_src, "<_reasoning_sweep extracted from server.py>", "exec"), namespace)
    return namespace["_reasoning_sweep"]


@pytest.mark.asyncio
async def test_expired_chat_job_not_sent_to_holistic_reasoning(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_ENABLED", "1")
    monkeypatch.setenv("BRIDGE_FALLBACK", "1")

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue(
        "chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
        now - 10, job_id="chat-job", now=now - 100,
    )

    calls = []

    async def fake_run_decision(wake, suggested, system):
        calls.append((wake, suggested, system))

    sweep = _load_real_reasoning_sweep(q, fake_run_decision)
    await sweep()

    assert calls == [], "expired chat job must NOT trigger holistic reasoning"
    job = q.get("chat-job")
    assert job["status"] == "expired"
    q.close()


@pytest.mark.asyncio
async def test_expired_holistic_job_still_sent_to_holistic_reasoning(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_ENABLED", "1")
    monkeypatch.setenv("BRIDGE_FALLBACK", "1")

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue(
        "holistic",
        {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
        {"snapshot": {"foo": "bar"}},
        now - 10, job_id="holistic-job", now=now - 100,
    )

    calls = []

    async def fake_run_decision(wake, suggested, system):
        calls.append((wake, suggested, system))

    sweep = _load_real_reasoning_sweep(q, fake_run_decision)
    await sweep()

    assert len(calls) == 1, "expired holistic job must still be reasoned over"
    wake, suggested, system = calls[0]
    assert wake.signal_kind == "holistic"
    assert wake.evidence["snapshot"] == {"foo": "bar"}
    assert system == SITUATION_HOLISTIC_SYSTEM
    job = q.get("holistic-job")
    assert job["status"] == "expired"
    q.close()


@pytest.mark.asyncio
async def test_mixed_sweep_only_holistic_reasoned_chat_left_expired(tmp_path, monkeypatch):
    """Both kinds expire in the same sweep pass: only the holistic one
    reaches _run_decision, the chat one is simply left in 'expired' state
    (surfaced to the user via the poll route, Fix 2)."""
    monkeypatch.setenv("BRIDGE_ENABLED", "1")
    monkeypatch.setenv("BRIDGE_FALLBACK", "1")

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
              now - 10, job_id="chat-job", now=now - 100)
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
              {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)

    calls = []

    async def fake_run_decision(wake, suggested, system):
        calls.append(wake.signal_kind)

    sweep = _load_real_reasoning_sweep(q, fake_run_decision)
    await sweep()

    assert calls == ["holistic"]
    assert q.get("chat-job")["status"] == "expired"
    assert q.get("holistic-job")["status"] == "expired"
    q.close()
