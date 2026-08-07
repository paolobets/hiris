"""Task 5 of "memoria unica 3a" -- the proof that the whole slice holds
together, not just each of its parts in isolation.

Tasks 1-4 (plus the discovered Task 6, "la memoria non evapora") were each
verified on their own terms: the prompt says to save (Task 1, pinned in
tests/test_base_prompt_memoria.py), the two tools became one (Task 2,
tests/test_knowledge_tools.py + tests/test_memory_alias_unified.py), memory
stopped being scoped to a single chatbot (Task 3,
tests/test_knowledge_store_chatbot.py), what a person declares always enters
context (Task 4, formerly tests/test_declared_block_chat.py -- retired for
the chat surface by Task 3 of the "nucleo alla chat" slice, 2.0, see the
note on Test 1 below -- + tests/test_declared_block_reasoner.py, which is
untouched), and memory stopped expiring (Task 6,
tests/test_memory_alias_unified.py + tests/test_knowledge_store.py). None of
those checked the whole chain end to end, with the REAL default-install
embedder, the way a real conversation would actually exercise it. That is
this file's only job.

`NullEmbedder` (`hiris.app.backends.embeddings.NullEmbedder`) is used
throughout, not a fake -- it is what a stock HIRIS install runs with no
embedding provider configured, and the production bug this whole slice
exists to close was found on exactly that install.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reasoner_memory import relevant_memory
from hiris.app.chat_store import close_all_stores
from hiris.app.server import _reason_memory_context
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.watcher.reasoner import build_user_message
from hiris.app.watcher.signals import WakeEvent

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

PREF_TEXT = "d'inverno il soggiorno sta bene a 19.5 gradi"
INSIGHT_TEXT = "media settimanale del consumo elettrico"


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


class _FakeHA:
    async def call_service(self, d, s, data):
        return {"ok": True}


class _LocalRouter:
    """Stand-in for LLMRouter: automatic_allows_sensitive() is the only
    method _reason_memory_context reads off app["llm_router"]."""

    def automatic_allows_sensitive(self) -> bool:
        return True


def _wake() -> WakeEvent:
    return WakeEvent(signal_kind="temperature_change", entity_id="climate.salotto",
                      severity_hint="info", evidence={}, ts=1.0)


def _declared_section(msg: str) -> str:
    """Slice out just the "Fatti dichiarati:" block from a rendered
    build_user_message() string, so a test can assert what is/isn't in THAT
    block specifically rather than anywhere in the whole prompt (memory
    recalled by similarity lands in a different block, "Ultimi ricordi:" /
    "Cosa so di rilevante:", and is allowed to contain other rows)."""
    if "Fatti dichiarati:" not in msg:
        return ""
    start = msg.index("Fatti dichiarati:")
    rest = msg[start:]
    end = rest.find("\n\n")
    return rest if end == -1 else rest[:end]


# ---------------------------------------------------------------------------
# Test 1 -- the whole promise, in one test.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_whole_slice_end_to_end_with_real_null_embedder(tmp_path):
    """One test, traversing the whole slice with the real NullEmbedder:

    1. a preference is saved with the single save tool, WITHOUT any approval
       step;
    2. it is recallable while talking to a DIFFERENT chatbot than the one
       that saved it;
    3. it appears in the proactive reasoner's context too;
    4. an insight sitting in the same store does NOT appear in the declared
       block.

    A step used to sit here between (2) and (3): "it appears ON ITS OWN in
    the chat context of a later turn". Task 3 of the "nucleo alla chat"
    slice (.superpowers/sdd/task-3-brief.md, 2.0) retired that path --
    `handle_chat` no longer calls `KnowledgeStore.declared()`/`.search()` at
    all, its context comes from the nucleo (`casa/nucleo.py`) instead. The
    step was removed rather than repointed: "a person's declared fact
    always enters context, unsearched" is still true and still tested (this
    file's own Step 3 below, via the reasoner; the chat surface's OWN
    equivalent claim -- "the nucleo degrades honestly when it can't be
    composed" -- is covered by tests/test_chat_al_nucleo.py, a genuinely
    different contract, not a repointed copy of this one).
    """
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    embedder = NullEmbedder()
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=embedder)

    # An insight HIRIS produced on its own, sharing the store with what a
    # person will declare below -- it must never surface as "declared".
    store.add_item(
        kind="insight", content=INSIGHT_TEXT, owner="home",
        status="approved", source="history-digest",
    )

    # --- Step 1: save with the single tool, no approval step -------------
    saved = await disp.dispatch(
        "save_memory", {"content": PREF_TEXT},
        chatbot_id="chatbot-a", user_id="home",
    )
    assert saved.get("saved") is True, saved
    item_id = saved["id"]
    # "senza approvazione": the row is 'approved' the instant it is written
    # -- nobody called an approve endpoint, there is no intermediate state.
    item = store.get_item(item_id)
    assert item["status"] == "approved"
    assert item["content"] == PREF_TEXT

    # --- Step 2: recallable from a DIFFERENT chatbot ----------------------
    recalled = await disp.dispatch(
        "recall_memory", {"query": "temperatura ideale del soggiorno d'inverno"},
        chatbot_id="chatbot-b", user_id="home",
    )
    recalled_contents = [r["content"] for r in recalled.get("results", [])]
    assert PREF_TEXT in recalled_contents, (
        "un ricordo salvato parlando con chatbot-a deve essere richiamabile "
        "parlando con chatbot-b: la memoria e' di HIRIS, non del chatbot"
    )

    # --- Step 3: appears in the proactive reasoner's context too ----------
    app_stub = {"knowledge_store": store, "llm_router": _LocalRouter()}
    mem = await _reason_memory_context(app_stub, embedder, _wake(), "Salotto")
    assert any(PREF_TEXT in d for d in mem.declared), (
        "il ragionatore proattivo deve vedere il dichiarato SEMPRE, non solo "
        "quando il segnale gli somiglia"
    )
    assert not any(INSIGHT_TEXT in d for d in mem.declared)

    # Rendered exactly as the real _gather_context closure shapes the
    # context dict (server.py, _on_startup) -- see this file's module
    # docstring / tests/test_declared_block_reasoner.py for why
    # _reason_memory_context (module-level) stands in for the closure.
    ctx = {
        "friendly_name": "Salotto",
        "memory": mem.snippets,
        "memory_by_meaning": mem.by_meaning,
        "declared": mem.declared,
    }
    msg = build_user_message(_wake(), ctx)
    assert "Fatti dichiarati:" in msg
    assert PREF_TEXT in msg
    declared_block = _declared_section(msg)
    assert declared_block, "il blocco dei dichiarati deve essere renderizzato"
    assert INSIGHT_TEXT not in declared_block, (
        "un insight non deve MAI comparire nel blocco dei dichiarati, anche "
        "se condivide l'archivio e potrebbe comparire altrove (es. 'Ultimi "
        "ricordi:', che e' un blocco diverso)"
    )

    store.close()


# ---------------------------------------------------------------------------
# Test 2 -- the row that must never come back: a saved item does NOT land
# in `pending`. This is the exact shape of the original bug: something
# saved and invisible in a limbo nobody ever looks at.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_saved_item_never_lands_in_pending(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=NullEmbedder())

    # Every kind the single save tool can produce -- kind omitted (bare
    # 'memory') and each of the five knowledge kinds it absorbed.
    await disp.dispatch("save_memory", {"content": "ricordo generico"},
                        chatbot_id="chatbot-a", user_id="home")
    for kind in ("fact", "preference", "obligation", "expense", "note"):
        res = await disp.dispatch(
            "save_memory", {"kind": kind, "content": f"elemento di tipo {kind}"},
            chatbot_id="chatbot-a", user_id="home",
        )
        assert res.get("saved") is True, res

    pending = store.list_items(status="pending", limit=200)
    assert pending == [], (
        "nessun elemento salvato deve MAI finire in 'pending': e' esattamente "
        "il limbo invisibile in cui viveva il bug originale (zero righe "
        "pending in produzione in quattro mesi, e la sezione Memoria "
        "interrogava SOLO quelle)"
    )
    approved = store.list_items(status="approved", limit=200)
    assert len(approved) == 6

    store.close()


# ---------------------------------------------------------------------------
# Test 3 -- it does not evaporate: a memory saved today is still readable
# and recallable far in the future. The clock is moved, not waited for.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_does_not_evaporate_years_later(tmp_path, monkeypatch):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=NullEmbedder())

    saved = await disp.dispatch(
        "save_memory", {"content": PREF_TEXT},
        chatbot_id="chatbot-a", user_id="home",
    )
    item_id = saved["id"]
    assert store.get_item(item_id)["valid_until"] is None, (
        "un ricordo salvato oggi non riceve alcuna scadenza automatica"
    )

    # Move the clock of READING (KnowledgeStore._now, used by
    # _clausole_di_scope for the valid_until comparison) five years forward
    # -- not waiting five years, same technique as
    # tests/test_memory_alias_unified.py's own Task 6 regression test.
    tra_cinque_anni = (
        datetime.now(timezone.utc) + timedelta(days=5 * 365)
    ).strftime(_TS_FMT)
    monkeypatch.setattr(store, "_now", lambda: tra_cinque_anni)

    # Still readable.
    item = store.get_item(item_id)
    assert item is not None
    assert item["content"] == PREF_TEXT

    # Still recallable, from a different chatbot than the one that saved it.
    recalled = await disp.dispatch(
        "recall_memory", {"query": "temperatura del soggiorno"},
        chatbot_id="chatbot-b", user_id="home",
    )
    recalled_contents = [r["content"] for r in recalled.get("results", [])]
    assert PREF_TEXT in recalled_contents

    store.close()


# ---------------------------------------------------------------------------
# Test 4 -- the production shape, revived: a row shaped exactly like the
# three real ones (kind='memory', status='approved',
# chatbot_id='hiris-default', valid_until already in the past, content
# ~340 characters) must come back readable, recallable, and present in the
# declared block after opening the database with the real class.
# ---------------------------------------------------------------------------

PRODUCTION_SHAPED_CONTENT = (
    "Il modulo meteo esterno risulta guasto dal mese di luglio: HIRIS deve "
    "continuare a usare le previsioni ufficiali di Home Assistant e non deve "
    "mai proporre soluzioni basate su sensori di temperatura esterna finche' "
    "il modulo non verra' sostituito o riparato dall'amministratore della "
    "casa, Paolo. Vale per ogni stanza, non solo per il soggiorno."
)


@pytest.mark.asyncio
async def test_production_shaped_expired_memory_row_is_revived(tmp_path):
    assert 300 <= len(PRODUCTION_SHAPED_CONTENT) <= 400

    db_path = tmp_path / "prod_shaped.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE knowledge_items ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,"
        " owner TEXT NOT NULL DEFAULT 'home', title TEXT NOT NULL DEFAULT '',"
        " content TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',"
        " amount REAL, due_date TEXT, category TEXT, embedding BLOB,"
        " sensitivity TEXT NOT NULL DEFAULT 'normal',"
        " source TEXT NOT NULL DEFAULT 'manual', source_ref TEXT,"
        " confidence REAL NOT NULL DEFAULT 1.0,"
        " status TEXT NOT NULL DEFAULT 'approved',"
        " valid_from TEXT, valid_until TEXT,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        " chatbot_id TEXT)"
    )
    past = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(_TS_FMT)
    created = (datetime.now(timezone.utc) - timedelta(days=120)).strftime(_TS_FMT)
    conn.execute(
        "INSERT INTO knowledge_items"
        " (kind, owner, content, status, source, valid_until, chatbot_id,"
        "  created_at, updated_at)"
        " VALUES ('memory','home',?,'approved','chat',?,'hiris-default',?,?)",
        (PRODUCTION_SHAPED_CONTENT, past, created, created),
    )
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    # Opened with the REAL class -- this is what runs the v5->v6 migration.
    store = KnowledgeStore(str(db_path))

    # Readable.
    rows = [i for i in store.list_items(kind="memory", limit=200)
            if i["content"] == PRODUCTION_SHAPED_CONTENT]
    assert len(rows) == 1
    revived = rows[0]
    assert revived["valid_until"] is None, (
        "la migrazione v6 azzera valid_until sulle righe kind='memory': "
        "questa era gia' scaduta sotto il vecchio schema e deve tornare "
        "leggibile, non restare per sempre invisibile e impurgabile"
    )
    assert revived["status"] == "approved"

    # Recallable (degrades to recent() with the real NullEmbedder -- the
    # same path a stock install takes).
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=NullEmbedder())
    recalled = await disp.dispatch(
        "recall_memory", {"query": "sensori esterni guasti"},
        chatbot_id="chatbot-nuovo", user_id="home",
    )
    recalled_contents = [r["content"] for r in recalled.get("results", [])]
    assert PRODUCTION_SHAPED_CONTENT in recalled_contents

    # Present in the declared block: source='chat' is a declared source, so
    # it must enter context unconditionally, exactly like the three real
    # production rows this shape is modeled on.
    declared_items, declared_total = store.declared(owner="home")
    assert declared_total >= 1
    assert any(i["content"] == PRODUCTION_SHAPED_CONTENT for i in declared_items)

    mem = await relevant_memory(
        store, NullEmbedder(), query_text="stato generale della casa",
        allow_sensitive=True, owner="home", limit=5,
    )
    assert any(PRODUCTION_SHAPED_CONTENT in d for d in mem.declared)

    store.close()
