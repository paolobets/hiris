import pytest
import numpy as np
from unittest.mock import MagicMock
from hiris.app.proxy.embedding_index import EmbeddingIndex, _entity_text


def test_entity_text_with_name():
    entity = {"id": "light.soggiorno", "name": "Luce Soggiorno", "state": "on", "unit": ""}
    assert _entity_text(entity) == "Luce Soggiorno [light soggiorno]"


def test_entity_text_without_name():
    entity = {"id": "light.soggiorno", "name": "", "state": "on", "unit": ""}
    assert _entity_text(entity) == "light soggiorno"


def test_ready_false_before_build():
    assert not EmbeddingIndex().ready


def test_search_returns_empty_when_not_built():
    assert EmbeddingIndex().search("test") == []


@pytest.mark.asyncio
async def test_build_empty_entities_does_nothing():
    index = EmbeddingIndex()
    await index.build([])
    assert not index.ready


@pytest.mark.asyncio
async def test_build_populates_matrix():
    index = EmbeddingIndex()
    fake_embs = [np.random.randn(384).astype(np.float32) for _ in range(2)]
    mock_model = MagicMock()
    mock_model.embed.return_value = iter(fake_embs)
    index._model = mock_model  # bypass lazy load / model download

    entities = [
        {"id": "light.a", "name": "Luce A", "state": "on", "unit": ""},
        {"id": "sensor.b", "name": "Temperatura", "state": "21", "unit": "°C"},
    ]
    await index.build(entities)

    assert index.ready
    assert index._matrix.shape == (2, 384)
    assert index._entity_ids == ["light.a", "sensor.b"]


def test_search_returns_correct_ranking():
    index = EmbeddingIndex()
    # Build matrix manually: entity 0 aligns with query, entity 1 and 2 do not
    index._entity_ids = ["light.soggiorno", "sensor.temp", "switch.boiler"]
    emb = np.zeros((3, 384), dtype=np.float32)
    emb[0, 0] = 1.0
    emb[1, 1] = 1.0
    emb[2, 2] = 1.0
    index._matrix = emb

    q_vec = np.zeros(384, dtype=np.float32)
    q_vec[0] = 1.0  # identical to light.soggiorno
    mock_model = MagicMock()
    mock_model.embed.return_value = iter([q_vec])
    index._model = mock_model

    results = index.search("luce soggiorno", top_k=2)
    assert len(results) == 2
    assert results[0] == "light.soggiorno"


def test_search_domain_filter_excludes_other_domains():
    index = EmbeddingIndex()
    index._entity_ids = ["light.a", "light.b", "switch.c"]
    index._matrix = np.ones((3, 384), dtype=np.float32)

    mock_model = MagicMock()
    mock_model.embed.return_value = iter([np.ones(384, dtype=np.float32)])
    index._model = mock_model

    results = index.search("luci", top_k=3, domain_filter="light")
    assert "switch.c" not in results
    assert all(eid.startswith("light.") for eid in results)


def test_search_top_k_capped_at_available_entities():
    index = EmbeddingIndex()
    index._entity_ids = ["light.a", "light.b"]
    index._matrix = np.eye(2, 384, dtype=np.float32)

    q_vec = np.zeros(384, dtype=np.float32)
    q_vec[0] = 1.0
    mock_model = MagicMock()
    mock_model.embed.return_value = iter([q_vec])
    index._model = mock_model

    results = index.search("test", top_k=99)
    assert len(results) == 2  # only 2 entities exist
