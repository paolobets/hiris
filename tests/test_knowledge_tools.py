import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.knowledge_tools import (
    SAVE_KNOWLEDGE_TOOL_DEF,
    RECALL_KNOWLEDGE_TOOL_DEF,
    LINK_KNOWLEDGE_TOOL_DEF,
)
from hiris.app.brain.knowledge_store import KnowledgeStore


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
