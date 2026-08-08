import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

from hiris.app.chat_store import (
    ChatStore,
    append_messages,
    clear_history,
    close_all_stores,
    count_user_turns,
    get_past_summaries,
    load_history,
)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture(autouse=True)
def reset_stores():
    """Ensure module-level store cache is clean between tests."""
    close_all_stores()
    yield
    close_all_stores()


# ---------------------------------------------------------------------------
# Basic append / load / clear (backward-compat API)
#
# fetta E4 Task 5 ("un bot solo"): tutte le funzioni di modulo perdono il
# parametro chatbot_id -- c'e' UNA cronologia, non piu' una per bot. I test
# che pinnavano `test_different_agents_have_separate_histories` non hanno
# piu' un soggetto: verificato che cade per costruzione (`append_messages()`
# con due argomenti posizionali sollevava `TypeError: append_messages() takes
# 2 positional arguments but 3 were given` prima di questa riscrittura) --
# rimosso, non spostato: non c'e' piu' alcuna "separazione per bot" da
# testare, e' proprio il concetto che il Task 5 ha tolto dallo schema.
# ---------------------------------------------------------------------------

def test_load_history_empty_when_no_data(tmp_path):
    assert load_history(str(tmp_path)) == []


def test_append_and_load_roundtrip(tmp_path):
    msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    append_messages(msgs, str(tmp_path))
    loaded = load_history(str(tmp_path))
    assert loaded == msgs


def test_load_strips_timestamps_from_output(tmp_path):
    append_messages([{"role": "user", "content": "test"}], str(tmp_path))
    result = load_history(str(tmp_path))
    assert "timestamp" not in result[0]


def test_append_accumulates(tmp_path):
    append_messages([{"role": "user", "content": "first"}], str(tmp_path))
    append_messages([{"role": "assistant", "content": "second"}], str(tmp_path))
    result = load_history(str(tmp_path))
    assert len(result) == 2
    assert result[0]["content"] == "first"
    assert result[1]["content"] == "second"


def test_clear_history(tmp_path):
    append_messages([{"role": "user", "content": "x"}], str(tmp_path))
    clear_history(str(tmp_path))
    assert load_history(str(tmp_path)) == []


def test_clear_history_noop_when_empty(tmp_path):
    clear_history(str(tmp_path))  # must not raise


# ---------------------------------------------------------------------------
# 30-day retention filter
# ---------------------------------------------------------------------------

def test_load_filters_messages_older_than_30_days(tmp_path):
    import hiris.app.chat_store as cs
    cs.HISTORY_RETENTION_DAYS = 30
    try:
        store = ChatStore(str(tmp_path / "chat_history.db"))
        old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime(_TS_FMT)
        new_ts = datetime.now(timezone.utc).strftime(_TS_FMT)
        # Inject a session and old+new messages directly
        session_id = "sess-old"
        conn = store._conn
        conn.execute(
            "INSERT INTO chat_sessions(session_id, started_at, last_msg_at) VALUES(?,?,?)",
            (session_id, old_ts, new_ts),
        )
        conn.execute(
            "INSERT INTO chat_messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
            (session_id, "user", "old msg", old_ts),
        )
        conn.execute(
            "INSERT INTO chat_messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
            (session_id, "assistant", "new msg", new_ts),
        )
        conn.commit()
        result = store.load_context()
        contents = [m["content"] for m in result]
        assert "old msg" not in contents
        assert "new msg" in contents
        store.close()
    finally:
        cs.HISTORY_RETENTION_DAYS = 90


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def test_new_session_after_gap(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    # Create a first session with a timestamp > 2h ago
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid1 = "sess-stale"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at) VALUES(?,?,?)",
        (sid1, old_ts, old_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
        (sid1, "assistant", "old reply", old_ts),
    )
    conn.commit()

    # Appending now should start a new session
    store.append([{"role": "user", "content": "fresh"}])

    # The old session should now be closed (summary set)
    row = conn.execute(
        "SELECT summary FROM chat_sessions WHERE session_id = ?", (sid1,)
    ).fetchone()
    assert row["summary"] is not None

    # New session message should be in a different session
    active = conn.execute(
        "SELECT session_id FROM chat_sessions WHERE summary IS NULL"
    ).fetchone()
    assert active is not None
    assert active["session_id"] != sid1
    store.close()


def test_active_session_reused_within_gap(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.append([{"role": "user", "content": "msg1"}])
    store.append([{"role": "assistant", "content": "reply1"}])
    conn = store._conn
    sessions = conn.execute("SELECT * FROM chat_sessions").fetchall()
    assert len(sessions) == 1  # still same session
    store.close()


def test_load_context_returns_empty_for_stale_session(tmp_path):
    """load_context must return [] if the session gap has elapsed (read path)."""
    store = ChatStore(str(tmp_path / "chat_history.db"))
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid = "stale-read"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at) VALUES(?,?,?)",
        (sid, old_ts, old_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
        (sid, "user", "old", old_ts),
    )
    conn.commit()
    # load_context must treat stale session as empty — no side effects
    assert store.load_context() == []
    assert store.count_user_turns() == 0
    # Session is still "open" (not closed) since we only read
    still_open = conn.execute(
        "SELECT summary FROM chat_sessions WHERE session_id = ?", (sid,)
    ).fetchone()
    assert still_open["summary"] is None
    store.close()


# ---------------------------------------------------------------------------
# Past summaries
# ---------------------------------------------------------------------------

def test_get_past_summaries_returns_closed_sessions(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    for i in range(4):
        sid = f"closed-{i}"
        store._conn.execute(
            "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, summary) "
            "VALUES(?,?,?,?)",
            (sid, ts, ts, f"summary {i}"),
        )
    store._conn.commit()
    summaries = store.get_past_summaries(n=3)
    assert len(summaries) == 3
    assert all(s["summary"] is not None for s in summaries)
    store.close()


def test_get_past_summaries_empty_when_no_closed_sessions(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.append([{"role": "user", "content": "hi"}])
    summaries = store.get_past_summaries()
    assert summaries == []
    store.close()


def test_module_get_past_summaries(tmp_path):
    append_messages([{"role": "user", "content": "hi"}], str(tmp_path))
    result = get_past_summaries(str(tmp_path))
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# count_user_turns
# ---------------------------------------------------------------------------

def test_count_user_turns(tmp_path):
    append_messages([{"role": "user", "content": "q1"}], str(tmp_path))
    append_messages([{"role": "assistant", "content": "a1"}], str(tmp_path))
    append_messages([{"role": "user", "content": "q2"}], str(tmp_path))
    assert count_user_turns(str(tmp_path)) == 2


def test_count_user_turns_zero_when_empty(tmp_path):
    assert count_user_turns(str(tmp_path)) == 0


# ---------------------------------------------------------------------------
# Summary truncation
# ---------------------------------------------------------------------------

def test_summary_truncated_to_200_chars(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    long_text = "x" * 300
    ts_old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid = "sess-long"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at) VALUES(?,?,?)",
        (sid, ts_old, ts_old),
    )
    conn.execute(
        "INSERT INTO chat_messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
        (sid, "assistant", long_text, ts_old),
    )
    conn.commit()

    store.append([{"role": "user", "content": "new"}])

    row = conn.execute("SELECT summary FROM chat_sessions WHERE session_id = ?", (sid,)).fetchone()
    assert row["summary"] is not None
    assert len(row["summary"]) <= 201  # 200 + ellipsis char
    store.close()


# ---------------------------------------------------------------------------
# Regression: filter toxic assistant turns on history load (v0.9.9)
# Pre-v0.9.8, some Mistral/Hermes routings on OpenRouter leaked tool calls as
# raw text content (e.g. `get_ha_healthיׂ{...}`); the chat handler also
# persisted generic synthetic errors ("Errore temporaneo del servizio AI...").
# Both poison the history sent to subsequent turns. load_history must purge
# them so existing users recover automatically without manual cleanup.
# ---------------------------------------------------------------------------

from hiris.app.chat_store import _purge_toxic_turns, _is_toxic_assistant


def test_is_toxic_detects_mistral_leak_pattern():
    assert _is_toxic_assistant("get_ha_healthיׂ{\"sections\":[\"all\"]}") is True
    assert _is_toxic_assistant("await_user_confirmationיׄ**Confermi?**") is True
    assert _is_toxic_assistant("get_ha_healthớ{}") is True


def test_is_toxic_detects_synthetic_error_strings():
    assert _is_toxic_assistant("Errore temporaneo del servizio AI. Riprova tra poco.") is True
    assert _is_toxic_assistant("Rate limit — riprova tra poco.") is True
    assert _is_toxic_assistant("") is True
    assert _is_toxic_assistant(
        "Crediti OpenRouter insufficienti per max_tokens=4096. Riduci..."
    ) is True
    assert _is_toxic_assistant(
        "Il modello selezionato non gestisce correttamente i tool tramite questo provider..."
    ) is True


def test_is_toxic_does_not_match_legit_responses():
    legit = [
        "Tutto ok, la casa è in buone condizioni.",
        "La temperatura in salotto è 21°C.",
        "Posso aiutarti — dimmi cosa serve.",
        "**Riepilogo consumi:**\n- Potenza: 550W",
    ]
    for s in legit:
        assert _is_toxic_assistant(s) is False, f"false positive on {s!r}"


def test_purge_drops_toxic_assistant_and_preceding_user():
    msgs = [
        {"role": "user", "content": "verifica salute HA"},
        {"role": "assistant", "content": "get_ha_healthיׂ{\"sections\":[\"all\"]}"},
        {"role": "user", "content": "che luci hai?"},
        {"role": "assistant", "content": "Errore temporaneo del servizio AI. Riprova tra poco."},
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "Ciao! Come stai?"},
    ]
    out = _purge_toxic_turns(msgs)
    assert out == [
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "Ciao! Come stai?"},
    ]


def test_purge_preserves_clean_history_unchanged():
    msgs = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
    ]
    assert _purge_toxic_turns(msgs) == msgs


def test_purge_handles_leading_toxic_assistant_with_no_preceding_user():
    """Edge case: assistant comes first (shouldn't happen but be safe)."""
    msgs = [
        {"role": "assistant", "content": "Errore temporaneo del servizio AI. Riprova tra poco."},
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "ciao!"},
    ]
    out = _purge_toxic_turns(msgs)
    assert out == [
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "ciao!"},
    ]


def test_load_history_purges_pre_v098_corrupted_history(tmp_path):
    """End-to-end: existing chat with leaked tool calls + error messages comes
    out clean, simulating what happens for users upgrading from v0.9.7."""
    msgs = [
        {"role": "user", "content": "check HA"},
        {"role": "assistant", "content": "get_ha_healthיׂ{\"sections\":[\"all\"]}"},
        {"role": "user", "content": "luci?"},
        {"role": "assistant", "content": "Errore temporaneo del servizio AI. Riprova tra poco."},
        {"role": "user", "content": "ora?"},
        {"role": "assistant", "content": "**Tutto ok**"},
    ]
    append_messages(msgs, str(tmp_path))
    out = load_history(str(tmp_path))
    # Two corrupted pairs dropped, only the last clean one survives
    assert out == [
        {"role": "user", "content": "ora?"},
        {"role": "assistant", "content": "**Tutto ok**"},
    ]


# ---------------------------------------------------------------------------
# fetta E4 Task 5 ("un bot solo"): azzeramento dello schema, non conversione.
#
# `_migrate_v2` (rinominava agent_id -> chatbot_id) e `migrate_from_json`
# (importava chat_history_*.json 1.x) sono usciti per intero: la decisione
# esplicita dell'utente e' "non serve migrare nulla, si riparte puliti".
# I test che pinnavano quelle due funzioni (test_migrate_from_json,
# test_migrate_skips_already_migrated,
# test_migration_renames_agent_id_column_and_indexes_preserving_data,
# test_migration_is_idempotent_on_reopen) non hanno piu' un soggetto --
# verificato che cadono per costruzione prima di cancellarli:
#   - test_migrate_from_json/test_migrate_skips_already_migrated:
#     `AttributeError: 'ChatStore' object has no attribute 'migrate_from_json'`
#   - i due test sulla migrazione v1->v2: `sqlite3.OperationalError: table
#     chat_messages has no column named agent_id` non e' nemmeno il punto in
#     cui falliscono -- `ChatStore(db_path)` sulla legacy-v1 db ora esegue
#     `_azzera` (droppa+ricrea), quindi le colonne/indici "agent_id" che gli
#     assert cercavano semplicemente non esistono piu' da nessuna parte: gli
#     assert su `chatbot_id in msg_cols`/`idx_msg_chatbot` falliscono con
#     `AssertionError` (chatbot_id non c'e' proprio piu', ne' nella forma
#     vecchia ne' in quella "migrata" che il test si aspettava).
# Quello che li sostituisce, sotto: `_azzera` droppa le tabelle 1.x/2.x e
# ricrea lo schema nuovo, logga esplicitamente cosa ha buttato via, ed e'
# pinnato con la stessa tecnica di tests/test_startup_legacy_db_silence.py.
# ---------------------------------------------------------------------------

def _make_legacy_v2_db(db_path: str, *, stamp_version: bool = True) -> None:
    """Costruisce un chat_history.db esattamente come lo lasciava HIRIS 1.x
    (fetta E4 Task 5 in poi): colonne chatbot_id NOT NULL in entrambe le
    tabelle, indici idx_msg_chatbot/idx_sess_chatbot, user_version=2 se
    `stamp_version` (il caso comune -- un'installazione gia' passata per la
    rinomina agent_id->chatbot_id di SP-4a)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE chat_messages ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, chatbot_id TEXT NOT NULL, "
        "session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, "
        "timestamp TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE chat_sessions ("
        "session_id TEXT PRIMARY KEY, chatbot_id TEXT NOT NULL, "
        "started_at TEXT NOT NULL, last_msg_at TEXT NOT NULL, summary TEXT)"
    )
    conn.execute("CREATE INDEX idx_msg_chatbot ON chat_messages(chatbot_id, timestamp)")
    conn.execute("CREATE INDEX idx_sess_chatbot ON chat_sessions(chatbot_id, last_msg_at)")
    conn.execute(
        "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at, summary) "
        "VALUES('sess-legacy', 'hiris-default', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:05:00Z', 'old summary')"
    )
    conn.execute(
        "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) "
        "VALUES('hiris-default', 'sess-legacy', 'user', 'ciao', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) "
        "VALUES('hiris-default', 'sess-legacy', 'assistant', 'salve', '2026-01-01T00:01:00Z')"
    )
    if stamp_version:
        conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def test_opening_legacy_v2_db_drops_chatbot_id_and_bumps_to_v3(tmp_path):
    """Opening a legacy v2 db (chatbot_id columns + idx_msg_chatbot/
    idx_sess_chatbot, user_version=2) through ChatStore must: drop the old
    rows, recreate the schema WITHOUT chatbot_id, and stamp user_version=3.
    No conversion — this is the azzeramento, not a migration."""
    db_path = str(tmp_path / "chat_history.db")
    _make_legacy_v2_db(db_path)

    store = ChatStore(db_path)
    try:
        conn = store._conn

        msg_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        sess_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
        assert "chatbot_id" not in msg_cols
        assert "chatbot_id" not in sess_cols

        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "idx_msg_chatbot" not in indexes
        assert "idx_sess_chatbot" not in indexes

        # The old rows are gone — this is an azzeramento, not a migration.
        assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 0

        # user_version stamped at the latest schema version.
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3

        # The store is immediately usable after the wipe.
        store.append([{"role": "user", "content": "prima frase pulita"}])
        assert store.load_context() == [{"role": "user", "content": "prima frase pulita"}]
    finally:
        store.close()


def test_azzeramento_is_idempotent_on_reopen(tmp_path):
    """A second ChatStore open (simulating an add-on restart post-upgrade)
    must not fail or re-wipe data written after the first open."""
    db_path = str(tmp_path / "chat_history.db")
    _make_legacy_v2_db(db_path)

    store1 = ChatStore(db_path)
    store1.append([{"role": "user", "content": "dopo l'azzeramento"}])
    store1.close()

    store2 = ChatStore(db_path)  # must not raise, must not re-wipe
    try:
        conn = store2._conn
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        assert "chatbot_id" not in cols
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        content = [r["content"] for r in conn.execute(
            "SELECT content FROM chat_messages"
        ).fetchall()]
        assert content == ["dopo l'azzeramento"]
    finally:
        store2.close()


def test_azzeramento_logs_what_it_discards(tmp_path, caplog):
    """Il silenzio dichiarato di questo task: l'azzeramento della cronologia
    all'upgrade e' il piu' visibile all'utente di questa fetta. Chi
    aggiorna da 1.x deve poterlo leggere nei log, non scoprirlo dalla chat
    vuota (stessa disciplina di tests/test_startup_legacy_db_silence.py)."""
    db_path = str(tmp_path / "chat_history.db")
    _make_legacy_v2_db(db_path)

    with caplog.at_level("INFO", logger="hiris.app.chat_store"):
        store = ChatStore(db_path)
    store.close()

    matches = [r for r in caplog.records if "azzerata" in r.message]
    assert matches, "l'azzeramento deve loggare esplicitamente, non in silenzio"
    msg = matches[0].message
    assert "2 messaggi" in msg
    assert "1 sessioni" in msg
    assert "non convertita" in msg


def test_azzeramento_silent_second_pass_when_nothing_left_to_discard(tmp_path, caplog):
    """Un DB gia' alla baseline pre-versioning (nessun user_version
    stampato) attraversa sia il target 2 sia il target 3 -- entrambi mappati
    su `_azzera` (vedi init_schema/migrations={2: _azzera, 3: _azzera}). La
    seconda passata trova le tabelle gia' vuote/nuove: logga comunque (e'
    la stessa funzione, non un ramo silenzioso), ma dichiara zero righe."""
    db_path = str(tmp_path / "chat_history.db")
    _make_legacy_v2_db(db_path, stamp_version=False)

    with caplog.at_level("INFO", logger="hiris.app.chat_store"):
        store = ChatStore(db_path)
    store.close()

    matches = [r for r in caplog.records if "azzerata" in r.message]
    assert len(matches) == 2, "target 2 e 3 richiamano entrambi _azzera su un DB pre-versioning"
    assert "2 messaggi" in matches[0].message and "1 sessioni" in matches[0].message
    assert "0 messaggi" in matches[1].message and "0 sessioni" in matches[1].message


def test_fresh_install_no_azzeramento_log(tmp_path, caplog):
    """Un'installazione nuova (nessuna tabella preesistente) non deve mai
    loggare l'azzeramento: non c'e' nulla da buttare via."""
    db_path = str(tmp_path / "chat_history.db")
    with caplog.at_level("INFO", logger="hiris.app.chat_store"):
        store = ChatStore(db_path)
    store.close()
    assert not any("azzerata" in r.message for r in caplog.records)
