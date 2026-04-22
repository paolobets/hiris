# Semantic Home Map + LLM Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a semantic entity map that gives Claude structured home domain knowledge, fix energy history, and add a pluggable LLM router with Ollama support for classification tasks.

**Architecture:** `SemanticMap` classifies HA entities via rules (80%) + LLM batch for ambiguous ones, persists to `/data/home_semantic_map.json`, and injects structured home context into the system prompt. `LLMRouter` wraps `ClaudeRunner` with the same public interface, adding `classify_entities()` that routes to Ollama if configured or falls back to Claude. `energy_tools.py` reads entity IDs from the map instead of hardcoded placeholders.

**Tech Stack:** Python 3.11, aiohttp, anthropic SDK, fnmatch pattern matching, JSON persistence, OpenAI-compat Ollama API.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `hiris/app/proxy/semantic_map.py` | **new** | SemanticMap class: load/save, rule classifier, LLM batch, prompt snippet, WebSocket hook |
| `hiris/app/backends/__init__.py` | **new** | package marker |
| `hiris/app/backends/base.py` | **new** | `LLMBackend` ABC with `simple_chat()` |
| `hiris/app/backends/claude.py` | **new** | `ClaudeBackend` wraps ClaudeRunner for classification simple_chat |
| `hiris/app/backends/ollama.py` | **new** | `OllamaBackend` — OpenAI-compat chat completions for classification |
| `hiris/app/llm_router.py` | **new** | `LLMRouter` — same public interface as ClaudeRunner + `classify_entities()` |
| `hiris/app/claude_runner.py` | **modified** | add `semantic_map` param, add `simple_chat()`, pass map to energy tool dispatch |
| `hiris/app/proxy/ha_client.py` | **modified** | add `_registry_listeners` + `entity_registry_updated` WebSocket subscription |
| `hiris/app/tools/energy_tools.py` | **modified** | read entity IDs from SemanticMap instead of hardcoded list |
| `hiris/app/tools/ha_tools.py` | **modified** | `get_home_status` enriched with semantic labels |
| `hiris/app/api/handlers_chat.py` | **modified** | use `app["llm_router"]`, inject `map.get_prompt_snippet()` |
| `hiris/app/server.py` | **modified** | init SemanticMap, LLMRouter, wire registry listener |
| `hiris/config.yaml` | **modified** | add `primary_model`, `local_model_url`, `local_model_name` options |
| `tests/test_semantic_map.py` | **new** | tests for SemanticMap |
| `tests/test_llm_router.py` | **new** | tests for LLMRouter routing logic |
| `tests/test_tools.py` | **modified** | update energy_tools test for SemanticMap |

---

## Task 1: SemanticMap — core class (load/save + rule classifier + get_category)

**Files:**
- Create: `hiris/app/proxy/semantic_map.py`
- Create: `tests/test_semantic_map.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_semantic_map.py
import json
import os
import pytest
from hiris.app.proxy.semantic_map import SemanticMap, classify_by_rules

def test_classify_by_rules_energy_meter():
    assert classify_by_rules("sensor.shellyem3_xxx_power") == "energy_meter"
    assert classify_by_rules("sensor.casa_energy_consumption") == "energy_meter"
    assert classify_by_rules("sensor.main_watt") == "energy_meter"

def test_classify_by_rules_solar():
    assert classify_by_rules("sensor.solaredge_pv_power") == "solar_production"
    assert classify_by_rules("sensor.solar_output") == "solar_production"

def test_classify_by_rules_grid():
    assert classify_by_rules("sensor.tibber_grid_import") == "grid_import"
    assert classify_by_rules("sensor.rete_export") == "grid_import"

def test_classify_by_rules_climate():
    assert classify_by_rules("climate.heatpump_salotto") == "climate_sensor"
    assert classify_by_rules("sensor.aqara_temperature") == "climate_sensor"

def test_classify_by_rules_lighting():
    assert classify_by_rules("light.salotto") == "lighting"
    assert classify_by_rules("light.cucina_led") == "lighting"

def test_classify_by_rules_presence():
    assert classify_by_rules("binary_sensor.motion_salotto") == "presence"
    assert classify_by_rules("binary_sensor.presence_home") == "presence"

def test_classify_by_rules_door_window():
    assert classify_by_rules("binary_sensor.door_front") == "door_window"
    assert classify_by_rules("binary_sensor.window_bedroom") == "door_window"

def test_classify_by_rules_appliance():
    assert classify_by_rules("switch.lavatrice") == "appliance"
    assert classify_by_rules("switch.lavastoviglie_cucina") == "appliance"

def test_classify_by_rules_diagnostic():
    assert classify_by_rules("sensor.shelly_cfgchanged") == "diagnostic"
    assert classify_by_rules("update.hiris_firmware") == "diagnostic"

def test_classify_by_rules_unknown():
    assert classify_by_rules("sensor.opaque_34945479_ch1_weird") is None


def test_semantic_map_get_category_empty():
    m = SemanticMap(data_dir="/tmp")
    assert m.get_category("energy_meter") == []


def test_semantic_map_add_and_get_category():
    m = SemanticMap(data_dir="/tmp")
    m._add_entity("sensor.power_main", "energy_meter", "Contatore principale", classified_by="rules")
    assert "sensor.power_main" in m.get_category("energy_meter")


def test_semantic_map_save_load_roundtrip(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.salotto", "lighting", "Luce salotto", classified_by="rules")
    m._add_entity("sensor.power_main", "energy_meter", "Contatore", classified_by="rules")
    m.save()

    m2 = SemanticMap(data_dir=str(tmp_path))
    m2.load()
    assert "light.salotto" in m2.get_category("lighting")
    assert "sensor.power_main" in m2.get_category("energy_meter")


def test_semantic_map_get_all_entity_ids(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.a", "lighting", "A", classified_by="rules")
    m._add_entity("sensor.b", "energy_meter", "B", classified_by="rules")
    ids = m.get_all_entity_ids()
    assert "light.a" in ids
    assert "sensor.b" in ids
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd hiris && python -m pytest tests/test_semantic_map.py -v 2>&1 | head -20
```
Expected: `ImportError` or `ModuleNotFoundError` for `semantic_map`.

- [ ] **Step 3: Implement SemanticMap core**

```python
# hiris/app/proxy/semantic_map.py
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ALL_ROLES = [
    "energy_meter", "solar_production", "grid_import",
    "climate_sensor", "presence", "lighting", "door_window",
    "appliance", "electrical", "diagnostic", "other", "unknown",
]

_RULES: list[tuple[str, str]] = [
    # (glob-style substring pattern, role)
    ("_power",          "energy_meter"),
    ("_energy",         "energy_meter"),
    ("_consumption",    "energy_meter"),
    ("_watt",           "energy_meter"),
    ("_solar",          "solar_production"),
    ("_pv",             "solar_production"),
    ("_photovoltaic",   "solar_production"),
    ("_grid",           "grid_import"),
    ("_import",         "grid_import"),
    ("_export",         "grid_import"),
    ("_temp",           "climate_sensor"),
    ("_temperature",    "climate_sensor"),
    ("_motion",         "presence"),
    ("_presence",       "presence"),
    ("_occupancy",      "presence"),
    ("_door",           "door_window"),
    ("_window",         "door_window"),
    ("_lavatrice",      "appliance"),
    ("_lavastoviglie",  "appliance"),
    ("_forno",          "appliance"),
    ("_boiler",         "appliance"),
    ("_voltage",        "electrical"),
    ("_current",        "electrical"),
    ("_cfgchanged",     "diagnostic"),
    ("config_",         "diagnostic"),
]

_DOMAIN_RULES: dict[str, str] = {
    "light":    "lighting",
    "climate":  "climate_sensor",
    "update":   "diagnostic",
}


def classify_by_rules(entity_id: str) -> Optional[str]:
    """Return a role string if the entity_id matches a known pattern, else None."""
    domain = entity_id.split(".")[0]
    if domain in _DOMAIN_RULES:
        return _DOMAIN_RULES[domain]
    lower = entity_id.lower()
    for pattern, role in _RULES:
        if pattern in lower:
            return role
    return None


class SemanticMap:
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._path = os.path.join(data_dir, "home_semantic_map.json")
        self._categories: dict[str, list[str]] = {role: [] for role in ALL_ROLES}
        self._entity_meta: dict[str, dict] = {}
        self._router: Any = None
        self._classify_task: Optional[asyncio.Task] = None
        self._generated_at: Optional[str] = None
        self._last_updated: Optional[str] = None

    def set_router(self, router: Any) -> None:
        self._router = router

    def _add_entity(
        self,
        entity_id: str,
        role: str,
        label: str,
        area: str = "",
        unit: str = "",
        classified_by: str = "rules",
        confidence: float = 1.0,
    ) -> None:
        if role not in self._categories:
            role = "other"
        if entity_id not in self._categories[role]:
            self._categories[role].append(entity_id)
        self._entity_meta[entity_id] = {
            "label": label,
            "role": role,
            "area": area,
            "unit": unit,
            "classified_by": classified_by,
            "confidence": confidence,
        }

    def get_category(self, role: str) -> list[str]:
        return list(self._categories.get(role, []))

    def get_all_entity_ids(self) -> list[str]:
        return list(self._entity_meta.keys())

    def load(self) -> bool:
        if not os.path.exists(self._path):
            return False
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._generated_at = data.get("generated_at")
            self._last_updated = data.get("last_updated")
            self._categories = {role: [] for role in ALL_ROLES}
            for role, ids in data.get("categories", {}).items():
                self._categories.setdefault(role, [])
                self._categories[role] = list(ids)
            self._entity_meta = data.get("entity_meta", {})
            return True
        except Exception as exc:
            logger.warning("SemanticMap load failed: %s", exc)
            return False

    def save(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self._generated_at:
            self._generated_at = now
        self._last_updated = now
        data = {
            "version": "1",
            "generated_at": self._generated_at,
            "last_updated": self._last_updated,
            "categories": self._categories,
            "entity_meta": self._entity_meta,
        }
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.error("SemanticMap save failed: %s", exc)
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_semantic_map.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/semantic_map.py tests/test_semantic_map.py
git commit -m "feat: add SemanticMap core — rule classifier, load/save, get_category"
```

---

## Task 2: SemanticMap — build_from_cache + WebSocket hook

**Files:**
- Modify: `hiris/app/proxy/semantic_map.py`
- Modify: `tests/test_semantic_map.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_semantic_map.py

from unittest.mock import MagicMock


def _make_cache(entity_ids: list[str]):
    """Create a minimal mock EntityCache."""
    cache = MagicMock()
    minimal = [{"id": eid, "state": "on", "name": eid.split(".")[-1], "unit": ""} for eid in entity_ids]
    cache.get_all_useful.return_value = minimal
    return cache


def test_build_from_cache_classifies_known(tmp_path):
    cache = _make_cache([
        "light.salotto",
        "sensor.shellyem3_xxx_power",
        "climate.heatpump",
    ])
    m = SemanticMap(data_dir=str(tmp_path))
    new_ids = m.build_from_cache(cache)
    assert "light.salotto" in m.get_category("lighting")
    assert "sensor.shellyem3_xxx_power" in m.get_category("energy_meter")
    assert "climate.heatpump" in m.get_category("climate_sensor")


def test_build_from_cache_returns_unknown_for_ambiguous(tmp_path):
    cache = _make_cache(["sensor.opaque_34945479_ch1_weird"])
    m = SemanticMap(data_dir=str(tmp_path))
    new_ids = m.build_from_cache(cache)
    assert "sensor.opaque_34945479_ch1_weird" in new_ids  # returned as needs-LLM


def test_build_from_cache_skips_existing(tmp_path):
    cache = _make_cache(["light.salotto", "sensor.new_sensor_power"])
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.salotto", "lighting", "Luce", classified_by="rules")
    new_ids = m.build_from_cache(cache)
    # light.salotto already in map — not returned as new
    assert "light.salotto" not in new_ids
    # new sensor is classified by rules
    assert "sensor.new_sensor_power" not in new_ids  # classified by rules, not ambiguous


def test_on_entity_added_classifies_by_rules(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m.on_entity_added("light.new_light", {"friendly_name": "New Light"})
    assert "light.new_light" in m.get_category("lighting")


def test_on_entity_added_marks_unknown_if_ambiguous(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m.on_entity_added("sensor.opaque_xyz_weird", {})
    assert "sensor.opaque_xyz_weird" in m.get_category("unknown")
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_semantic_map.py::test_build_from_cache_classifies_known -v
```
Expected: `AttributeError: 'SemanticMap' object has no attribute 'build_from_cache'`.

- [ ] **Step 3: Add build_from_cache and on_entity_added to semantic_map.py**

Add these methods to the `SemanticMap` class (after `save()`):

```python
    def build_from_cache(self, entity_cache: Any) -> list[str]:
        """Classify all entities not yet in the map. Returns list of ambiguous entity IDs needing LLM."""
        known = self.get_all_entity_ids()
        all_entities = entity_cache.get_all_useful()
        ambiguous: list[str] = []
        for e in all_entities:
            eid = e["id"]
            if eid in known:
                continue
            role = classify_by_rules(eid)
            if role:
                label = e.get("name") or eid.split(".")[-1]
                unit = e.get("unit") or ""
                self._add_entity(eid, role, label, unit=unit, classified_by="rules")
            else:
                self._add_entity(eid, "unknown", e.get("name") or eid, classified_by="pending")
                ambiguous.append(eid)
        if all_entities:
            self.save()
        return ambiguous

    def on_entity_added(self, entity_id: str, attributes: dict) -> None:
        """Called when HA fires entity_registry_updated for a new entity."""
        if entity_id in self.get_all_entity_ids():
            return
        role = classify_by_rules(entity_id)
        label = attributes.get("friendly_name") or entity_id.split(".")[-1]
        if role:
            self._add_entity(entity_id, role, label, classified_by="rules")
            logger.info("SemanticMap: auto-classified %s → %s", entity_id, role)
        else:
            self._add_entity(entity_id, "unknown", label, classified_by="pending")
            logger.info("SemanticMap: %s queued for LLM classification", entity_id)
            if self._router:
                asyncio.create_task(
                    self._classify_unknown_batch(),
                    name=f"classify_{entity_id}",
                )
        self.save()

    async def _classify_unknown_batch(self) -> None:
        """Classify all 'unknown'/'pending' entities via LLM router in batches of 20."""
        if not self._router:
            return
        pending = [
            eid for eid in self._categories.get("unknown", [])
            if self._entity_meta.get(eid, {}).get("classified_by") == "pending"
        ]
        if not pending:
            return
        BATCH = 20
        for i in range(0, len(pending), BATCH):
            batch_ids = pending[i:i + BATCH]
            entities = [
                {"id": eid, **self._entity_meta.get(eid, {})}
                for eid in batch_ids
            ]
            try:
                results = await self._router.classify_entities(entities)
                for eid, meta in results.items():
                    if eid not in self._entity_meta:
                        continue
                    role = meta.get("role", "other")
                    label = meta.get("label", eid.split(".")[-1])
                    confidence = float(meta.get("confidence", 0.8))
                    # Remove from unknown list
                    if eid in self._categories.get("unknown", []):
                        self._categories["unknown"].remove(eid)
                    self._add_entity(
                        eid, role, label,
                        classified_by="claude",
                        confidence=confidence,
                    )
                self.save()
            except Exception as exc:
                logger.warning("LLM batch classification failed: %s", exc)
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_semantic_map.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/semantic_map.py tests/test_semantic_map.py
git commit -m "feat: SemanticMap build_from_cache, on_entity_added, LLM batch classification"
```

---

## Task 3: SemanticMap — get_prompt_snippet

**Files:**
- Modify: `hiris/app/proxy/semantic_map.py`
- Modify: `tests/test_semantic_map.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_semantic_map.py

def test_get_prompt_snippet_contains_sections(tmp_path):
    cache = _make_cache([
        "sensor.shellyem3_power", "light.salotto", "climate.heatpump",
        "binary_sensor.presence_home",
    ])
    # override get_minimal to return states for climate
    cache.get_minimal.return_value = [
        {"id": "climate.heatpump", "state": "heat", "name": "Heatpump",
         "unit": "", "attributes": {"current_temperature": 20.5, "temperature": 21.0, "hvac_action": "heating"}},
    ]
    m = SemanticMap(data_dir=str(tmp_path))
    m.build_from_cache(cache)
    snippet = m.get_prompt_snippet(cache)
    assert "CASA" in snippet
    assert "Energia" in snippet or "energia" in snippet.lower()
    assert "sensor.shellyem3_power" in snippet
    assert "light" in snippet.lower() or "Luci" in snippet


def test_get_prompt_snippet_empty_map(tmp_path):
    cache = _make_cache([])
    m = SemanticMap(data_dir=str(tmp_path))
    snippet = m.get_prompt_snippet(cache)
    assert isinstance(snippet, str)
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_semantic_map.py::test_get_prompt_snippet_contains_sections -v
```
Expected: `AttributeError` for `get_prompt_snippet`.

- [ ] **Step 3: Add get_prompt_snippet to SemanticMap**

Add this method to `SemanticMap` in `semantic_map.py`:

```python
    def get_prompt_snippet(self, entity_cache: Any) -> str:
        """Return compact home context string for injection into system prompt."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%H:%M")

        parts = [f"CASA [mappa agg. {now}]"]

        # Energy meters
        energy_ids = (
            self.get_category("energy_meter") +
            self.get_category("solar_production") +
            self.get_category("grid_import")
        )
        if energy_ids:
            labels = []
            for eid in energy_ids[:6]:
                meta = self._entity_meta.get(eid, {})
                unit = meta.get("unit") or "?"
                labels.append(f"{eid}({unit})")
            parts.append("Energia: " + ", ".join(labels))

        # Climate
        climate_ids = self.get_category("climate_sensor")
        if climate_ids:
            states = entity_cache.get_minimal(climate_ids[:4])
            segs = []
            for e in states:
                seg = f"{e.get('name') or e['id']}: {e['state']}"
                a = e.get("attributes") or {}
                curr = a.get("current_temperature")
                setp = a.get("temperature")
                if curr is not None:
                    seg += f" {curr}°C"
                if setp is not None:
                    seg += f"→{setp}°C"
                segs.append(seg)
            if segs:
                parts.append("Clima: " + ", ".join(segs))

        # Presence
        presence_ids = self.get_category("presence")
        if presence_ids:
            states = entity_cache.get_minimal(presence_ids[:3])
            segs = [f"{e.get('name') or e['id']}({e['state']})" for e in states]
            if segs:
                parts.append("Presenze: " + ", ".join(segs))

        # Lighting
        lighting_ids = self.get_category("lighting")
        if lighting_ids:
            parts.append(f"Luci: {len(lighting_ids)} entità")

        # Appliances
        appliance_ids = self.get_category("appliance")
        if appliance_ids:
            names = [self._entity_meta.get(eid, {}).get("label") or eid for eid in appliance_ids[:4]]
            parts.append("Elettrodomestici: " + ", ".join(names))

        # Unknown pending classification
        unknown_count = len([
            eid for eid in self._categories.get("unknown", [])
            if self._entity_meta.get(eid, {}).get("classified_by") == "pending"
        ])
        if unknown_count:
            parts.append(f"In classificazione: {unknown_count} entità")

        return "\n".join(parts)
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_semantic_map.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/semantic_map.py tests/test_semantic_map.py
git commit -m "feat: SemanticMap.get_prompt_snippet — structured home context for Claude"
```

---

## Task 4: HAClient — entity_registry_updated WebSocket

**Files:**
- Modify: `hiris/app/proxy/ha_client.py`
- Modify: `tests/test_ha_client.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_ha_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.ha_client import HAClient


def test_add_registry_listener():
    ha = HAClient("http://supervisor/core", "token")
    callback = MagicMock()
    ha.add_registry_listener(callback)
    assert callback in ha._registry_listeners
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_ha_client.py::test_add_registry_listener -v
```
Expected: `AttributeError: 'HAClient' object has no attribute 'add_registry_listener'`.

- [ ] **Step 3: Modify HAClient**

In `hiris/app/proxy/ha_client.py`:

**Add `_registry_listeners` to `__init__`:**
```python
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._state_listeners: list[Callable[[dict], None]] = []
        self._registry_listeners: list[Callable[[str, dict], None]] = []
```

**Add `add_registry_listener` method (after `add_state_listener`):**
```python
    def add_registry_listener(self, callback: Callable[[str, dict], None]) -> None:
        """Register callback(entity_id, attributes) for entity_registry_updated events."""
        self._registry_listeners.append(callback)
```

**Modify `_ws_loop` to subscribe to `entity_registry_updated` and dispatch callbacks:**
```python
    async def _ws_loop(self, ws_url: str) -> None:
        try:
            async with self._session.ws_connect(ws_url) as ws:
                auth_req = await ws.receive_json()
                if auth_req.get("type") == "auth_required":
                    token = self._headers["Authorization"].removeprefix("Bearer ")
                    await ws.send_json({"type": "auth", "access_token": token})
                    auth_resp = await ws.receive_json()
                    if auth_resp.get("type") != "auth_ok":
                        logger.error("HA WebSocket auth failed")
                        return

                await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
                await ws.send_json({"id": 2, "type": "subscribe_events", "event_type": "entity_registry_updated"})

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        if data.get("type") != "event":
                            continue
                        event = data.get("event", {})
                        event_type = event.get("event_type")
                        if event_type == "state_changed":
                            for cb in self._state_listeners:
                                cb(event["data"])
                        elif event_type == "entity_registry_updated":
                            action = event.get("data", {}).get("action")
                            if action == "create":
                                eid = event["data"].get("entity_id", "")
                                attrs = event["data"].get("changes", {})
                                for cb in self._registry_listeners:
                                    cb(eid, attrs)
        except Exception as exc:
            logger.warning("HA WebSocket disconnected: %s", exc)
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_ha_client.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/ha_client.py tests/test_ha_client.py
git commit -m "feat: HAClient entity_registry_updated WebSocket listener"
```

---

## Task 5: LLMBackend ABC + ClaudeBackend (simple_chat) + OllamaBackend

**Files:**
- Create: `hiris/app/backends/__init__.py`
- Create: `hiris/app/backends/base.py`
- Create: `hiris/app/backends/claude.py`
- Create: `hiris/app/backends/ollama.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm_router.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.backends.base import LLMBackend
from hiris.app.backends.ollama import OllamaBackend


def test_llm_backend_is_abstract():
    import inspect
    assert inspect.isabstract(LLMBackend)


@pytest.mark.asyncio
async def test_ollama_backend_simple_chat():
    backend = OllamaBackend(url="http://localhost:11434", model="llama3.2")
    mock_resp_data = {"message": {"content": '{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}'}}
    with patch("aiohttp.ClientSession") as MockSession:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.json = AsyncMock(return_value=mock_resp_data)
        ctx.raise_for_status = MagicMock()
        session_inst = MagicMock()
        session_inst.__aenter__ = AsyncMock(return_value=session_inst)
        session_inst.__aexit__ = AsyncMock(return_value=False)
        session_inst.post = MagicMock(return_value=ctx)
        MockSession.return_value = session_inst

        result = await backend.simple_chat([{"role": "user", "content": "classify"}])
        assert isinstance(result, str)
        assert "energy_meter" in result
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_llm_router.py::test_llm_backend_is_abstract -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create backend files**

```python
# hiris/app/backends/__init__.py
```

```python
# hiris/app/backends/base.py
from __future__ import annotations
from abc import ABC, abstractmethod


class LLMBackend(ABC):
    @abstractmethod
    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Single LLM call with no tool loop. Returns text response."""
```

```python
# hiris/app/backends/claude.py
from __future__ import annotations
from .base import LLMBackend


class ClaudeBackend(LLMBackend):
    """Thin wrapper around ClaudeRunner for simple (non-agentic) classification calls."""

    def __init__(self, runner: "ClaudeRunner") -> None:  # type: ignore[name-defined]
        self._runner = runner

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        return await self._runner.simple_chat(messages, system=system)
```

```python
# hiris/app/backends/ollama.py
from __future__ import annotations
import logging
import aiohttp
from .base import LLMBackend

logger = logging.getLogger(__name__)


class OllamaBackend(LLMBackend):
    """OpenAI-compat chat completions via Ollama for low-complexity tasks."""

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/")
        self._model = model

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": self._model, "messages": msgs, "stream": False}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self._url}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("message", {}).get("content", "")
        except Exception as exc:
            logger.warning("OllamaBackend simple_chat failed: %s", exc)
            raise
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_llm_router.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/backends/ tests/test_llm_router.py
git commit -m "feat: LLMBackend ABC, ClaudeBackend, OllamaBackend"
```

---

## Task 6: ClaudeRunner — add simple_chat()

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_claude_runner.py

@pytest.mark.asyncio
async def test_simple_chat_returns_text(runner):
    fake_message = MagicMock()
    fake_message.content = [MagicMock(type="text", text='{"result": "ok"}')]
    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=fake_message)
        runner._client = instance
        result = await runner.simple_chat(
            [{"role": "user", "content": "classify"}],
            system="Classify entities",
        )
    assert result == '{"result": "ok"}'
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_claude_runner.py::test_simple_chat_returns_text -v
```
Expected: `AttributeError: 'ClaudeRunner' object has no attribute 'simple_chat'`.

- [ ] **Step 3: Add simple_chat to ClaudeRunner**

In `hiris/app/claude_runner.py`, add this method to `ClaudeRunner` class (after `reset_agent_usage`):

```python
    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Single API call with no tools and no retry loop — for classification tasks."""
        try:
            response = await self._client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                messages=messages,
            )
            return next((b.text for b in response.content if b.type == "text"), "")
        except Exception as exc:
            logger.error("simple_chat failed: %s", exc)
            return ""
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_claude_runner.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/claude_runner.py tests/test_claude_runner.py
git commit -m "feat: ClaudeRunner.simple_chat for classification tasks"
```

---

## Task 7: LLMRouter — full interface + classify_entities

**Files:**
- Create: `hiris/app/llm_router.py`
- Modify: `tests/test_llm_router.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_llm_router.py
import json
from hiris.app.llm_router import LLMRouter


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    runner.chat = AsyncMock(return_value="response text")
    runner.run_with_actions = AsyncMock(return_value=("text", "OK", "action"))
    runner.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
    runner.last_tool_calls = []
    runner.total_input_tokens = 10
    runner.total_output_tokens = 5
    runner.total_requests = 1
    runner.total_cost_usd = 0.001
    runner.total_rate_limit_errors = 0
    runner.usage_last_reset = "2026-04-22T00:00:00Z"
    runner.get_agent_usage = MagicMock(return_value={"input_tokens": 10})
    runner.reset_agent_usage = MagicMock()
    runner.reset_usage = MagicMock()
    return runner


@pytest.mark.asyncio
async def test_router_chat_delegates_to_runner(mock_runner):
    router = LLMRouter(runner=mock_runner)
    result = await router.chat(user_message="hello", system_prompt="sys")
    mock_runner.chat.assert_awaited_once()
    assert result == "response text"


@pytest.mark.asyncio
async def test_router_classify_entities_no_local_uses_runner(mock_runner):
    router = LLMRouter(runner=mock_runner)
    entities = [{"id": "sensor.test", "state": "100", "name": "Test", "unit": "W"}]
    result = await router.classify_entities(entities)
    mock_runner.simple_chat.assert_awaited_once()
    assert "sensor.test" in result
    assert result["sensor.test"]["role"] == "energy_meter"


@pytest.mark.asyncio
async def test_router_classify_entities_uses_ollama_if_configured(mock_runner):
    router = LLMRouter(runner=mock_runner, local_model_url="http://localhost:11434", local_model_name="llama3.2")
    entities = [{"id": "sensor.test", "state": "100", "name": "Test", "unit": "W"}]
    with patch("hiris.app.llm_router.OllamaBackend") as MockOllama:
        mock_ollama = MagicMock()
        mock_ollama.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
        MockOllama.return_value = mock_ollama
        result = await router.classify_entities(entities)
    mock_ollama.simple_chat.assert_awaited_once()
    mock_runner.simple_chat.assert_not_awaited()


def test_router_proxies_usage_properties(mock_runner):
    router = LLMRouter(runner=mock_runner)
    assert router.total_input_tokens == 10
    assert router.last_tool_calls == []
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_llm_router.py::test_router_chat_delegates_to_runner -v
```
Expected: `ImportError` for `LLMRouter`.

- [ ] **Step 3: Create LLMRouter**

```python
# hiris/app/llm_router.py
from __future__ import annotations
import json
import logging
import re
from typing import Any, Optional
from .backends.ollama import OllamaBackend

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = (
    "Sei un classificatore di entità Home Assistant. "
    "Rispondi SOLO con JSON valido, nessun testo aggiuntivo."
)

_CLASSIFY_ROLES = (
    "energy_meter, solar_production, grid_import, climate_sensor, "
    "presence, lighting, appliance, door_window, electrical, diagnostic, other"
)


class LLMRouter:
    """Wraps ClaudeRunner with the same public interface + classify_entities() routing."""

    def __init__(
        self,
        runner: Any,
        local_model_url: str = "",
        local_model_name: str = "",
    ) -> None:
        self._runner = runner
        self._local_model_url = local_model_url.strip()
        self._local_model_name = local_model_name.strip()

    # ── full agentic loop interface (forwards to ClaudeRunner) ────────────────

    async def chat(self, **kwargs) -> str:
        return await self._runner.chat(**kwargs)

    async def run_with_actions(self, **kwargs):
        return await self._runner.run_with_actions(**kwargs)

    # ── usage properties proxied from runner ──────────────────────────────────

    @property
    def last_tool_calls(self) -> list:
        return getattr(self._runner, "last_tool_calls", [])

    @property
    def total_input_tokens(self) -> int:
        return getattr(self._runner, "total_input_tokens", 0)

    @property
    def total_output_tokens(self) -> int:
        return getattr(self._runner, "total_output_tokens", 0)

    @property
    def total_requests(self) -> int:
        return getattr(self._runner, "total_requests", 0)

    @property
    def total_cost_usd(self) -> float:
        return getattr(self._runner, "total_cost_usd", 0.0)

    @property
    def total_rate_limit_errors(self) -> int:
        return getattr(self._runner, "total_rate_limit_errors", 0)

    @property
    def usage_last_reset(self) -> str:
        return getattr(self._runner, "usage_last_reset", "")

    def get_agent_usage(self, agent_id: str) -> dict:
        return self._runner.get_agent_usage(agent_id)

    def reset_agent_usage(self, agent_id: str) -> None:
        self._runner.reset_agent_usage(agent_id)

    def reset_usage(self) -> None:
        self._runner.reset_usage()

    # ── low-complexity classification routing ─────────────────────────────────

    async def classify_entities(self, entities: list[dict]) -> dict[str, dict]:
        """Classify entities via LLM. Routes to Ollama if configured, else Claude.

        Returns {entity_id: {role, label, confidence}}.
        """
        if not entities:
            return {}

        batch_text = "\n".join(
            f"- {e['id']}: state={e.get('state', 'unknown')}, "
            f"name={e.get('name', '')}, unit={e.get('unit', '')}"
            for e in entities
        )
        user_msg = (
            f"Classifica queste entità HA. Restituisci JSON:\n"
            f"{{\"entity_id\": {{\"role\": \"...\", \"label\": \"...\", \"confidence\": 0.0}}}}\n\n"
            f"Ruoli validi: {_CLASSIFY_ROLES}\n\n"
            f"Entità:\n{batch_text}\n\n"
            f"Rispondi con SOLO il JSON."
        )
        messages = [{"role": "user", "content": user_msg}]

        if self._local_model_url and self._local_model_name:
            backend = OllamaBackend(url=self._local_model_url, model=self._local_model_name)
            raw = await backend.simple_chat(messages, system=_CLASSIFY_SYSTEM)
        else:
            raw = await self._runner.simple_chat(messages, system=_CLASSIFY_SYSTEM)

        return _parse_classify_response(raw)


def _parse_classify_response(raw: str) -> dict[str, dict]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    logger.warning("classify_entities: could not parse JSON from LLM response: %.200s", raw)
    return {}
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/test_llm_router.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/llm_router.py tests/test_llm_router.py
git commit -m "feat: LLMRouter — forward interface + classify_entities with Ollama routing"
```

---

## Task 8: server.py — wire SemanticMap + LLMRouter

**Files:**
- Modify: `hiris/app/server.py`

- [ ] **Step 1: Modify `_on_startup` in server.py**

Replace the entire `_on_startup` function with:

```python
async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner
    from .proxy.semantic_map import SemanticMap
    from .llm_router import LLMRouter

    ha_client = HAClient(
        base_url=os.environ.get("HA_BASE_URL", "http://supervisor/core"),
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
    )
    await ha_client.start()
    app["ha_client"] = ha_client

    entity_cache = EntityCache()
    try:
        await entity_cache.load(ha_client)
    except Exception as exc:
        logger.warning("EntityCache load failed: %s", exc)
    try:
        await entity_cache.load_area_registry(ha_client)
    except Exception as exc:
        logger.warning("Area registry load failed: %s", exc)
    ha_client.add_state_listener(entity_cache.on_state_changed)
    app["entity_cache"] = entity_cache

    data_path = os.environ.get("AGENTS_DATA_PATH", "/data/agents.json")
    data_dir = os.path.dirname(os.path.abspath(data_path))
    app["data_dir"] = data_dir

    # Build semantic map
    semantic_map = SemanticMap(data_dir=data_dir)
    semantic_map.load()
    ambiguous = semantic_map.build_from_cache(entity_cache)
    app["semantic_map"] = semantic_map
    ha_client.add_registry_listener(semantic_map.on_entity_added)

    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
    engine.set_entity_cache(entity_cache)
    await engine.start()
    app["engine"] = engine

    embedding_index = EmbeddingIndex()
    asyncio.create_task(
        embedding_index.build(entity_cache.get_all_useful()),
        name="embedding_index_build",
    )
    app["embedding_index"] = embedding_index

    notify_config = {
        "ha_notify_service": os.environ.get("HA_NOTIFY_SERVICE", "notify.notify"),
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "retropanel_url": os.environ.get("RETROPANEL_URL", "http://retropanel:8098"),
    }
    app["theme"] = os.environ.get("THEME", "auto")
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    usage_path = os.environ.get("USAGE_DATA_PATH", "/data/usage.json")
    primary_model = os.environ.get("PRIMARY_MODEL", "claude-sonnet-4-6")
    local_model_url = os.environ.get("LOCAL_MODEL_URL", "")
    local_model_name = os.environ.get("LOCAL_MODEL_NAME", "")

    if api_key:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            usage_path=usage_path,
            entity_cache=entity_cache,
            embedding_index=embedding_index,
            semantic_map=semantic_map,
        )
        router = LLMRouter(
            runner=runner,
            local_model_url=local_model_url,
            local_model_name=local_model_name,
        )
        semantic_map.set_router(router)
        app["claude_runner"] = runner   # backward compat
        app["llm_router"] = router
        engine.set_claude_runner(router)

        # Kick off LLM classification for ambiguous entities (background, non-blocking)
        if ambiguous:
            asyncio.create_task(
                semantic_map._classify_unknown_batch(),
                name="semantic_map_initial_classify",
            )
    else:
        app["claude_runner"] = None
        app["llm_router"] = None
```

- [ ] **Step 2: Add `semantic_map` param to ClaudeRunner.__init__**

In `hiris/app/claude_runner.py`, modify `ClaudeRunner.__init__`:

```python
    def __init__(
        self,
        api_key: str,
        ha_client: HAClient,
        notify_config: dict,
        usage_path: str = "",
        entity_cache=None,
        embedding_index=None,
        semantic_map=None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._ha = ha_client
        self._notify_config = notify_config
        self._usage_path = usage_path
        self._cache = entity_cache
        self._index = embedding_index
        self._semantic_map = semantic_map
        self.last_tool_calls: list[dict] = []
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_requests: int = 0
        self.total_cost_usd: float = 0.0
        self.total_rate_limit_errors: int = 0
        self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
        self._per_agent_usage: dict[str, dict] = {}
        self._load_usage()
```

- [ ] **Step 3: Run full test suite**

```
cd hiris && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all tests pass (server.py changes are startup-only, not directly tested by unit tests).

- [ ] **Step 4: Commit**

```bash
git add hiris/app/server.py hiris/app/claude_runner.py
git commit -m "feat: wire SemanticMap + LLMRouter in server.py startup"
```

---

## Task 9: handlers_chat.py — use llm_router + inject map snippet

**Files:**
- Modify: `hiris/app/api/handlers_chat.py`

- [ ] **Step 1: Modify handle_chat to use llm_router and inject map snippet**

Replace `handle_chat` in `hiris/app/api/handlers_chat.py`:

```python
import logging

from aiohttp import web

from ..chat_store import load_history, append_messages

logger = logging.getLogger(__name__)

_RAG_TOP_K = 12


def _prefetch_context(message: str, app: web.Application) -> str:
    """Semantic search → fetch current states → return compact context block."""
    idx = app.get("embedding_index")
    cache = app.get("entity_cache")
    if not idx or not cache or not idx.ready:
        return ""
    ids = idx.search(message, top_k=_RAG_TOP_K)
    if not ids:
        return ""
    entities = cache.get_minimal(ids)
    if not entities:
        return ""
    lines = []
    for e in entities:
        name = e.get("name") or e["id"]
        seg = f"- {name} [{e['id']}]: {e['state']}"
        if e.get("unit"):
            seg += f" {e['unit']}"
        a = e.get("attributes") or {}
        curr = a.get("current_temperature")
        setp = a.get("temperature")
        action = a.get("hvac_action")
        if curr is not None:
            seg += f", corrente {curr}°C"
        if setp is not None:
            seg += f" → setpoint {setp}°C"
        if action:
            seg += f" ({action})"
        lines.append(seg)
    return "Entità rilevanti (dati in tempo reale):\n" + "\n".join(lines)


async def handle_chat(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response(
            {"error": "Claude runner not configured — set CLAUDE_API_KEY"}, status=503
        )

    agent_id = body.get("agent_id")
    data_dir = request.app.get("data_dir", "/data")
    engine = request.app["engine"]

    agent = None
    if agent_id:
        agent = engine.get_agent(agent_id)
    if agent is None:
        agent = engine.get_default_agent()

    effective_agent_id = getattr(agent, "id", None) if agent else None

    history = load_history(effective_agent_id, data_dir) if effective_agent_id else []

    max_turns = getattr(agent, "max_chat_turns", 0) if agent else 0
    if max_turns > 0:
        turn_count = sum(1 for m in history if m["role"] == "user")
        if turn_count >= max_turns:
            return web.json_response({
                "error": "max_turns_reached",
                "turns": turn_count,
                "limit": max_turns,
            })

    _MAX_CONTEXT = 30
    context_history = history[-_MAX_CONTEXT:] if len(history) > _MAX_CONTEXT else history

    if agent:
        if agent.strategic_context:
            system_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
        else:
            system_prompt = agent.system_prompt or (
                "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
            )
        allowed_tools = agent.allowed_tools or None
        allowed_entities = agent.allowed_entities or None
        allowed_services = agent.allowed_services or None
    else:
        logger.warning("No agent found (requested: %s). Using fallback prompt.", agent_id)
        system_prompt = "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
        allowed_tools = None
        allowed_entities = None
        allowed_services = None

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

    agent_model = getattr(agent, "model", "auto") if agent else "auto"
    agent_max_tokens = getattr(agent, "max_tokens", 4096) if agent else 4096
    agent_type = getattr(agent, "type", "chat") if agent else "chat"
    agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False
    agent_require_confirmation = getattr(agent, "require_confirmation", False) if agent else False

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
    )

    if effective_agent_id:
        append_messages(effective_agent_id, [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ], data_dir)

    raw = getattr(runner, "last_tool_calls", None)
    tools_called = raw if isinstance(raw, list) else []
    return web.json_response({"response": response, "debug": {"tools_called": tools_called}})
```

- [ ] **Step 2: Run tests**

```
cd hiris && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add hiris/app/api/handlers_chat.py
git commit -m "feat: handlers_chat uses llm_router, injects semantic map snippet into prompt"
```

---

## Task 10: energy_tools.py — read entity IDs from SemanticMap

**Files:**
- Modify: `hiris/app/tools/energy_tools.py`
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_tools.py

from hiris.app.proxy.semantic_map import SemanticMap


@pytest.mark.asyncio
async def test_get_energy_history_uses_semantic_map(mock_ha, tmp_path):
    """Energy tool must read entity IDs from SemanticMap, not hardcoded list."""
    smap = SemanticMap(data_dir=str(tmp_path))
    smap._add_entity("sensor.real_power", "energy_meter", "Real meter", unit="W", classified_by="rules")
    smap._add_entity("sensor.real_solar", "solar_production", "Solar", unit="W", classified_by="rules")

    mock_ha.get_history = AsyncMock(return_value=[
        {"entity_id": "sensor.real_power", "state": "250.0", "last_changed": "2026-04-22T10:00:00"},
    ])

    result = await get_energy_history(mock_ha, days=1, semantic_map=smap)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "sensor.real_power"
    called_ids = mock_ha.get_history.call_args[1]["entity_ids"]
    assert "sensor.real_power" in called_ids
    assert "sensor.real_solar" in called_ids
    # Must NOT contain the old hardcoded placeholders
    assert "sensor.energy_consumption" not in called_ids


@pytest.mark.asyncio
async def test_get_energy_history_returns_error_if_no_map_entities(mock_ha, tmp_path):
    smap = SemanticMap(data_dir=str(tmp_path))  # empty map
    result = await get_energy_history(mock_ha, days=1, semantic_map=smap)
    assert isinstance(result, dict)
    assert "error" in result
```

- [ ] **Step 2: Run to confirm failure**

```
cd hiris && python -m pytest tests/test_tools.py::test_get_energy_history_uses_semantic_map -v
```
Expected: `TypeError` because `get_energy_history` doesn't accept `semantic_map` param.

- [ ] **Step 3: Modify energy_tools.py**

Replace the content of `hiris/app/tools/energy_tools.py`:

```python
from __future__ import annotations
from collections import defaultdict
from typing import Optional
from ..proxy.ha_client import HAClient

TOOL_DEF = {
    "name": "get_energy_history",
    "description": (
        "Get energy history for the last N days. "
        "Returns compressed daily records: "
        "[{id, day (YYYY-MM-DD), start (first reading), end (last reading), n (samples)}]. "
        "Use start/end to compute daily delta. "
        "Source entities: consumption meters, solar production, grid import/export."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days of history to retrieve (1-30)",
                "minimum": 1,
                "maximum": 30,
            }
        },
        "required": ["days"],
    },
}


def _compress_energy_history(raw: list[dict]) -> list[dict]:
    """Group raw HA history records by (entity_id, day).

    Input:  [{"entity_id": ..., "state": ..., "last_changed": "YYYY-MM-DDTHH:..."}]
    Output: [{"id": ..., "day": "YYYY-MM-DD", "start": ..., "end": ..., "n": int}]
    """
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in raw:
        eid = item.get("entity_id", "")
        ts = item.get("last_changed", "")
        if not eid or not ts:
            continue
        day = ts[:10]
        buckets[(eid, day)].append(item.get("state", ""))
    result = []
    for (eid, day), readings in sorted(buckets.items()):
        result.append({"id": eid, "day": day, "start": readings[0], "end": readings[-1], "n": len(readings)})
    return result


async def get_energy_history(
    ha: HAClient,
    days: int,
    semantic_map: Optional[object] = None,
) -> list[dict] | dict:
    if semantic_map is not None:
        entity_ids = (
            semantic_map.get_category("energy_meter") +
            semantic_map.get_category("solar_production") +
            semantic_map.get_category("grid_import")
        )
        if not entity_ids:
            return {
                "error": "Nessun contatore energia nella mappa semantica.",
                "hint": "Attendi la classificazione automatica o aggiungi sensori energia.",
            }
    else:
        # Fallback when no map — return informative error
        return {
            "error": "Mappa semantica non disponibile.",
            "hint": "Il sistema sta inizializzando la mappa degli sensori.",
        }
    raw = await ha.get_history(entity_ids=entity_ids, days=days)
    return _compress_energy_history(raw)
```

- [ ] **Step 4: Modify ClaudeRunner._dispatch_tool to pass semantic_map**

In `hiris/app/claude_runner.py`, find the `get_energy_history` dispatch line and update it:

```python
            if name == "get_energy_history":
                return await get_energy_history(self._ha, inputs["days"], semantic_map=self._semantic_map)
```

- [ ] **Step 5: Update the old test in test_tools.py that used hardcoded IDs**

The old `test_get_energy_history_returns_compressed_format` test imports `ENERGY_ENTITY_IDS` which no longer exists. Update it:

```python
@pytest.mark.asyncio
async def test_get_energy_history_returns_compressed_format(mock_ha, tmp_path):
    from hiris.app.proxy.semantic_map import SemanticMap
    smap = SemanticMap(data_dir=str(tmp_path))
    smap._add_entity("sensor.energy_consumption", "energy_meter", "Consumption", unit="kWh", classified_by="rules")
    smap._add_entity("sensor.solar_production", "solar_production", "Solar", unit="W", classified_by="rules")
    smap._add_entity("sensor.grid_import", "grid_import", "Grid Import", unit="kWh", classified_by="rules")
    smap._add_entity("sensor.grid_export", "grid_import", "Grid Export", unit="kWh", classified_by="rules")

    result = await get_energy_history(mock_ha, days=1, semantic_map=smap)
    assert len(result) == 4
    ids = [r["id"] for r in result]
    assert "sensor.energy_consumption" in ids
    assert "sensor.solar_production" in ids
    rec = next(r for r in result if r["id"] == "sensor.energy_consumption")
    assert rec["day"] == "2026-04-17"
    assert rec["start"] == "1.5"
    assert rec["end"] == "1.5"
    assert rec["n"] == 1
```

Also remove the `from hiris.app.tools.energy_tools import get_energy_history, ENERGY_ENTITY_IDS` import and replace with `from hiris.app.tools.energy_tools import get_energy_history`.

- [ ] **Step 6: Run tests**

```
cd hiris && python -m pytest tests/test_tools.py tests/test_claude_runner.py -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add hiris/app/tools/energy_tools.py hiris/app/claude_runner.py tests/test_tools.py
git commit -m "fix: energy_tools reads entity IDs from SemanticMap instead of hardcoded placeholders"
```

---

## Task 11: ha_tools.py — enrich get_home_status with semantic labels

**Files:**
- Modify: `hiris/app/tools/ha_tools.py`

- [ ] **Step 1: Identify the get_home_status function**

In `hiris/app/tools/ha_tools.py`, find `get_home_status`. It currently calls `entity_cache.get_all_useful()` and returns the list. We want to enrich it with semantic labels when a map is available.

- [ ] **Step 2: Modify get_home_status**

Find the `get_home_status` function and update its signature and logic. Locate the existing function (look for `def get_home_status`) and replace it:

```python
def get_home_status(entity_cache, semantic_map=None) -> list[dict]:
    """Return all useful entity states, enriched with semantic labels if map is available."""
    entities = entity_cache.get_all_useful() if entity_cache else []
    if semantic_map is None:
        return entities
    enriched = []
    for e in entities:
        eid = e["id"]
        meta = semantic_map._entity_meta.get(eid)
        if meta and meta.get("label"):
            e = dict(e)
            e["semantic_label"] = meta["label"]
            e["semantic_role"] = meta.get("role", "")
        enriched.append(e)
    return enriched
```

- [ ] **Step 3: Update ClaudeRunner._dispatch_tool for get_home_status**

In `hiris/app/claude_runner.py`, find the `get_home_status` dispatch and update:

```python
            if name == "get_home_status":
                return get_home_status(self._cache, semantic_map=self._semantic_map) if self._cache else []
```

- [ ] **Step 4: Run tests**

```
cd hiris && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/ha_tools.py hiris/app/claude_runner.py
git commit -m "feat: get_home_status enriched with semantic labels from SemanticMap"
```

---

## Task 12: config.yaml — new configuration options

**Files:**
- Modify: `hiris/config.yaml`

- [ ] **Step 1: Add new options to config.yaml**

In `hiris/config.yaml`, add to `options` and `schema`:

```yaml
options:
  claude_api_key: ""
  log_level: "info"
  theme: "auto"
  primary_model: "claude-sonnet-4-6"
  local_model_url: ""
  local_model_name: ""
schema:
  claude_api_key: password
  log_level: "list(debug|info|warning|error)"
  theme: "list(light|dark|auto)"
  primary_model: str
  local_model_url: str
  local_model_name: str
```

- [ ] **Step 2: Update run.sh to pass new env vars**

Replace the entire `hiris/run.sh` with:

```bash
#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export THEME=$(bashio::config 'theme' 'auto')
export PRIMARY_MODEL=$(bashio::config 'primary_model' 'claude-sonnet-4-6')
export LOCAL_MODEL_URL=$(bashio::config 'local_model_url' '')
export LOCAL_MODEL_NAME=$(bashio::config 'local_model_name' '')

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"
bashio::log.info "Primary model: ${PRIMARY_MODEL}"

cd /usr/lib/hiris
exec python3 -m app.main
```

- [ ] **Step 3: Run tests to confirm nothing broken**

```
cd hiris && python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add hiris/config.yaml hiris/run.sh
git commit -m "feat: config.yaml — primary_model, local_model_url, local_model_name options"
```

---

## Task 13: Final integration — run full test suite + version bump

- [ ] **Step 1: Run the complete test suite**

```
cd hiris && python -m pytest tests/ -v 2>&1 | tee /tmp/test_results.txt; tail -20 /tmp/test_results.txt
```
Expected: all tests pass. Fix any failures before proceeding.

- [ ] **Step 2: Verify imports**

```
cd hiris && python -c "
from app.proxy.semantic_map import SemanticMap, classify_by_rules
from app.llm_router import LLMRouter
from app.backends.base import LLMBackend
from app.backends.claude import ClaudeBackend
from app.backends.ollama import OllamaBackend
from app.tools.energy_tools import get_energy_history
print('All imports OK')
"
```
Expected: `All imports OK`.

- [ ] **Step 3: Bump version to 0.2.0**

In `hiris/app/server.py`, update the health endpoint version string:
```python
    return web.json_response({"status": "ok", "version": "0.2.0"})
```

In `hiris/config.yaml`, update:
```yaml
version: "0.2.0"
```

In `tests/test_api.py`, update any version assertions from `"0.1.9"` to `"0.2.0"`.

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "feat: semantic home map + LLM router — v0.2.0

- SemanticMap: rule-based + LLM batch entity classification
- SemanticMap: persists to /data/home_semantic_map.json
- SemanticMap: WebSocket hook for new HA devices (entity_registry_updated)
- SemanticMap: structured home context injected into system prompt
- LLMRouter: pluggable backend, routes classify_entities() to Ollama if configured
- energy_tools: reads entity IDs from SemanticMap (fixes empty history bug)
- get_home_status: enriched with semantic labels
- config: primary_model, local_model_url, local_model_name options"
```
