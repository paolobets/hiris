# hiris/app/tools/history_tools.py
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

MAX_ENTITIES = 20
MAX_DAYS = 365
MAX_RAW_POINTS = 500            # per-entity cap before downsampling
RECORDER_WINDOW_DAYS = 10       # routing threshold (HA recorder default retention)
_VALID_RESOLUTION = ("auto", "raw", "hourly", "daily")
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

GET_HISTORY_TOOL_DEF = {
    "name": "get_history",
    "description": (
        "Historical/time-series data for entities (trends, min/max/avg). READ-only. "
        "Numeric entities return COMPRESSED daily/hourly 'buckets'; non-numeric "
        "entities (on/off) return downsampled 'samples'. Never unbounded raw dumps. "
        "Use for: 'temperature trend last week', 'energy this month', sensor history. "
        "Args: entity_ids (1-20), days (1-365, default 7), "
        "resolution ('auto'|'raw'|'hourly'|'daily')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_ids": {"type": "array", "items": {"type": "string"},
                           "minItems": 1, "maxItems": MAX_ENTITIES},
            "days": {"type": "integer", "minimum": 1, "maximum": MAX_DAYS},
            "resolution": {"type": "string", "enum": list(_VALID_RESOLUTION)},
        },
        "required": ["entity_ids"],
    },
}


def validate_inputs(entity_ids: Any, days: int, resolution: str) -> Optional[str]:
    if not isinstance(entity_ids, list) or not (1 <= len(entity_ids) <= MAX_ENTITIES):
        return f"entity_ids must be a list of 1..{MAX_ENTITIES} ids"
    if not all(isinstance(e, str) and _ENTITY_ID_RE.match(e) for e in entity_ids):
        return "each entity_id must look like 'domain.object_id' (lowercase)"
    if not isinstance(days, int) or isinstance(days, bool) or not (1 <= days <= MAX_DAYS):
        return f"days must be an integer 1..{MAX_DAYS}"
    if resolution not in _VALID_RESOLUTION:
        return f"resolution must be one of {_VALID_RESOLUTION}"
    return None


def _to_float(s: Any) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def classify(samples: list[dict]) -> str:
    """'numeric' if the majority of states parse as float, else 'state'."""
    if not samples:
        return "state"
    numeric = sum(1 for s in samples if _to_float(s.get("state")) is not None)
    return "numeric" if numeric * 2 >= len(samples) else "state"


def _bucket_key(ts: str, resolution: str) -> str:
    # ts is ISO8601; daily -> YYYY-MM-DD, hourly -> YYYY-MM-DDTHH
    return ts[:13] if resolution == "hourly" else ts[:10]


def aggregate_numeric(samples: list[dict], resolution: str) -> list[dict]:
    """Group numeric samples (each {'t','state'}) into min/max/mean/n per bucket."""
    buckets: dict[str, list[float]] = {}
    for s in samples:
        v = _to_float(s.get("state"))
        ts = s.get("t", "")
        if v is None or len(ts) < 10:        # need a parsable value AND a date-able ts
            continue
        key = _bucket_key(ts, resolution)
        buckets.setdefault(key, []).append(v)
    out = []
    for key in sorted(buckets):
        vals = buckets[key]
        out.append({"t": key, "min": min(vals), "max": max(vals),
                    "mean": round(sum(vals) / len(vals), 3), "n": len(vals)})
    return out


def downsample(points: list[dict], cap: int) -> list[dict]:
    """Evenly thin a point list to <= cap, always keeping first and last."""
    if len(points) <= cap or cap < 2:
        return points
    step = (len(points) - 1) / (cap - 1)
    idxs = sorted({round(i * step) for i in range(cap)})
    idxs = [min(i, len(points) - 1) for i in idxs]
    return [points[i] for i in idxs]


def _stat_ts_to_day(start: Any) -> str:
    if isinstance(start, (int, float)):
        return datetime.fromtimestamp(start / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(start)[:10]


def normalize_statistics(rows: list[dict]) -> list[dict]:
    """HA statistics rows -> uniform numeric buckets {t,min,max,mean,n}."""
    out = []
    for r in rows:
        start = r.get("start")
        if start is None:
            continue
        out.append({
            "t": _stat_ts_to_day(start),
            "min": r.get("min"), "max": r.get("max"), "mean": r.get("mean"),
            "n": 1,
        })
    return out


def _ts_of(sample: dict) -> str:
    return sample.get("last_changed") or sample.get("last_updated") or ""


def _period_for(days: int, resolution: str) -> str:
    if resolution == "hourly":
        return "hour"
    if resolution == "daily":
        return "day"
    return "hour" if days <= 35 else "day"


def _resolution_for(days: int, resolution: str) -> str:
    if resolution != "auto":
        return resolution
    return "daily" if days > 2 else "raw"


async def _entity_series(ha: Any, eid: str, days: int, resolution: str,
                         store: Any = None, today: Optional[str] = None) -> dict:
    long_range = days > RECORDER_WINDOW_DAYS
    want_raw = resolution == "raw"

    # Captured entities: the HIRIS store is authoritative for aggregated history.
    if store is not None and not want_raw and store.has_entity(eid):
        res = store.query(eid, days, today)
        if res and res.get("buckets"):
            res["resolution"] = "daily"
            return res

    # Long numeric range -> try HA statistics first.
    if long_range and not want_raw:
        period = _period_for(days, resolution)
        stats = await ha.get_statistics([eid], period=period, days=days)
        rows = stats.get(eid) or []
        if rows:
            return {"id": eid, "source": "statistics", "unit": None,
                    "resolution": "hourly" if period == "hour" else "daily",
                    "buckets": downsample(normalize_statistics(rows), MAX_RAW_POINTS)}

    # Recorder path (recent, or statistics-less fallback).
    raw = await ha.get_history([eid], days)
    samples = [{"t": _ts_of(s), "state": s.get("state")} for s in raw
               if s.get("entity_id", eid) == eid]
    series: dict = {"id": eid, "source": "recorder", "unit": None}
    if long_range:
        series["partial"] = True   # recorder retains only ~RECORDER_WINDOW_DAYS days

    eff = _resolution_for(days, resolution)
    if eff != "raw" and classify(samples) == "numeric":
        series["resolution"] = eff
        series["buckets"] = aggregate_numeric(samples, eff)
    else:
        series["resolution"] = "raw"
        series["samples"] = downsample(samples, MAX_RAW_POINTS)
    return series


async def get_history(ha: Any, entity_ids: list[str], days: int = 7,
                      resolution: str = "auto", store: Any = None,
                      today: Optional[str] = None) -> Any:
    err = validate_inputs(entity_ids, days, resolution)
    if err:
        return {"error": err}
    if today is None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [await _entity_series(ha, eid, days, resolution, store=store, today=today)
            for eid in entity_ids]
