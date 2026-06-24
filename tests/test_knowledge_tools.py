import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.tools.knowledge_tools import (
    SAVE_KNOWLEDGE_TOOL_DEF,
    RECALL_KNOWLEDGE_TOOL_DEF,
    LINK_KNOWLEDGE_TOOL_DEF,
)
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_recall_pseudonymizes_sensitive_for_cloud(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    txt = res["results"][0]["content"]
    assert "IT60X0542811101000000123456" not in txt
    assert "[IBAN_1]" in txt
    store.close()


@pytest.mark.asyncio
async def test_recall_sensitive_raw_for_local(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    store = KnowledgeStore(str(tmp_path / "b2.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v2.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=False)
    txt = res["results"][0]["content"]
    # Local model: content is returned raw (not pseudonymized)
    assert "IT60X0542811101000000123456" in txt
    store.close()


def test_tool_defs_have_names():
    assert SAVE_KNOWLEDGE_TOOL_DEF["name"] == "save_knowledge"
    assert RECALL_KNOWLEDGE_TOOL_DEF["name"] == "recall_knowledge"
    assert LINK_KNOWLEDGE_TOOL_DEF["name"] == "link_knowledge"


@pytest.mark.asyncio
async def test_save_knowledge_creates_pending(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_save_knowledge

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])
    res = await handle_save_knowledge(
        store,
        embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home",
    )
    assert res["status"] == "pending"
    pending = store.list_items(status="pending")
    assert pending[0]["content"] == "Paolo ama la pizza"
    store.close()


@pytest.mark.asyncio
async def test_dispatcher_routes_save_knowledge(tmp_path):
    """ToolDispatcher.dispatch('save_knowledge') must route to _knowledge_store
    and return status='pending'; a pending item must be recorded in the store."""
    from hiris.app.tools.dispatcher import ToolDispatcher

    store = KnowledgeStore(str(tmp_path / "dispatch_brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    # Minimal stubs for required ToolDispatcher constructor args
    ha_stub = MagicMock()
    notify_cfg: dict = {}

    dispatcher = ToolDispatcher(
        ha_client=ha_stub,
        notify_config=notify_cfg,
        knowledge_store=store,
        embedder=embedder,
    )

    result = await dispatcher.dispatch(
        "save_knowledge",
        {"kind": "preference", "content": "Paolo ama la pizza"},
    )

    assert result.get("status") == "pending"
    pending = store.list_items(status="pending")
    assert len(pending) == 1
    assert pending[0]["content"] == "Paolo ama la pizza"
    store.close()
