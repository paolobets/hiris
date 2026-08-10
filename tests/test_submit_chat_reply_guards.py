"""Slice 4b final-review Fix 3: server.py's ``_submit_chat_reply`` (the
kind="chat" submit-branch that writes the external runner's reply into
chat_store) must apply the SAME two persistence guards the sync path
(handlers_chat.py's ``handle_chat``, ~line 423-435) already applies before
persisting an assistant reply:

  1. de-tokenize pseudonymized vault tokens (``app["pseudonymizer"]``), so
     the stored history contains real values, not tokens;
  2. drop the reply entirely (never append it to chat_store) if it trips
     the toxic/leak sentinel (``chat_store._is_toxic_assistant``), so the
     next turn doesn't inherit a poisoned history.

Before this fix, ``_submit_chat_reply`` wrote the raw reply straight to
chat_store, skipping both guards.

SECURITY addendum (review B/#7 — PII cross-leak, ``brain/privacy.py``):
``Pseudonymizer.detokenize`` no longer accepts a bare ``text`` and resolves
tokens against the shared, unscoped vault. It now takes an explicit
``mapping`` of ``token -> value`` and expands ONLY tokens present in it.
This async-bridge path has no per-job pseudonymize step of its own (the
external runner's tool calls, if any, ran in a completely different
request/Task — ``_enqueue_chat_job`` never pseudonymizes the job context
either), so there is no legitimate per-job mapping to thread through here.
``_submit_chat_reply`` therefore calls ``detokenize(reply_text, {})`` with
an explicit empty mapping: any ``[TYPE_N]``-shaped text in the reply
(hallucinated, injected, or belonging to a different conversation's vault
entry) is left verbatim rather than resolved to real PII.

``_submit_chat_reply`` is a closure defined inside ``server._on_startup``
(same situation as ``_reasoning_sweep`` -- see
test_reasoning_sweep_chat_skip.py / test_coverage_wiring.py for the same
convention). Rather than hand-maintain a mirror copy that could silently
drift from the shipped code, this test extracts the REAL function source via
``inspect.getsource`` and executes it against test doubles for its free
variables (``app``, ``data_dir``, ``_append_chat_messages``,
``_is_toxic_chat_reply``).

fetta E4 Task 5 ("un bot solo"): ``_submit_chat_reply`` perde il parametro
``chatbot_id`` -- chat_store non ha piu' un id per cui instradare, c'e' UNA
cronologia. Ogni fake/call qui sotto passa/riceve solo ``reply_text``.
"""
import inspect
import textwrap

import pytest

from hiris.app import server
from hiris.app.chat_store import _is_toxic_assistant, append_messages, close_all_stores, load_history


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _load_real_submit_chat_reply(app, data_dir, append_fn=None):
    src = inspect.getsource(server._on_startup)
    start = src.index("    async def _submit_chat_reply(reply_text: str) -> None:")
    end_marker = '_append_chat_messages([{"role": "assistant", "content": reply_text}], data_dir)'
    end = src.index(end_marker, start) + len(end_marker)
    func_src = textwrap.dedent(src[start:end])

    namespace = {
        "app": app,
        "data_dir": data_dir,
        "_append_chat_messages": append_fn if append_fn is not None else append_messages,
        "_is_toxic_chat_reply": _is_toxic_assistant,
    }
    exec(compile(func_src, "<_submit_chat_reply extracted from server.py>", "exec"), namespace)
    return namespace["_submit_chat_reply"]


class _FakePseudonymizer:
    """Mirrors the real Pseudonymizer.detokenize(text, mapping) contract:
    expansion uses ONLY the mapping passed in at call time, never state
    stashed on the instance -- so a test can prove exactly what mapping the
    caller threaded through (or didn't)."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []

    def detokenize(self, text, mapping=None):
        self.calls.append((text, mapping))
        for token, real in (mapping or {}).items():
            text = text.replace(token, real)
        return text


class _FakePseudonymizerFixedOutput:
    """detokenize() always returns a fixed string regardless of input --
    used only to test call ORDERING (detokenize-before-toxicity-check),
    independent of mapping-substitution semantics (covered separately)."""

    def __init__(self, fixed_output: str):
        self._fixed_output = fixed_output
        self.calls: list[tuple[str, dict | None]] = []

    def detokenize(self, text, mapping=None):
        self.calls.append((text, mapping))
        return self._fixed_output


@pytest.mark.asyncio
async def test_toxic_reply_is_dropped_not_persisted(tmp_path):
    """Uses a recording fake for _append_chat_messages (rather than routing
    through the real chat_store and reading back via load_history) because
    chat_store's own load_context() ALSO purges toxic assistant turns at
    read time (_purge_toxic_turns) -- so a load_history-based assertion
    would pass even without this guard, and wouldn't catch a regression.
    What must be pinned here is that _submit_chat_reply itself never calls
    the append function at all for toxic content -- e.g. because raw rows
    are also read elsewhere without purging (ChatStore._close_session's
    session-digest builder), so a toxic reply that reaches the DB can still
    leak into a later get_past_summaries() prompt injection."""
    data_dir = str(tmp_path / "data")
    calls = []

    def _fake_append(messages, data_dir):
        calls.append(messages)

    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit("Errore temporaneo del servizio AI. Riprova tra poco.")

    assert calls == []


@pytest.mark.asyncio
async def test_bridge_error_sentinel_is_dropped_not_persisted(tmp_path):
    """fetta E4, fix della review totale (I5): il sentinella che il RUNNER DEL
    PONTE produce quando `claude -p` esce con rc != 0 arriva qui -- e' la
    ``reply`` del job di chat -- e prima di questo fix veniva scritto in
    chat_history.db (la review ne ha trovati due dal vivo). Questo e' il
    percorso end-to-end del filtro: la stringa non e' ricopiata a mano ma
    prodotta dal runner vero, come in
    tests/test_chat_store.py::test_is_toxic_copre_i_sentinella_veri_del_ponte.
    """
    from unittest.mock import patch

    from hiris.app.agent import runner

    class _Proc:
        returncode = 3221226505
        stdout = '{"result": "Invalid API key"}'
        stderr = ""

    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        sentinella = runner._reason_chat(
            {"kind": "chat", "context": {"history": [], "system_prompt": "S"}},
            "live")["reply"]

    data_dir = str(tmp_path / "data")
    calls = []

    def _fake_append(messages, data_dir):
        calls.append(messages)

    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit(sentinella)

    assert calls == [], (
        f"il sentinella del ponte {sentinella!r} e' stato persistito: "
        "tornerebbe al modello a ogni turno successivo")


@pytest.mark.asyncio
async def test_clean_reply_is_persisted(tmp_path):
    data_dir = str(tmp_path / "data")
    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir)

    await submit("ecco la risposta")

    assert load_history(data_dir) == [
        {"role": "assistant", "content": "ecco la risposta"},
    ]


@pytest.mark.asyncio
async def test_pseudonymizer_detokenize_called_with_empty_mapping_no_expansion(tmp_path):
    """SECURITY (review B/#7): this async-bridge path has no per-job
    pseudonymize step of its own, so _submit_chat_reply must call
    detokenize with an explicit EMPTY mapping -- a [[TOKEN_1]]-shaped
    pattern in the reply (which could belong to a completely different
    conversation's vault entry, or be model-hallucinated/injected) is left
    verbatim, never resolved to real PII."""
    data_dir = str(tmp_path / "data")
    pseudonymizer = _FakePseudonymizer()
    app = {"pseudonymizer": pseudonymizer}
    submit = _load_real_submit_chat_reply(app, data_dir)

    await submit("Il tuo indirizzo è [[TOKEN_1]].")

    assert pseudonymizer.calls == [("Il tuo indirizzo è [[TOKEN_1]].", {})]
    assert load_history(data_dir) == [
        {"role": "assistant", "content": "Il tuo indirizzo è [[TOKEN_1]]."},
    ]


@pytest.mark.asyncio
async def test_detokenize_runs_before_toxicity_check(tmp_path):
    """Mirrors the sync path's ordering (handlers_chat.py comment: 'De-tokenize
    ... before toxicity check'): if de-tokenizing could ever turn the text into
    toxic-looking content, the toxicity check must see the POST-detokenize
    value, not the raw one. Uses a fixed-output fake (ordering-only; the
    empty-mapping/no-expansion behavior is covered by the test above) and a
    recording fake for _append_chat_messages -- see
    test_toxic_reply_is_dropped_not_persisted for why load_history can't be
    used to observe this."""
    data_dir = str(tmp_path / "data")
    pseudonymizer = _FakePseudonymizerFixedOutput(
        "Errore temporaneo del servizio AI. Riprova tra poco."
    )
    calls = []

    def _fake_append(messages, data_dir):
        calls.append(messages)

    app = {"pseudonymizer": pseudonymizer}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit("risposta grezza qualsiasi")

    # detokenize was invoked (with an explicit empty mapping) and its
    # returned value -- the toxic sentinel -- is what the toxicity check
    # saw, since the reply was dropped.
    assert pseudonymizer.calls == [("risposta grezza qualsiasi", {})]
    assert calls == []


@pytest.mark.asyncio
async def test_no_pseudonymizer_configured_still_persists(tmp_path):
    """app["pseudonymizer"] absent (not configured) must not crash -- the
    reply is persisted as-is, same as the sync path's `if pseudonymizer is
    not None` guard."""
    data_dir = str(tmp_path / "data")
    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir)

    await submit("risposta senza pseudonymizer")

    assert load_history(data_dir) == [
        {"role": "assistant", "content": "risposta senza pseudonymizer"},
    ]


@pytest.mark.asyncio
async def test_empty_reply_still_short_circuits(tmp_path):
    """Pre-existing guard must survive the refactor: fetta E4 Task 5 dropped
    the `chatbot_id` half of this guard (there's nothing left to be empty/
    None on that side -- the parameter itself is gone), the empty-reply half
    survives unchanged."""
    data_dir = str(tmp_path / "data")
    calls = []

    def _fake_append(messages, data_dir):
        calls.append(messages)

    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit("")
    await submit(None)

    assert calls == []
