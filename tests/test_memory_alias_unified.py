"""Slice 3 Task 2: save_memory/recall_memory routed into the unified
KnowledgeStore as chatbot-scoped memory, with the real user_id as owner."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.brain.knowledge_store import KnowledgeStore

pytestmark = pytest.mark.asyncio


class _FakeHA:
    async def call_service(self, d, s, data):
        return {"ok": True}


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
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    await disp.dispatch("save_memory", {"content": "l'utente preferisce 21°C"},
                        chatbot_id="agentA", user_id="paolo")
    res = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                              chatbot_id="agentA", user_id="paolo")
    # the recalled result mentions the stored memory
    assert "21" in str(res)
    # a DIFFERENT agent still sees it: chatbot_id no longer scopes visibility
    res_b = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                                chatbot_id="agentB", user_id="paolo")
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
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    saved_memory = await disp.dispatch(
        "save_memory", {"content": "nota di paolo"},
        chatbot_id="agentA", user_id="paolo",
    )
    mem_item = store.get_item(saved_memory["id"])
    assert mem_item["owner"] == "paolo"

    saved_knowledge = await disp.dispatch(
        "save_memory", {"kind": "fact", "content": "fatto di paolo"},
        chatbot_id="agentA", user_id="paolo",
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
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    await disp.dispatch("save_memory", {"content": "userA preferisce 21 gradi"},
                        chatbot_id="agentA", user_id="userA")

    res_a = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                                chatbot_id="agentA", user_id="userA")
    assert "21" in str(res_a)

    res_b = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                                chatbot_id="agentA", user_id="userB")
    assert "21" not in str(res_b)

    # A home-owned chatbot-scoped item (e.g. saved with no user_id) is
    # shared across both users of this same agent.
    await disp.dispatch("save_memory", {"content": "nota condivisa casa 99"},
                        chatbot_id="agentA")  # no user_id -> owner defaults to 'home'
    res_a2 = await disp.dispatch("recall_memory", {"query": "nota condivisa"},
                                 chatbot_id="agentA", user_id="userA")
    res_b2 = await disp.dispatch("recall_memory", {"query": "nota condivisa"},
                                 chatbot_id="agentA", user_id="userB")
    assert "99" in str(res_a2)
    assert "99" in str(res_b2)
    store.close()


async def test_save_memory_defaults_owner_to_home_without_user_id(tmp_path):
    """No user_id supplied -> owner falls back to 'home' (Slice 3 contract)."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    saved = await disp.dispatch("save_memory", {"content": "ricordo senza utente"},
                                chatbot_id="agentA")
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
    ricordo salvato ora non porta MAI una scadenza, a prescindere da cosa
    venga passato al dispatcher (che non accetta piu' nemmeno il parametro:
    vedi test_security.py/_make_dispatcher e ToolDispatcher.__init__)."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    saved = await disp.dispatch("save_memory", {"content": "non scade mai"},
                                chatbot_id="agentA", user_id="paolo")
    item = store.get_item(saved["id"])
    assert item["valid_until"] is None
    store.close()


async def test_save_memory_leggibile_a_distanza_di_anni_senza_aspettare(tmp_path, monkeypatch):
    """Test 2 del brief Task 6: un ricordo salvato oggi resta leggibile e
    richiamabile a distanza di anni. Si simula spostando l'orologio di
    LETTURA (`KnowledgeStore._now`, usato da `_clausole_di_scope` per il
    confronto su `valid_until`), non aspettando davvero anni."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    saved = await disp.dispatch("save_memory", {"content": "ricordo permanente"},
                                chatbot_id="agentA", user_id="paolo")

    tra_cinque_anni = (datetime.now(timezone.utc) + timedelta(days=5 * 365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    monkeypatch.setattr(store, "_now", lambda: tra_cinque_anni)

    trovato = await disp.dispatch("recall_memory", {"query": "ricordo permanente"},
                                  chatbot_id="agentA", user_id="paolo")
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
    kinds it may see (knowledge_access.kinds -> dispatcher's knowledge_kinds
    param), that restriction is honored by the merged recall_memory exactly
    as it always was by recall_knowledge."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    store.add_item(
        kind="expense", content="bolletta luce 123 euro", owner="paolo",
        chatbot_id=None, status="approved", embedding=[0.1, 0.2, 0.3],
    )
    await disp.dispatch("save_memory", {"content": "l'utente preferisce il te verde"},
                        chatbot_id="agentA", user_id="paolo")

    # No kinds restriction configured: both the memory and the expense are
    # visible -- the union is the whole point of one recall tool.
    unrestricted = await disp.dispatch("recall_memory", {"query": "bolletta luce spesa"},
                                       chatbot_id="agentA", user_id="paolo")
    assert "123" in str(unrestricted)

    # An agent configured with knowledge_access.kinds=['memory'] must NOT see
    # the expense via recall_memory.
    restricted = await disp.dispatch(
        "recall_memory", {"query": "bolletta luce spesa"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds=["memory"],
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
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    await disp.dispatch("save_memory", {"content": "nota privata agente"},
                        chatbot_id="agentA", user_id="paolo")
    await disp.dispatch(
        "save_memory",
        {"kind": "fact", "content": "il modulo meteo esterno e' guasto"},
        chatbot_id="agentA", user_id="paolo",
    )
    res = await disp.dispatch("recall_memory", {"query": "nota privata"},
                              chatbot_id="agentA", user_id="paolo")
    contents = [r["content"] for r in res.get("results", [])]
    assert "nota privata agente" in contents
    assert "il modulo meteo esterno e' guasto" in contents
    store.close()


async def test_recall_memory_kinds_filter_still_restricts_to_memory_when_asked(tmp_path):
    """The old recall_memory hardcoded kinds=['memory'] to protect an agent's
    configured kinds egress filter (knowledge_access.kinds) from being
    bypassed. After the merge there is only one recall tool and the SAME
    mechanism (the `kinds` param the dispatcher forwards from agent config)
    still restricts results when a caller passes it explicitly -- it is no
    longer automatic, but it still works."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    await disp.dispatch("save_memory", {"content": "nota privata agente"},
                        chatbot_id="agentA", user_id="paolo")
    await disp.dispatch(
        "save_memory",
        {"kind": "fact", "content": "il modulo meteo esterno e' guasto"},
        chatbot_id="agentA", user_id="paolo",
    )
    res = await disp.dispatch(
        "recall_memory", {"query": "nota privata"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds=["memory"],
    )
    contents = [r["content"] for r in res.get("results", [])]
    assert "nota privata agente" in contents
    assert "il modulo meteo esterno e' guasto" not in contents
    store.close()


async def test_recall_memory_own_memory_still_recallable_when_kinds_restricted_to_fact(tmp_path):
    """Review Important (fix 1): `knowledge_kinds` here is `['fact']` --
    a value a REAL caller can produce, unlike the pre-existing test above
    that used `['memory']` (chatbot-editor.js / KNOWLEDGE_KINDS never emit
    'memory': the UI serializes "all" or a subset of the five *knowledge*
    kinds only, see hiris/app/static/config/chatbot-editor.js and
    templates.js KNOWLEDGE_KINDS). Before the fix, a Chatbot configured with
    kinds=['fact'] could save_memory (kind omitted -> 'memory') and get
    saved:true, but recall_memory with that same config forwarded
    kinds=['fact'] unmodified -- the just-saved memory could never come
    back. This is the exact silent-loss class the memoria-unica slice exists
    to eliminate."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    saved = await disp.dispatch(
        "save_memory", {"content": "l'utente preferisce 21 gradi"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds=["fact"],
    )
    assert saved.get("saved") is True

    res = await disp.dispatch(
        "recall_memory", {"query": "temperatura preferita"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds=["fact"],
    )
    contents = [r["content"] for r in res.get("results", [])]
    assert "l'utente preferisce 21 gradi" in contents, (
        "un agente ristretto a kinds=['fact'] (valore reale della UI) deve "
        "comunque poter richiamare la propria memoria di lavoro appena "
        "salvata -- 'memory' non fa parte del vocabolario che "
        "knowledge_access.kinds governa"
    )
    store.close()


async def test_recall_memory_own_memory_still_recallable_when_kinds_empty_but_knowledge_stays_hidden(tmp_path):
    """Review Important (fix 1), second real value: `knowledge_kinds=[]` is
    the UI's "no access to the second brain at all" setting (chatbot-editor.js
    comment: "kinds:[] e' una scelta valida e significa 'nessun accesso al
    second brain'"). An agent configured this way must still see its own
    save_memory -- 'memory' isn't second-brain knowledge -- but must NOT
    gain visibility into house-wide facts as a side effect of the union."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    await disp.dispatch(
        "save_memory", {"kind": "fact", "content": "il modulo meteo esterno e' guasto"},
        chatbot_id="agentA", user_id="paolo",
    )
    saved = await disp.dispatch(
        "save_memory", {"content": "nota privata agente"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds=[],
    )
    assert saved.get("saved") is True

    res = await disp.dispatch(
        "recall_memory", {"query": "nota privata modulo meteo"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds=[],
    )
    contents = [r["content"] for r in res.get("results", [])]
    assert "nota privata agente" in contents, (
        "kinds=[] non deve bloccare la memoria propria dell'agente"
    )
    assert "il modulo meteo esterno e' guasto" not in contents, (
        "kinds=[] deve comunque bloccare l'accesso alla conoscenza condivisa"
    )
    store.close()


async def test_save_memory_un_solo_strumento_salva_preferenza_e_scadenza_e_recall_trova_entrambe(tmp_path):
    """Task 2 -- un solo strumento di salvataggio, uno di richiamo: una
    preferenza nuda (kind omesso) e una scadenza con due campi strutturati
    (due_date, amount) passano dallo STESSO save_memory -- niente
    save_knowledge separato -- e la scadenza nasce gia' approvata, non in
    coda. Entrambe sono ritrovabili dallo STESSO recall_memory."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    pref = await disp.dispatch(
        "save_memory", {"content": "preferisco 21 gradi"},
        chatbot_id="agentA", user_id="paolo",
    )
    assert pref.get("saved") is True
    pref_item = store.get_item(pref["id"])
    assert pref_item["kind"] == "memory"
    assert pref_item["status"] == "approved"

    scadenza = await disp.dispatch(
        "save_memory",
        {"kind": "obligation", "content": "TARI da pagare",
         "due_date": "2026-09-15", "amount": 120.50},
        chatbot_id="agentA", user_id="paolo",
    )
    assert scadenza.get("saved") is True
    scadenza_item = store.get_item(scadenza["id"])
    assert scadenza_item["kind"] == "obligation"
    assert scadenza_item["due_date"] == "2026-09-15"
    assert scadenza_item["amount"] == pytest.approx(120.50)
    assert scadenza_item["status"] == "approved"  # subito, niente coda

    res = await disp.dispatch(
        "recall_memory", {"query": "gradi tasse casa"},
        chatbot_id="agentA", user_id="paolo",
    )
    contenuti = [r["content"] for r in res["results"]]
    assert "preferisco 21 gradi" in contenuti
    assert "TARI da pagare" in contenuti
    store.close()


# ---------------------------------------------------------------------------
# Fix 1 (CRITICAL, whole-branch review, final fix wave): save_memory's
# `source` depends on WHO called dispatch(), not on what was saved.
# `from_remote_gateway` is threaded ONLY by api/handlers_execute.py, based on
# a process secret (_is_local_chat) the request body cannot forge -- every
# other caller (this test's direct dispatch(), claude_runner.py,
# openai_compat_runner.py) leaves it at its default False and keeps writing
# source="chat", unchanged from before this fix.
# ---------------------------------------------------------------------------

async def test_save_memory_default_source_is_chat(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    saved = await disp.dispatch(
        "save_memory", {"content": "detto in chat locale"},
        chatbot_id="agentA", user_id="paolo",
    )
    item = store.get_item(saved["id"])
    assert item["source"] == "chat"
    store.close()


async def test_save_memory_from_remote_gateway_writes_gateway_source(tmp_path):
    """The defect this fix closes: before it, EVERY save_memory call (gateway
    included) wrote source='chat', which IS in DECLARED_SOURCES -- a single
    tool call from a remote MCP session (reachable via api/handlers_execute.py,
    /api/execute) produced a row auto-injected into every future prompt as
    something 'a person of the house declared'. source='gateway' is not in
    DECLARED_SOURCES (test_knowledge_store_declared.py pins the exclusion),
    so the row stays recallable but is never auto-injected as a declaration."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    saved = await disp.dispatch(
        "save_memory", {"content": "salvato dal gateway MCP remoto"},
        chatbot_id="mcp-gateway", user_id="home", from_remote_gateway=True,
    )
    assert saved.get("saved") is True
    item = store.get_item(saved["id"])
    assert item["source"] == "gateway"

    # Still recallable -- Fix 1 narrows WHERE it surfaces, not whether it can
    # be found at all.
    recalled = await disp.dispatch(
        "recall_memory", {"query": "salvato dal gateway"},
        chatbot_id="mcp-gateway", user_id="home",
    )
    assert "salvato dal gateway MCP remoto" in str(recalled)

    # Never in the declared() read path, regardless of caller.
    declared_items, _total = store.declared(owner="home")
    assert not any("salvato dal gateway MCP remoto" in (d.get("content") or "")
                   for d in declared_items)
    store.close()


# ---------------------------------------------------------------------------
# Fix 6 (Minor, whole-branch review, final fix wave): `knowledge_kinds` given
# as a plain string (a form KnowledgeStore itself normalises, e.g. a
# hand-edited knowledge_access.kinds: "fact") must still gain the 'memory'
# union recall_memory needs to see the caller's own working memory --
# dispatcher.py used to test only `isinstance(recall_kinds, list)`.
# ---------------------------------------------------------------------------

async def test_recall_memory_kinds_as_plain_string_still_unions_memory(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    saved = await disp.dispatch(
        "save_memory", {"content": "memoria propria dell'agente"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds="fact",
    )
    assert saved.get("saved") is True

    res = await disp.dispatch(
        "recall_memory", {"query": "memoria propria"},
        chatbot_id="agentA", user_id="paolo", knowledge_kinds="fact",
    )
    contents = [r["content"] for r in res.get("results", [])]
    assert "memoria propria dell'agente" in contents, (
        "kinds='fact' (stringa nuda) deve comunque unire 'memory', esattamente "
        "come kinds=['fact']"
    )
    store.close()
