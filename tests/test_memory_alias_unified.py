"""Slice 3 Task 2: save_memory/recall_memory routed into the unified
KnowledgeStore as lens-scoped memory, with the real user_id as owner."""
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


async def test_save_memory_writes_lens_item_and_recall_finds_it(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    await disp.dispatch("save_memory", {"content": "l'utente preferisce 21°C"},
                        agent_id="agentA", user_id="paolo")
    res = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                              agent_id="agentA", user_id="paolo")
    # the recalled result mentions the stored memory
    assert "21" in str(res)
    # a different agent does NOT see agentA's lens memory
    res_b = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                                agent_id="agentB", user_id="paolo")
    assert "21" not in str(res_b)
    store.close()


async def test_save_memory_writes_real_owner_not_hardcoded_home(tmp_path):
    """Regression guard: save_memory/save_knowledge with user_id='paolo' must
    persist owner='paolo', not a hardcoded 'home'. If a future refactor
    reverts owner threading, this catches it directly on the stored row
    (rather than relying only on search-visibility side effects)."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    saved_memory = await disp.dispatch(
        "save_memory", {"content": "nota di paolo"},
        agent_id="agentA", user_id="paolo",
    )
    mem_item = store.get_item(saved_memory["id"])
    assert mem_item["owner"] == "paolo"

    saved_knowledge = await handle_save_knowledge(
        store, _Emb(), {"kind": "fact", "content": "fatto di paolo"},
        owner="paolo",
    )
    know_item = store.get_item(saved_knowledge["id"])
    assert know_item["owner"] == "paolo"
    store.close()


async def test_recall_memory_two_users_same_agent_no_leak(tmp_path):
    """Two different HA users chatting with the SAME agent must not see
    each other's save_memory (lens) items — the cross-user leak this task
    fixes. A home-owned lens item, however, is visible to both."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    await disp.dispatch("save_memory", {"content": "userA preferisce 21 gradi"},
                        agent_id="agentA", user_id="userA")

    res_a = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                                agent_id="agentA", user_id="userA")
    assert "21" in str(res_a)

    res_b = await disp.dispatch("recall_memory", {"query": "temperatura preferita"},
                                agent_id="agentA", user_id="userB")
    assert "21" not in str(res_b)

    # A home-owned lens item (e.g. saved with no user_id) is shared across
    # both users of this same agent.
    await disp.dispatch("save_memory", {"content": "nota condivisa casa 99"},
                        agent_id="agentA")  # no user_id -> owner defaults to 'home'
    res_a2 = await disp.dispatch("recall_memory", {"query": "nota condivisa"},
                                 agent_id="agentA", user_id="userA")
    res_b2 = await disp.dispatch("recall_memory", {"query": "nota condivisa"},
                                 agent_id="agentA", user_id="userB")
    assert "99" in str(res_a2)
    assert "99" in str(res_b2)
    store.close()


async def test_save_memory_defaults_owner_to_home_without_user_id(tmp_path):
    """No user_id supplied -> owner falls back to 'home' (Slice 3 contract)."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    saved = await disp.dispatch("save_memory", {"content": "ricordo senza utente"},
                                agent_id="agentA")
    assert saved.get("saved") is True
    item = store.get_item(saved["id"])
    assert item["owner"] == "home"
    assert item["lens"] == "agentA"
    assert item["kind"] == "memory"
    assert item["status"] == "approved"
    store.close()


async def test_save_memory_sets_valid_until_from_retention_days(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb(),
                          memory_retention_days=30)
    saved = await disp.dispatch("save_memory", {"content": "scade tra 30gg"},
                                agent_id="agentA", user_id="paolo")
    item = store.get_item(saved["id"])
    assert item["valid_until"] is not None
    valid_until = datetime.strptime(item["valid_until"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    expected = datetime.now(timezone.utc) + timedelta(days=30)
    assert abs((valid_until - expected).total_seconds()) < 60
    store.close()


async def test_purge_expired_lens_deletes_only_expired_lens_rows(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    expired_lens_id = store.add_item(
        kind="memory", content="scaduto", lens="agentA", valid_until=past
    )
    fresh_lens_id = store.add_item(
        kind="memory", content="fresco", lens="agentA", valid_until=future
    )
    no_expiry_lens_id = store.add_item(
        kind="memory", content="senza scadenza", lens="agentA", valid_until=None
    )
    shared_knowledge_id = store.add_item(
        kind="fact", content="conoscenza condivisa", lens=None, valid_until=past
    )

    deleted = store.purge_expired_lens()

    assert deleted == 1
    assert store.get_item(expired_lens_id) is None
    assert store.get_item(fresh_lens_id) is not None
    assert store.get_item(no_expiry_lens_id) is not None
    # Shared (non-lens) knowledge is untouched even if expired — Task 2 scope
    # is only per-agent lens memory retention.
    assert store.get_item(shared_knowledge_id) is not None
    store.close()


async def test_recall_memory_does_not_leak_non_memory_kinds(tmp_path):
    """recall_memory must only ever return kind='memory' items. The unified
    scope WHERE also returns un-lensed knowledge rows (expenses, obligations,
    facts...) owned by the same user, so without an explicit kinds=['memory']
    filter an agent could use recall_memory to read data outside its
    configured kinds egress filter (e.g. an agent restricted to
    kinds=['fact'] reading expenses via recall_memory instead of
    recall_knowledge). This is the egress-filter bypass this fix closes."""
    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())

    # An approved, un-lensed knowledge item (e.g. an expense the user already
    # approved) — this is the kind of row the unified scope WHERE also
    # matches for owner=paolo regardless of lens, which is exactly what
    # recall_memory must NOT expose.
    store.add_item(
        kind="expense", content="bolletta luce 123 euro", owner="paolo",
        lens=None, status="approved", embedding=[0.1, 0.2, 0.3],
    )
    await disp.dispatch("save_memory", {"content": "l'utente preferisce il te verde"},
                        agent_id="agentA", user_id="paolo")

    res = await disp.dispatch("recall_memory", {"query": "bolletta luce spesa"},
                              agent_id="agentA", user_id="paolo")
    assert "123" not in str(res)
    assert "bolletta" not in str(res)
    store.close()


async def test_recall_knowledge_includes_agents_own_lens_memory(tmp_path):
    """recall_knowledge must also pass lens=agent_id so an agent's own
    working memory shows up alongside shared knowledge."""
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          knowledge_store=store, embedder=_Emb())
    await disp.dispatch("save_memory", {"content": "nota privata agente"},
                        agent_id="agentA", user_id="paolo")
    res = await disp.dispatch("recall_knowledge", {"query": "nota privata"},
                              agent_id="agentA", user_id="paolo")
    contents = [r["content"] for r in res.get("results", [])]
    assert "nota privata agente" in contents
    store.close()
