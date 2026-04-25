# Token Optimization Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ridurre il consumo di token nelle 5 aree di spreco ancora aperte dopo la Phase 1: HOME_PROFILE TTL cache, area registry cache, compressione energy/weather, pre-injection per agenti proattivi.

**Architecture:** Ogni task è indipendente e chirurgico su 1-3 file. Nessuna modifica all'interfaccia pubblica delle API HTTP. La compressione di energy/weather cambia il formato della tool result (non il tool schema esterno); i test vengono aggiornati di conseguenza. La pre-injection inietta il contesto entità nel `user_message` degli agenti monitor/reactive/preventive prima di chiamare Claude, evitando 1-2 round-trip di tool call.

**Tech Stack:** Python 3.11, aiohttp, anthropic SDK, pytest + pytest-asyncio. Zero nuove dipendenze.

---

## File Structure

| File | Modifica |
|---|---|
| `hiris/app/proxy/home_profile.py` | Aggiunge `get_cached_home_profile()` con TTL 60s |
| `hiris/app/proxy/entity_cache.py` | Aggiunge `_area_map`, `load_area_registry()`, `get_area_map()` |
| `hiris/app/tools/ha_tools.py` | `get_area_entities()` accetta `entity_cache` opzionale, usa la cache |
| `hiris/app/tools/energy_tools.py` | Aggiunge `_compress_energy_history()`, modifica `get_energy_history()` |
| `hiris/app/tools/weather_tools.py` | Aggiunge `_compress_weather()`, modifica `get_weather_forecast()` |
| `hiris/app/claude_runner.py` | Usa `get_cached_home_profile()`, passa `entity_cache` a `get_area_entities` |
| `hiris/app/agent_engine.py` | Aggiunge `set_entity_cache()`, `_build_entity_context()`, modifica `_run_agent()` |
| `hiris/app/server.py` | Chiama `load_area_registry()`, `engine.set_entity_cache()` |
| `tests/test_home_profile.py` | Aggiunge test TTL cache |
| `tests/test_entity_cache.py` | Aggiunge test area registry cache |
| `tests/test_tools.py` | Aggiorna test energy/weather (formato cambiato), aggiunge test area cache |
| `tests/test_agent_engine.py` | Aggiunge test pre-injection |

---

## Task 1: HOME_PROFILE TTL cache

**Perché:** `generate_home_profile()` è chiamata ad ogni chat call e include un timestamp `HH:MM` che cambia ogni minuto. Questo invalida la Anthropic API prompt cache ad ogni minuto. Con TTL 60s la stringa è stabile per un intero minuto → le chiamate consecutive riusano la cached system prompt di Anthropic → risparmio fino al 90% sui token input cached.

**Files:**
- Modify: `hiris/app/proxy/home_profile.py`
- Modify: `hiris/app/claude_runner.py:191`
- Modify: `tests/test_home_profile.py`

- [ ] **Step 1: Scrivi i test fallenti per il TTL cache**

Aggiungi in fondo a `tests/test_home_profile.py`:

```python
import time
from unittest.mock import patch
from hiris.app.proxy.home_profile import get_cached_home_profile, _reset_profile_cache


def test_cached_home_profile_returns_string():
    _reset_profile_cache()
    cache = _make_cache([])
    result = get_cached_home_profile(cache)
    assert result.startswith("CASA [aggiornato")


def test_cached_home_profile_hit_within_ttl():
    _reset_profile_cache()
    cache = _make_cache([
        {"id": "light.a", "state": "on", "name": "A", "unit": ""},
    ])
    t0 = 1000.0
    with patch("hiris.app.proxy.home_profile._now", return_value=t0):
        first = get_cached_home_profile(cache, ttl=60.0)
    with patch("hiris.app.proxy.home_profile._now", return_value=t0 + 30.0):
        second = get_cached_home_profile(cache, ttl=60.0)
    assert first == second
    # get_all_useful deve essere chiamato 1 sola volta (cache hit)
    assert cache.get_all_useful.call_count == 1


def test_cached_home_profile_miss_after_ttl():
    _reset_profile_cache()
    cache = _make_cache([])
    t0 = 1000.0
    with patch("hiris.app.proxy.home_profile._now", return_value=t0):
        get_cached_home_profile(cache, ttl=60.0)
    with patch("hiris.app.proxy.home_profile._now", return_value=t0 + 61.0):
        get_cached_home_profile(cache, ttl=60.0)
    assert cache.get_all_useful.call_count == 2


def test_reset_profile_cache_forces_regeneration():
    _reset_profile_cache()
    cache = _make_cache([])
    t0 = 1000.0
    with patch("hiris.app.proxy.home_profile._now", return_value=t0):
        get_cached_home_profile(cache, ttl=600.0)
    _reset_profile_cache()
    with patch("hiris.app.proxy.home_profile._now", return_value=t0 + 1.0):
        get_cached_home_profile(cache, ttl=600.0)
    assert cache.get_all_useful.call_count == 2
```

- [ ] **Step 2: Verifica che i test falliscano**

```
py -3 -m pytest tests/test_home_profile.py -x -q
```

Atteso: FAIL — `ImportError: cannot import name 'get_cached_home_profile'`

- [ ] **Step 3: Implementa la TTL cache in `home_profile.py`**

Sostituisci l'intero contenuto di `hiris/app/proxy/home_profile.py` con:

```python
from __future__ import annotations
import time
from datetime import datetime, timezone
from .entity_cache import EntityCache

# ── module-level cache ────────────────────────────────────────────────────────
_cached_profile: str = ""
_cached_at: float = 0.0


def _now() -> float:
    """Indirection for monkeypatching in tests."""
    return time.monotonic()


def _reset_profile_cache() -> None:
    """Force cache invalidation — used in tests."""
    global _cached_profile, _cached_at
    _cached_profile = ""
    _cached_at = 0.0


# ── public API ────────────────────────────────────────────────────────────────

def generate_home_profile(entity_cache: EntityCache) -> str:
    """Generate fresh profile string (no caching). Used internally and in tests."""
    now = datetime.now(timezone.utc).strftime("%H:%M")
    entities = entity_cache.get_all_useful()

    on_entities = [e for e in entities if e.get("state") == "on"]
    on_by_domain: dict[str, int] = {}
    for e in on_entities:
        domain = e["id"].split(".")[0]
        on_by_domain[domain] = on_by_domain.get(domain, 0) + 1

    on_count = len(on_entities)
    on_summary = (
        ", ".join(f"{d}({n})" for d, n in sorted(on_by_domain.items()))
        if on_by_domain else "nessuno"
    )

    climate = [e for e in entities if e["id"].startswith("climate.")]
    climate_str = (
        ", ".join(f"{(e.get('name') or e['id'])}: {e['state']}" for e in climate[:3])
        if climate else "n/a"
    )

    return (
        f"CASA [aggiornato {now}]:\n"
        f"Accesi({on_count}): {on_summary}\n"
        f"Clima: {climate_str}"
    )


def get_cached_home_profile(entity_cache: EntityCache, ttl: float = 60.0) -> str:
    """Return HOME_PROFILE, regenerating at most once per `ttl` seconds.

    Keeping the system prompt string stable within the TTL window maximises
    Anthropic API prompt-cache hits, cutting cached-input token cost by ~90%.
    TTL defaults to 60 s (aligned with the HH:MM timestamp granularity).
    """
    global _cached_profile, _cached_at
    ts = _now()
    if _cached_profile and (ts - _cached_at) < ttl:
        return _cached_profile
    _cached_profile = generate_home_profile(entity_cache)
    _cached_at = ts
    return _cached_profile
```

- [ ] **Step 4: Aggiorna `claude_runner.py` riga 191**

In `hiris/app/claude_runner.py` modifica la riga dell'import e quella di utilizzo:

```python
# riga 26 — cambia import
from .proxy.home_profile import generate_home_profile, get_cached_home_profile
```

```python
# riga 191 — usa la versione cached
if self._cache is not None:
    effective_system = f"{effective_system}\n\n---\n\n{get_cached_home_profile(self._cache)}"
```

- [ ] **Step 5: Verifica che i test passino**

```
py -3 -m pytest tests/test_home_profile.py -v
```

Atteso: tutti PASS (vecchi + nuovi).

- [ ] **Step 6: Suite completa**

```
py -3 -m pytest tests/ -q
```

Atteso: 150+ passed, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add hiris/app/proxy/home_profile.py hiris/app/claude_runner.py tests/test_home_profile.py
git commit -m "perf: add 60s TTL cache for HOME_PROFILE to maximise Anthropic prompt-cache hits"
```

---

## Task 2: Area registry cache in EntityCache

**Perché:** `get_area_entities()` fa 2 richieste HTTP a HA (`area_registry` + `entity_registry`) ad ogni chiamata. Le aree cambiano raramente. Carichiamo entrambe all'avvio, le mettiamo in cache su EntityCache.

**Files:**
- Modify: `hiris/app/proxy/entity_cache.py`
- Modify: `hiris/app/tools/ha_tools.py`
- Modify: `hiris/app/claude_runner.py:270`
- Modify: `hiris/app/server.py`
- Modify: `tests/test_entity_cache.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Scrivi test fallenti per area cache in `test_entity_cache.py`**

Aggiungi in fondo a `tests/test_entity_cache.py`:

```python
@pytest.mark.asyncio
async def test_load_area_registry_builds_area_map():
    mock_ha = AsyncMock()
    mock_ha.get_area_registry = AsyncMock(return_value=[
        {"area_id": "cucina_id", "name": "Cucina"},
        {"area_id": "soggiorno_id", "name": "Soggiorno"},
    ])
    mock_ha.get_entity_registry = AsyncMock(return_value=[
        {"entity_id": "light.luce_cucina",    "area_id": "cucina_id"},
        {"entity_id": "switch.presa_cucina",  "area_id": "cucina_id"},
        {"entity_id": "light.luce_soggiorno", "area_id": "soggiorno_id"},
        {"entity_id": "sensor.no_area",       "area_id": None},
    ])
    cache = EntityCache()
    await cache.load_area_registry(mock_ha)
    area_map = cache.get_area_map()
    assert "Cucina" in area_map
    assert "light.luce_cucina" in area_map["Cucina"]
    assert "switch.presa_cucina" in area_map["Cucina"]
    assert "Soggiorno" in area_map
    assert "light.luce_soggiorno" in area_map["Soggiorno"]
    assert "__no_area__" in area_map
    assert "sensor.no_area" in area_map["__no_area__"]


def test_get_area_map_returns_empty_before_load():
    cache = EntityCache()
    assert cache.get_area_map() == {}


@pytest.mark.asyncio
async def test_load_area_registry_survives_empty_registries():
    mock_ha = AsyncMock()
    mock_ha.get_area_registry = AsyncMock(return_value=[])
    mock_ha.get_entity_registry = AsyncMock(return_value=[])
    cache = EntityCache()
    await cache.load_area_registry(mock_ha)
    assert cache.get_area_map() == {}
```

- [ ] **Step 2: Verifica che i test falliscano**

```
py -3 -m pytest tests/test_entity_cache.py -x -q
```

Atteso: FAIL — `AttributeError: 'EntityCache' object has no attribute 'load_area_registry'`

- [ ] **Step 3: Implementa `load_area_registry` e `get_area_map` in `entity_cache.py`**

In `hiris/app/proxy/entity_cache.py`, modifica `EntityCache.__init__` aggiungendo:

```python
def __init__(self) -> None:
    self._states: dict[str, dict] = {}
    self._by_domain: dict[str, list[str]] = {}
    self._area_map: dict[str, list[str]] = {}
```

Aggiungi i due nuovi metodi dopo `get_all()`:

```python
async def load_area_registry(self, ha_client) -> None:
    """Load area→entity mapping from HA registries. Cached until next call."""
    areas = await ha_client.get_area_registry()
    entities = await ha_client.get_entity_registry()
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
    self._area_map = result

def get_area_map(self) -> dict[str, list[str]]:
    """Return cached area→[entity_id] map. Empty dict if not yet loaded."""
    return self._area_map
```

- [ ] **Step 4: Scrivi test fallenti per `get_area_entities` con cache in `test_tools.py`**

Aggiungi in fondo a `tests/test_tools.py` (dopo i test `get_area_entities` esistenti):

```python
@pytest.mark.asyncio
async def test_get_area_entities_uses_cache_when_populated():
    """Quando la cache è popolata non deve fare chiamate HTTP."""
    cache = MagicMock()
    cache.get_area_map.return_value = {"Cucina": ["light.cucina", "switch.presa"]}
    ha = AsyncMock()
    result = await get_area_entities(ha, entity_cache=cache)
    ha.get_area_registry.assert_not_called()
    ha.get_entity_registry.assert_not_called()
    assert result == {"Cucina": ["light.cucina", "switch.presa"]}


@pytest.mark.asyncio
async def test_get_area_entities_falls_back_to_http_when_cache_empty():
    """Quando la cache è vuota deve fare le chiamate HTTP come prima."""
    cache = MagicMock()
    cache.get_area_map.return_value = {}
    ha = AsyncMock()
    ha.get_area_registry = AsyncMock(return_value=[
        {"area_id": "cucina_id", "name": "Cucina"},
    ])
    ha.get_entity_registry = AsyncMock(return_value=[
        {"entity_id": "light.cucina", "area_id": "cucina_id"},
    ])
    result = await get_area_entities(ha, entity_cache=cache)
    ha.get_area_registry.assert_awaited_once()
    assert "Cucina" in result
```

- [ ] **Step 5: Verifica che i nuovi test tools falliscano**

```
py -3 -m pytest tests/test_tools.py::test_get_area_entities_uses_cache_when_populated -x -q
```

Atteso: FAIL — `TypeError: get_area_entities() got unexpected keyword argument 'entity_cache'`

- [ ] **Step 6: Modifica `get_area_entities` in `ha_tools.py`**

In `hiris/app/tools/ha_tools.py`, sostituisci la funzione `get_area_entities`:

```python
async def get_area_entities(
    ha: HAClient,
    entity_cache: EntityCache | None = None,
) -> dict[str, list[str]]:
    """Return area→[entity_id] map. Uses EntityCache if populated, else HTTP fallback."""
    if entity_cache is not None:
        cached = entity_cache.get_area_map()
        if cached:
            return cached

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
```

- [ ] **Step 7: Aggiorna `claude_runner.py` per passare la cache**

In `hiris/app/claude_runner.py` riga ~270, modifica il dispatch di `get_area_entities`:

```python
if name == "get_area_entities":
    return await get_area_entities(self._ha, entity_cache=self._cache)
```

- [ ] **Step 8: Aggiorna `server.py` per caricare la area registry all'avvio**

In `hiris/app/server.py`, subito dopo il blocco `entity_cache.load()`:

```python
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
```

- [ ] **Step 9: Verifica che tutti i test passino**

```
py -3 -m pytest tests/test_entity_cache.py tests/test_tools.py -v
```

Atteso: tutti PASS (vecchi + nuovi).

- [ ] **Step 10: Suite completa**

```
py -3 -m pytest tests/ -q
```

Atteso: 155+ passed, 0 failed.

- [ ] **Step 11: Commit**

```bash
git add hiris/app/proxy/entity_cache.py hiris/app/tools/ha_tools.py \
        hiris/app/claude_runner.py hiris/app/server.py \
        tests/test_entity_cache.py tests/test_tools.py
git commit -m "perf: cache area/entity registry in EntityCache — zero HTTP on get_area_entities"
```

---

## Task 3: Comprimi output di `get_energy_history`

**Perché:** HA history API ritorna 1 lettura al minuto per entità. 4 entità × 7 giorni = ~40.000 letture = ~2.000 token. Raggruppando per (entità, giorno) con prima/ultima lettura otteniamo 28 record = ~150 token (−92%).

**Formato output nuovo:** `[{"id": str, "day": "YYYY-MM-DD", "start": str, "end": str, "n": int}]`

- `start` = prima lettura del giorno (valore del contatore)
- `end` = ultima lettura del giorno
- `n` = numero di campioni (per diagnostica)

**Files:**
- Modify: `hiris/app/tools/energy_tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Aggiorna il test esistente e aggiungi test per la compressione**

In `tests/test_tools.py`, **sostituisci** `test_get_energy_history_returns_list` con:

```python
@pytest.mark.asyncio
async def test_get_energy_history_returns_compressed_format(mock_ha):
    result = await get_energy_history(mock_ha, days=1)
    # 4 entità × 1 giorno = 4 record compressi
    assert len(result) == 4
    ids = [r["id"] for r in result]
    assert "sensor.energy_consumption" in ids
    assert "sensor.solar_production" in ids
    # ogni record deve avere il formato compresso
    rec = next(r for r in result if r["id"] == "sensor.energy_consumption")
    assert rec["day"] == "2026-04-17"
    assert rec["start"] == "1.5"
    assert rec["end"] == "1.5"
    assert rec["n"] == 1
    mock_ha.get_history.assert_awaited_once_with(entity_ids=ENERGY_ENTITY_IDS, days=1)
```

Aggiungi poi (come nuovi test, non in sostituzione del precedente):

```python
from hiris.app.tools.energy_tools import _compress_energy_history


def test_compress_energy_history_groups_by_entity_and_day():
    raw = [
        {"entity_id": "sensor.e", "state": "100.0", "last_changed": "2026-04-17T08:00:00"},
        {"entity_id": "sensor.e", "state": "102.0", "last_changed": "2026-04-17T12:00:00"},
        {"entity_id": "sensor.e", "state": "105.0", "last_changed": "2026-04-17T20:00:00"},
        {"entity_id": "sensor.e", "state": "107.0", "last_changed": "2026-04-18T09:00:00"},
    ]
    result = _compress_energy_history(raw)
    assert len(result) == 2
    day17 = next(r for r in result if r["day"] == "2026-04-17")
    assert day17["id"] == "sensor.e"
    assert day17["start"] == "100.0"
    assert day17["end"] == "105.0"
    assert day17["n"] == 3
    day18 = next(r for r in result if r["day"] == "2026-04-18")
    assert day18["start"] == "107.0"
    assert day18["n"] == 1


def test_compress_energy_history_handles_unavailable_state():
    raw = [
        {"entity_id": "sensor.e", "state": "unavailable", "last_changed": "2026-04-17T08:00:00"},
        {"entity_id": "sensor.e", "state": "unavailable", "last_changed": "2026-04-17T09:00:00"},
    ]
    result = _compress_energy_history(raw)
    assert len(result) == 1
    assert result[0]["start"] == "unavailable"


def test_compress_energy_history_multiple_entities():
    raw = [
        {"entity_id": "sensor.a", "state": "10", "last_changed": "2026-04-17T10:00:00"},
        {"entity_id": "sensor.b", "state": "20", "last_changed": "2026-04-17T10:00:00"},
    ]
    result = _compress_energy_history(raw)
    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert ids == {"sensor.a", "sensor.b"}


def test_compress_energy_history_empty_input():
    assert _compress_energy_history([]) == []
```

- [ ] **Step 2: Verifica che i test falliscano**

```
py -3 -m pytest tests/test_tools.py::test_compress_energy_history_groups_by_entity_and_day -x -q
```

Atteso: FAIL — `ImportError: cannot import name '_compress_energy_history'`

- [ ] **Step 3: Implementa la compressione in `energy_tools.py`**

Sostituisci l'intero contenuto di `hiris/app/tools/energy_tools.py` con:

```python
from __future__ import annotations
from collections import defaultdict
from ..proxy.ha_client import HAClient

ENERGY_ENTITY_IDS = [
    "sensor.energy_consumption",
    "sensor.solar_production",
    "sensor.grid_import",
    "sensor.grid_export",
]

TOOL_DEF = {
    "name": "get_energy_history",
    "description": (
        "Get energy history for the last N days. "
        "Returns compressed daily records: "
        "[{id, day (YYYY-MM-DD), start (first reading), end (last reading), n (samples)}]. "
        "Use start/end to compute daily delta. "
        "Source entities: consumption, solar production, grid import/export."
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
    # bucket: (entity_id, day) -> list of state strings in order
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)

    for item in raw:
        eid = item.get("entity_id", "")
        ts = item.get("last_changed", "")
        if not eid or not ts:
            continue
        day = ts[:10]  # "YYYY-MM-DD"
        buckets[(eid, day)].append(item.get("state", ""))

    result = []
    for (eid, day), readings in sorted(buckets.items()):
        result.append({
            "id": eid,
            "day": day,
            "start": readings[0],
            "end": readings[-1],
            "n": len(readings),
        })
    return result


async def get_energy_history(ha: HAClient, days: int) -> list[dict]:
    raw = await ha.get_history(entity_ids=ENERGY_ENTITY_IDS, days=days)
    return _compress_energy_history(raw)
```

- [ ] **Step 4: Verifica che tutti i test energy passino**

```
py -3 -m pytest tests/test_tools.py -k "energy" -v
```

Atteso: tutti PASS.

- [ ] **Step 5: Suite completa**

```
py -3 -m pytest tests/ -q
```

Atteso: 160+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/tools/energy_tools.py tests/test_tools.py
git commit -m "perf: compress energy_history output to daily aggregates (−92% tokens)"
```

---

## Task 4: Comprimi output di `get_weather_forecast`

**Perché:** Per ≤48h il formato attuale è già orario ma include lat/lon e nomi campo lunghi. Per >48h un forecast orario di 168 record è eccessivo: Claude ha bisogno di min/max giornalieri.

**Formato output nuovo:**
- `hours ≤ 48` → hourly compatto: `{"hourly": [{"h": "2026-04-18T10", "t": 22.1, "cc": 10, "r": 0.0}]}`
- `hours > 48` → daily summary: `{"daily": [{"day": "2026-04-18", "t_lo": 12.0, "t_hi": 24.0, "r": 0.5, "cc": 40}]}`
- Rimossi `latitude` e `longitude` (non utili per Claude)

**Files:**
- Modify: `hiris/app/tools/weather_tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Aggiorna il test esistente e aggiungi test per la compressione**

In `tests/test_tools.py`, **sostituisci** `test_get_weather_forecast_returns_forecast` con:

```python
@pytest.mark.asyncio
async def test_get_weather_forecast_returns_compact_hourly():
    """hours <= 48 → formato orario compatto, senza lat/lon."""
    mock_resp_data = {
        "hourly": {
            "time": ["2026-04-18T12:00", "2026-04-18T13:00"],
            "temperature_2m": [22.1, 23.5],
            "cloudcover": [10, 20],
            "precipitation": [0.0, 0.1],
        }
    }

    async def fake_fetch(url: str) -> dict:
        return mock_resp_data

    result = await get_weather_forecast(hours=2, _fetch=fake_fetch)
    assert "latitude" not in result
    assert "longitude" not in result
    assert "hourly" in result
    assert len(result["hourly"]) == 2
    h0 = result["hourly"][0]
    assert h0["h"] == "2026-04-18T12"   # troncato al minuto
    assert h0["t"] == 22.1
    assert h0["cc"] == 10
    assert h0["r"] == 0.0
```

Aggiungi poi:

```python
from hiris.app.tools.weather_tools import _compress_weather


def test_compress_weather_hourly_for_short_forecast():
    hourly = {
        "time": ["2026-04-18T10:00", "2026-04-18T11:00"],
        "temperature_2m": [20.0, 21.0],
        "cloudcover": [30, 40],
        "precipitation": [0.0, 0.5],
    }
    result = _compress_weather(hourly, hours=2)
    assert "hourly" in result
    assert "daily" not in result
    assert result["hourly"][0] == {"h": "2026-04-18T10", "t": 20.0, "cc": 30, "r": 0.0}
    assert result["hourly"][1] == {"h": "2026-04-18T11", "t": 21.0, "cc": 40, "r": 0.5}


def test_compress_weather_daily_for_long_forecast():
    # 3 giorni di dati, 6 ore per giorno (semplificato)
    times = (
        ["2026-04-18T00:00", "2026-04-18T06:00", "2026-04-18T12:00", "2026-04-18T18:00"] +
        ["2026-04-19T00:00", "2026-04-19T12:00"]
    )
    temps = [10.0, 15.0, 22.0, 18.0,  8.0, 20.0]
    clouds = [10, 20, 30, 40, 50, 60]
    rain   = [0.0, 0.0, 0.5, 0.2, 0.0, 1.0]
    hourly = {
        "time": times,
        "temperature_2m": temps,
        "cloudcover": clouds,
        "precipitation": rain,
    }
    result = _compress_weather(hourly, hours=72)
    assert "daily" in result
    assert "hourly" not in result
    days = {d["day"]: d for d in result["daily"]}
    assert "2026-04-18" in days
    d18 = days["2026-04-18"]
    assert d18["t_lo"] == 10.0
    assert d18["t_hi"] == 22.0
    assert abs(d18["r"] - 0.7) < 0.001
    assert "2026-04-19" in days


def test_compress_weather_handles_empty_hourly():
    result = _compress_weather({"time": [], "temperature_2m": [], "cloudcover": [], "precipitation": []}, hours=24)
    assert result == {"hourly": []}
```

- [ ] **Step 2: Verifica che i test falliscano**

```
py -3 -m pytest tests/test_tools.py::test_compress_weather_hourly_for_short_forecast -x -q
```

Atteso: FAIL — `ImportError: cannot import name '_compress_weather'`

- [ ] **Step 3: Implementa la compressione in `weather_tools.py`**

Sostituisci l'intero contenuto di `hiris/app/tools/weather_tools.py` con:

```python
from __future__ import annotations
import os
from collections import defaultdict
from typing import Any, Callable, Awaitable, Optional
import aiohttp

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

TOOL_DEF = {
    "name": "get_weather_forecast",
    "description": (
        "Get weather forecast for the home location. "
        "For ≤48 h returns hourly compact records: [{h: 'YYYY-MM-DDTHH', t, cc, r}]. "
        "For >48 h returns daily summaries: [{day: 'YYYY-MM-DD', t_lo, t_hi, r, cc}]. "
        "Fields: t=temperature °C, cc=cloud cover %, r=precipitation mm."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "Number of hours of forecast to retrieve (1-168)",
                "minimum": 1,
                "maximum": 168,
            }
        },
        "required": ["hours"],
    },
}


def _compress_weather(hourly: dict, hours: int) -> dict:
    """Compress Open-Meteo hourly dict into compact format.

    ≤48 h → {"hourly": [{"h": ..., "t": ..., "cc": ..., "r": ...}]}
    >48 h → {"daily":  [{"day": ..., "t_lo": ..., "t_hi": ..., "r": ..., "cc": ...}]}
    """
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    clouds = hourly.get("cloudcover", [])
    rain = hourly.get("precipitation", [])

    if not times:
        return {"hourly": []} if hours <= 48 else {"daily": []}

    if hours <= 48:
        return {
            "hourly": [
                {
                    "h": t[:13],        # "YYYY-MM-DDTHH"
                    "t": round(temp, 1),
                    "cc": int(cc),
                    "r": round(r, 2),
                }
                for t, temp, cc, r in zip(times, temps, clouds, rain)
            ]
        }

    # Daily summary for long forecasts
    by_day: dict[str, dict[str, list]] = defaultdict(lambda: {"t": [], "cc": [], "r": []})
    for t, temp, cc, r in zip(times, temps, clouds, rain):
        day = t[:10]
        by_day[day]["t"].append(temp)
        by_day[day]["cc"].append(cc)
        by_day[day]["r"].append(r)

    daily = []
    for day in sorted(by_day):
        d = by_day[day]
        daily.append({
            "day": day,
            "t_lo": round(min(d["t"]), 1),
            "t_hi": round(max(d["t"]), 1),
            "r":    round(sum(d["r"]), 2),
            "cc":   int(sum(d["cc"]) / len(d["cc"])),
        })
    return {"daily": daily}


async def _default_fetch(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_weather_forecast(
    hours: int,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    _fetch: Callable[[str], Awaitable[dict]] = _default_fetch,
) -> dict[str, Any]:
    lat = latitude or float(os.environ.get("HA_LATITUDE", "45.4642"))
    lon = longitude or float(os.environ.get("HA_LONGITUDE", "9.1900"))
    url = (
        f"{OPEN_METEO_URL}?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,cloudcover,precipitation"
        f"&forecast_hours={hours}"
        f"&timezone=auto"
    )
    data = await _fetch(url)
    return _compress_weather(data.get("hourly", {}), hours)
```

- [ ] **Step 4: Verifica che tutti i test weather passino**

```
py -3 -m pytest tests/test_tools.py -k "weather" -v
```

Atteso: tutti PASS.

- [ ] **Step 5: Suite completa**

```
py -3 -m pytest tests/ -q
```

Atteso: 168+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/tools/weather_tools.py tests/test_tools.py
git commit -m "perf: compress weather_forecast output — hourly<48h, daily>48h (−90% tokens)"
```

---

## Task 5: Entity pre-injection per agenti proattivi

**Perché:** Monitor/reactive/preventive agent chiamano `get_home_status()` o simili come primo tool call per "scoprire" lo stato della casa — ma lo sanno già prima di iniziare (è in EntityCache). Iniettando gli stati delle `allowed_entities` nel `user_message`, Claude può rispondere o agire senza nessun tool call di lettura → risparmio di 1-2 round-trip (~800-1.400 token/run).

**Logica:** Solo per agent type `monitor`, `reactive`, `preventive`. Per `chat` non si inietta (l'utente pone domande dinamiche).

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Modify: `hiris/app/server.py`
- Modify: `tests/test_agent_engine.py`

- [ ] **Step 1: Scrivi test fallenti in `test_agent_engine.py`**

Aggiungi in fondo a `tests/test_agent_engine.py`:

```python
def _make_entity_cache(entities):
    cache = MagicMock()
    cache.get_all_useful.return_value = entities
    return cache


def test_set_entity_cache_stores_cache(engine):
    cache = _make_entity_cache([])
    engine.set_entity_cache(cache)
    assert engine._entity_cache is cache


def test_build_entity_context_with_allowed_entities(engine):
    cache = _make_entity_cache([
        {"id": "light.soggiorno", "state": "on",   "name": "Luce Soggiorno", "unit": ""},
        {"id": "sensor.temp",     "state": "22.5", "name": "Temperatura",    "unit": "°C"},
        {"id": "switch.pompa",    "state": "off",  "name": "Pompa",          "unit": ""},
    ])
    engine.set_entity_cache(cache)
    agent = engine.create_agent({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Monitor",
        "allowed_tools": [],
        "allowed_entities": ["light.*", "sensor.*"],
        "enabled": False,
    })
    ctx = engine._build_entity_context(agent)
    assert "[CONTESTO ENTITÀ]" in ctx
    assert "Luce Soggiorno: on" in ctx
    assert "Temperatura: 22.5 °C" in ctx
    # switch.pompa non è in allowed_entities → non compare
    assert "Pompa" not in ctx


def test_build_entity_context_no_allowed_entities_uses_useful(engine):
    entities = [
        {"id": f"light.l{i}", "state": "on", "name": f"Luce {i}", "unit": ""}
        for i in range(60)
    ]
    cache = _make_entity_cache(entities)
    engine.set_entity_cache(cache)
    agent = engine.create_agent({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule"},
        "system_prompt": "test",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    ctx = engine._build_entity_context(agent)
    # cap a 50 entità anche senza filtro
    lines = [l for l in ctx.splitlines() if l.startswith("- ")]
    assert len(lines) == 50


def test_build_entity_context_returns_empty_without_cache(engine):
    # nessuna cache impostata → stringa vuota
    agent = engine.create_agent({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule"},
        "system_prompt": "test",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    ctx = engine._build_entity_context(agent)
    assert ctx == ""


@pytest.mark.asyncio
async def test_run_agent_injects_context_for_monitor(engine):
    cache = _make_entity_cache([
        {"id": "sensor.temp", "state": "21.0", "name": "Temp", "unit": "°C"},
    ])
    engine.set_entity_cache(cache)

    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.last_tool_calls = []
    runner.total_input_tokens = 0
    runner.total_output_tokens = 0
    engine.set_claude_runner(runner)

    agent = engine.create_agent({
        "name": "Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Analizza",
        "allowed_tools": [],
        "allowed_entities": ["sensor.*"],
        "enabled": False,
    })
    await engine._run_agent(agent)

    call_args = runner.chat.call_args
    user_msg = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][0]
    assert "[CONTESTO ENTITÀ]" in user_msg
    assert "Temp: 21.0 °C" in user_msg


@pytest.mark.asyncio
async def test_run_agent_does_not_inject_for_chat(engine):
    cache = _make_entity_cache([
        {"id": "sensor.temp", "state": "21.0", "name": "Temp", "unit": "°C"},
    ])
    engine.set_entity_cache(cache)

    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.last_tool_calls = []
    runner.total_input_tokens = 0
    runner.total_output_tokens = 0
    engine.set_claude_runner(runner)

    agent = engine.create_agent({
        "name": "Chat",
        "type": "chat",
        "trigger": {"type": "manual"},
        "system_prompt": "Chat",
        "allowed_tools": [],
        "allowed_entities": [],
        "enabled": False,
    })
    await engine._run_agent(agent)

    call_args = runner.chat.call_args
    user_msg = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][0]
    assert "[CONTESTO ENTITÀ]" not in user_msg
```

- [ ] **Step 2: Verifica che i test falliscano**

```
py -3 -m pytest tests/test_agent_engine.py -x -q -k "entity_cache or build_entity or inject"
```

Atteso: FAIL — `AttributeError: 'AgentEngine' object has no attribute 'set_entity_cache'`

- [ ] **Step 3: Implementa `set_entity_cache` e `_build_entity_context` in `agent_engine.py`**

In `hiris/app/agent_engine.py`:

**3a.** Aggiungi l'import di `fnmatch` (già presente) e verifica l'import `from typing import Any, Optional` (già presente).

**3b.** In `AgentEngine.__init__`, aggiungi:

```python
def __init__(self, ha_client: HAClient, data_path: str = DEFAULT_AGENTS_DATA_PATH) -> None:
    self._agents: dict[str, Agent] = {}
    self._scheduler = AsyncIOScheduler()
    self._claude_runner: Any = None
    self._ha = ha_client
    self._data_path = data_path
    self._entity_cache: Any = None          # ← aggiunto
```

**3c.** Aggiungi il metodo `set_entity_cache` dopo `set_claude_runner`:

```python
def set_entity_cache(self, cache: Any) -> None:
    self._entity_cache = cache
```

**3d.** Aggiungi il metodo `_build_entity_context` prima di `_run_agent`:

```python
def _build_entity_context(self, agent: "Agent") -> str:
    """Build entity state context string for pre-injection into proactive agent runs."""
    import fnmatch as _fnmatch
    if self._entity_cache is None:
        return ""
    all_entities = self._entity_cache.get_all_useful()
    if agent.allowed_entities:
        relevant = [
            e for e in all_entities
            if any(_fnmatch.fnmatch(e["id"], pat) for pat in agent.allowed_entities)
        ]
    else:
        relevant = all_entities
    if not relevant:
        return ""
    lines = ["[CONTESTO ENTITÀ]"]
    for e in relevant[:50]:
        name = e.get("name") or e["id"]
        unit = f" {e['unit']}" if e.get("unit") else ""
        lines.append(f"- {name}: {e['state']}{unit}")
    return "\n".join(lines)
```

- [ ] **Step 4: Modifica `_run_agent` per iniettare il contesto**

In `hiris/app/agent_engine.py`, metodo `_run_agent`, subito prima della `await self._claude_runner.chat(...)`:

```python
async def _run_agent(self, agent: Agent, context: Optional[dict] = None) -> str:
    if not self._claude_runner:
        logger.warning("No Claude runner configured")
        return ""
    logger.info("Running agent: %s (%s)", agent.name, agent.id)
    inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
    out_before = getattr(self._claude_runner, "total_output_tokens", 0)
    try:
        agent.last_run = datetime.now(timezone.utc).isoformat()
        if agent.strategic_context:
            effective_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
        else:
            effective_prompt = agent.system_prompt
        if context:
            effective_prompt = f"{effective_prompt}\n\nContext: {context}"

        # Pre-inject current entity states for proactive agents
        user_message = f"[Agent trigger: {agent.trigger.get('type')}]"
        if agent.type in ("monitor", "reactive", "preventive"):
            entity_ctx = self._build_entity_context(agent)
            if entity_ctx:
                user_message = f"{user_message}\n\n{entity_ctx}"

        result = await self._claude_runner.chat(
            user_message=user_message,
            system_prompt=effective_prompt,
            allowed_tools=agent.allowed_tools or None,
            allowed_entities=agent.allowed_entities or None,
            allowed_services=agent.allowed_services or None,
            model=agent.model,
            max_tokens=agent.max_tokens,
            agent_type=agent.type,
            restrict_to_home=agent.restrict_to_home,
            require_confirmation=agent.require_confirmation,
        )
        tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
        agent.last_result = result
        self._append_execution_log(agent, result, inp_before, out_before, tool_calls_snapshot, success=True)
        self._save()
        return result
    except Exception as exc:
        tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
        logger.error("Agent %s failed: %s", agent.name, exc)
        agent.last_result = f"Error: {exc}"
        self._append_execution_log(agent, agent.last_result, inp_before, out_before, tool_calls_snapshot, success=False)
        self._save()
        return agent.last_result
```

- [ ] **Step 5: Aggiorna `server.py` per passare la cache all'engine**

In `hiris/app/server.py`, subito dopo `await engine.start()`:

```python
engine = AgentEngine(ha_client=ha_client, data_path=data_path)
await engine.start()
engine.set_entity_cache(entity_cache)   # ← aggiunto
app["engine"] = engine
```

- [ ] **Step 6: Verifica che tutti i test agenti passino**

```
py -3 -m pytest tests/test_agent_engine.py -v
```

Atteso: tutti PASS (vecchi + nuovi).

- [ ] **Step 7: Suite completa**

```
py -3 -m pytest tests/ -q
```

Atteso: 180+ passed, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add hiris/app/agent_engine.py hiris/app/server.py tests/test_agent_engine.py
git commit -m "perf: pre-inject entity states into proactive agent user_message — skip get_home_status round-trip"
```

---

## Task 6: Version bump + push

**Files:**
- Modify: `hiris/app/server.py` (version string)
- Modify: `hiris/config.yaml`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Bump versione 0.1.3 → 0.1.4**

In `hiris/app/server.py`:
```python
return web.json_response({"status": "ok", "version": "0.1.4"})
```

In `hiris/config.yaml`:
```yaml
version: "0.1.4"
```

In `tests/test_api.py`:
```python
assert data["version"] == "0.1.4"
```

- [ ] **Step 2: Suite completa finale**

```
py -3 -m pytest tests/ -q
```

Atteso: 180+ passed, 0 failed.

- [ ] **Step 3: Commit e push**

```bash
git add hiris/app/server.py hiris/config.yaml tests/test_api.py
git commit -m "chore: bump version to 0.1.4"
git push origin master
```

---

## Self-Review

**Spec coverage:**
1. ✅ HOME_PROFILE TTL cache → Task 1
2. ✅ Area registry cache → Task 2
3. ✅ Compress energy_history → Task 3
4. ✅ Compress weather_forecast → Task 4
5. ✅ Pre-injection proactive agents → Task 5

**Placeholder scan:** nessuno — ogni step ha codice completo.

**Type consistency:**
- `get_cached_home_profile` (Task 1) usato in `claude_runner.py` — firme coerenti ✓
- `entity_cache.get_area_map()` (Task 2) chiamato in `ha_tools.get_area_entities` — firme coerenti ✓
- `_compress_energy_history` (Task 3) chiamato in `get_energy_history` — firme coerenti ✓
- `_compress_weather` (Task 4) chiamato in `get_weather_forecast` — firme coerenti ✓
- `engine._entity_cache` (Task 5) impostato via `set_entity_cache` e usato in `_build_entity_context` — coerente ✓
- Test `test_run_agent_injects_context_for_monitor` legge `call_args[1]["user_message"]` che corrisponde a come ClaudeRunner.chat è chiamato con keyword arg `user_message=` ✓
