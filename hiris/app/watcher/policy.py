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
    },
    "preparation": {
        "evening_arrival": {"enabled": False, "target_entity": "", "sun_entity": "sun.sun", "after_hour": 18},
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
_BRAIN_PATH = "sentinel_brain.json"
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


def _brain_file(data_dir: str) -> str:
    return os.path.join(data_dir, _BRAIN_PATH)


def _load_brain_registry(data_dir: str) -> dict:
    """Load the brain-added-entity sidecar registry.

    This registry is deliberately kept OUTSIDE sentinel_policy.json: save_policy()
    rebuilds the policy from DEFAULT_POLICY and only copies allowed detector keys,
    so any extra bookkeeping key stored inside the policy body would be silently
    stripped on the next save. The sidecar is the only durable place to remember
    which (detector, entity) pairs were added by the brain, which is what lets
    remove_brain_detector()/undo() guarantee they never touch a user-added entity.
    """
    try:
        with open(_brain_file(data_dir), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    detectors = data.get("detectors")
    if not isinstance(detectors, dict):
        detectors = {}
    return {"detectors": {k: list(v) for k, v in detectors.items() if isinstance(v, list)}}


def _save_brain_registry(data_dir: str, registry: dict) -> None:
    os.makedirs(data_dir, exist_ok=True)
    tmp = _brain_file(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _brain_file(data_dir))


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
    pol["preparation"] = _deep_merge(DEFAULT_POLICY["preparation"], stored.get("preparation"))
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
    clean["preparation"] = _deep_merge(DEFAULT_POLICY["preparation"], body.get("preparation"))
    os.makedirs(data_dir, exist_ok=True)
    tmp = _file(data_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _file(data_dir))
    return clean


def apply_brain_detector(data_dir: str, detector: str, entity: str, params: dict | None = None) -> dict:
    """Enable `detector`, add `entity` to it, merge allowed `params`, and record the
    (detector, entity) pair as brain-added in the sidecar registry (see
    _load_brain_registry). Returns the delta needed to undo this exact change."""
    pol = load_policy(data_dir)
    det_cfg = pol["detectors"].setdefault(detector, {"enabled": False, "entities": []})
    det_cfg["enabled"] = True
    entities = det_cfg.setdefault("entities", [])
    if entity not in entities:
        entities.append(entity)
    for k, v in (params or {}).items():
        if k in _ALLOWED_KEYS.get(detector, set()):
            det_cfg[k] = v
    save_policy(data_dir, pol)

    registry = _load_brain_registry(data_dir)
    det_list = registry["detectors"].setdefault(detector, [])
    if entity not in det_list:
        det_list.append(entity)
    _save_brain_registry(data_dir, registry)

    return {"detector": detector, "entity": entity}


def remove_brain_detector(data_dir: str, detector: str, entity: str) -> bool:
    """Undo apply_brain_detector: remove `entity` from `detector`'s entities, but
    ONLY if that exact pair is present in the brain sidecar registry. This is the
    guarantee that a user-added entity (never recorded in the registry) is never
    touched by undo. Returns True if a removal happened, False otherwise (no-op)."""
    registry = _load_brain_registry(data_dir)
    det_list = registry["detectors"].get(detector, [])
    if entity not in det_list:
        return False

    pol = load_policy(data_dir)
    det_cfg = pol["detectors"].get(detector)
    if isinstance(det_cfg, dict):
        entities = det_cfg.get("entities", [])
        if entity in entities:
            entities.remove(entity)
        save_policy(data_dir, pol)

    det_list.remove(entity)
    if not det_list:
        registry["detectors"].pop(detector, None)
    _save_brain_registry(data_dir, registry)
    return True
