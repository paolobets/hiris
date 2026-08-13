"""Slice 4b Task 2, Fix 1: the ponte-push sweep (server.py's
``_reasoning_sweep``, scheduled as ``hiris_reasoning_sweep``) must not treat
an expired ``kind="chat"`` job as anything else -- it stays 'expired' for its
own caller (the chat poll route) to surface.

fetta E3 Task 4: the holistic branch that used to reason locally over an
expired ``kind="holistic"`` job (the ponte-push fallback, via ``_run_decision``)
is GONE -- it left with ``_holistic_reason``, the only producer of
``kind="holistic"`` jobs. No such job is ever enqueued anymore. If one is
swept anyway (only possible from a ``reasoning.db`` left by a pre-upgrade
install), the sweep must NOT silently drop it: it logs an explicit warning
naming the job and its stale kind, then lets it expire -- same as it always
did for chat, just declared instead of silent. This file used to pin "an
expired holistic job is still reasoned over"; that behavior no longer exists
in the product, so the test adapts to what replaced it rather than being
deleted outright -- the subject (the sweep's per-kind branching) survives,
only its outcome for non-chat kinds changed.

``_reasoning_sweep`` is a closure defined inside ``server._on_startup`` (same
reason test_reasoning_wiring.py mirrors ``_execute_decision``'s verdict logic
rather than instantiating the whole app -- full startup wires Supervisor/
MQTT/etc and every existing fixture calls ``app.on_startup.clear()`` before
use). Rather than hand-maintaining a mirror copy that could silently drift
from the shipped code, this test extracts the REAL function source via
``inspect.getsource`` and executes it against a test double for its one
remaining free variable of interest (``reasoning_queue``) -- everything else
it references (``_time``, ``logger``, ``env_bool``, ``_sub_first_class``) is
either a plain importable symbol in server.py or a simple closure value
supplied directly, not per-instance state, so binding them is exact, not a
guess. (Dalla 2.4.0 fra questi c'e' anche ``_ponte_attivo``, il combinatore
che la spazzata condivide con l'instradamento della chat.)
"""
import inspect
import logging
import textwrap
import time as _time

import pytest

from hiris.app import server
from hiris.app.reasoning.queue import ReasoningQueue


def _load_real_reasoning_sweep(reasoning_queue, *, sub_first_class=False):
    src = inspect.getsource(server._on_startup)
    start = src.index("    async def _reasoning_sweep() -> None:")
    end_marker = "reasoning_queue.prune(_time.time() - 7 * 86400)"
    end = src.index(end_marker, start) + len(end_marker)
    func_src = textwrap.dedent(src[start:end])

    namespace = {
        "_time": _time,
        "logger": logging.getLogger("test_reasoning_sweep_chat_skip"),
        "reasoning_queue": reasoning_queue,
        "_sub_first_class": sub_first_class,
        # SP-2 tech-debt: _reasoning_sweep reads BRIDGE_ENABLED via the
        # shared env_util.env_bool helper (module-level import in server.py);
        # the extracted-source exec namespace must provide it too.
        "env_bool": server.env_bool,
        # Fusione dei due interruttori (2.4.0): la spazzata non combina piu' a
        # mano BRIDGE_ENABLED e _sub_first_class, ma passa dal combinatore
        # condiviso con l'instradamento. E' il simbolo nuovo che il namespace
        # deve fornire -- ed e' anche la ragione per cui questo file estrae il
        # sorgente vero invece di specchiarlo: un mirror sarebbe rimasto
        # indietro in silenzio, questo namespace ha smesso di funzionare
        # rumorosamente.
        "_ponte_attivo": server._ponte_attivo,
    }
    exec(compile(func_src, "<_reasoning_sweep extracted from server.py>", "exec"), namespace)
    return namespace["_reasoning_sweep"]


@pytest.mark.asyncio
async def test_expired_chat_job_left_expired_without_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("BRIDGE_ENABLED", "1")

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue(
        "chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
        now - 10, job_id="chat-job", now=now - 100,
    )

    sweep = _load_real_reasoning_sweep(q)
    with caplog.at_level("WARNING"):
        await sweep()

    job = q.get("chat-job")
    assert job["status"] == "expired"
    assert not caplog.records, "chat jobs must never trigger the orphan-kind warning"
    q.close()


@pytest.mark.asyncio
async def test_expired_holistic_job_is_logged_and_left_expired(tmp_path, monkeypatch, caplog):
    """fetta E3 Task 4: a stray kind="holistic" job (only possible from a
    pre-upgrade reasoning.db -- nothing in the product enqueues this kind
    anymore, `_holistic_reason` is gone) is no longer reasoned locally: it
    is declared via an explicit warning and left to expire, never silently
    dropped."""
    monkeypatch.setenv("BRIDGE_ENABLED", "1")

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue(
        "holistic",
        {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
        {"snapshot": {"foo": "bar"}},
        now - 10, job_id="holistic-job", now=now - 100,
    )

    sweep = _load_real_reasoning_sweep(q)
    with caplog.at_level("WARNING"):
        await sweep()

    job = q.get("holistic-job")
    assert job["status"] == "expired"
    assert any("holistic-job" in rec.message for rec in caplog.records)
    q.close()


@pytest.mark.asyncio
async def test_mixed_sweep_only_non_chat_kind_logged(tmp_path, monkeypatch, caplog):
    """Both kinds expire in the same sweep pass: only the non-chat one is
    logged as orphaned; the chat one is simply left in 'expired' state
    (surfaced to the user via the poll route, Fix 2), silently."""
    monkeypatch.setenv("BRIDGE_ENABLED", "1")

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("chat", {}, {"chatbot_id": "a1", "history": [], "system_prompt": ""},
              now - 10, job_id="chat-job", now=now - 100)
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
              {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)

    sweep = _load_real_reasoning_sweep(q)
    with caplog.at_level("WARNING"):
        await sweep()

    assert q.get("chat-job")["status"] == "expired"
    assert q.get("holistic-job")["status"] == "expired"
    messages = [rec.message for rec in caplog.records]
    assert any("holistic-job" in m for m in messages)
    assert not any("chat-job" in m for m in messages)
    q.close()


@pytest.mark.asyncio
async def test_sweep_no_op_when_bridge_and_subscription_both_off(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIDGE_ENABLED", raising=False)

    q = ReasoningQueue(str(tmp_path / "r.db"))
    now = _time.time()
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info"},
              {"snapshot": {}}, now - 10, job_id="holistic-job", now=now - 100)

    sweep = _load_real_reasoning_sweep(q, sub_first_class=False)
    await sweep()

    # Early return before sweep_expired: the job is untouched (still 'pending').
    assert q.get("holistic-job")["status"] == "pending"
    q.close()
