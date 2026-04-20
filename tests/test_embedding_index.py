import pytest
from hiris.app.proxy.embedding_index import EmbeddingIndex, _entity_text, _tokenize, _score


# ── helpers ──────────────────────────────────────────────────────────────────

def test_entity_text_with_name():
    entity = {"id": "light.soggiorno", "name": "Luce Soggiorno", "state": "on", "unit": ""}
    assert _entity_text(entity) == "Luce Soggiorno [light soggiorno]"


def test_entity_text_without_name():
    entity = {"id": "light.soggiorno", "name": "", "state": "on", "unit": ""}
    assert _entity_text(entity) == "light soggiorno"


def test_tokenize_splits_on_special_chars():
    assert set(_tokenize("Luce Soggiorno [light soggiorno]")) == {
        "luce", "soggiorno", "light"
    }


def test_tokenize_normalises_to_lowercase():
    assert _tokenize("Living Room LIGHT") == ["living", "room", "light"]


def test_score_full_match():
    q = _tokenize("luce soggiorno")
    c = _tokenize("Luce Soggiorno [light soggiorno]")
    assert _score(q, c) > 0


def test_score_no_match():
    assert _score(_tokenize("xyz"), _tokenize("light cucina")) == 0.0


def test_score_empty_query():
    assert _score([], _tokenize("light a")) == 0.0


# ── EmbeddingIndex state ──────────────────────────────────────────────────────

def test_ready_false_before_build():
    assert not EmbeddingIndex().ready


def test_search_returns_empty_when_not_built():
    assert EmbeddingIndex().search("test") == []


# ── build ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_empty_entities_does_nothing():
    index = EmbeddingIndex()
    await index.build([])
    assert not index.ready


@pytest.mark.asyncio
async def test_build_indexes_entities():
    index = EmbeddingIndex()
    entities = [
        {"id": "light.soggiorno", "name": "Luce Soggiorno", "state": "on",  "unit": ""},
        {"id": "sensor.temp",     "name": "Temperatura",    "state": "21",  "unit": "°C"},
    ]
    await index.build(entities)
    assert index.ready
    assert index._entity_ids == ["light.soggiorno", "sensor.temp"]
    assert len(index._tokens) == 2


# ── search ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_best_match_first():
    index = EmbeddingIndex()
    entities = [
        {"id": "light.soggiorno", "name": "Luce Soggiorno", "state": "on",  "unit": ""},
        {"id": "light.cucina",    "name": "Luce Cucina",    "state": "off", "unit": ""},
        {"id": "sensor.temp",     "name": "Temperatura",    "state": "21",  "unit": "°C"},
    ]
    await index.build(entities)
    results = index.search("luce soggiorno", top_k=3)
    assert results[0] == "light.soggiorno"


@pytest.mark.asyncio
async def test_search_no_match_returns_empty():
    index = EmbeddingIndex()
    entities = [
        {"id": "light.soggiorno", "name": "Luce Soggiorno", "state": "on", "unit": ""},
    ]
    await index.build(entities)
    results = index.search("xyznomatch12345", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_top_k_limits_results():
    index = EmbeddingIndex()
    entities = [
        {"id": f"light.lamp{i}", "name": f"Lampada {i}", "state": "on", "unit": ""}
        for i in range(10)
    ]
    await index.build(entities)
    results = index.search("lampada", top_k=3)
    assert len(results) <= 3


# ── domain filter ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_domain_filter_excludes_other_domains():
    index = EmbeddingIndex()
    entities = [
        {"id": "light.a",     "name": "Luce A",    "state": "on",  "unit": ""},
        {"id": "light.b",     "name": "Luce B",    "state": "off", "unit": ""},
        {"id": "switch.luce", "name": "Switch",    "state": "off", "unit": ""},
    ]
    await index.build(entities)
    results = index.search("luce", top_k=10, domain_filter="light")
    assert "switch.luce" not in results
    assert all(eid.startswith("light.") for eid in results)


@pytest.mark.asyncio
async def test_search_domain_filter_empty_query_still_filters():
    index = EmbeddingIndex()
    entities = [
        {"id": "light.a",   "name": "Luce A",  "state": "on",  "unit": ""},
        {"id": "sensor.b",  "name": "Sensor B","state": "21",  "unit": ""},
    ]
    await index.build(entities)
    # Empty query returns all, but filter still applies
    results = index.search("", top_k=10, domain_filter="light")
    assert "sensor.b" not in results


# ── rebuild_entity ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rebuild_entity_updates_tokens():
    index = EmbeddingIndex()
    entities = [
        {"id": "light.x", "name": "Vecchio Nome", "state": "on", "unit": ""},
    ]
    await index.build(entities)
    index.rebuild_entity("light.x", "Nuovo Nome Cucina")
    results = index.search("cucina", top_k=5)
    assert "light.x" in results


@pytest.mark.asyncio
async def test_rebuild_entity_unknown_id_is_noop():
    index = EmbeddingIndex()
    await index.build([{"id": "light.a", "name": "A", "state": "on", "unit": ""}])
    # Should not raise
    index.rebuild_entity("light.unknown", "New Name")
    assert index.ready
