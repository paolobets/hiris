"""User-defined Sentinella "lenses" -- store + strict whitelist validation.

A lens is a user-authored rule on top of the Sentinella pipeline (Slice 5b):
a trigger (event or schedule), optional AI reasoning, an action, and a
severity. Lenses are persisted as a sidecar `sentinel_lenses.json` (a JSON
list), independent from `sentinel_policy.json` (see watcher.policy).

Validation is fail-safe by construction, mirroring
brain.suggestions.validate_coverage / brain.coverage_review.parse_suggestions:
every field is whitelisted, unknown keys are silently dropped, malformed
required fields make the whole lens invalid (returns None) rather than
raising. validate_lens() NEVER raises.

Atomic write + lock mirror watcher.policy.save_policy: write to a .tmp file
then os.replace() it into place, guarded by a module-level RLock (single
process only, same scope as _POLICY_LOCK).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading

log = logging.getLogger(__name__)

_PATH = "sentinel_lenses.json"

# Guards the load_lenses -> mutate -> save_lenses critical sections in
# upsert_lens/delete_lens against a concurrent save_lenses call (e.g. two web
# UI requests racing). Single process only, mirrors watcher.policy._POLICY_LOCK.
# Reentrant because upsert_lens/delete_lens call save_lenses while already
# holding it.
_LENSES_LOCK = threading.RLock()

ALLOWED_OPERATORS = {">", "<", ">=", "<=", "==", "!="}
ALLOWED_TRIGGER_TYPES = {"event", "schedule"}
ALLOWED_ACTION_TYPES = {"notify", "service"}
ALLOWED_SEVERITIES = {"info", "warn", "alert"}


def _file(data_dir: str) -> str:
    return os.path.join(data_dir, _PATH)


def _is_number(v) -> bool:
    # bool is a subclass of int in Python; a lens threshold/interval must be
    # an actual number, not True/False leaking through.
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _clean_nonempty_str(v):
    return v if isinstance(v, str) and v else None


def _validate_condition(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    entity_id = _clean_nonempty_str(raw.get("entity_id"))
    operator = raw.get("operator")
    threshold = raw.get("threshold")
    if entity_id is None or operator not in ALLOWED_OPERATORS or not _is_number(threshold):
        return None
    return {"entity_id": entity_id, "operator": operator, "threshold": threshold}


def _validate_trigger(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    ttype = raw.get("type")
    if ttype not in ALLOWED_TRIGGER_TYPES:
        return None

    if ttype == "event":
        entity_id = _clean_nonempty_str(raw.get("entity_id"))
        operator = raw.get("operator")
        threshold = raw.get("threshold")
        if entity_id is None or operator not in ALLOWED_OPERATORS or not _is_number(threshold):
            return None
        out = {"type": "event", "entity_id": entity_id, "operator": operator, "threshold": threshold}
        attribute = _clean_nonempty_str(raw.get("attribute"))
        if attribute is not None:
            out["attribute"] = attribute
        duration_min = raw.get("duration_min")
        if _is_number(duration_min) and duration_min >= 0:
            out["duration_min"] = duration_min
        return out

    # schedule
    cron = _clean_nonempty_str(raw.get("cron"))
    interval_min = raw.get("interval_min")
    has_interval = _is_number(interval_min) and interval_min > 0
    has_cron = cron is not None
    if has_cron == has_interval:  # both present or neither -> not a valid XOR
        return None
    out = {"type": "schedule"}
    if has_cron:
        out["cron"] = cron
    else:
        out["interval_min"] = interval_min
    condition = _validate_condition(raw.get("condition")) if isinstance(raw.get("condition"), dict) else None
    if condition is not None:
        out["condition"] = condition
    return out


def _validate_action(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    atype = raw.get("type")
    if atype not in ALLOWED_ACTION_TYPES:
        return None
    out = {"type": atype}
    if atype == "service":
        domain = _clean_nonempty_str(raw.get("domain"))
        service = _clean_nonempty_str(raw.get("service"))
        entity_id = _clean_nonempty_str(raw.get("entity_id"))
        if domain is None or service is None or entity_id is None:
            return None  # service action REQUIRES domain, service, entity_id
        out["domain"] = domain
        out["service"] = service
        out["entity_id"] = entity_id
    message = raw.get("message")
    if isinstance(message, str):
        out["message"] = message
    off_after_min = raw.get("off_after_min")
    if _is_number(off_after_min) and off_after_min >= 0:
        out["off_after_min"] = off_after_min
    return out


def _validate_reasoning(raw) -> dict:
    # reasoning missing/malformed -> safe default is zero-AI (enabled: False),
    # never an error: reasoning is inert (no side effects) unlike trigger/action.
    if not isinstance(raw, dict):
        return {"enabled": False}
    out = {"enabled": bool(raw.get("enabled", False))}
    prompt = raw.get("prompt")
    if isinstance(prompt, str) and prompt:
        out["prompt"] = prompt[:2000]
    return out


def validate_lens(raw: dict) -> dict | None:
    """Whitelist-validate a single raw lens dict against the Slice 5b schema.

    Returns a cleaned, fully-shaped lens dict, or None if the lens is
    unsalvageable (unknown trigger/action type, invalid operator, a service
    action missing domain/service/entity_id, an event trigger missing
    entity_id/operator/threshold, a schedule trigger without exactly one of
    cron/interval_min). Unknown top-level and nested fields are silently
    dropped rather than causing rejection. NEVER raises.
    """
    try:
        if not isinstance(raw, dict):
            return None

        trigger = _validate_trigger(raw.get("trigger"))
        if trigger is None:
            return None

        action = _validate_action(raw.get("action"))
        if action is None:
            return None

        severity = raw.get("severity")
        if severity not in ALLOWED_SEVERITIES:
            severity = "info"

        lens_id = raw.get("id")
        if not isinstance(lens_id, str) or not lens_id:
            lens_id = secrets.token_hex(6)

        name = raw.get("name")
        name = name[:80] if isinstance(name, str) else ""

        enabled = bool(raw.get("enabled", True))

        reasoning = _validate_reasoning(raw.get("reasoning"))

        return {
            "id": lens_id,
            "name": name,
            "enabled": enabled,
            "trigger": trigger,
            "reasoning": reasoning,
            "action": action,
            "severity": severity,
        }
    except Exception:
        log.warning("validate_lens: unsalvageable lens, dropping", exc_info=True)
        return None


def load_lenses(data_dir: str) -> list[dict]:
    """Read+validate sentinel_lenses.json. Missing file -> []. Unreadable
    (corrupted JSON, wrong top-level type, I/O error) -> [] (logged).
    Invalid individual lenses are dropped, valid ones are kept."""
    try:
        with open(_file(data_dir), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except (ValueError, OSError):
        log.warning("load_lenses: %s unreadable/corrupted, treating as empty", _file(data_dir), exc_info=True)
        return []

    if not isinstance(data, list):
        log.warning("load_lenses: %s is not a JSON list, treating as empty", _file(data_dir))
        return []

    out = []
    for item in data:
        cleaned = validate_lens(item)
        if cleaned is not None:
            out.append(cleaned)
    return out


def save_lenses(data_dir: str, lenses: list) -> list[dict]:
    """Validate every lens, then atomically persist the cleaned list
    (tmp file + os.replace, under _LENSES_LOCK). Returns the cleaned list."""
    clean = []
    if isinstance(lenses, list):
        for item in lenses:
            cleaned = validate_lens(item)
            if cleaned is not None:
                clean.append(cleaned)

    os.makedirs(data_dir, exist_ok=True)
    tmp = _file(data_dir) + ".tmp"
    with _LENSES_LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _file(data_dir))
    return clean


def upsert_lens(data_dir: str, lens: dict) -> list[dict]:
    """Validate `lens` and insert it, or replace the existing lens with the
    same id. An invalid `lens` is a no-op (current store is returned unchanged)."""
    with _LENSES_LOCK:
        cleaned = validate_lens(lens)
        if cleaned is None:
            return load_lenses(data_dir)
        current = load_lenses(data_dir)
        for i, existing in enumerate(current):
            if existing.get("id") == cleaned["id"]:
                current[i] = cleaned
                break
        else:
            current.append(cleaned)
        return save_lenses(data_dir, current)


def delete_lens(data_dir: str, lens_id: str) -> list[dict]:
    """Remove the lens with id == lens_id, if present. No-op otherwise."""
    with _LENSES_LOCK:
        current = load_lenses(data_dir)
        current = [l for l in current if l.get("id") != lens_id]
        return save_lenses(data_dir, current)
