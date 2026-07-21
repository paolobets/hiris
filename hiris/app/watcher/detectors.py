from __future__ import annotations
from typing import Callable, Optional
from .signals import Signal

def _num(state_dict: dict) -> Optional[float]:
    if not isinstance(state_dict, dict):
        return None
    raw = state_dict.get("state")
    if raw in (None, "unavailable", "unknown", ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

def detect_open(entity_id, old, new, cfg, now) -> Optional[Signal]:
    if (new or {}).get("state") != "on":
        return None
    return Signal(kind="opening", entity_id=entity_id, severity="warn",
                  evidence={"needs_duration": True, "threshold_min": cfg.get("open_minutes", 10)},
                  ts=now)

def detect_fridge_temp(entity_id, old, new, cfg, now) -> Optional[Signal]:
    temp = _num(new)
    if temp is None or temp <= cfg.get("max_temp_c", 8):
        return None
    return Signal(kind="fridge_temp", entity_id=entity_id, severity="critico",
                  evidence={"needs_duration": True, "threshold_min": cfg.get("duration_min", 30),
                            "temp": temp, "max_temp_c": cfg.get("max_temp_c", 8)},
                  ts=now)

def detect_power_anomaly(entity_id, old, new, cfg, now) -> Optional[Signal]:
    watt = _num(new)
    if watt is None or watt <= cfg.get("max_watt", 3000):
        return None
    return Signal(kind="power", entity_id=entity_id, severity="warn",
                  evidence={"watt": watt, "max_watt": cfg.get("max_watt", 3000)}, ts=now)

def detect_low_battery(entity_id, old, new, cfg, now) -> Optional[Signal]:
    pct = _num(new)
    if pct is None or pct >= cfg.get("min_pct", 10):
        return None
    return Signal(kind="battery", entity_id=entity_id, severity="info",
                  evidence={"pct": pct, "min_pct": cfg.get("min_pct", 10)}, ts=now)

DETECTORS: dict[str, Callable] = {
    "opening": detect_open,
    "fridge_temp": detect_fridge_temp,
    "power": detect_power_anomaly,
    "battery": detect_low_battery,
}
