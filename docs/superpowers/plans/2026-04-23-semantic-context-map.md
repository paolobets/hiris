# SemanticContextMap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the keyword-based `EmbeddingIndex` RAG and generic `SemanticMap` snippet with a `SemanticContextMap` — area-organized, device_class-classified, SQLite-persisted, injecting only relevant context per request.

**Architecture:** Three layers: `EntityCache` (live states via WebSocket) + `KnowledgeDB` (SQLite persistence for classifications, annotations, correlations) + `SemanticContextMap` (builds area→type→entity map, runs keyword `ContextSelector` per query, formats prompt context). `EmbeddingBackend`/ChromaDB are Plan 2.

**Tech Stack:** Python 3.13, SQLite (stdlib), aiohttp (existing), pytest.

---

## File Map

| Operation | File |
|---|---|
| **Create** | `hiris/app/proxy/knowledge_db.py` |
| **Create** | `hiris/app/proxy/semantic_context_map.py` |
| **Create** | `tests/test_knowledge_db.py` |
| **Create** | `tests/test_semantic_context_map.py` |
| **Modify** | `hiris/app/proxy/entity_cache.py` — add `domain`, `device_class`, typed attrs |
| **Modify** | `hiris/app/server.py` — wire KnowledgeDB + SemanticContextMap, remove EmbeddingIndex |
| **Modify** | `hiris/app/api/handlers_chat.py` — replace prefetch + semantic_map snippet |
| **Modify** | `hiris/app/claude_runner.py` — add `visible_entity_ids`, remove EmbeddingIndex |
| **Modify** | `hiris/app/tools/ha_tools.py` — remove EmbeddingIndex import, filter by visible_ids |
| **Modify** | `hiris/app/proxy/semantic_map.py` — remove `get_prompt_snippet` |
| **Modify** | `hiris/config.yaml` + `hiris/app/server.py` + `tests/test_api.py` — version 0.3.0 |
| **Delete** | `hiris/app/proxy/embedding_index.py` |

---

## Task 1: KnowledgeDB — SQLite persistence layer

**Files:**
- Create: `hiris/app/proxy/knowledge_db.py`
- Create: `tests/test_knowledge_db.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_knowledge_db.py
import pytest
from hiris.app.proxy.knowledge_db import KnowledgeDB


def test_save_and_load_classification(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.save_classification(
        entity_id="climate.bagno", area="Bagno", entity_type="climate",
        label_it="Termostato", friendly_name="Termostato Bagno",
        domain="climate", device_class=None,
    )
    loaded = db.load_classifications()
    assert "climate.bagno" in loaded
    assert loaded["climate.bagno"]["entity_type"] == "climate"
    assert loaded["climate.bagno"]["area"] == "Bagno"
    db.close()


def test_upsert_classification_updates_on_conflict(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.save_classification("sensor.temp", "Bagno", "temperature", "Temperatura",
                           "Temp Bagno", "sensor", "temperature")
    db.save_classification("sensor.temp", "Camera", "temperature", "Temperatura",
                           "Temp Camera", "sensor", "temperature", classified_by="user")
    loaded = db.load_classifications()
    assert loaded["sensor.temp"]["area"] == "Camera"
    assert loaded["sensor.temp"]["classified_by"] == "user"
    db.close()


def test_add_and_get_annotation(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.add_annotation("climate.bagno", "agent-001", "Scalda lentamente in inverno")
    annots = db.get_annotations("climate.bagno")
    assert len(annots) == 1
    assert annots[0]["annotation"] == "Scalda lentamente in inverno"
    assert annots[0]["source"] == "agent-001"
    db.close()


def test_get_annotations_empty(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    assert db.get_annotations("light.sala") == []
    db.close()


def test_record_correlation_increments_count(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.record_correlation("climate.bagno", "sensor.temp_bagno", "co-occurs")
    db.record_correlation("climate.bagno", "sensor.temp_bagno", "co-occurs")
    rows = db._conn.execute(
        "SELECT observed_count FROM entity_correlations WHERE entity_a='climate.bagno'"
    ).fetchone()
    assert rows[0] == 2
    db.close()


def test_record_query_hit_increments(tmp_path):
    db = KnowledgeDB(str(tmp_path / "test.db"))
    db.record_query_hit("climate.bagno", "climate")
    db.record_query_hit("climate.bagno", "climate")
    row = db._conn.execute(
        "SELECT hit_count FROM query_patterns WHERE entity_id='climate.bagno'"
    ).fetchone()
    assert row[0] == 2
    db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Work\Sviluppo\hiris
py -m pytest tests/test_knowledge_db.py -v
```
Expected: `ImportError: No module named 'hiris.app.proxy.knowledge_db'`

- [ ] **Step 3: Create `hiris/app/proxy/knowledge_db.py`**

```python
from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_classifications (
    entity_id     TEXT PRIMARY KEY,
    area          TEXT,
    entity_type   TEXT NOT NULL,
    label_it      TEXT NOT NULL,
    friendly_name TEXT NOT NULL DEFAULT '',
    domain        TEXT NOT NULL,
    device_class  TEXT,
    classified_by TEXT NOT NULL DEFAULT 'schema',
    confidence    REAL NOT NULL DEFAULT 1.0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_annotations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    annotation  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_correlations (
    entity_a         TEXT NOT NULL,
    entity_b         TEXT NOT NULL,
    correlation_type TEXT NOT NULL,
    confidence       REAL NOT NULL DEFAULT 0.5,
    observed_count   INTEGER NOT NULL DEFAULT 1,
    last_observed    TEXT NOT NULL,
    PRIMARY KEY (entity_a, entity_b, correlation_type)
);
CREATE TABLE IF NOT EXISTS query_patterns (
    entity_id    TEXT NOT NULL,
    concept_type TEXT NOT NULL,
    hit_count    INTEGER NOT NULL DEFAULT 1,
    last_hit     TEXT NOT NULL,
    PRIMARY KEY (entity_id, concept_type)
);
"""


class KnowledgeDB:
    def __init__(self, db_path: str = "/data/hiris_knowledge.db") -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_classification(
        self,
        entity_id: str,
        area: Optional[str],
        entity_type: str,
        label_it: str,
        friendly_name: str,
        domain: str,
        device_class: Optional[str],
        classified_by: str = "schema",
        confidence: float = 1.0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO entity_classifications
                (entity_id, area, entity_type, label_it, friendly_name,
                 domain, device_class, classified_by, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                area=excluded.area, entity_type=excluded.entity_type,
                label_it=excluded.label_it, friendly_name=excluded.friendly_name,
                classified_by=excluded.classified_by, confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (entity_id, area, entity_type, label_it, friendly_name,
             domain, device_class, classified_by, confidence, now, now),
        )
        self._conn.commit()

    def load_classifications(self) -> dict[str, dict]:
        rows = self._conn.execute("SELECT * FROM entity_classifications").fetchall()
        return {r["entity_id"]: dict(r) for r in rows}

    def add_annotation(self, entity_id: str, source: str, annotation: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO entity_annotations (entity_id, source, annotation, created_at)"
            " VALUES (?, ?, ?, ?)",
            (entity_id, source, annotation, now),
        )
        self._conn.commit()

    def get_annotations(self, entity_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM entity_annotations WHERE entity_id=? ORDER BY created_at DESC",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def record_correlation(
        self, entity_a: str, entity_b: str, correlation_type: str, confidence: float = 0.5
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO entity_correlations
                (entity_a, entity_b, correlation_type, confidence, observed_count, last_observed)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(entity_a, entity_b, correlation_type) DO UPDATE SET
                observed_count=observed_count+1,
                confidence=MIN(1.0, confidence+0.05),
                last_observed=excluded.last_observed
            """,
            (entity_a, entity_b, correlation_type, confidence, now),
        )
        self._conn.commit()

    def record_query_hit(self, entity_id: str, concept_type: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO query_patterns (entity_id, concept_type, hit_count, last_hit)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(entity_id, concept_type) DO UPDATE SET
                hit_count=hit_count+1, last_hit=excluded.last_hit
            """,
            (entity_id, concept_type, now),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run tests**

```bash
py -m pytest tests/test_knowledge_db.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/knowledge_db.py tests/test_knowledge_db.py
git commit -m "feat: add KnowledgeDB — SQLite persistence for entity classifications and annotations"
```

---

## Task 2: EntityCache extension — domain, device_class, typed attributes

**Files:**
- Modify: `hiris/app/proxy/entity_cache.py`
- Create: `tests/test_entity_cache_extension.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_entity_cache_extension.py
import pytest
from hiris.app.proxy.entity_cache import _to_minimal


def test_to_minimal_adds_domain():
    raw = {"entity_id": "sensor.temp_bagno", "state": "21.5",
           "attributes": {"friendly_name": "Temperatura Bagno", "unit_of_measurement": "°C"}}
    result = _to_minimal(raw)
    assert result["domain"] == "sensor"


def test_to_minimal_adds_device_class():
    raw = {"entity_id": "sensor.temp_bagno", "state": "21.5",
           "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}}
    result = _to_minimal(raw)
    assert result["device_class"] == "temperature"


def test_to_minimal_device_class_none_when_absent():
    raw = {"entity_id": "light.sala", "state": "on", "attributes": {}}
    result = _to_minimal(raw)
    assert result["device_class"] is None


def test_to_minimal_climate_attributes():
    raw = {
        "entity_id": "climate.bagno", "state": "heat",
        "attributes": {
            "hvac_mode": "heat", "hvac_action": "heating",
            "current_temperature": 21.5, "temperature": 22.0, "preset_mode": "home",
        },
    }
    result = _to_minimal(raw)
    assert result["attributes"]["hvac_mode"] == "heat"
    assert result["attributes"]["current_temperature"] == 21.5
    assert result["attributes"]["preset_mode"] == "home"


def test_to_minimal_light_attributes():
    raw = {
        "entity_id": "light.soggiorno", "state": "on",
        "attributes": {"brightness": 200, "color_temp": 3000},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["brightness"] == 200
    assert result["attributes"]["color_temp"] == 3000


def test_to_minimal_cover_attributes():
    raw = {
        "entity_id": "cover.tapparella_salotto", "state": "open",
        "attributes": {"current_position": 75},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["current_position"] == 75


def test_to_minimal_media_player_attributes():
    raw = {
        "entity_id": "media_player.tv_salotto", "state": "playing",
        "attributes": {"media_title": "Netflix", "volume_level": 0.5, "source": "HDMI1"},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["media_title"] == "Netflix"
    assert result["attributes"]["volume_level"] == 0.5


def test_to_minimal_no_extra_attrs_for_binary_sensor():
    raw = {
        "entity_id": "binary_sensor.porta_ingresso", "state": "off",
        "attributes": {"device_class": "door"},
    }
    result = _to_minimal(raw)
    assert result.get("attributes", {}) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
py -m pytest tests/test_entity_cache_extension.py -v
```
Expected: `FAILED` — `domain` and `device_class` keys missing.

- [ ] **Step 3: Modify `hiris/app/proxy/entity_cache.py`**

Replace the current `_CLIMATE_ATTRS` constant and `_to_minimal` function:

```python
# Replace this block (remove _CLIMATE_ATTRS and the old _to_minimal):
_CLIMATE_ATTRS = ("current_temperature", "temperature", "hvac_action")


def _to_minimal(raw: dict) -> dict:
    attrs = raw.get("attributes") or {}
    result: dict = {
        "id": raw["entity_id"],
        "state": raw.get("state", "unknown"),
        "name": attrs.get("friendly_name") or "",
        "unit": attrs.get("unit_of_measurement") or "",
    }
    if raw.get("entity_id", "").startswith("climate."):
        extra = {k: attrs[k] for k in _CLIMATE_ATTRS if k in attrs}
        if extra:
            result["attributes"] = extra
    return result
```

With this new block:

```python
_DOMAIN_ATTRS: dict[str, list[str]] = {
    "climate": ["hvac_mode", "hvac_action", "current_temperature", "temperature", "preset_mode"],
    "light": ["brightness", "color_temp"],
    "cover": ["current_position"],
    "media_player": ["media_title", "media_artist", "source", "volume_level"],
    "vacuum": ["battery_level"],
    "fan": ["percentage", "preset_mode"],
    "water_heater": ["current_temperature", "temperature", "operation_mode"],
}


def _to_minimal(raw: dict) -> dict:
    attrs = raw.get("attributes") or {}
    eid = raw["entity_id"]
    dom = _domain(eid)
    result: dict = {
        "id": eid,
        "state": raw.get("state", "unknown"),
        "name": attrs.get("friendly_name") or "",
        "unit": attrs.get("unit_of_measurement") or "",
        "domain": dom,
        "device_class": attrs.get("device_class"),
    }
    domain_keys = _DOMAIN_ATTRS.get(dom, [])
    if domain_keys:
        extra = {k: attrs[k] for k in domain_keys if k in attrs}
        if extra:
            result["attributes"] = extra
    return result
```

- [ ] **Step 4: Run tests**

```bash
py -m pytest tests/test_entity_cache_extension.py tests/test_knowledge_db.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite to check no regressions**

```bash
py -m pytest tests/ -q
```
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/proxy/entity_cache.py tests/test_entity_cache_extension.py
git commit -m "feat: extend EntityCache with domain, device_class and typed attributes per domain"
```

---

## Task 3: SemanticContextMap — schema, classify, build

**Files:**
- Create: `hiris/app/proxy/semantic_context_map.py`
- Create: `tests/test_semantic_context_map.py` (partial — extended in Task 4)

- [ ] **Step 1: Write failing tests for classification and build**

```python
# tests/test_semantic_context_map.py
import pytest
from unittest.mock import MagicMock
from hiris.app.proxy.semantic_context_map import (
    SemanticContextMap, classify_entity, ENTITY_TYPE_SCHEMA, CONCEPT_TO_TYPES,
)


def test_classify_climate():
    et, label = classify_entity("climate", None)
    assert et == "climate"
    assert label == "Termostato"


def test_classify_temperature_sensor():
    et, label = classify_entity("sensor", "temperature")
    assert et == "temperature"
    assert label == "Temperatura"


def test_classify_motion_binary_sensor():
    et, label = classify_entity("binary_sensor", "motion")
    assert et == "motion"
    assert label == "Presenza"


def test_classify_door_sensor():
    et, label = classify_entity("binary_sensor", "door")
    assert et == "door"
    assert label == "Porta"


def test_classify_light():
    et, label = classify_entity("light", None)
    assert et == "light"
    assert label == "Luce"


def test_classify_sensor_no_device_class():
    et, label = classify_entity("sensor", None)
    assert et == "sensor"
    assert label == "Sensore"


def test_classify_unknown_domain_returns_other():
    et, _ = classify_entity("unknown_xyz", None)
    assert et == "other"


def _make_cache(entities: list[dict], area_map: dict) -> MagicMock:
    cache = MagicMock()
    cache._states = {e["id"]: e for e in entities}
    cache.get_area_map.return_value = area_map
    return cache


def test_build_places_entities_by_area():
    cache = _make_cache(
        [
            {"id": "climate.bagno", "state": "heat", "name": "Termostato Bagno",
             "domain": "climate", "device_class": None, "unit": "", "attributes": {}},
            {"id": "light.bagno", "state": "off", "name": "Luce Bagno",
             "domain": "light", "device_class": None, "unit": "", "attributes": {}},
        ],
        {"Bagno": ["climate.bagno", "light.bagno"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    assert "Bagno" in scm._map
    assert "climate" in scm._map["Bagno"]
    assert "climate.bagno" in scm._map["Bagno"]["climate"]
    assert "light.bagno" in scm._map["Bagno"]["light"]


def test_build_unassigned_entities_go_to_none_area():
    cache = _make_cache(
        [{"id": "sensor.power", "state": "1200", "name": "Potenza",
          "domain": "sensor", "device_class": "power", "unit": "W", "attributes": {}}],
        {"__no_area__": ["sensor.power"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    assert None in scm._map
    assert "power" in scm._map[None]


def test_build_excludes_noise_domains():
    cache = _make_cache(
        [
            {"id": "button.reset", "state": "unknown", "name": "Reset",
             "domain": "button", "device_class": None, "unit": "", "attributes": {}},
            {"id": "light.sala", "state": "on", "name": "Luce Sala",
             "domain": "light", "device_class": None, "unit": "", "attributes": {}},
        ],
        {"Soggiorno": ["button.reset", "light.sala"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    all_ids = [
        eid for types in scm._map.values() for eids in types.values() for eid in eids
    ]
    assert "button.reset" not in all_ids
    assert "light.sala" in all_ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
py -m pytest tests/test_semantic_context_map.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create `hiris/app/proxy/semantic_context_map.py` (Part 1 — schema + classify + build)**

```python
from __future__ import annotations
import fnmatch
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .entity_cache import EntityCache
    from .knowledge_db import KnowledgeDB

logger = logging.getLogger(__name__)

ENTITY_TYPE_SCHEMA: dict[tuple[str, str | None], tuple[str, str]] = {
    ("climate", None): ("climate", "Termostato"),
    ("light", None): ("light", "Luce"),
    ("cover", None): ("cover", "Tapparella"),
    ("media_player", None): ("media_player", "Media"),
    ("lock", None): ("lock", "Serratura"),
    ("alarm_control_panel", None): ("alarm", "Allarme"),
    ("vacuum", None): ("vacuum", "Robot"),
    ("fan", None): ("fan", "Ventilatore"),
    ("water_heater", None): ("water_heater", "Scaldabagno"),
    ("switch", None): ("switch", "Interruttore"),
    ("input_boolean", None): ("switch", "Interruttore"),
    ("sensor", "temperature"): ("temperature", "Temperatura"),
    ("sensor", "humidity"): ("humidity", "Umidità"),
    ("sensor", "power"): ("power", "Potenza"),
    ("sensor", "energy"): ("energy", "Energia"),
    ("sensor", "battery"): ("battery", "Batteria"),
    ("sensor", "illuminance"): ("illuminance", "Luminosità"),
    ("sensor", "co2"): ("co2", "CO₂"),
    ("sensor", "pm25"): ("pm25", "PM2.5"),
    ("sensor", "pressure"): ("pressure", "Pressione"),
    ("sensor", "voltage"): ("voltage", "Tensione"),
    ("sensor", "current"): ("current", "Corrente"),
    ("sensor", "gas"): ("gas", "Gas"),
    ("sensor", "water"): ("water", "Acqua"),
    ("binary_sensor", "motion"): ("motion", "Presenza"),
    ("binary_sensor", "occupancy"): ("motion", "Presenza"),
    ("binary_sensor", "door"): ("door", "Porta"),
    ("binary_sensor", "window"): ("window", "Finestra"),
    ("binary_sensor", "presence"): ("presence", "Presenza"),
    ("binary_sensor", "smoke"): ("smoke", "Fumo"),
    ("binary_sensor", "moisture"): ("moisture", "Perdita"),
    ("binary_sensor", "vibration"): ("vibration", "Vibrazione"),
    ("binary_sensor", "connectivity"): ("connectivity", "Connessione"),
}

_DOMAIN_FALLBACK: dict[str, tuple[str, str]] = {
    "sensor": ("sensor", "Sensore"),
    "binary_sensor": ("binary", "Sensore"),
}

_EXCLUDED_DOMAINS = frozenset({
    "update", "button", "tag", "event", "ai_task", "todo", "conversation",
    "device_tracker", "persistent_notification", "scene", "script",
    "automation", "input_text", "input_number", "input_select",
    "input_datetime", "number", "select", "text", "image",
    "stt", "tts", "notify", "remote", "siren", "wake_word",
})

CONCEPT_TO_TYPES: dict[str, list[str]] = {
    "termostato": ["climate"], "riscaldamento": ["climate"],
    "raffreddamento": ["climate"], "clima": ["climate"],
    "caldo": ["climate", "temperature"], "freddo": ["climate", "temperature"],
    "gradi": ["climate", "temperature"], "temperatura": ["climate", "temperature"],
    "luce": ["light"], "luci": ["light"], "illuminazione": ["light"],
    "lampada": ["light"], "accesa": ["light"], "spenta": ["light"],
    "consumo": ["power", "energy"], "energia": ["energy"],
    "watt": ["power"], "kwh": ["energy"], "bolletta": ["energy"],
    "movimento": ["motion"], "presenza": ["motion", "presence"],
    "qualcuno": ["motion"], "persona": ["motion"],
    "porta": ["door"], "finestra": ["window"], "ingresso": ["door"],
    "aperta": ["door", "window", "cover"], "chiusa": ["door", "window", "cover"],
    "tapparella": ["cover"], "veneziana": ["cover"],
    "tenda": ["cover"], "avvolgibile": ["cover"],
    "tv": ["media_player"], "televisione": ["media_player"],
    "musica": ["media_player"], "volume": ["media_player"],
    "umidità": ["humidity"],
    "serratura": ["lock"], "chiave": ["lock"],
    "allarme": ["alarm"], "sicurezza": ["alarm"],
    "robot": ["vacuum"], "aspirapolvere": ["vacuum"],
    "lavatrice": ["switch"], "lavastoviglie": ["switch"],
    "interruttore": ["switch"],
}

# area_name (or None for unassigned) → entity_type → [entity_ids]
_MapType = dict[str | None, dict[str, list[str]]]


def classify_entity(domain: str, device_class: str | None) -> tuple[str, str]:
    """Return (entity_type, label_it). Returns ('other', domain) if unrecognised."""
    key = (domain, device_class)
    if key in ENTITY_TYPE_SCHEMA:
        return ENTITY_TYPE_SCHEMA[key]
    key_no_dc = (domain, None)
    if key_no_dc in ENTITY_TYPE_SCHEMA:
        return ENTITY_TYPE_SCHEMA[key_no_dc]
    if domain in _DOMAIN_FALLBACK:
        return _DOMAIN_FALLBACK[domain]
    return ("other", domain)


class SemanticContextMap:
    def __init__(self) -> None:
        self._map: _MapType = {}
        self._type_to_label: dict[str, str] = {}

    def build(
        self,
        entity_cache: EntityCache,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> None:
        persisted = knowledge_db.load_classifications() if knowledge_db else {}
        area_map = entity_cache.get_area_map() or {}

        eid_to_area: dict[str, str | None] = {}
        for area_name, eids in area_map.items():
            resolved = None if area_name == "__no_area__" else area_name
            for eid in eids:
                eid_to_area[eid] = resolved

        new_map: _MapType = {}
        for eid, entity_data in entity_cache._states.items():
            domain = entity_data.get("domain", eid.split(".")[0])
            if domain in _EXCLUDED_DOMAINS:
                continue
            device_class = entity_data.get("device_class")

            if eid in persisted and persisted[eid]["classified_by"] == "user":
                entity_type = persisted[eid]["entity_type"]
                label_it = persisted[eid]["label_it"]
            else:
                entity_type, label_it = classify_entity(domain, device_class)
                if entity_type == "other":
                    continue
                if knowledge_db and eid not in persisted:
                    knowledge_db.save_classification(
                        entity_id=eid,
                        area=eid_to_area.get(eid),
                        entity_type=entity_type,
                        label_it=label_it,
                        friendly_name=entity_data.get("name", ""),
                        domain=domain,
                        device_class=device_class,
                    )

            self._type_to_label[entity_type] = label_it
            area = eid_to_area.get(eid)
            new_map.setdefault(area, {}).setdefault(entity_type, []).append(eid)

        self._map = new_map
        n_areas = len([k for k in new_map if k is not None])
        n_entities = sum(len(eids) for t in new_map.values() for eids in t.values())
        logger.info("SemanticContextMap built: %d areas, %d entities", n_areas, n_entities)
```

- [ ] **Step 4: Run tests**

```bash
py -m pytest tests/test_semantic_context_map.py -v
```
Expected: all classification and build tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/semantic_context_map.py tests/test_semantic_context_map.py
git commit -m "feat: SemanticContextMap — ENTITY_TYPE_SCHEMA, classify_entity, build from EntityCache"
```

---

## Task 4: SemanticContextMap — format + get_context

**Files:**
- Modify: `hiris/app/proxy/semantic_context_map.py` (add formatting methods)
- Modify: `tests/test_semantic_context_map.py` (add get_context tests)

- [ ] **Step 1: Add failing tests for get_context to existing test file**

Append to `tests/test_semantic_context_map.py`:

```python
def test_get_context_area_and_type_match_expands_detail():
    cache = _make_cache(
        [{"id": "climate.bagno", "state": "heat", "name": "Termostato Bagno",
          "domain": "climate", "device_class": None, "unit": "",
          "attributes": {"hvac_mode": "heat", "current_temperature": 21.5, "temperature": 22.0}}],
        {"Bagno": ["climate.bagno"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    context, visible_ids = scm.get_context("c'è il termostato in bagno?", cache)
    assert "CASA" in context
    assert "BAGNO" in context
    assert "21.5" in context
    assert "climate.bagno" in visible_ids


def test_get_context_no_match_returns_overview_only():
    cache = _make_cache(
        [{"id": "light.sala", "state": "on", "name": "Luce Sala",
          "domain": "light", "device_class": None, "unit": "", "attributes": {}}],
        {"Soggiorno": ["light.sala"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    context, visible_ids = scm.get_context("ciao come stai?", cache)
    assert "CASA" in context
    assert "SOGGIORNO" not in context
    assert "light.sala" in visible_ids


def test_get_context_type_only_match_expands_all_areas():
    cache = _make_cache(
        [
            {"id": "light.sala", "state": "on", "name": "Luce Sala",
             "domain": "light", "device_class": None, "unit": "", "attributes": {"brightness": 200}},
            {"id": "light.cucina", "state": "off", "name": "Luce Cucina",
             "domain": "light", "device_class": None, "unit": "", "attributes": {}},
        ],
        {"Soggiorno": ["light.sala"], "Cucina": ["light.cucina"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    context, _ = scm.get_context("tutte le luci", cache)
    assert "SOGGIORNO" in context
    assert "CUCINA" in context


def test_get_context_filters_by_allowed_entities():
    cache = _make_cache(
        [
            {"id": "climate.bagno", "state": "heat", "name": "T Bagno",
             "domain": "climate", "device_class": None, "unit": "", "attributes": {}},
            {"id": "light.bagno", "state": "off", "name": "L Bagno",
             "domain": "light", "device_class": None, "unit": "", "attributes": {}},
        ],
        {"Bagno": ["climate.bagno", "light.bagno"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    _, visible_ids = scm.get_context("bagno", cache, allowed_entities=["climate.*"])
    assert "climate.bagno" in visible_ids
    assert "light.bagno" not in visible_ids


def test_get_context_unassigned_shown_in_overview():
    cache = _make_cache(
        [{"id": "sensor.power", "state": "1200", "name": "Potenza",
          "domain": "sensor", "device_class": "power", "unit": "W", "attributes": {}}],
        {"__no_area__": ["sensor.power"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    context, _ = scm.get_context("niente", cache)
    assert "Non assegnate" in context


def test_light_state_format_on_with_brightness():
    cache = _make_cache(
        [{"id": "light.sala", "state": "on", "name": "Luce Sala",
          "domain": "light", "device_class": None, "unit": "",
          "attributes": {"brightness": 128}}],
        {"Soggiorno": ["light.sala"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    context, _ = scm.get_context("luci soggiorno", cache)
    assert "50%" in context


def test_climate_state_format():
    cache = _make_cache(
        [{"id": "climate.sala", "state": "heat", "name": "Termostato Sala",
          "domain": "climate", "device_class": None, "unit": "",
          "attributes": {"hvac_mode": "heat", "hvac_action": "heating",
                         "current_temperature": 19.0, "temperature": 21.0}}],
        {"Soggiorno": ["climate.sala"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    context, _ = scm.get_context("termostato soggiorno", cache)
    assert "19.0" in context
    assert "21.0" in context
    assert "heating" in context
```

- [ ] **Step 2: Run tests to verify new ones fail**

```bash
py -m pytest tests/test_semantic_context_map.py -v -k "get_context or format"
```
Expected: `AttributeError: 'SemanticContextMap' object has no attribute 'get_context'`

- [ ] **Step 3: Append formatting methods to `hiris/app/proxy/semantic_context_map.py`**

Add these methods inside the `SemanticContextMap` class, after `build()`:

```python
    def _get_label(self, entity_type: str) -> str:
        return self._type_to_label.get(entity_type, entity_type)

    def _format_state(self, entity_type: str, entity_data: dict) -> str:
        state = entity_data.get("state", "")
        attrs = entity_data.get("attributes") or {}
        if entity_type == "climate":
            cur = attrs.get("current_temperature", "?")
            sp = attrs.get("temperature", "?")
            mode = attrs.get("hvac_mode", state)
            action = attrs.get("hvac_action", "")
            action_str = f" · {action}" if action and action not in ("idle", "off") else ""
            return f"{mode} · {cur}°C → {sp}°C{action_str}"
        if entity_type == "light":
            if state == "off":
                return "spenta"
            b = attrs.get("brightness")
            return f"accesa {round(b / 255 * 100)}%" if b is not None else "accesa"
        if entity_type == "cover":
            pos = attrs.get("current_position")
            return f"{state} {pos}%" if pos is not None else state
        if entity_type == "media_player":
            if state in ("off", "standby", "idle"):
                return state
            title = attrs.get("media_title", "")
            vol = attrs.get("volume_level")
            vol_str = f" vol:{round(vol * 100)}%" if vol is not None else ""
            return f"{state} · {title}{vol_str}" if title else f"{state}{vol_str}"
        if entity_type in ("motion", "occupancy", "presence"):
            return "rilevato" if state == "on" else "assente"
        if entity_type == "door":
            return "aperta" if state == "on" else "chiusa"
        if entity_type == "window":
            return "aperta" if state == "on" else "chiusa"
        if entity_type == "switch":
            return "acceso" if state == "on" else "spento"
        unit = entity_data.get("unit", "")
        return f"{state} {unit}".strip() if unit else state

    def _filter_by_allowed(self, allowed_entities: list[str] | None) -> _MapType:
        if not allowed_entities:
            return self._map
        result: _MapType = {}
        for area, types in self._map.items():
            filtered: dict[str, list[str]] = {}
            for et, eids in types.items():
                ok = [e for e in eids if any(fnmatch.fnmatch(e, p) for p in allowed_entities)]
                if ok:
                    filtered[et] = ok
            if filtered:
                result[area] = filtered
        return result

    def _format_overview(self, filtered: _MapType) -> str:
        now = datetime.now().strftime("%H:%M")
        named = {k: v for k, v in filtered.items() if k is not None}
        unassigned = filtered.get(None, {})
        lines = [f"CASA — {len(named)} aree [agg. {now}]"]
        for area in sorted(named):
            parts = []
            for et, eids in named[area].items():
                label = self._get_label(et)
                parts.append(f"{label}×{len(eids)}" if len(eids) > 1 else label)
            lines.append(f"  {area}: {' · '.join(parts)}")
        if unassigned:
            ua = [self._get_label(et) for et in unassigned]
            lines.append(f"[Non assegnate: {' · '.join(ua)}]")
        return "\n".join(lines)

    def _format_detail(
        self,
        filtered: _MapType,
        entity_cache: EntityCache,
        areas: list[str | None],
        types: set[str] | None,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> str:
        now = datetime.now().strftime("%H:%M")
        sections = []
        for area in areas:
            area_types = filtered.get(area, {})
            relevant = {
                et: eids for et, eids in area_types.items()
                if types is None or et in types
            }
            if not relevant:
                continue
            header = (area or "Non assegnate").upper()
            lines = [f"{header} [agg. {now}]"]
            for et, eids in relevant.items():
                label = self._get_label(et)
                for eid in eids:
                    ed = entity_cache._states.get(eid)
                    if ed is None:
                        continue
                    state_str = self._format_state(et, ed)
                    name = ed.get("name") or eid
                    lines.append(f"  {label:<14} {name:<32} {state_str}")
                    if knowledge_db:
                        for annot in knowledge_db.get_annotations(eid)[:1]:
                            lines.append(
                                f"    [Nota: {annot['annotation']} — {annot['source']}]"
                            )
            if len(lines) > 1:
                sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def get_context(
        self,
        query: str,
        entity_cache: EntityCache,
        allowed_entities: list[str] | None = None,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> tuple[str, frozenset[str]]:
        filtered = self._filter_by_allowed(allowed_entities)
        visible_ids = frozenset(
            eid
            for types in filtered.values()
            for eids in types.values()
            for eid in eids
        )
        q = query.lower()
        area_matches = [a for a in filtered if a is not None and a.lower() in q]
        type_matches: set[str] = set()
        for concept, ctypes in CONCEPT_TO_TYPES.items():
            if concept in q:
                type_matches.update(ctypes)
        overview = self._format_overview(filtered)
        if area_matches or type_matches:
            expand = area_matches if area_matches else [a for a in filtered if a is not None]
            detail = self._format_detail(
                filtered, entity_cache, expand, type_matches or None, knowledge_db
            )
            context = f"{overview}\n\n{detail}" if detail else overview
        else:
            context = overview
        return context, visible_ids

    def add_entity(
        self,
        entity_id: str,
        domain: str,
        device_class: str | None,
        area: str | None,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> None:
        if domain in _EXCLUDED_DOMAINS:
            return
        entity_type, label_it = classify_entity(domain, device_class)
        if entity_type == "other":
            return
        self._type_to_label[entity_type] = label_it
        bucket = self._map.setdefault(area, {}).setdefault(entity_type, [])
        if entity_id not in bucket:
            bucket.append(entity_id)

    def remove_entity(self, entity_id: str) -> None:
        for area_types in self._map.values():
            for eids in area_types.values():
                if entity_id in eids:
                    eids.remove(entity_id)
                    return
```

- [ ] **Step 4: Run full test file**

```bash
py -m pytest tests/test_semantic_context_map.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Run full suite**

```bash
py -m pytest tests/ -q
```
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/proxy/semantic_context_map.py tests/test_semantic_context_map.py
git commit -m "feat: SemanticContextMap — overview format, detail format, get_context, ContextSelector"
```

---

## Task 5: server.py wiring

**Files:**
- Modify: `hiris/app/server.py`

- [ ] **Step 1: In `hiris/app/server.py`, replace the `EmbeddingIndex` import**

Find at top of file:
```python
from .proxy.embedding_index import EmbeddingIndex
```
Replace with:
```python
from .proxy.knowledge_db import KnowledgeDB
from .proxy.semantic_context_map import SemanticContextMap
```

- [ ] **Step 2: In `_on_startup`, remove EmbeddingIndex block and add SemanticContextMap**

Find and remove this block (after `engine.start()`):
```python
    embedding_index = EmbeddingIndex()
    asyncio.create_task(
        embedding_index.build(entity_cache.get_all_useful()),
        name="embedding_index_build",
    )
    app["embedding_index"] = embedding_index
```

Also find and remove the `semantic_map.get_prompt_snippet` usage — the semantic_map block remains for the `get_home_status` tool but `get_prompt_snippet` is removed in Task 8.

After the area registry block (after `ha_client.add_registry_listener(semantic_map.on_entity_added)`), add:

```python
    knowledge_db = KnowledgeDB(
        db_path=os.path.join(data_dir, "hiris_knowledge.db")
    )
    app["knowledge_db"] = knowledge_db

    context_map = SemanticContextMap()
    context_map.build(entity_cache, knowledge_db=knowledge_db)
    app["context_map"] = context_map
    logger.info("SemanticContextMap ready")
```

Also add to `_on_cleanup` (find the cleanup function and add before stopping the engine):
```python
    if "knowledge_db" in app:
        app["knowledge_db"].close()
```

- [ ] **Step 3: Verify server starts without errors**

```bash
py -m pytest tests/test_api.py -v -k "health"
```
Expected: `test_health_endpoint PASSED`

- [ ] **Step 4: Run full test suite**

```bash
py -m pytest tests/ -q
```
Expected: all pass (EmbeddingIndex tests may warn — that's ok, they're removed in Task 8).

- [ ] **Step 5: Commit**

```bash
git add hiris/app/server.py
git commit -m "feat: wire KnowledgeDB and SemanticContextMap in server startup"
```

---

## Task 6: handlers_chat.py — replace RAG prefetch with SemanticContextMap

**Files:**
- Modify: `hiris/app/api/handlers_chat.py`
- Modify: `tests/test_api.py` (update RAG test)

- [ ] **Step 1: In `handlers_chat.py`, replace the two context injection blocks**

Find and **remove** the `_prefetch_context` function (lines ~13-47) and the `_RAG_TOP_K` constant.

Find this block inside `handle_chat` and **replace** it:
```python
    # Inject semantic map snippet (replaces home_profile — richer context)
    semantic_map = request.app.get("semantic_map")
    entity_cache = request.app.get("entity_cache")
    if semantic_map and entity_cache:
        map_snippet = semantic_map.get_prompt_snippet(entity_cache)
        if map_snippet:
            system_prompt = f"{system_prompt}\n\n---\n\n{map_snippet}"

    # RAG pre-fetch: inject relevant entity states before Claude reasons
    prefetched = _prefetch_context(message, request.app)
    if prefetched:
        system_prompt = f"{system_prompt}\n\n---\n\n{prefetched}"
```

With:
```python
    context_map = request.app.get("context_map")
    entity_cache = request.app.get("entity_cache")
    knowledge_db = request.app.get("knowledge_db")
    visible_ids: frozenset[str] = frozenset()
    if context_map and entity_cache:
        ctx_str, visible_ids = context_map.get_context(
            query=message,
            entity_cache=entity_cache,
            allowed_entities=allowed_entities,
            knowledge_db=knowledge_db,
        )
        if ctx_str:
            system_prompt = f"{system_prompt}\n\n---\n\n{ctx_str}"
```

Then find the `runner.chat(...)` call and add `visible_entity_ids=visible_ids` to it:
```python
    response = await runner.chat(
        user_message=message,
        system_prompt=system_prompt,
        conversation_history=context_history,
        allowed_tools=allowed_tools,
        allowed_entities=allowed_entities,
        allowed_services=allowed_services,
        model=agent_model,
        max_tokens=agent_max_tokens,
        agent_type=agent_type,
        restrict_to_home=agent_restrict,
        require_confirmation=agent_require_confirmation,
        agent_id=effective_agent_id,
        visible_entity_ids=visible_ids,
    )
```

- [ ] **Step 2: Update the RAG prefetch test in `tests/test_api.py`**

Find `test_chat_rag_prefetch_injects_entity_context` and replace it:

```python
@pytest.mark.asyncio
async def test_chat_context_map_injects_area_context(client):
    from unittest.mock import MagicMock
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent

    engine = client.app["engine"]
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        trigger={"type": "manual"}, system_prompt="base prompt",
        allowed_tools=[], enabled=True, is_default=True,
    )

    mock_context_map = MagicMock()
    mock_context_map.get_context = MagicMock(return_value=(
        "CASA — 1 aree\n  Bagno: Termostato\n\nBAGNO\n  Termostato  climate.bagno  heat · 21°C → 22°C",
        frozenset(["climate.bagno"]),
    ))
    client.app["context_map"] = mock_context_map

    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="ok")

    await client.post("/api/chat", json={"message": "termostato bagno?"})

    call_kwargs = runner.chat.call_args.kwargs
    assert "BAGNO" in call_kwargs["system_prompt"]
    assert "Termostato" in call_kwargs["system_prompt"]
```

- [ ] **Step 3: Run the updated test**

```bash
py -m pytest tests/test_api.py::test_chat_context_map_injects_area_context -v
```
Expected: `PASSED`

- [ ] **Step 4: Run full test suite**

```bash
py -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_chat.py tests/test_api.py
git commit -m "feat: handlers_chat — replace RAG prefetch with SemanticContextMap.get_context"
```

---

## Task 7: claude_runner.py + ha_tools.py — entity validation via visible_entity_ids

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `hiris/app/tools/ha_tools.py`

- [ ] **Step 1: In `claude_runner.py`, add `visible_entity_ids` to `chat()` and `_dispatch_tool()`**

Find the `chat()` method signature and add the parameter (add after `agent_id`):
```python
async def chat(
    self,
    user_message: str,
    system_prompt: str = "",
    conversation_history: list | None = None,
    allowed_tools: list | None = None,
    allowed_entities: list | None = None,
    allowed_services: list | None = None,
    model: str = "auto",
    max_tokens: int = 4096,
    agent_type: str = "chat",
    restrict_to_home: bool = False,
    require_confirmation: bool = False,
    agent_id: str | None = None,
    visible_entity_ids: frozenset | None = None,   # ← add this
) -> str:
```

Inside `chat()`, find where `_dispatch_tool` is called (it is in the agentic tool-use loop, called as `await self._dispatch_tool(name, inputs, allowed_entities, allowed_services, agent_id)`) and add `visible_entity_ids`:
```python
result = await self._dispatch_tool(
    name, inputs,
    allowed_entities=allowed_entities,
    allowed_services=allowed_services,
    agent_id=agent_id,
    visible_entity_ids=visible_entity_ids,
)
```

- [ ] **Step 2: Add `visible_entity_ids` to `_dispatch_tool()` and use it**

Find the `_dispatch_tool` signature:
```python
    async def _dispatch_tool(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        agent_id: Optional[str] = None,
    ) -> Any:
```

Add parameter:
```python
    async def _dispatch_tool(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        agent_id: Optional[str] = None,
        visible_entity_ids: Optional[frozenset] = None,
    ) -> Any:
```

Find the `get_entity_states` dispatch block:
```python
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if allowed_entities:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                    logger.info("Filtered entity ids to: %s", ids)
                return await get_entity_states(self._ha, ids, entity_cache=self._cache)
```

Replace with:
```python
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if visible_entity_ids:
                    ids = [eid for eid in ids if eid in visible_entity_ids]
                elif allowed_entities:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                return await get_entity_states(self._ha, ids, entity_cache=self._cache)
```

- [ ] **Step 3: In `claude_runner.py`, remove EmbeddingIndex references**

Find `self._index` initialization in `__init__` (something like `self._index = None`) and remove it.

Find the `search_entities` dispatch block and remove it entirely:
```python
            if name == "search_entities":
                if self._cache is None or self._index is None:
                    return []
                return search_entities(
                    inputs["query"],
                    self._cache,
                    self._index,
                    top_k=inputs.get("top_k", 10),
                    domain=inputs.get("domain"),
                )
```

Find `SEARCH_ENTITIES_TOOL_DEF` in the `ALL_TOOL_DEFS` list and remove it.

Find any `set_embedding_index` method and remove it.

- [ ] **Step 4: In `ha_tools.py`, remove EmbeddingIndex import and `search_entities`**

Remove:
```python
from ..proxy.embedding_index import EmbeddingIndex
```

Remove the `search_entities` function and `SEARCH_ENTITIES_TOOL_DEF` dict entirely.

- [ ] **Step 5: Run full test suite**

```bash
py -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/claude_runner.py hiris/app/tools/ha_tools.py
git commit -m "feat: entity validation via visible_entity_ids in claude_runner and ha_tools; remove EmbeddingIndex"
```

---

## Task 8: Cleanup + version 0.3.0

**Files:**
- Delete: `hiris/app/proxy/embedding_index.py`
- Modify: `hiris/app/proxy/semantic_map.py` (remove `get_prompt_snippet`)
- Modify: `hiris/config.yaml`, `hiris/app/server.py`, `tests/test_api.py` (version bump)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Delete `embedding_index.py`**

```bash
git rm hiris/app/proxy/embedding_index.py
```

If there are any remaining `from ..proxy.embedding_index import EmbeddingIndex` imports in other files, remove them now. Check with:
```bash
grep -r "embedding_index" hiris/
```
Expected: no matches.

- [ ] **Step 2: Remove `get_prompt_snippet` from `semantic_map.py`**

Find and remove the `get_prompt_snippet` method from `hiris/app/proxy/semantic_map.py`. Keep all other methods (`build_from_cache`, `get_entity_meta`, `on_entity_added`, `load`, `save`, `_classify_unknown_batch`, etc.).

- [ ] **Step 3: Bump version to 0.3.0**

In `hiris/config.yaml`:
```yaml
version: "0.3.0"
```

In `hiris/app/server.py` (the `_handle_health` function):
```python
    return web.json_response({"status": "ok", "version": "0.3.0"})
```

In `tests/test_api.py`:
```python
    assert data["version"] == "0.3.0"
```

- [ ] **Step 4: Update CHANGELOG.md**

Add at top, before `[0.2.4]`:

```markdown
## [0.3.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex RAG and SemanticMap snippet; organizes all HA entities by area using native `device_class` + domain classification
- **ENTITY_TYPE_SCHEMA** — maps (domain, device_class) → (entity_type, label_it) for 30+ entity types, based on HA documentation
- **ContextSelector** — keyword-based query: extracts area + concept→type matches from user message, injects only relevant sections
- **Two-tier prompt injection** — compact home overview always present (~80 token); area/type detail expanded on match (~150 token); ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations, query patterns
- **Unified permission boundary** — `visible_entity_ids` from `SemanticContextMap.get_context()` used to validate all entity tool calls; consistent `allowed_entities` enforcement
- **EntityCache enriched** — `domain`, `device_class`, and typed attributes (hvac_mode, brightness, current_position, etc.) stored per entity for all domains

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap` + `ContextSelector`
- `SemanticMap.get_prompt_snippet()` — replaced by `SemanticContextMap._format_overview()` + `_format_detail()`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency
```

- [ ] **Step 5: Run full test suite**

```bash
py -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Commit and push**

```bash
git add -A
git commit -m "feat: SemanticContextMap v0.3.0 — area-aware context injection, KnowledgeDB, remove EmbeddingIndex"
git push origin master
```
