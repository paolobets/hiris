import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.brain_trace import record_brain_action, remove_brain_action


class _FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


class _FalsyEmbedder:
    def __init__(self, value):
        self._value = value

    async def embed(self, text):
        return self._value


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
    # No-regression pin: a working embedder must still store the vector,
    # asserted on the row itself, not inferred from search() succeeding.
    assert got["has_embedding"] is True

    # Must be recallable via search: status='approved' AND embedding NOT NULL.
    res = store.search(query_vec=[1.0, 0.0, 0.0], k=5, kinds="brain-action")
    assert any(r["id"] == int(item_id) for r in res)
    store.close()


@pytest.mark.asyncio
async def test_record_brain_action_without_embedder_writes_undoable_trace(tmp_path):
    """No embedder configured (embedder=None) must NOT cost the Brain its
    undo: the trace is still written -- with a NULL embedding, so it
    degrades to recent() instead of vector search -- and remove_brain_action
    must still be able to find and remove it."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    ref = "brain-action:threshold:binary_sensor.porta"

    item_id = await record_brain_action(
        store, None,
        text="Soglia auto-tuning per binary_sensor.porta alzata a 0.8",
        source_ref=ref,
    )

    assert item_id is not None
    got = store.get_item(int(item_id))
    assert got["source_ref"] == ref
    assert got["status"] == "approved"
    assert got["has_embedding"] is False

    removed = await remove_brain_action(store, ref)
    assert removed == 1
    assert store.get_item(int(item_id)) is None
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


@pytest.mark.asyncio
@pytest.mark.parametrize("falsy_value", [None, []])
async def test_record_brain_action_falsy_embedding_still_writes_undoable_trace(
    tmp_path, falsy_value,
):
    """An embedder that returns a falsy vector (e.g. [] -- the factory
    NullEmbedder) must not refuse the write either: same undoable-trace
    contract as embedder=None above."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    ref = "brain-action:threshold:binary_sensor.porta"
    bad_emb = _FalsyEmbedder(falsy_value)

    item_id = await record_brain_action(
        store, bad_emb, text="Soglia alzata a 0.8", source_ref=ref,
    )

    assert item_id is not None
    got = store.get_item(int(item_id))
    assert got["source_ref"] == ref
    assert got["has_embedding"] is False

    removed = await remove_brain_action(store, ref)
    assert removed == 1
    assert store.get_item(int(item_id)) is None
    store.close()


@pytest.mark.asyncio
async def test_record_brain_action_falsy_embedding_supersedes_prior_good_trace(tmp_path):
    """A subsequent write whose embedder returns a falsy vector must still
    supersede (delete-then-add) any prior trace for the same source_ref --
    the trace stays undoable, it just degrades to recent() instead of
    vector search. Losing the prior trace's vector silently would be the
    same defect (data written but not the RIGHT data) wearing a different
    hat."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    good_emb = _FakeEmbedder()
    ref = "brain-action:threshold:binary_sensor.porta"

    prior_id = await record_brain_action(
        store, good_emb, text="Soglia alzata a 0.7", source_ref=ref,
    )
    assert prior_id is not None
    assert store.get_item(int(prior_id))["has_embedding"] is True

    bad_emb = _FalsyEmbedder([])
    new_id = await record_brain_action(
        store, bad_emb, text="Soglia alzata a 0.8 (embed fallito)", source_ref=ref,
    )

    assert new_id is not None
    assert new_id != prior_id
    assert store.get_item(int(prior_id)) is None  # superseded
    rows = store.list_items(kind="brain-action")
    assert len(rows) == 1
    assert rows[0]["id"] == int(new_id)
    assert rows[0]["content"] == "Soglia alzata a 0.8 (embed fallito)"

    removed = await remove_brain_action(store, ref)
    assert removed == 1
    store.close()
