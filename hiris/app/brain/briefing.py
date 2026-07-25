"""Slice 7 (Maggiordomo) -- deterministic daily briefing bundle.

Pure/read-only: pulls upcoming obligations from the KnowledgeStore and
notable home status (open doors/windows, low batteries) from the
EntityCache, and folds them into a single dict. No LLM, no network, no
writes. Never raises -- any failure on either input source degrades to an
empty section rather than propagating.
"""
from __future__ import annotations

from datetime import date, timedelta

_OPENING_DEVICE_CLASSES = {"door", "window", "garage_door", "opening"}
_CAP = 20


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _battery_threshold(policy: dict | None, default_pct: int) -> int:
    try:
        return int(policy["detectors"]["battery"]["min_pct"])  # type: ignore[index]
    except Exception:
        return default_pct


def _collect_deadlines(
    knowledge_store, *, today: date, horizon_days: int, allow_sensitive: bool,
) -> tuple[list[dict], int]:
    """Returns (visible_deadlines, hidden_sensitive_count)."""
    if knowledge_store is None:
        return [], 0
    try:
        before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
        rows = knowledge_store.upcoming_obligations(before=before)
    except Exception:
        return [], 0

    deadlines: list[dict] = []
    hidden_sensitive = 0
    for row in rows or []:
        try:
            sensitivity = row.get("sensitivity") or "normal"
            is_sensitive = sensitivity != "normal"
            if is_sensitive and not allow_sensitive:
                hidden_sensitive += 1
                continue
            due_date = row.get("due_date")
            due = _parse_iso_date(due_date)
            days_left = (due - today).days if due is not None else None
            deadlines.append({
                "content": row.get("content"),
                "due_date": due_date,
                "days_left": days_left,
                "sensitive": is_sensitive,
            })
        except Exception:
            continue

    deadlines.sort(key=lambda d: d.get("due_date") or "")
    return deadlines, hidden_sensitive


def _collect_home_status(
    entity_cache, *, policy: dict | None, battery_default_pct: int,
) -> tuple[list[dict], list[dict]]:
    """Returns (open_now, low_batteries), each capped at 20 entries."""
    if entity_cache is None:
        return [], []
    try:
        states = entity_cache.all_states()
    except Exception:
        return [], []

    threshold = _battery_threshold(policy, battery_default_pct)
    open_now: list[dict] = []
    low_batteries: list[dict] = []

    for entity in states or []:
        try:
            eid = entity.get("id") or entity.get("entity_id") or ""
            if not eid:
                continue

            if eid.startswith("binary_sensor.") and len(open_now) < _CAP:
                device_class = entity.get("device_class")
                if device_class in _OPENING_DEVICE_CLASSES and entity.get("state") == "on":
                    name = entity.get("name") or eid
                    open_now.append({"name": name})
                continue

            if eid.startswith("sensor.") and len(low_batteries) < _CAP:
                device_class = entity.get("device_class")
                unit = entity.get("unit") or ""
                name = entity.get("name") or ""
                is_battery = device_class == "battery" or (
                    unit == "%" and "batter" in name.lower()
                )
                if not is_battery:
                    continue
                try:
                    pct = float(entity.get("state"))
                except (TypeError, ValueError):
                    continue
                if pct < threshold:
                    low_batteries.append({"name": name or eid, "pct": pct})
        except Exception:
            continue

    return open_now[:_CAP], low_batteries[:_CAP]


def build_briefing_bundle(
    knowledge_store,
    entity_cache,
    policy,
    *,
    today: date,
    allow_sensitive: bool,
    horizon_days: int = 7,
    battery_default_pct: int = 20,
) -> dict:
    """Deterministic butler briefing bundle: deadlines from ingested
    documents (obligations) plus notable home status (open doors/windows,
    low batteries). Egress-gated: sensitive deadlines are excluded from the
    list when `allow_sensitive` is False, but still counted. Never raises.
    """
    try:
        deadlines, hidden_sensitive = _collect_deadlines(
            knowledge_store, today=today, horizon_days=horizon_days,
            allow_sensitive=allow_sensitive,
        )
    except Exception:
        deadlines, hidden_sensitive = [], 0

    try:
        open_now, low_batteries = _collect_home_status(
            entity_cache, policy=policy, battery_default_pct=battery_default_pct,
        )
    except Exception:
        open_now, low_batteries = [], []

    return {
        "deadlines": deadlines,
        "home": {"open_now": open_now, "low_batteries": low_batteries},
        "counts": {
            "deadlines": len(deadlines),
            "hidden_sensitive": hidden_sensitive,
            "open_now": len(open_now),
            "low_batteries": len(low_batteries),
        },
        "generated_for": today.isoformat(),
    }
