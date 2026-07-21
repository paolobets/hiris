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
    return pol


def save_policy(data_dir: str, body: dict) -> dict:
    clean = copy.deepcopy(DEFAULT_POLICY)
    for det, cfg in (body.get("detectors") or {}).items():
        if det not in clean["detectors"] or not isinstance(cfg, dict):
            continue
        for k, v in cfg.items():
            if k in _ALLOWED_KEYS[det]:
                clean["detectors"][det][k] = v
    os.makedirs(data_dir, exist_ok=True)
    tmp = _file(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _file(data_dir))
    return clean
