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
note on Test 1 below -- + tests/test_declared_block_reasoner.py, retired in
turn by fetta E3 Task 7 together with the whole proactive reasoner it
pinned), and memory stopped expiring (Task 6,
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
from hiris.app.chat_store import close_all_stores

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

PREF_TEXT = "d'inverno il soggiorno sta bene a 19.5 gradi"


# fetta E2 Task 8 ("escono i trentaquattro"): `handle_save_memory`/
# `handle_recall_memory` (tools/memory_tools.py) sono usciti -- orfani dal
# Task 7 (il `ToolDispatcher` che li chiamava e' uscito), nessun chiamante di
# produzione li invocava piu'. Questo file prova la catena end-to-end della
# memoria unica, non l'orchestrazione di quei due wrapper: le due funzioni
# sotto chiamano `KnowledgeStore` direttamente, con lo stesso comportamento
# che i wrapper avevano per il caso 'memory' che questo file esercita
# (nessuna scadenza, provenienza chatbot_id solo per kind='memory', subito
# 'approved') -- non un test dei wrapper stessi, che e' stato spostato dove
# vive ora la logica che stavano sparendo (tests/test_kinds_egress.py, il
# forward di `kinds` a `KnowledgeStore.search`) o cancellato dove non aveva
# successore (tests/test_knowledge_tools.py e affini: validazione e
# pseudonimizzazione erano proprieta' dei wrapper stessi, morte con loro).
async def _salva_ricordo(store: KnowledgeStore, embedder, content: str, *,
                         owner: str = "home", chatbot_id: str | None = None,
                         kind: str | None = None) -> dict:
    kind = kind or "memory"
    try:
        embedding = await embedder.embed(content)
    except Exception:
        embedding = None
    item_id = store.add_item(
        kind=kind, content=content, owner=owner,
        chatbot_id=chatbot_id if kind == "memory" else None,
        embedding=embedding or None, source="chat",
    )
    return {"saved": True, "id": item_id}


async def _richiama_ricordi(store: KnowledgeStore, embedder, query: str, *,
                            owner: str = "home") -> dict:
    try:
        qv = await embedder.embed(query)
    except Exception:
        qv = None
    return {"results": store.search(query_vec=qv or [], k=5, owner=owner)}


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


# ---------------------------------------------------------------------------
# Test 1 -- the whole promise, in one test.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_whole_slice_end_to_end_with_real_null_embedder(tmp_path):
    """One test, traversing the whole slice with the real NullEmbedder:

    1. a preference is saved with the single save tool, WITHOUT any approval
       step;
    2. it is recallable while talking to a DIFFERENT chatbot than the one
       that saved it.

    A step used to sit here between (2) and what used to be Step 3: "it
    appears ON ITS OWN in the chat context of a later turn". Task 3 of the
    "nucleo alla chat" slice (.superpowers/sdd/task-3-brief.md, 2.0) retired
    that path -- `handle_chat` no longer calls
    `KnowledgeStore.declared()`/`.search()` at all, its context comes from
    the nucleo (`casa/nucleo.py`) instead (chat's own equivalent claim --
    "the nucleo degrades honestly when it can't be composed" -- is covered
    by tests/test_chat_al_nucleo.py, a genuinely different contract).

    Steps 3 ("it appears in the proactive reasoner's context too") and 4
    ("an insight sitting in the same store does NOT appear in the declared
    block") drove `_reason_memory_context`/`build_user_message`
    (server.py/watcher.reasoner) directly -- both gone with the whole
    proactive reasoner, fetta E3 Task 7. Removed, not moved: the insight-
    exclusion property they pinned via the reasoner's declared block is
    already independently proven at the store level, where it actually
    lives (`KnowledgeStore.declared()`'s `source in DECLARED_SOURCES`
    filter, tests/test_knowledge_store_declared.py) -- that test never
    routed through the reasoner in the first place.
    """
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    embedder = NullEmbedder()

    # --- Step 1: save with the single tool, no approval step -------------
    # fetta E2 Task 8: `_salva_ricordo` chiama KnowledgeStore direttamente
    # (era `handle_save_memory`, uscita -- vedi il commento sopra
    # l'helper) -- stesso comportamento, un livello di wrapper in meno.
    saved = await _salva_ricordo(
        store, embedder, PREF_TEXT,
        owner="home", chatbot_id="chatbot-a",
    )
    assert saved.get("saved") is True, saved
    item_id = saved["id"]
    # "senza approvazione": the row is 'approved' the instant it is written
    # -- nobody called an approve endpoint, there is no intermediate state.
    item = store.get_item(item_id)
    assert item["status"] == "approved"
    assert item["content"] == PREF_TEXT

    # --- Step 2: recallable from a DIFFERENT chatbot ----------------------
    recalled = await _richiama_ricordi(
        store, embedder, "temperatura ideale del soggiorno d'inverno",
        owner="home",
    )
    recalled_contents = [r["content"] for r in recalled.get("results", [])]
    assert PREF_TEXT in recalled_contents, (
        "un ricordo salvato parlando con chatbot-a deve essere richiamabile "
        "parlando con chatbot-b: la memoria e' di HIRIS, non del chatbot"
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
    embedder = NullEmbedder()

    # Every kind the single save tool can produce -- kind omitted (bare
    # 'memory') and each of the five knowledge kinds it absorbed.
    await _salva_ricordo(store, embedder, "ricordo generico",
                         owner="home", chatbot_id="chatbot-a")
    for kind in ("fact", "preference", "obligation", "expense", "note"):
        res = await _salva_ricordo(
            store, embedder, f"elemento di tipo {kind}",
            owner="home", chatbot_id="chatbot-a", kind=kind,
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
    embedder = NullEmbedder()

    saved = await _salva_ricordo(
        store, embedder, PREF_TEXT,
        owner="home", chatbot_id="chatbot-a",
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
    recalled = await _richiama_ricordi(
        store, embedder, "temperatura del soggiorno",
        owner="home",
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
    recalled = await _richiama_ricordi(
        store, NullEmbedder(), "sensori esterni guasti",
        owner="home",
    )
    recalled_contents = [r["content"] for r in recalled.get("results", [])]
    assert PRODUCTION_SHAPED_CONTENT in recalled_contents

    # Present in the declared block: source='chat' is a declared source, so
    # it must enter context unconditionally, exactly like the three real
    # production rows this shape is modeled on.
    #
    # fetta E3 Task 7: this used to also drive the row through
    # `reasoner_memory.relevant_memory` (`brain/reasoner_memory.py`, gone
    # with the whole proactive reasoner) to prove it reached
    # `MemoryRecall.declared` too. Removed, not moved: `relevant_memory`'s
    # declared branch was a thin pass-through over exactly this
    # `KnowledgeStore.declared()` call (see the module's own docstring,
    # deleted with it) -- proving the store call below is enough, there is
    # no separate transformation left to pin.
    declared_items, declared_total = store.declared(owner="home")
    assert declared_total >= 1
    assert any(i["content"] == PRODUCTION_SHAPED_CONTENT for i in declared_items)

    store.close()
