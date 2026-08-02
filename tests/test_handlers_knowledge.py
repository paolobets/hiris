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
async def test_list_pending_scoped_to_owner_and_home(aiohttp_client, tmp_path):
    """IDOR regression (review B/#16): user B must not see user A's private
    pending items, only their own + shared 'home' items."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA",
                           sensitivity="sensitive", status="pending")
    b_id = store.add_item(kind="fact", content="B's own", owner="userB", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending", headers={"X-Remote-User-Id": "userB"})
    assert r.status == 200
    data = await r.json()
    ids = {i["id"] for i in data["items"]}
    assert ids == {b_id, home_id}
    assert a_id not in ids

    store.close()


@pytest.mark.asyncio
async def test_approve_cross_owner_rejected(aiohttp_client, tmp_path):
    """IDOR regression: user B cannot approve user A's pending item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r = await client.post(f"/api/knowledge/{a_id}/approve", headers={"X-Remote-User-Id": "userB"})
    assert r.status in (403, 404)
    assert store.get_item(a_id)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_reject_cross_owner_rejected(aiohttp_client, tmp_path):
    """IDOR regression: user B cannot delete (reject) user A's pending item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_reject

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    client = await aiohttp_client(app)

    r = await client.post(f"/api/knowledge/{a_id}/reject", headers={"X-Remote-User-Id": "userB"})
    assert r.status in (403, 404)
    assert store.get_item(a_id) is not None
    assert store.get_item(a_id)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_approve_own_item_and_home_item_still_works(aiohttp_client, tmp_path):
    """Legitimate flow: a user approves their OWN pending item, and any user
    can approve a shared 'home' item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    own_id = store.add_item(kind="fact", content="mine", owner="userA", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r1 = await client.post(f"/api/knowledge/{own_id}/approve", headers={"X-Remote-User-Id": "userA"})
    assert r1.status == 200
    assert store.get_item(own_id)["status"] == "approved"

    r2 = await client.post(f"/api/knowledge/{home_id}/approve", headers={"X-Remote-User-Id": "userA"})
    assert r2.status == 200
    assert store.get_item(home_id)["status"] == "approved"

    store.close()


@pytest.mark.asyncio
async def test_unknown_identity_fails_closed_to_home_scope(aiohttp_client, tmp_path):
    """No X-Remote-User-Id header (unknown identity) must fail closed: only
    'home' items are visible/actionable, never another user's private item."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending, handle_approve

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A's secret", owner="userA", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    # No identity header at all.
    r = await client.get("/api/knowledge/pending")
    data = await r.json()
    ids = {i["id"] for i in data["items"]}
    assert ids == {home_id}
    assert a_id not in ids

    r2 = await client.post(f"/api/knowledge/{a_id}/approve")
    assert r2.status in (403, 404)
    assert store.get_item(a_id)["status"] == "pending"

    store.close()


@pytest.mark.asyncio
async def test_no_store_list_signals_unavailable(aiohttp_client):
    """Uno store assente NON e' una coda vuota: rispondere 200 {"items": []}
    faceva apparire "non ho potuto leggere" come "non c'e' niente da
    approvare", che e' esattamente il modo in cui un ricordo si perde in
    silenzio. Stesso 503 delle rotte di scrittura, cosi' la coda in chat puo'
    distinguere i due casi."""
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import handle_list_pending

    app = web.Application()
    # knowledge_store NOT set
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending")
    assert r.status == 503
    data = await r.json()
    assert data["items"] == []
    assert data["error"]


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
