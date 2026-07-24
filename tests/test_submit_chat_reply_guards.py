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

``_submit_chat_reply`` is a closure defined inside ``server._on_startup``
(same situation as ``_reasoning_sweep`` -- see
test_reasoning_sweep_chat_skip.py / test_coverage_wiring.py for the same
convention). Rather than hand-maintain a mirror copy that could silently
drift from the shipped code, this test extracts the REAL function source via
``inspect.getsource`` and executes it against test doubles for its free
variables (``app``, ``data_dir``, ``_append_chat_messages``,
``_is_toxic_chat_reply``).
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
    start = src.index("    async def _submit_chat_reply(agent_id: str, reply_text: str) -> None:")
    end_marker = '_append_chat_messages(agent_id, [{"role": "assistant", "content": reply_text}], data_dir)'
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
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def detokenize(self, text):
        self.calls.append(text)
        for token, real in self.mapping.items():
            text = text.replace(token, real)
        return text


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

    def _fake_append(agent_id, messages, data_dir):
        calls.append((agent_id, messages))

    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit("agentX", "Errore temporaneo del servizio AI. Riprova tra poco.")

    assert calls == []


@pytest.mark.asyncio
async def test_clean_reply_is_persisted(tmp_path):
    data_dir = str(tmp_path / "data")
    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir)

    await submit("agentX", "ecco la risposta")

    assert load_history("agentX", data_dir) == [
        {"role": "assistant", "content": "ecco la risposta"},
    ]


@pytest.mark.asyncio
async def test_pseudonymizer_detokenize_applied_before_persisting(tmp_path):
    data_dir = str(tmp_path / "data")
    pseudonymizer = _FakePseudonymizer({"[[TOKEN_1]]": "Via Roma 12"})
    app = {"pseudonymizer": pseudonymizer}
    submit = _load_real_submit_chat_reply(app, data_dir)

    await submit("agentX", "Il tuo indirizzo è [[TOKEN_1]].")

    assert pseudonymizer.calls == ["Il tuo indirizzo è [[TOKEN_1]]."]
    assert load_history("agentX", data_dir) == [
        {"role": "assistant", "content": "Il tuo indirizzo è Via Roma 12."},
    ]


@pytest.mark.asyncio
async def test_detokenize_runs_before_toxicity_check(tmp_path):
    """Mirrors the sync path's ordering (handlers_chat.py comment: 'De-tokenize
    ... before toxicity check'): if de-tokenizing could ever turn a token into
    toxic-looking text (or vice versa), the toxicity check must see the
    POST-detokenize value, not the raw one. Uses a recording fake for
    _append_chat_messages -- see test_toxic_reply_is_dropped_not_persisted
    for why load_history can't be used to observe this."""
    data_dir = str(tmp_path / "data")
    pseudonymizer = _FakePseudonymizer({
        "[[TOKEN_1]]": "Errore temporaneo del servizio AI. Riprova tra poco.",
    })
    calls = []

    def _fake_append(agent_id, messages, data_dir):
        calls.append((agent_id, messages))

    app = {"pseudonymizer": pseudonymizer}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit("agentX", "[[TOKEN_1]]")

    # The detokenized value IS the toxic sentinel -- must be dropped.
    assert calls == []


@pytest.mark.asyncio
async def test_no_pseudonymizer_configured_still_persists(tmp_path):
    """app["pseudonymizer"] absent (not configured) must not crash -- the
    reply is persisted as-is, same as the sync path's `if pseudonymizer is
    not None` guard."""
    data_dir = str(tmp_path / "data")
    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir)

    await submit("agentX", "risposta senza pseudonymizer")

    assert load_history("agentX", data_dir) == [
        {"role": "assistant", "content": "risposta senza pseudonymizer"},
    ]


@pytest.mark.asyncio
async def test_empty_agent_id_or_reply_still_short_circuits(tmp_path):
    """Pre-existing guard must survive the refactor unchanged."""
    data_dir = str(tmp_path / "data")
    calls = []

    def _fake_append(agent_id, messages, data_dir):
        calls.append((agent_id, messages))

    app = {}
    submit = _load_real_submit_chat_reply(app, data_dir, append_fn=_fake_append)

    await submit("", "some reply")
    await submit("agentX", "")
    await submit(None, "some reply")

    assert calls == []
