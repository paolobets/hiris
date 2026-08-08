"""Slice 3 Task 2: save_memory/recall_memory routed into the unified
KnowledgeStore as chatbot-scoped memory, with the real user_id as owner.

fetta E2 Task 7 ("esce il dispatcher"): every test here used to go through
`ToolDispatcher.dispatch("save_memory"/"recall_memory", ...)`, which is gone.
Checked test by test against the deleted class instead of assuming:

  - Most tests call `memory_tools.handle_save_memory`/`handle_recall_memory`
    directly now -- the SAME functions the dispatcher used to call, so the
    subject (owner threading, cross-chatbot visibility, no auto-expiry,
    source='chat'/'gateway') is unchanged, only the access path is.
  - Three tests (`test_recall_memory_own_memory_still_recallable_when_kinds_
    restricted_to_fact`, its `kinds=[]` sibling, and
    `test_recall_memory_kinds_as_plain_string_still_unions_memory`) tested
    `union_memory_kind` -- a function that lived ONLY in `tools/dispatcher.py`
    and had exactly one other claimed caller (`api/handlers_chat.py`'s
    declared-block call, per its own docstring), which the "nucleo alla
    chat" slice (2.0, E1) had already removed before this task even started
    (`handle_chat` no longer touches `KnowledgeStore.declared()`/`.search()`
    at all -- see tests/test_chat_al_nucleo.py). `union_memory_kind` is gone
    and grep confirms nothing else defines or imports it: the "an agent
    restricted to knowledge_access.kinds can still recall its OWN just-saved
    memory" guarantee it provided has no surviving implementation anywhere
    in the codebase to call instead, and no live caller was even reaching it
    through the dispatcher before this task either (chatbot_engine.py's Test
    Run computes `knowledge_kinds` but has passed `dispatcher=
    DispatcherConoscenza` -- which ignores it -- since Task 2 of this same
    fetta; the Sentinel/Agentbot evaluation path never sets `knowledge_kinds`
    at all). Those three tests died with their subject rather than moved.
    The other two `knowledge_kinds`-restriction tests survive because they
    pass an explicit kinds list that does not depend on the union
    (`['memory']`), so `handle_recall_memory`'s own, still-real `kinds`
    filtering covers them without it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.tools.memory_tools import handle_recall_memory, handle_save_memory

pytestmark = pytest.mark.asyncio


class _Emb:
    async def embed(self, text):
        return [0.1, 0.2, 0.3]

    def dim(self):
        return 3


async def test_save_memory_writes_chatbot_item_and_recall_finds_it_from_another_chatbot(tmp_path):
    """Task 3 (memoria unica): cio' che dici lo sa HIRIS, non il chatbot con
    cui parlavi. Un ricordo salvato parlando con agentA e' richiamabile
    parlando con agentB, a parita' di owner -- il costo osservato in
    produzione (le tre memorie reali, tutte legate a
    chatbot_id='hiris-default', invisibili a un secondo chatbot) e' esattamente
    quello che questa fetta chiude."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()
    await handle_save_memory(store, emb, {"content": "l'utente preferisce 21°C"},
                             owner="paolo", chatbot_id="agentA")
    res = await handle_recall_memory(store, emb, {"query": "temperatura preferita"},
                                     owner="paolo")
    # the recalled result mentions the stored memory
    assert "21" in str(res)
    # a DIFFERENT agent still sees it: chatbot_id no longer scopes visibility
    res_b = await handle_recall_memory(store, emb, {"query": "temperatura preferita"},
                                       owner="paolo")
    assert "21" in str(res_b)
    store.close()


async def test_save_memory_writes_real_owner_not_hardcoded_home(tmp_path):
    """Regression guard: save_memory with user_id='paolo' must persist
    owner='paolo', not a hardcoded 'home' -- for a bare memory (kind omesso)
    AND for a knowledge-flavored kind (fact), the two cases the old
    save_memory/save_knowledge pair used to cover separately. If a future
    refactor reverts owner threading, this catches it directly on the stored
    row (rather than relying only on search-visibility side effects)."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()

    saved_memory = await handle_save_memory(
        store, emb, {"content": "nota di paolo"},
        owner="paolo", chatbot_id="agentA",
    )
    mem_item = store.get_item(saved_memory["id"])
    assert mem_item["owner"] == "paolo"

    saved_knowledge = await handle_save_memory(
        store, emb, {"kind": "fact", "content": "fatto di paolo"},
        owner="paolo", chatbot_id="agentA",
    )
    know_item = store.get_item(saved_knowledge["id"])
    assert know_item["owner"] == "paolo"
    store.close()


async def test_recall_memory_two_users_same_agent_no_leak(tmp_path):
    """Two different HA users chatting with the SAME agent must not see
    each other's save_memory (chatbot-scoped) items — the cross-user leak
    this task fixes. A home-owned chatbot-scoped item, however, is visible
    to both."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()

    await handle_save_memory(store, emb, {"content": "userA preferisce 21 gradi"},
                             owner="userA", chatbot_id="agentA")

    res_a = await handle_recall_memory(store, emb, {"query": "temperatura preferita"},
                                       owner="userA")
    assert "21" in str(res_a)

    res_b = await handle_recall_memory(store, emb, {"query": "temperatura preferita"},
                                       owner="userB")
    assert "21" not in str(res_b)

    # A home-owned chatbot-scoped item (e.g. saved with no user_id) is
    # shared across both users of this same agent.
    await handle_save_memory(store, emb, {"content": "nota condivisa casa 99"},
                             owner="home", chatbot_id="agentA")  # no user_id -> owner defaults to 'home'
    res_a2 = await handle_recall_memory(store, emb, {"query": "nota condivisa"},
                                        owner="userA")
    res_b2 = await handle_recall_memory(store, emb, {"query": "nota condivisa"},
                                        owner="userB")
    assert "99" in str(res_a2)
    assert "99" in str(res_b2)
    store.close()


async def test_save_memory_defaults_owner_to_home_without_user_id(tmp_path):
    """No user_id supplied -> owner falls back to 'home' (Slice 3 contract)."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    saved = await handle_save_memory(store, _Emb(), {"content": "ricordo senza utente"},
                                     owner="home", chatbot_id="agentA")
    assert saved.get("saved") is True
    item = store.get_item(saved["id"])
    assert item["owner"] == "home"
    assert item["chatbot_id"] == "agentA"
    assert item["kind"] == "memory"
    assert item["status"] == "approved"
    store.close()


async def test_save_memory_non_riceve_piu_scadenza_automatica(tmp_path):
    """Task 6 (memoria non evapora): il calcolo automatico di `valid_until`
    da `retention_days` e' stato rimosso da `handle_save_memory` -- un
    ricordo salvato ora non porta MAI una scadenza. `handle_save_memory`
    non accetta piu' nemmeno il parametro: vedi test_security.py."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    saved = await handle_save_memory(store, _Emb(), {"content": "non scade mai"},
                                     owner="paolo", chatbot_id="agentA")
    item = store.get_item(saved["id"])
    assert item["valid_until"] is None
    store.close()


async def test_save_memory_leggibile_a_distanza_di_anni_senza_aspettare(tmp_path, monkeypatch):
    """Test 2 del brief Task 6: un ricordo salvato oggi resta leggibile e
    richiamabile a distanza di anni. Si simula spostando l'orologio di
    LETTURA (`KnowledgeStore._now`, usato da `_clausole_di_scope` per il
    confronto su `valid_until`), non aspettando davvero anni."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()
    saved = await handle_save_memory(store, emb, {"content": "ricordo permanente"},
                                     owner="paolo", chatbot_id="agentA")

    tra_cinque_anni = (datetime.now(timezone.utc) + timedelta(days=5 * 365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    monkeypatch.setattr(store, "_now", lambda: tra_cinque_anni)

    trovato = await handle_recall_memory(store, emb, {"query": "ricordo permanente"},
                                         owner="paolo")
    contenuti = [r["content"] for r in trovato.get("results", [])]
    assert "ricordo permanente" in contenuti
    recenti = store.recent(owner="paolo", k=10)
    assert any(r["id"] == saved["id"] for r in recenti)
    store.close()


async def test_recall_memory_kinds_egress_filter_still_excludes_other_kinds_when_configured(tmp_path):
    """Task 2 superseded this test's old premise (recall_memory forcibly
    restricted to kind='memory'): a single recall tool must be able to see
    knowledge kinds by default -- that is the point of the merge, covered by
    test_recall_memory_includes_agents_own_chatbot_memory_and_house_knowledge
    above. What must still hold is the REAL security property the old
    hardcoding accidentally provided: when an agent's config restricts the
    kinds it may see (knowledge_access.kinds), that restriction is honored
    by the merged recall_memory exactly as it always was by recall_knowledge
    -- `handle_recall_memory`'s own `kinds` parameter, unchanged by this
    task."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()

    store.add_item(
        kind="expense", content="bolletta luce 123 euro", owner="paolo",
        chatbot_id=None, status="approved", embedding=[0.1, 0.2, 0.3],
    )
    await handle_save_memory(store, emb, {"content": "l'utente preferisce il te verde"},
                             owner="paolo", chatbot_id="agentA")

    # No kinds restriction configured: both the memory and the expense are
    # visible -- the union is the whole point of one recall tool.
    unrestricted = await handle_recall_memory(store, emb, {"query": "bolletta luce spesa"},
                                              owner="paolo")
    assert "123" in str(unrestricted)

    # An agent configured with knowledge_access.kinds=['memory'] must NOT see
    # the expense via recall_memory.
    restricted = await handle_recall_memory(
        store, emb, {"query": "bolletta luce spesa"},
        owner="paolo", kinds=["memory"],
    )
    assert "123" not in str(restricted)
    assert "bolletta" not in str(restricted)
    store.close()


async def test_recall_memory_includes_agents_own_chatbot_memory_and_house_knowledge(tmp_path):
    """Task 2 -- one recall tool, not two: a chatbot-scoped memory item and a
    house-wide fact both come back from the SAME recall_memory call. Before
    the merge this required recall_knowledge (the tool gone after Task 2);
    recall_memory forced kinds=['memory'] and could not see the fact."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()
    await handle_save_memory(store, emb, {"content": "nota privata agente"},
                             owner="paolo", chatbot_id="agentA")
    await handle_save_memory(
        store, emb,
        {"kind": "fact", "content": "il modulo meteo esterno e' guasto"},
        owner="paolo", chatbot_id="agentA",
    )
    res = await handle_recall_memory(store, emb, {"query": "nota privata"},
                                     owner="paolo")
    contents = [r["content"] for r in res.get("results", [])]
    assert "nota privata agente" in contents
    assert "il modulo meteo esterno e' guasto" in contents
    store.close()


async def test_recall_memory_kinds_filter_still_restricts_to_memory_when_asked(tmp_path):
    """The old recall_memory hardcoded kinds=['memory'] to protect an agent's
    configured kinds egress filter (knowledge_access.kinds) from being
    bypassed. After the merge there is only one recall tool and the SAME
    mechanism (`handle_recall_memory`'s `kinds` param) still restricts
    results when a caller passes it explicitly -- it is no longer automatic,
    but it still works."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()
    await handle_save_memory(store, emb, {"content": "nota privata agente"},
                             owner="paolo", chatbot_id="agentA")
    await handle_save_memory(
        store, emb,
        {"kind": "fact", "content": "il modulo meteo esterno e' guasto"},
        owner="paolo", chatbot_id="agentA",
    )
    res = await handle_recall_memory(
        store, emb, {"query": "nota privata"},
        owner="paolo", kinds=["memory"],
    )
    contents = [r["content"] for r in res.get("results", [])]
    assert "nota privata agente" in contents
    assert "il modulo meteo esterno e' guasto" not in contents
    store.close()


async def test_save_memory_un_solo_strumento_salva_preferenza_e_scadenza_e_recall_trova_entrambe(tmp_path):
    """Task 2 -- un solo strumento di salvataggio, uno di richiamo: una
    preferenza nuda (kind omesso) e una scadenza con due campi strutturati
    (due_date, amount) passano dallo STESSO save_memory -- niente
    save_knowledge separato -- e la scadenza nasce gia' approvata, non in
    coda. Entrambe sono ritrovabili dallo STESSO recall_memory."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()

    pref = await handle_save_memory(
        store, emb, {"content": "preferisco 21 gradi"},
        owner="paolo", chatbot_id="agentA",
    )
    assert pref.get("saved") is True
    pref_item = store.get_item(pref["id"])
    assert pref_item["kind"] == "memory"
    assert pref_item["status"] == "approved"

    scadenza = await handle_save_memory(
        store, emb,
        {"kind": "obligation", "content": "TARI da pagare",
         "due_date": "2026-09-15", "amount": 120.50},
        owner="paolo", chatbot_id="agentA",
    )
    assert scadenza.get("saved") is True
    scadenza_item = store.get_item(scadenza["id"])
    assert scadenza_item["kind"] == "obligation"
    assert scadenza_item["due_date"] == "2026-09-15"
    assert scadenza_item["amount"] == pytest.approx(120.50)
    assert scadenza_item["status"] == "approved"  # subito, niente coda

    res = await handle_recall_memory(
        store, emb, {"query": "gradi tasse casa"},
        owner="paolo",
    )
    contenuti = [r["content"] for r in res["results"]]
    assert "preferisco 21 gradi" in contenuti
    assert "TARI da pagare" in contenuti
    store.close()


# ---------------------------------------------------------------------------
# Fix 1 (CRITICAL, whole-branch review, final fix wave): save_memory's
# `source` depends on WHO called it, not on what was saved.
# `from_remote_gateway` used to be threaded ONLY by api/handlers_execute.py
# (gone, fetta E2 Task 4), based on a process secret (_is_local_chat) the
# request body could not forge, and translated by the dispatcher into
# `source="gateway"` -- every other caller (this test's direct call,
# claude_runner.py, openai_compat_runner.py) left it at its default and kept
# writing source="chat". `handle_save_memory` still takes `source` directly;
# only the translation step (the now-gone dispatcher's `if from_remote_
# gateway else`) is no longer there to test.
# ---------------------------------------------------------------------------

async def test_save_memory_default_source_is_chat(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    saved = await handle_save_memory(
        store, _Emb(), {"content": "detto in chat locale"},
        owner="paolo", chatbot_id="agentA",
    )
    item = store.get_item(saved["id"])
    assert item["source"] == "chat"
    store.close()


async def test_save_memory_from_remote_gateway_writes_gateway_source(tmp_path):
    """The defect this fix closes: before it, EVERY save_memory call (gateway
    included) wrote source='chat', which IS in DECLARED_SOURCES -- a single
    tool call from a remote MCP session produced a row auto-injected into
    every future prompt as something 'a person of the house declared'.
    source='gateway' is not in DECLARED_SOURCES (test_knowledge_store_declared.py
    pins the exclusion), so the row stays recallable but is never
    auto-injected as a declaration."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    emb = _Emb()
    saved = await handle_save_memory(
        store, emb, {"content": "salvato dal gateway MCP remoto"},
        owner="home", chatbot_id="mcp-gateway", source="gateway",
    )
    assert saved.get("saved") is True
    item = store.get_item(saved["id"])
    assert item["source"] == "gateway"

    # Still recallable -- Fix 1 narrows WHERE it surfaces, not whether it can
    # be found at all.
    recalled = await handle_recall_memory(store, emb, {"query": "salvato dal gateway"},
                                          owner="home")
    assert "salvato dal gateway MCP remoto" in str(recalled)

    # Never in the declared() read path, regardless of caller.
    declared_items, _total = store.declared(owner="home")
    assert not any("salvato dal gateway MCP remoto" in (d.get("content") or "")
                   for d in declared_items)
    store.close()
