import pytest
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_pending_and_approve(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import (
        handle_list_pending, handle_approve,
    )
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="x", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending")
    data = await r.json()
    assert [i["id"] for i in data["items"]] == [pid]

    r2 = await client.post(f"/api/knowledge/{pid}/approve")
    assert r2.status == 200
    assert store.get_item(pid)["status"] == "approved"

    store.close()


@pytest.mark.asyncio
async def test_manual_add_no_embedder(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_manual_add, handle_list_pending

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    app = web.Application()
    app["knowledge_store"] = store
    # No embedding_provider — must still work
    app.router.add_post("/api/knowledge", handle_manual_add)
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.post(
        "/api/knowledge",
        json={"kind": "note", "content": "x"},
    )
    assert r.status == 200
    data = await r.json()
    assert data["status"] == "approved"
    item_id = data["id"]

    # Verify item is approved and visible via list_items
    approved = store.list_items(status="approved")
    assert any(i["id"] == item_id for i in approved)

    # Verify item does NOT appear in pending list
    r2 = await client.get("/api/knowledge/pending")
    pending_data = await r2.json()
    assert all(i["id"] != item_id for i in pending_data["items"])

    store.close()


@pytest.mark.asyncio
async def test_reject_deletes_item(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending, handle_reject

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="to reject", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    client = await aiohttp_client(app)

    r = await client.post(f"/api/knowledge/{pid}/reject")
    assert r.status == 200

    assert store.get_item(pid) is None

    store.close()


@pytest.mark.asyncio
async def test_no_store_list_returns_empty(aiohttp_client):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending

    app = web.Application()
    # knowledge_store NOT set
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending")
    assert r.status == 200
    data = await r.json()
    assert data == {"items": []}


@pytest.mark.asyncio
async def test_no_store_write_returns_503(aiohttp_client):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import (
        handle_approve, handle_reject, handle_manual_add,
    )

    app = web.Application()
    # knowledge_store NOT set
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    app.router.add_post("/api/knowledge", handle_manual_add)
    client = await aiohttp_client(app)

    r1 = await client.post("/api/knowledge/1/approve")
    assert r1.status == 503

    r2 = await client.post("/api/knowledge/1/reject")
    assert r2.status == 503

    r3 = await client.post("/api/knowledge", json={"kind": "note", "content": "x"})
    assert r3.status == 503
