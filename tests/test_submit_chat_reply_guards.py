"""Slice 4b final-review Fix 3: server.py's ``_submit_chat_reply`` (the
kind="chat" submit-branch that writes the external runner's reply into
chat_store) must apply the SAME persistence guard the sync path
(handlers_chat.py's ``handle_chat``) already applies before persisting an
assistant reply: drop the reply entirely (never append it to chat_store) if
it trips the toxic/leak sentinel (``chat_store._is_toxic_assistant``), so the
next turn doesn't inherit a poisoned history.

Before this fix, ``_submit_chat_reply`` wrote the raw reply straight to
chat_store, skipping the guard.

Fetta "esce il documentale": la seconda guardia -- la detokenizzazione dei
token del vault (``app["pseudonymizer"].detokenize(reply_text, {})``) -- e'
uscita insieme a ``brain/privacy.py``, e con lei i tre test che la
pinnavano. Vedi la nota in fondo al file: cadevano per costruzione, e cio'
che provavano era gia' un no-op nel prodotto.

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
        # fetta "il ponte riceve gli strumenti" (parita' B, Task 2): stdout
        # nella forma NDJSON di `--output-format stream-json --verbose`.
        returncode = 3221226505
        stdout = ('{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
                  '{"type":"result","subtype":"error_during_execution",'
                  '"is_error":true,"result":"Invalid API key"}\n')
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


# Fetta "esce il documentale": qui vivevano tre test e due finti
# (`_FakePseudonymizer`, `_FakePseudonymizerFixedOutput`).
#
#   - `test_pseudonymizer_detokenize_called_with_empty_mapping_no_expansion`
#   - `test_detokenize_runs_before_toxicity_check`
#   - `test_no_pseudonymizer_configured_still_persists`
#
# Cadono PER COSTRUZIONE: il loro soggetto -- la chiamata
# `app["pseudonymizer"].detokenize(reply_text, {})` dentro
# `_submit_chat_reply` -- non esiste piu' nel sorgente che
# `_load_real_submit_chat_reply` estrae via `inspect.getsource`. I primi due
# asserivano su `pseudonymizer.calls`, che ora resta vuoto sempre; il terzo
# provava il ramo `if pseudonymizer is not None` con `app = {}`, cioe'
# esattamente cio' che oggi fa `test_clean_reply_is_persisted` -- sarebbe
# rimasto verde come duplicato, non come prova.
#
# Non lasciano un buco: la detokenizzazione qui era gia' un no-op dichiarato.
# Si chiamava SEMPRE con una mappa vuota (questo percorso non pseudonimizza
# nulla di suo, e nessun percorso del prodotto lo faceva piu' da quando il
# dispatcher che popolava `last_pseudonym_map` e' uscito, fetta E2 Task 7),
# e con mappa vuota `detokenize` restituisce il testo identico. L'ordine
# "detokenize prima del controllo di tossicita'" che il secondo test
# pinnava non ha piu' due cose da ordinare.
