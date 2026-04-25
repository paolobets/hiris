# HIRIS Cycle 1 — Token Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce per-query Claude API token usage from ~67,771 to ~400–10,000 tokens by introducing an in-memory EntityCache, a semantic EmbeddingIndex, and a set of optimized tools.

**Architecture:** `EntityCache` holds all 606 HA entities in memory (loaded at startup, updated via WebSocket `state_changed` events) and serves data locally without HTTP calls. `EmbeddingIndex` (fastembed `intfloat/multilingual-e5-small`) provides semantic search in Italian/English to return only relevant entities per query. Five new tools replace the raw `get_entity_states([])` pattern, reducing average token cost by 85–99%.

**Tech Stack:** Python 3.11, aiohttp, fastembed ≥ 0.3.0, numpy ≥ 1.24.0, anthropic SDK 0.40

---

## File Map

**New files:**
- `hiris/app/proxy/entity_cache.py` — in-memory entity store with WebSocket updates
- `hiris/app/proxy/embedding_index.py` — semantic search via fastembed
- `tests/test_entity_cache.py` — EntityCache unit tests
- `tests/test_embedding_index.py` — EmbeddingIndex unit tests

**Modified files:**
- `hiris/requirements.txt` — add `fastembed>=0.3.0`, `numpy>=1.24.0`
- `hiris/app/tools/ha_tools.py` — add 4 new tools, update `get_entity_states`
- `hiris/app/claude_runner.py` — add `entity_cache`/`embedding_index` params, new tool defs and dispatch cases
- `hiris/app/server.py` — startup sequence: load cache, register listener, build index, pass to runner

---

## Task 1: Add dependencies

**Files:**
- Modify: `hiris/requirements.txt`

- [ ] **Step 1: Add fastembed and numpy to requirements.txt**

The current `hiris/requirements.txt` has 8 packages. Add these two lines:

```
fastembed>=0.3.0
numpy>=1.24.0
```

- [ ] **Step 2: Install and verify imports**

```bash
pip install "fastembed>=0.3.0" "numpy>=1.24.0"
python -c "import fastembed; import numpy; print('OK')"
```

Expected output: `OK` (fastembed may download model metadata on first import — this is normal)

- [ ] **Step 3: Commit**

```bash
git add hiris/requirements.txt
git commit -m "chore: add fastembed and numpy for semantic entity search"
```

---

## Task 2: EntityCache

**Files:**
- Create: `hiris/app/proxy/entity_cache.py`
- Create: `tests/test_entity_cache.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entity_cache.py`:

```python
import pytest
from unittest.mock import AsyncMock
from hiris.app.proxy.entity_cache import EntityCache, NOISE_DOMAINS


@pytest.mark.asyncio
async def test_load_calls_get_states_once():
    mock_ha = AsyncMock()
    mock_ha.get_states.return_value = []
    cache = EntityCache()
    await cache.load(mock_ha)
    mock_ha.get_states.assert_called_once_with([])


@pytest.mark.asyncio
async def test_load_builds_minimal_state():
    mock_ha = AsyncMock()
    mock_ha.get_states.return_value = [
        {
            "entity_id": "light.soggiorno",
            "state": "on",
            "attributes": {"friendly_name": "Luce Soggiorno", "unit_of_measurement": ""},
        },
        {
            "entity_id": "sensor.temp",
            "state": "21.5",
            "attributes": {"friendly_name": "Temperatura", "unit_of_measurement": "°C"},
        },
    ]
    cache = EntityCache()
    await cache.load(mock_ha)

    assert cache.get_minimal(["light.soggiorno"]) == [
        {"id": "light.soggiorno", "state": "on", "name": "Luce Soggiorno", "unit": ""}
    ]
    assert cache.get_minimal(["sensor.temp"]) == [
        {"id": "sensor.temp", "state": "21.5", "name": "Temperatura", "unit": "°C"}
    ]


def test_get_minimal_skips_missing_ids():
    cache = EntityCache()
    cache._states = {"light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""}}
    result = cache.get_minimal(["light.a", "light.missing"])
    assert len(result) == 1
    assert result[0]["id"] == "light.a"


def test_get_on_returns_only_on_state():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "light.b": {"id": "light.b", "state": "off", "name": "B", "unit": ""},
        "switch.c": {"id": "switch.c", "state": "on", "name": "C", "unit": ""},
    }
    result = cache.get_on()
    assert len(result) == 2
    assert all(e["state"] == "on" for e in result)
    assert {e["id"] for e in result} == {"light.a", "switch.c"}


def test_get_all_useful_excludes_noise_domains():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "button.b": {"id": "button.b", "state": "available", "name": "B", "unit": ""},
        "update.c": {"id": "update.c", "state": "on", "name": "C", "unit": ""},
        "select.d": {"id": "select.d", "state": "option1", "name": "D", "unit": ""},
        "sensor.e": {"id": "sensor.e", "state": "21", "name": "E", "unit": "°C"},
    }
    result = cache.get_all_useful()
    assert {e["id"] for e in result} == {"light.a", "sensor.e"}


def test_noise_domains_constant():
    assert NOISE_DOMAINS == {"button", "update", "number", "select", "tag",
                             "event", "ai_task", "todo", "conversation"}


def test_get_by_domain():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "light.b": {"id": "light.b", "state": "off", "name": "B", "unit": ""},
        "switch.c": {"id": "switch.c", "state": "on", "name": "C", "unit": ""},
    }
    cache._by_domain = {"light": ["light.a", "light.b"], "switch": ["switch.c"]}

    result = cache.get_by_domain("light")
    assert len(result) == 2
    assert all(e["id"].startswith("light.") for e in result)

    assert cache.get_by_domain("nonexistent") == []


def test_on_state_changed_updates_existing_entity():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "off", "name": "Luce", "unit": ""},
    }
    cache._by_domain = {"light": ["light.a"]}

    cache.on_state_changed({
        "new_state": {
            "entity_id": "light.a",
            "state": "on",
            "attributes": {"friendly_name": "Luce Aggiornata"},
        }
    })

    assert cache._states["light.a"]["state"] == "on"
    assert cache._states["light.a"]["name"] == "Luce Aggiornata"


def test_on_state_changed_adds_new_entity():
    cache = EntityCache()
    cache._states = {}
    cache._by_domain = {}

    cache.on_state_changed({
        "new_state": {
            "entity_id": "light.new",
            "state": "on",
            "attributes": {"friendly_name": "New Light"},
        }
    })

    assert "light.new" in cache._states
    assert cache._states["light.new"]["state"] == "on"
    assert "light.new" in cache._by_domain.get("light", [])


def test_on_state_changed_ignores_none_new_state():
    cache = EntityCache()
    cache._states = {}
    cache.on_state_changed({"new_state": None})
    assert cache._states == {}


def test_get_all_returns_all_states():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "button.b": {"id": "button.b", "state": "available", "name": "B", "unit": ""},
    }
    assert len(cache.get_all()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Work/Sviluppo/hiris
py -m pytest tests/test_entity_cache.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'hiris.app.proxy.entity_cache'`

- [ ] **Step 3: Implement EntityCache**

Create `hiris/app/proxy/entity_cache.py`:

```python
from __future__ import annotations

NOISE_DOMAINS = {"button", "update", "number", "select", "tag",
                 "event", "ai_task", "todo", "conversation"}


def _domain(entity_id: str) -> str:
    return entity_id.split(".")[0]


def _to_minimal(raw: dict) -> dict:
    attrs = raw.get("attributes", {})
    return {
        "id": raw["entity_id"],
        "state": raw.get("state", "unknown"),
        "name": attrs.get("friendly_name") or "",
        "unit": attrs.get("unit_of_measurement") or "",
    }


class EntityCache:
    def __init__(self) -> None:
        self._states: dict[str, dict] = {}
        self._by_domain: dict[str, list[str]] = {}

    async def load(self, ha_client) -> None:
        raw_states = await ha_client.get_states([])
        self._states = {}
        self._by_domain = {}
        for raw in raw_states:
            eid = raw["entity_id"]
            self._states[eid] = _to_minimal(raw)
            dom = _domain(eid)
            self._by_domain.setdefault(dom, []).append(eid)

    def on_state_changed(self, event_data: dict) -> None:
        new_state = event_data.get("new_state")
        if not new_state:
            return
        eid = new_state["entity_id"]
        minimal = _to_minimal(new_state)
        if eid not in self._states:
            dom = _domain(eid)
            self._by_domain.setdefault(dom, []).append(eid)
        self._states[eid] = minimal

    def get_minimal(self, entity_ids: list[str]) -> list[dict]:
        return [self._states[eid] for eid in entity_ids if eid in self._states]

    def get_by_domain(self, domain: str) -> list[dict]:
        ids = self._by_domain.get(domain, [])
        return self.get_minimal(ids)

    def get_on(self) -> list[dict]:
        return [e for e in self._states.values() if e["state"] == "on"]

    def get_all_useful(self) -> list[dict]:
        return [
            e for eid, e in self._states.items()
            if _domain(eid) not in NOISE_DOMAINS
        ]

    def get_all(self) -> list[dict]:
        return list(self._states.values())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
py -m pytest tests/test_entity_cache.py -v
```

Expected: All 11 tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/entity_cache.py tests/test_entity_cache.py
git commit -m "feat: EntityCache — in-memory HA entity store with WebSocket updates"
```

---

## Task 3: EmbeddingIndex

**Files:**
- Create: `hiris/app/proxy/embedding_index.py`
- Create: `tests/test_embedding_index.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_embedding_index.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
py -m pytest tests/test_embedding_index.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'hiris.app.proxy.embedding_index'`

- [ ] **Step 3: Implement EmbeddingIndex**

Create `hiris/app/proxy/embedding_index.py`:

```python
from __future__ import annotations
import asyncio
import logging
import numpy as np

logger = logging.getLogger(__name__)

_FASTEMBED_MODEL = "intfloat/multilingual-e5-small"
_FASTEMBED_CACHE_DIR = "/data/fastembed_cache"


def _entity_text(entity: dict) -> str:
    eid = entity["id"]
    name = (entity.get("name") or "").strip()
    domain, slug = eid.split(".", 1)
    slug_clean = slug.replace("_", " ")
    if name:
        return f"{name} [{domain} {slug_clean}]"
    return f"{domain} {slug_clean}"


class EmbeddingIndex:
    def __init__(self) -> None:
        self._model = None
        self._entity_ids: list[str] = []
        self._matrix: np.ndarray | None = None

    @property
    def ready(self) -> bool:
        return self._matrix is not None

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding  # type: ignore
            self._model = TextEmbedding(_FASTEMBED_MODEL, cache_dir=_FASTEMBED_CACHE_DIR)
        return self._model

    async def build(self, entities: list[dict]) -> None:
        if not entities:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._build_sync, entities)

    def _build_sync(self, entities: list[dict]) -> None:
        model = self._get_model()
        texts = [_entity_text(e) for e in entities]
        self._entity_ids = [e["id"] for e in entities]
        self._matrix = np.array(list(model.embed(texts)), dtype=np.float32)
        logger.info("EmbeddingIndex built: %d entities indexed", len(self._entity_ids))

    def search(self, query: str, top_k: int = 30,
               domain_filter: str | None = None) -> list[str]:
        if self._matrix is None or not self._entity_ids:
            return []
        model = self._get_model()
        q_vec = np.array(list(model.embed([query]))[0], dtype=np.float32)
        scores = self._matrix @ q_vec
        if domain_filter:
            for i, eid in enumerate(self._entity_ids):
                if not eid.startswith(domain_filter + "."):
                    scores[i] = -999.0
        n = min(top_k, len(self._entity_ids))
        idx = np.argsort(scores)[::-1][:n]
        return [self._entity_ids[i] for i in idx]

    def rebuild_entity(self, entity_id: str, friendly_name: str) -> None:
        if self._model is None or entity_id not in self._entity_ids:
            return
        i = self._entity_ids.index(entity_id)
        domain, slug = entity_id.split(".", 1)
        text = f"{friendly_name} [{domain} {slug.replace('_', ' ')}]"
        self._matrix[i] = np.array(list(self._model.embed([text]))[0], dtype=np.float32)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
py -m pytest tests/test_embedding_index.py -v
```

Expected: All 9 tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/embedding_index.py tests/test_embedding_index.py
git commit -m "feat: EmbeddingIndex — semantic entity search with fastembed multilingual-e5-small"
```

---

## Task 4: New tools in ha_tools.py

Current `hiris/app/tools/ha_tools.py` has two functions (`get_entity_states`, `get_area_entities`) that call HA via HTTP. This task adds 4 new cache-backed tools and updates `get_entity_states`.

**Files:**
- Modify: `hiris/app/tools/ha_tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Update the existing `get_entity_states` test to match new format**

In `tests/test_tools.py`, replace the existing `test_get_entity_states_returns_dict` test (lines 24-29):

```python
# BEFORE (lines 24-29):
@pytest.mark.asyncio
async def test_get_entity_states_returns_dict(mock_ha):
    result = await get_entity_states(mock_ha, ["light.living"])
    assert "light.living" in result
    assert result["light.living"]["state"] == "on"
    assert result["light.living"]["attributes"]["brightness"] == 200

# REPLACE WITH:
@pytest.mark.asyncio
async def test_get_entity_states_http_fallback_returns_minimal_list(mock_ha):
    result = await get_entity_states(mock_ha, ["light.living"])
    assert isinstance(result, list)
    assert result[0]["id"] == "light.living"
    assert result[0]["state"] == "on"
    mock_ha.get_states.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_entity_states_uses_cache_for_specific_ids():
    from unittest.mock import AsyncMock
    from hiris.app.proxy.entity_cache import EntityCache
    cache = EntityCache()
    cache._states = {
        "light.living": {"id": "light.living", "state": "on", "name": "Living Light", "unit": ""}
    }
    cache._by_domain = {"light": ["light.living"]}
    mock_ha = AsyncMock()
    result = await get_entity_states(mock_ha, ["light.living"], entity_cache=cache)
    assert result == [{"id": "light.living", "state": "on", "name": "Living Light", "unit": ""}]
    mock_ha.get_states.assert_not_called()


@pytest.mark.asyncio
async def test_get_entity_states_empty_ids_returns_useful_entities():
    from unittest.mock import AsyncMock
    from hiris.app.proxy.entity_cache import EntityCache
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "Light A", "unit": ""},
        "button.b": {"id": "button.b", "state": "available", "name": "Button", "unit": ""},
    }
    cache._by_domain = {"light": ["light.a"], "button": ["button.b"]}
    mock_ha = AsyncMock()
    result = await get_entity_states(mock_ha, [], entity_cache=cache)
    ids = {e["id"] for e in result}
    assert "light.a" in ids
    assert "button.b" not in ids  # noise domain excluded
    mock_ha.get_states.assert_not_called()
```

- [ ] **Step 2: Add tests for new tools at the end of `tests/test_tools.py`**

Append to `tests/test_tools.py`:

```python
# ── New cache-backed tool tests ───────────────────────────────────────────

from hiris.app.proxy.entity_cache import EntityCache
from hiris.app.proxy.embedding_index import EmbeddingIndex
from hiris.app.tools.ha_tools import (
    get_home_status,
    get_entities_on,
    search_entities,
    get_entities_by_domain,
)
import numpy as np
from unittest.mock import MagicMock


def _make_cache(*specs):
    """Create EntityCache from (id, state, name) tuples."""
    cache = EntityCache()
    cache._states = {
        eid: {"id": eid, "state": state, "name": name, "unit": ""}
        for eid, state, name in specs
    }
    cache._by_domain = {}
    for eid in cache._states:
        dom = eid.split(".")[0]
        cache._by_domain.setdefault(dom, []).append(eid)
    return cache


@pytest.mark.asyncio
async def test_get_home_status_excludes_noise():
    cache = _make_cache(
        ("light.soggiorno", "on", "Luce"),
        ("button.test", "available", "Button"),
        ("sensor.temp", "21", "Temp"),
    )
    result = await get_home_status(cache)
    ids = {e["id"] for e in result}
    assert "light.soggiorno" in ids
    assert "sensor.temp" in ids
    assert "button.test" not in ids


@pytest.mark.asyncio
async def test_get_entities_on_returns_only_on():
    cache = _make_cache(
        ("light.a", "on", "Light A"),
        ("light.b", "off", "Light B"),
        ("switch.c", "on", "Switch C"),
    )
    result = await get_entities_on(cache)
    assert all(e["state"] == "on" for e in result)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_search_entities_with_ready_index():
    cache = _make_cache(
        ("light.soggiorno", "on", "Luce Soggiorno"),
        ("sensor.temp", "21", "Temperatura"),
    )
    index = EmbeddingIndex()
    index._entity_ids = ["light.soggiorno", "sensor.temp"]
    emb = np.zeros((2, 384), dtype=np.float32)
    emb[0, 0] = 1.0
    emb[1, 1] = 1.0
    index._matrix = emb
    q_vec = np.zeros(384, dtype=np.float32)
    q_vec[0] = 1.0
    mock_model = MagicMock()
    mock_model.embed.return_value = iter([q_vec])
    index._model = mock_model

    result = await search_entities("luce soggiorno", cache, index, top_k=1)
    assert len(result) == 1
    assert result[0]["id"] == "light.soggiorno"


@pytest.mark.asyncio
async def test_search_entities_fallback_when_index_not_ready():
    cache = _make_cache(
        ("light.a", "on", "Light A"),
        ("sensor.b", "21", "Sensor B"),
    )
    index = EmbeddingIndex()  # not built
    result = await search_entities("test", cache, index, top_k=10)
    assert len(result) == 2  # fallback: all useful entities


@pytest.mark.asyncio
async def test_get_entities_by_domain():
    cache = _make_cache(
        ("light.a", "on", "Light A"),
        ("light.b", "off", "Light B"),
        ("switch.c", "on", "Switch C"),
    )
    result = await get_entities_by_domain("light", cache)
    assert len(result) == 2
    assert all(e["id"].startswith("light.") for e in result)
```

- [ ] **Step 3: Run tests to verify existing test now fails and new tests fail**

```bash
py -m pytest tests/test_tools.py -v 2>&1 | head -40
```

Expected: `test_get_entity_states_returns_dict` → **PASS** (still exists until you replace it), but `get_home_status`, `get_entities_on`, `search_entities`, `get_entities_by_domain` → **ERROR** (not yet defined)

- [ ] **Step 4: Rewrite `hiris/app/tools/ha_tools.py` entirely**

Replace the full file content with:

```python
from typing import Any
from ..proxy.ha_client import HAClient

# ── Tool definitions ──────────────────────────────────────────────────────

TOOL_DEF = {
    "name": "get_entity_states",
    "description": (
        "Get current states of specific Home Assistant entities by ID. "
        "Pass an empty list [] to get all useful entities (noise-filtered, compact format). "
        "Prefer search_entities() when you don't know the exact entity IDs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of entity IDs to query. Pass [] to get all useful entities.",
                "default": [],
            }
        },
        "required": [],
    },
}

GET_AREA_ENTITIES_TOOL_DEF = {
    "name": "get_area_entities",
    "description": (
        "Discover all Home Assistant areas (rooms/zones) and their assigned entities. "
        "Returns a dict mapping area_name -> [entity_ids]. "
        "Entities without an area are listed under '__no_area__'. "
        "Use this when the user refers to a room (e.g. 'kitchen lights', "
        "'turn off everything in the living room')."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

GET_HOME_STATUS_TOOL_DEF = {
    "name": "get_home_status",
    "description": (
        "Get all useful home entities in compact format (~10,000 tokens). "
        "Excludes noise domains (button, update, number, select, tag). "
        "Use for general queries about the state of the whole home."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

GET_ENTITIES_ON_TOOL_DEF = {
    "name": "get_entities_on",
    "description": (
        "Get only entities currently ON (~53 entities, ~1,300 tokens). "
        "Use to answer 'cosa ho acceso?', 'what is active?', 'what is on?'."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

SEARCH_ENTITIES_TOOL_DEF = {
    "name": "search_entities",
    "description": (
        "Find relevant Home Assistant entities by natural language query (~400 tokens). "
        "Use when you don't know exact entity IDs. "
        "Examples: search_entities('consumi cucina'), search_entities('temperatura camera'), "
        "search_entities('cosa è acceso in soggiorno'). "
        "Supports Italian and English."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What you are looking for in natural language",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results (default: 20)",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}

GET_ENTITIES_BY_DOMAIN_TOOL_DEF = {
    "name": "get_entities_by_domain",
    "description": (
        "Get all entities of a specific HA domain in compact format. "
        "Useful domains: light, switch, sensor, climate, binary_sensor, cover, media_player, automation. "
        "Example: get_entities_by_domain('light') → all lights."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "HA domain (e.g. light, switch, sensor, climate)",
            }
        },
        "required": ["domain"],
    },
}


# ── Tool implementations ──────────────────────────────────────────────────

async def get_entity_states(
    ha: HAClient,
    ids: list[str],
    entity_cache=None,
) -> list[dict]:
    if entity_cache is not None:
        if not ids:
            return entity_cache.get_all_useful()
        return entity_cache.get_minimal(ids)
    # HTTP fallback (no cache — e.g. during startup race)
    states = await ha.get_states(ids)
    return [
        {
            "id": s["entity_id"],
            "state": s.get("state", "unknown"),
            "name": s.get("attributes", {}).get("friendly_name") or "",
            "unit": s.get("attributes", {}).get("unit_of_measurement") or "",
        }
        for s in states
    ]


async def get_area_entities(ha: HAClient) -> dict[str, list[str]]:
    areas = await ha.get_area_registry()
    entities = await ha.get_entity_registry()

    area_lookup: dict[str, str] = {a["area_id"]: a["name"] for a in areas}
    result: dict[str, list[str]] = {}
    no_area: list[str] = []

    for entry in entities:
        eid = entry.get("entity_id", "")
        if not eid:
            continue
        area_id = entry.get("area_id")
        if area_id and area_id in area_lookup:
            result.setdefault(area_lookup[area_id], []).append(eid)
        else:
            no_area.append(eid)

    if no_area:
        result["__no_area__"] = no_area

    return result


async def get_home_status(entity_cache) -> list[dict]:
    return entity_cache.get_all_useful()


async def get_entities_on(entity_cache) -> list[dict]:
    return entity_cache.get_on()


async def search_entities(
    query: str,
    entity_cache,
    embedding_index,
    top_k: int = 20,
) -> list[dict]:
    if embedding_index is not None and embedding_index.ready:
        ids = embedding_index.search(query, top_k=top_k)
        return entity_cache.get_minimal(ids)
    return entity_cache.get_all_useful()[:top_k]


async def get_entities_by_domain(domain: str, entity_cache) -> list[dict]:
    return entity_cache.get_by_domain(domain)
```

- [ ] **Step 5: Run all tool tests to verify they pass**

```bash
py -m pytest tests/test_tools.py -v
```

Expected: All tests **PASS**

- [ ] **Step 6: Commit**

```bash
git add hiris/app/tools/ha_tools.py tests/test_tools.py
git commit -m "feat: add get_home_status, get_entities_on, search_entities, get_entities_by_domain tools; update get_entity_states to use EntityCache"
```

---

## Task 5: ClaudeRunner — integrate cache/index and dispatch new tools

Current `hiris/app/claude_runner.py` `__init__` takes `(api_key, ha_client, notify_config, restrict_to_home, usage_path)`. This task adds optional `entity_cache` and `embedding_index` parameters, registers 4 new tool definitions, and adds dispatch cases.

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_claude_runner.py`:

```python
# ── New tool dispatch tests ───────────────────────────────────────────────

import numpy as np
from unittest.mock import MagicMock
from hiris.app.proxy.entity_cache import EntityCache
from hiris.app.proxy.embedding_index import EmbeddingIndex


def _make_runner_cache():
    cache = EntityCache()
    cache._states = {
        "light.soggiorno": {"id": "light.soggiorno", "state": "on", "name": "Luce Soggiorno", "unit": ""},
        "sensor.temp": {"id": "sensor.temp", "state": "21", "name": "Temperatura", "unit": "°C"},
        "button.test": {"id": "button.test", "state": "available", "name": "Button", "unit": ""},
        "switch.boiler": {"id": "switch.boiler", "state": "off", "name": "Boiler", "unit": ""},
    }
    cache._by_domain = {
        "light": ["light.soggiorno"],
        "sensor": ["sensor.temp"],
        "button": ["button.test"],
        "switch": ["switch.boiler"],
    }
    return cache


@pytest.mark.asyncio
async def test_dispatch_get_home_status():
    mock_ha = AsyncMock()
    cache = _make_runner_cache()
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner("key", mock_ha, {}, entity_cache=cache)
    result = await r._dispatch_tool("get_home_status", {}, None, None)
    ids = {e["id"] for e in result}
    assert "light.soggiorno" in ids
    assert "button.test" not in ids  # noise excluded


@pytest.mark.asyncio
async def test_dispatch_get_entities_on():
    mock_ha = AsyncMock()
    cache = _make_runner_cache()
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner("key", mock_ha, {}, entity_cache=cache)
    result = await r._dispatch_tool("get_entities_on", {}, None, None)
    assert all(e["state"] == "on" for e in result)
    assert any(e["id"] == "light.soggiorno" for e in result)


@pytest.mark.asyncio
async def test_dispatch_get_entities_by_domain():
    mock_ha = AsyncMock()
    cache = _make_runner_cache()
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner("key", mock_ha, {}, entity_cache=cache)
    result = await r._dispatch_tool("get_entities_by_domain", {"domain": "light"}, None, None)
    assert all(e["id"].startswith("light.") for e in result)


@pytest.mark.asyncio
async def test_dispatch_search_entities_with_index():
    mock_ha = AsyncMock()
    cache = _make_runner_cache()
    index = EmbeddingIndex()
    index._entity_ids = ["light.soggiorno", "sensor.temp", "switch.boiler"]
    emb = np.zeros((3, 384), dtype=np.float32)
    emb[0, 0] = 1.0
    emb[1, 1] = 1.0
    emb[2, 2] = 1.0
    index._matrix = emb
    q_vec = np.zeros(384, dtype=np.float32)
    q_vec[0] = 1.0
    mock_model = MagicMock()
    mock_model.embed.return_value = iter([q_vec])
    index._model = mock_model
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner("key", mock_ha, {}, entity_cache=cache, embedding_index=index)
    result = await r._dispatch_tool("search_entities", {"query": "luce", "top_k": 1}, None, None)
    assert len(result) == 1
    assert result[0]["id"] == "light.soggiorno"


@pytest.mark.asyncio
async def test_dispatch_get_entity_states_uses_cache():
    mock_ha = AsyncMock()
    cache = _make_runner_cache()
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner("key", mock_ha, {}, entity_cache=cache)
    result = await r._dispatch_tool("get_entity_states", {"ids": ["light.soggiorno"]}, None, None)
    assert isinstance(result, list)
    assert result[0]["id"] == "light.soggiorno"
    mock_ha.get_states.assert_not_called()


def test_new_tool_defs_in_all_tool_defs():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    names = {t["name"] for t in ALL_TOOL_DEFS}
    assert "get_home_status" in names
    assert "get_entities_on" in names
    assert "search_entities" in names
    assert "get_entities_by_domain" in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
py -m pytest tests/test_claude_runner.py -k "dispatch_get_home_status or dispatch_get_entities or dispatch_search or new_tool_defs" -v 2>&1 | head -30
```

Expected: `TypeError` — `ClaudeRunner.__init__` doesn't accept `entity_cache`/`embedding_index` yet

- [ ] **Step 3: Update `ClaudeRunner.__init__` in `hiris/app/claude_runner.py`**

Find the `__init__` signature at line 59–66 and replace it:

```python
# BEFORE:
def __init__(
    self,
    api_key: str,
    ha_client: HAClient,
    notify_config: dict,
    restrict_to_home: bool = False,
    usage_path: str = "",
) -> None:

# AFTER:
def __init__(
    self,
    api_key: str,
    ha_client: HAClient,
    notify_config: dict,
    restrict_to_home: bool = False,
    usage_path: str = "",
    entity_cache=None,
    embedding_index=None,
) -> None:
```

Then add two lines at the end of the `__init__` body (after `self._load_usage()`):

```python
        self._cache = entity_cache
        self._index = embedding_index
```

- [ ] **Step 4: Update imports in `hiris/app/claude_runner.py`**

Replace line 9 (the `ha_tools` import):

```python
# BEFORE:
from .tools.ha_tools import get_entity_states, TOOL_DEF as HA_TOOL, get_area_entities, GET_AREA_ENTITIES_TOOL_DEF

# AFTER:
from .tools.ha_tools import (
    get_entity_states, TOOL_DEF as HA_TOOL,
    get_area_entities, GET_AREA_ENTITIES_TOOL_DEF,
    get_home_status, GET_HOME_STATUS_TOOL_DEF,
    get_entities_on, GET_ENTITIES_ON_TOOL_DEF,
    search_entities, SEARCH_ENTITIES_TOOL_DEF,
    get_entities_by_domain, GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
)
```

- [ ] **Step 5: Update `ALL_TOOL_DEFS` in `hiris/app/claude_runner.py`**

Find `ALL_TOOL_DEFS` at lines 35–45 and replace:

```python
# BEFORE:
ALL_TOOL_DEFS = [
    HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    ENERGY_TOOL,
    WEATHER_TOOL,
    NOTIFY_TOOL,
    GET_AUTOMATIONS_TOOL_DEF,
    TRIGGER_TOOL_DEF,
    TOGGLE_TOOL_DEF,
    CALL_SERVICE_TOOL_DEF,
]

# AFTER:
ALL_TOOL_DEFS = [
    HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    SEARCH_ENTITIES_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
    ENERGY_TOOL,
    WEATHER_TOOL,
    NOTIFY_TOOL,
    GET_AUTOMATIONS_TOOL_DEF,
    TRIGGER_TOOL_DEF,
    TOGGLE_TOOL_DEF,
    CALL_SERVICE_TOOL_DEF,
]
```

- [ ] **Step 6: Update `get_entity_states` dispatch and add new dispatch cases in `_dispatch_tool`**

In `_dispatch_tool`, find the `get_entity_states` block at lines 192–197 and replace it. Then add four new `if` blocks immediately after:

```python
# BEFORE (lines 192-197):
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if allowed_entities:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                    logger.info("Filtered entity ids to: %s", ids)
                return await get_entity_states(self._ha, ids)

# AFTER:
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if allowed_entities and ids:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                    logger.info("Filtered entity ids to: %s", ids)
                return await get_entity_states(self._ha, ids, entity_cache=self._cache)
            if name == "get_home_status":
                if self._cache is None:
                    return {"error": "Entity cache not initialized"}
                return await get_home_status(self._cache)
            if name == "get_entities_on":
                if self._cache is None:
                    return {"error": "Entity cache not initialized"}
                return await get_entities_on(self._cache)
            if name == "search_entities":
                if self._cache is None:
                    return {"error": "Entity cache not initialized"}
                return await search_entities(
                    inputs.get("query", ""),
                    self._cache,
                    self._index,
                    inputs.get("top_k", 20),
                )
            if name == "get_entities_by_domain":
                if self._cache is None:
                    return {"error": "Entity cache not initialized"}
                return await get_entities_by_domain(inputs.get("domain", ""), self._cache)
```

- [ ] **Step 7: Run all ClaudeRunner tests**

```bash
py -m pytest tests/test_claude_runner.py -v
```

Expected: All tests **PASS**

- [ ] **Step 8: Run full test suite**

```bash
py -m pytest tests/ -v
```

Expected: All tests **PASS**

- [ ] **Step 9: Commit**

```bash
git add hiris/app/claude_runner.py tests/test_claude_runner.py
git commit -m "feat: ClaudeRunner — integrate EntityCache/EmbeddingIndex, add 4 new tool dispatchers"
```

---

## Task 6: Server startup integration

Wire `EntityCache` and `EmbeddingIndex` into the server startup sequence.

The current `_on_startup` in `hiris/app/server.py`:
1. Calls `await ha_client.start()` (HTTP session only)
2. Creates `AgentEngine` and calls `await engine.start()` — this is where `add_state_listener()` and `start_websocket()` happen (see `agent_engine.py` lines 48-49)
3. Creates `ClaudeRunner`

The EntityCache listener must be registered **before** `engine.start()` so it receives events from the WebSocket that starts there.

**Files:**
- Modify: `hiris/app/server.py`

- [ ] **Step 1: Add imports at top of `hiris/app/server.py`**

After the existing imports (after line 10), add:

```python
import asyncio
from .proxy.entity_cache import EntityCache
from .proxy.embedding_index import EmbeddingIndex
```

- [ ] **Step 2: Update `_on_startup` to load EntityCache before engine start**

In `_on_startup`, replace lines 20–26 (from `await ha_client.start()` through `app["engine"] = engine`):

```python
# BEFORE:
    await ha_client.start()
    app["ha_client"] = ha_client

    data_path = os.environ.get("AGENTS_DATA_PATH", "/data/agents.json")
    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
    await engine.start()
    app["engine"] = engine

# AFTER:
    await ha_client.start()
    app["ha_client"] = ha_client

    entity_cache = EntityCache()
    await entity_cache.load(ha_client)
    ha_client.add_state_listener(entity_cache.on_state_changed)
    app["entity_cache"] = entity_cache

    data_path = os.environ.get("AGENTS_DATA_PATH", "/data/agents.json")
    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
    await engine.start()
    app["engine"] = engine

    embedding_index = EmbeddingIndex()
    asyncio.create_task(embedding_index.build(entity_cache.get_all_useful()))
    app["embedding_index"] = embedding_index
```

- [ ] **Step 3: Pass cache and index to `ClaudeRunner`**

Find the `ClaudeRunner(...)` instantiation at lines 40–46 and add two new keyword arguments:

```python
# BEFORE:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            restrict_to_home=restrict_to_home,
            usage_path=usage_path,
        )

# AFTER:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            restrict_to_home=restrict_to_home,
            usage_path=usage_path,
            entity_cache=entity_cache,
            embedding_index=embedding_index,
        )
```

- [ ] **Step 4: Run the full test suite**

```bash
py -m pytest tests/ -v
```

Expected: All tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add hiris/app/server.py
git commit -m "feat: wire EntityCache and EmbeddingIndex into server startup sequence"
```

---

## Task 7: Version bump to 0.0.9

Per project convention, version must be bumped before every push.

**Files:**
- Modify: `hiris/app/server.py` (line 100: `"version": "0.0.8"`)
- Modify: `hiris/config.yaml`
- Modify: `tests/test_api.py` (version assertion)

- [ ] **Step 1: Bump version in `hiris/app/server.py`**

Find line 100:
```python
    return web.json_response({"status": "ok", "version": "0.0.8"})
```
Change to:
```python
    return web.json_response({"status": "ok", "version": "0.0.9"})
```

- [ ] **Step 2: Bump version in `hiris/config.yaml`**

Find the `version:` field and update it to `"0.0.9"`.

- [ ] **Step 3: Update version assertion in `tests/test_api.py`**

Search for `"0.0.8"` in `tests/test_api.py` and replace with `"0.0.9"`.

```bash
grep -n "0.0.8" tests/test_api.py
```

Replace the found line(s).

- [ ] **Step 4: Run full test suite**

```bash
py -m pytest tests/ -v
```

Expected: All tests **PASS**

- [ ] **Step 5: Final commit**

```bash
git add hiris/app/server.py hiris/config.yaml tests/test_api.py
git commit -m "chore: bump version to 0.0.9"
```

---

## UAT Checklist (after deploying to HA)

After deploying the add-on, check the following in the HIRIS UI:

1. - [ ] Server log on startup shows `EmbeddingIndex built: N entities indexed` within ~5 seconds
2. - [ ] Chat: *"Cosa ho acceso?"* → usage widget shows **~1,300 tokens** (not 67,771)
3. - [ ] Chat: *"Luci del soggiorno"* → usage widget shows **~400 tokens**
4. - [ ] Chat: *"Consumi solare"* → usage widget shows **~1,355 tokens**
5. - [ ] Chat: *"Stato casa generale"* → usage widget shows **~10,000 tokens**
6. - [ ] Send 10 messages in quick succession → **no rate limit error**
7. - [ ] Restart the add-on → EntityCache reloads and EmbeddingIndex rebuilds cleanly

---

## Self-Review

**Spec coverage (§ references to `2026-04-20-hiris-optimization-design.md`):**

| Spec requirement | Covered by |
|---|---|
| §1.1 EntityCache load + state_changed callback | Task 2 |
| §1.1 Minimal format `{id, state, name, unit}` | Task 2 (`_to_minimal`) |
| §1.1 `get_all_useful()` excludes noise domains | Task 2 (`NOISE_DOMAINS`) |
| §1.2 EmbeddingIndex with multilingual-e5-small | Task 3 |
| §1.2 `search()` top_k + domain_filter | Task 3 |
| §1.3 `get_home_status` tool | Task 4 |
| §1.3 `get_entities_on` tool | Task 4 |
| §1.3 `search_entities` tool | Task 4 |
| §1.3 `get_entities_by_domain` tool | Task 4 |
| §1.3 `get_entity_states([])` redirects to home_status | Task 4 (`get_entity_states` with empty ids) |
| §1.4 Startup sequence order | Task 6 |
| §1.4 EmbeddingIndex built as background task | Task 6 (`asyncio.create_task`) |
| §1.4 Fallback to home_status while index builds | `search_entities` fallback in Task 4 |
| §1.5 fastembed + numpy in requirements.txt | Task 1 |
| §1.5 Cache dir `/data/fastembed_cache` | Task 3 (`_FASTEMBED_CACHE_DIR`) |

**Gaps and decisions:**
- `EmbeddingIndex.rebuild_entity()` is implemented but not called from the startup WebSocket listener. The index stays in sync via server restarts. Wiring per-event rebuild is left for a follow-up (it requires passing the index into the state-changed callback chain).
- `get_area_entities` is preserved unchanged — it still calls HA HTTP. No new cache-backed area tool is needed in Cycle 1.

**Placeholder scan:** No `TBD`, `TODO`, or incomplete steps found.

**Type consistency:**
- All new tool functions accept `entity_cache` and/or `embedding_index` as positional or keyword args — signatures match across Tasks 4 and 5.
- `get_entity_states` returns `list[dict]` in both code paths (cache and HTTP fallback).
- `ClaudeRunner._cache` and `ClaudeRunner._index` are set in `__init__` and used in `_dispatch_tool` — consistent throughout.
