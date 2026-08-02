"""Sentinella detector configuration — load/save with atomic writes, defaults merging."""
from __future__ import annotations

import copy
import json
import math
import os
import threading

DEFAULT_POLICY: dict = {
    "detectors": {
        "opening":    {"enabled": False, "entities": [], "open_minutes": 10},
        "fridge_temp":{"enabled": False, "entities": [], "max_temp_c": 8, "duration_min": 30},
        "power":      {"enabled": False, "entities": [], "max_watt": 3000},
        # `min_pct` parte dallo stesso numero del controllo di salute del
        # Brain (brain/health_checks.SOGLIA_BATTERIA_PCT). Tenuto qui come
        # letterale, non importato, per non invertire la dipendenza
        # watcher->brain (stessa scelta gia' fatta per i bound di max_watt,
        # v. PARAM_BOUNDS); un test in tests/test_health_checks.py verifica
        # che i due numeri restino uguali. Resta modificabile dall'utente: la
        # Sentinella sorveglia poche entita' scelte e li' una soglia piu'
        # stretta ha senso.
        "battery":    {"enabled": False, "entities": [], "min_pct": 15},
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
# Structural keys that a brain-suggested `config`/`params` must NEVER be able to
# override via apply_brain_detector -- enabling/disabling a detector or wiping
# its entities list is exclusively the caller's own logic, never untrusted config.
_BRAIN_PARAM_DENY = frozenset({"enabled", "entities"})

# Review C/#8 (2026-07-25): type + range validation for detector keys, applied
# BEFORE a policy body is persisted (save_policy) or merged over defaults
# (load_policy). Every numeric threshold key is unique to exactly one
# detector, so a single flat bounds table is unambiguous across detectors.
# PUBLIC (no leading underscore): brain.suggestions imports this directly so
# its own coverage-param clamp (review C/#6) uses the exact same bounds
# rather than a second, driftable copy. max_watt's bounds also match
# brain.learned_thresholds' own absolute clamp (_ABS_MIN_WATT/_ABS_MAX_WATT)
# for the deterministic auto-tune path -- kept as literals here (not
# imported from brain) to avoid a watcher->brain dependency inversion.
PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "open_minutes": (1, 1440),
    "max_temp_c": (-20, 60),
    "duration_min": (1, 1440),
    "max_watt": (100, 20000),
    "min_pct": (1, 100),
}


class PolicyValidationError(ValueError):
    """Raised by save_policy() when a detector value fails type/range
    validation. Callers accepting untrusted input (the sentinel policy POST
    handler) must catch this and surface a 4xx -- a malformed config must
    never reach disk or the live Guardian."""


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_detector_value(key: str, value: object) -> bool:
    """True iff `value` is well-typed and in-range for detector key `key`.

    - "enabled" must be an actual bool (not a truthy string/int).
    - "entities" must be a list of strings (a string here would make the
      guardian's entity filter do substring matching instead of membership).
    - every numeric threshold key (see PARAM_BOUNDS) must be a finite
      number within its sane bound -- NaN/inf/strings/bools are rejected.
    Unknown keys are rejected as a fail-safe default (callers already
    restrict to _ALLOWED_KEYS[detector] before calling this)."""
    if key == "enabled":
        return isinstance(value, bool)
    if key == "entities":
        return isinstance(value, list) and all(isinstance(e, str) for e in value)
    bounds = PARAM_BOUNDS.get(key)
    if bounds is None:
        return False
    if not _is_finite_number(value):
        return False
    lo, hi = bounds
    return lo <= value <= hi
# Guards the load_policy -> mutate -> save_policy critical sections (including the
# sentinel_brain.json sidecar update) against a concurrent save_policy call from
# e.g. the web UI handler clobbering an in-flight brain auto-apply/undo. Single
# process only -- cross-process locking is out of scope. Reentrant because
# apply_brain_detector/remove_brain_detector hold it across their own call to
# save_policy, which also takes it internally.
_POLICY_LOCK = threading.RLock()


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
    # "tunings" (Task 5A) is a sibling key holding, per detector, a snapshot of
    # the pre-tuning value of each detector-level param touched by
    # apply_brain_tuning. Old sidecar files predating this key simply lack it
    # -> defaults to {} here, so they keep loading exactly as before.
    tunings = data.get("tunings")
    if not isinstance(tunings, dict):
        tunings = {}
    return {
        "detectors": {k: list(v) for k, v in detectors.items() if isinstance(v, list)},
        "tunings": {k: dict(v) for k, v in tunings.items() if isinstance(v, dict)},
    }


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
            # Review C/#8: an on-disk file can be corrupt (hand-edited, a
            # partial write from an old version, etc.). load_policy must
            # never crash and must never let a malformed value through --
            # any key that fails validate_detector_value() is simply
            # dropped here, so that detector key keeps its DEFAULT_POLICY
            # value instead of a bad one.
            pol["detectors"][det].update({k: v for k, v in cfg.items()
                                          if k in _ALLOWED_KEYS[det]
                                          and validate_detector_value(k, v)})
    pol["situations"] = _deep_merge(DEFAULT_POLICY["situations"], stored.get("situations"))
    pol["preparation"] = _deep_merge(DEFAULT_POLICY["preparation"], stored.get("preparation"))
    return pol


def save_policy(data_dir: str, body: dict) -> dict:
    """Validate + persist a policy body. Raises PolicyValidationError (review
    C/#8) if any provided detector key is malformed -- a bad save must never
    reach disk (nor the live Guardian, which the API handler applies `clean`
    to only after this call returns successfully). Internal callers
    (apply_brain_detector/apply_brain_tuning/remove_brain_*) only ever pass a
    `pol` built from load_policy() plus already-validated mutations (coverage
    params are clamped in suggestions.py before reaching here; tuning params
    come from the already-clamped learned_threshold path), so this never
    raises on the legitimate internal round-trip -- only on untrusted input
    reaching save_policy directly (the sentinel policy POST handler)."""
    clean = copy.deepcopy(DEFAULT_POLICY)
    for det, cfg in (body.get("detectors") or {}).items():
        if det not in clean["detectors"] or not isinstance(cfg, dict):
            continue
        for k, v in cfg.items():
            if k in _ALLOWED_KEYS[det]:
                if not validate_detector_value(k, v):
                    raise PolicyValidationError(
                        f"invalid value for detectors.{det}.{k}: {v!r}")
                clean["detectors"][det][k] = v
    clean["situations"] = _deep_merge(DEFAULT_POLICY["situations"], body.get("situations"))
    clean["preparation"] = _deep_merge(DEFAULT_POLICY["preparation"], body.get("preparation"))
    os.makedirs(data_dir, exist_ok=True)
    tmp = _file(data_dir) + ".tmp"
    with _POLICY_LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _file(data_dir))
    return clean


def apply_brain_detector(data_dir: str, detector: str, entity: str, params: dict | None = None) -> dict:
    """Enable `detector`, add `entity` to it, merge allowed `params`, and record the
    (detector, entity) pair as brain-added in the sidecar registry (see
    _load_brain_registry). Returns the delta needed to undo this exact change.

    Review C/#3: `params` (e.g. max_watt/max_temp_c/min_pct/open_minutes) are
    SHARED detector-level config, not entity-scoped -- applying them here
    overwrites the value for every entity already on `detector`, exactly like
    apply_brain_tuning. So, same as apply_brain_tuning's one-time snapshot,
    capture each touched key's PRE-apply value here and hand it back in the
    delta as "param_snapshot" -- this is per-suggestion (not per-detector like
    apply_brain_tuning's sidecar), since each coverage suggestion is undone
    independently via its own stored delta, not a shared registry key.
    """
    allowed_params = _ALLOWED_KEYS.get(detector, set()) - _BRAIN_PARAM_DENY
    with _POLICY_LOCK:
        pol = load_policy(data_dir)
        det_cfg = pol["detectors"].setdefault(detector, {"enabled": False, "entities": []})
        det_cfg["enabled"] = True
        entities = det_cfg.setdefault("entities", [])
        if entity not in entities:
            entities.append(entity)
        param_snapshot = {k: det_cfg.get(k) for k in (params or {}) if k in allowed_params}
        for k, v in (params or {}).items():
            if k in allowed_params:
                det_cfg[k] = v

        registry = _load_brain_registry(data_dir)
        det_list = registry["detectors"].setdefault(detector, [])
        if entity not in det_list:
            det_list.append(entity)

        # Review L/backlog (write-order): persist the registry BEFORE the
        # policy -- mirrors apply_brain_tuning's documented crash-safe
        # order. If we crash between the two writes, the safe residue is
        # "registry says entity is brain-added, policy doesn't have it
        # yet" (harmless no-op restore on undo), not the reverse (a
        # policy-added entity with no registry record -- permanently
        # un-undoable).
        _save_brain_registry(data_dir, registry)
        save_policy(data_dir, pol)

    return {"detector": detector, "entity": entity, "param_snapshot": param_snapshot}


def remove_brain_detector(data_dir: str, detector: str, entity: str,
                          restore_params: dict | None = None) -> bool:
    """Undo apply_brain_detector: remove `entity` from `detector`'s entities, but
    ONLY if that exact pair is present in the brain sidecar registry. This is the
    guarantee that a user-added entity (never recorded in the registry) is never
    touched by undo. Returns True if a removal happened, False otherwise (no-op).

    Review C/#3: `restore_params` (apply_brain_detector's returned
    "param_snapshot") is optionally written back into the shared detector
    config alongside the entity removal, so a coverage suggestion that
    overwrote a shared param (e.g. max_watt) is fully reversed, not just its
    entity. Restricted to this detector's allowed params (defense in depth --
    the snapshot itself is already `allowed_params`-filtered at capture time).
    """
    with _POLICY_LOCK:
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
            if restore_params:
                allowed_params = _ALLOWED_KEYS.get(detector, set()) - _BRAIN_PARAM_DENY
                for k, v in restore_params.items():
                    if k in allowed_params:
                        det_cfg[k] = v
            save_policy(data_dir, pol)

        det_list.remove(entity)
        if not det_list:
            registry["detectors"].pop(detector, None)
        _save_brain_registry(data_dir, registry)
    return True


def apply_brain_tuning(data_dir: str, detector: str, params: dict) -> dict:
    """Tune allowed detector-level params (e.g. power.max_watt) and, the FIRST
    time this detector is tuned, snapshot the CURRENT (pre-tuning) value of
    each touched param into the brain sidecar under "tunings". Unlike
    apply_brain_detector (which tracks brain-added ENTITIES for undo),
    detector params like `max_watt` are shared by every entity on the
    detector, so this is a separate primitive: it never touches
    `enabled`/`entities` (see _BRAIN_PARAM_DENY), and the snapshot is taken
    only once so a chain of auto-tunes (drift) still undoes back to the
    user's ORIGINAL value, not just the previous auto-tune's value."""
    allowed_params = _ALLOWED_KEYS.get(detector, set()) - _BRAIN_PARAM_DENY
    with _POLICY_LOCK:
        pol = load_policy(data_dir)
        det_cfg = pol["detectors"].setdefault(detector, {"enabled": False, "entities": []})

        registry = _load_brain_registry(data_dir)
        tunings = registry.setdefault("tunings", {})
        if detector not in tunings:
            snapshot = {k: det_cfg.get(k) for k in params if k in allowed_params}
            if snapshot:
                tunings[detector] = snapshot

        for k, v in (params or {}).items():
            if k in allowed_params:
                det_cfg[k] = v

        # Persist the snapshot BEFORE the tuned policy: if we crash between the
        # two writes, the safe residue is a snapshot with an untouched policy
        # (undo becomes a harmless no-op restore) rather than a tuned policy
        # with no snapshot (which would make the next tune snapshot the tuned
        # value as if it were the user's original).
        _save_brain_registry(data_dir, registry)
        save_policy(data_dir, pol)

    return {"detector": detector}


def remove_brain_tuning(data_dir: str, detector: str) -> bool:
    """Undo apply_brain_tuning: restore the detector's params to the
    snapshotted pre-tuning values and delete the snapshot. Returns True if a
    restore happened, False otherwise (no snapshot -> no-op). Never touches
    `entities`/`enabled`."""
    with _POLICY_LOCK:
        registry = _load_brain_registry(data_dir)
        tunings = registry.setdefault("tunings", {})
        snapshot = tunings.get(detector)
        if not snapshot:
            return False

        pol = load_policy(data_dir)
        det_cfg = pol["detectors"].get(detector)
        if isinstance(det_cfg, dict):
            for k, v in snapshot.items():
                det_cfg[k] = v
            save_policy(data_dir, pol)

        tunings.pop(detector, None)
        _save_brain_registry(data_dir, registry)
    return True
