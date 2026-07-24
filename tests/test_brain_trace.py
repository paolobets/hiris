import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.brain_trace import record_brain_action, remove_brain_action


class _FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_record_brain_action_creates_recallable_item(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    emb = _FakeEmbedder()

    item_id = await record_brain_action(
        store, emb,
        text="Soglia auto-tuning per binary_sensor.porta alzata a 0.8",
        source_ref="brain-action:threshold:binary_sensor.porta",
    )

    assert item_id is not None
    got = store.get_item(int(item_id))
    assert got["kind"] == "brain-action"
    assert got["status"] == "approved"
    assert got["source"] == "brain"
    assert got["source_ref"] == "brain-action:threshold:binary_sensor.porta"
    assert got["sensitivity"] == "normal"

    # Must be recallable via search: status='approved' AND embedding NOT NULL.
    res = store.search(query_vec=[1.0, 0.0, 0.0], k=5, kinds="brain-action")
    assert any(r["id"] == int(item_id) for r in res)
    store.close()


@pytest.mark.asyncio
async def test_record_brain_action_without_embedder_returns_none_and_writes_nothing(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))

    result = await record_brain_action(
        store, None,
        text="Soglia auto-tuning per binary_sensor.porta alzata a 0.8",
        source_ref="brain-action:threshold:binary_sensor.porta",
    )

    assert result is None
    assert store.list_items(kind="brain-action") == []
    store.close()


@pytest.mark.asyncio
async def test_record_brain_action_supersedes_same_source_ref(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    emb = _FakeEmbedder()
    ref = "brain-action:threshold:binary_sensor.porta"

    first_id = await record_brain_action(
        store, emb, text="Soglia alzata a 0.7", source_ref=ref,
    )
    second_id = await record_brain_action(
        store, emb, text="Soglia alzata a 0.8", source_ref=ref,
    )

    assert first_id != second_id
    rows = store.list_items(kind="brain-action")
    assert len(rows) == 1
    assert rows[0]["content"] == "Soglia alzata a 0.8"
    assert store.get_item(int(first_id)) is None
    store.close()


@pytest.mark.asyncio
async def test_remove_brain_action_deletes_trace(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    emb = _FakeEmbedder()
    ref = "brain-action:threshold:binary_sensor.porta"

    item_id = await record_brain_action(store, emb, text="Soglia alzata", source_ref=ref)
    assert store.list_items(kind="brain-action") != []

    removed = await remove_brain_action(store, ref)

    assert removed == 1
    assert store.list_items(kind="brain-action") == []
    assert store.get_item(int(item_id)) is None
    store.close()


@pytest.mark.asyncio
async def test_remove_brain_action_no_match_is_noop(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    removed = await remove_brain_action(store, "brain-action:threshold:nope")
    assert removed == 0
    store.close()
