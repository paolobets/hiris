"""Sentinella detector configuration — load/save with atomic writes, defaults merging."""
from __future__ import annotations

import copy
import json
import os

DEFAULT_POLICY: dict = {
    "detectors": {
        "opening":    {"enabled": False, "entities": [], "open_minutes": 10},
        "fridge_temp":{"enabled": False, "entities": [], "max_temp_c": 8, "duration_min": 30},
        "power":      {"enabled": False, "entities": [], "max_watt": 3000},
        "battery":    {"enabled": False, "entities": [], "min_pct": 10},
    },
    "situations": {
        "ronda_minutes": 15,
        "presence_entity": "",
        "hot_and_away": {"enabled": False, "outside_temp_entity": "", "hot_threshold_c": 32,
                         "valve_entity": "", "run_minutes": 5, "skip_if_rain": True},
        "away_alarm_off": {"enabled": False, "alarm_entity": "", "disarmed_states": ["disarmed"]},
        "holistic": {"enabled": False, "hour": 9, "per_day": 1},
    }
}

SENTINEL_DETECTORS = [
    {"id": "opening", "label": "Aperture prolungate",
     "fields": [{"key": "open_minutes", "type": "int", "label": "Minuti aperta"}]},
    {"id": "fridge_temp", "label": "Catena del freddo",
     "fields": [{"key": "max_temp_c", "type": "int", "label": "Temp. max °C"},
                {"key": "duration_min", "type": "int", "label": "Durata min"}]},
    {"id": "power", "label": "Consumo anomalo",
     "fields": [{"key": "max_watt", "type": "int", "label": "Watt max"}]},
    {"id": "battery", "label": "Batterie scariche",
     "fields": [{"key": "min_pct", "type": "int", "label": "% minima"}]},
]

_PATH = "sentinel_policy.json"
_ALLOWED_KEYS = {k: set(v) for k, v in DEFAULT_POLICY["detectors"].items()}


def _deep_merge(default: dict, stored: dict | None) -> dict:
    """Deep merge stored values over defaults, restricted to keys present in default."""
    out = copy.deepcopy(default)
    if not isinstance(stored, dict):
        return out
    for k, dv in default.items():
        if k not in stored:
            continue
        sv = stored[k]
        out[k] = _deep_merge(dv, sv) if isinstance(dv, dict) and isinstance(sv, dict) else sv
    return out


def _file(data_dir: str) -> str:
    return os.path.join(data_dir, _PATH)


def load_policy(data_dir: str) -> dict:
    pol = copy.deepcopy(DEFAULT_POLICY)
    try:
        with open(_file(data_dir), "r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return pol
    for det, cfg in (stored.get("detectors") or {}).items():
        if det in pol["detectors"] and isinstance(cfg, dict):
            pol["detectors"][det].update({k: v for k, v in cfg.items()
                                          if k in _ALLOWED_KEYS[det]})
    pol["situations"] = _deep_merge(DEFAULT_POLICY["situations"], stored.get("situations"))
    return pol


def save_policy(data_dir: str, body: dict) -> dict:
    clean = copy.deepcopy(DEFAULT_POLICY)
    for det, cfg in (body.get("detectors") or {}).items():
        if det not in clean["detectors"] or not isinstance(cfg, dict):
            continue
        for k, v in cfg.items():
            if k in _ALLOWED_KEYS[det]:
                clean["detectors"][det][k] = v
    clean["situations"] = _deep_merge(DEFAULT_POLICY["situations"], body.get("situations"))
    os.makedirs(data_dir, exist_ok=True)
    tmp = _file(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _file(data_dir))
    return clean
