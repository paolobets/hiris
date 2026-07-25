"""User-defined Sentinella "lenses" -- store + strict whitelist validation.

A lens is a user-authored rule on top of the Sentinella pipeline (Slice 5b):
a trigger (event or schedule), optional AI reasoning, an action, and a
severity. Lenses are persisted as a sidecar `sentinel_lenses.json` (a JSON
list), independent from `sentinel_policy.json` (see watcher.policy).

Validation is fail-safe by construction, mirroring
brain.suggestions.validate_coverage / brain.coverage_review.parse_suggestions:
every field is whitelisted and unknown keys are silently dropped. Malformed
*required* fields make the whole lens invalid (returns None). Optional
fields follow the rule "absent -> default, PRESENT but invalid -> reject the
whole lens" (never silently dropped) -- this is a fail-safe gate in front of
an LLM prompt and a semaphore-gated Home Assistant action, so a malformed
optional must never cause the action to fire *more* broadly than the user
wrote. validate_lens() NEVER raises.

Atomic write + lock mirror watcher.policy.save_policy: write to a .tmp file
then os.replace() it into place, guarded by a module-level RLock (single
process only, same scope as _POLICY_LOCK).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
import threading

from apscheduler.triggers.cron import CronTrigger

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

# Home Assistant's real grammar for the bits of a lens that end up in an
# actual HA API call (action target) or a cron parser. Presence-only
# whitelisting leaves a path-smuggling residual (e.g. domain="light/../..");
# these patterns are the defense against that.
_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_DOMAIN_SERVICE_RE = re.compile(r"^[a-z0-9_]+$")
_ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
# Basic 5-field shape check (full cron correctness is the scheduler's job).
_CRON_RE = re.compile(r"^[0-9*,/\-]+(?:\s+[0-9*,/\-]+){4}$")

_MESSAGE_MAX_LEN = 1000


def translate_cron_dow(field: str) -> str:
    """Remap a cron day-of-week FIELD from STANDARD crontab numbering
    (POSIX cron(5): 0 or 7 = Sunday, 1 = Monday, ..., 6 = Saturday -- what
    every SCHEDULE-trigger user lens is authored against, and what
    `_CRON_RE` whitelists) to APScheduler's OWN CronTrigger day_of_week
    numbering (0 = Monday, ..., 6 = Sunday, i.e. Python's
    `datetime.weekday()`).

    This translation is REQUIRED even though the caller builds the trigger
    via `CronTrigger.from_crontab` -- verified against the installed
    apscheduler==3.10.4, `from_crontab` does NOT perform any day_of_week
    remapping itself: it feeds a numeric day_of_week token straight into
    APScheduler's own field parser unchanged. Confirmed empirically: an
    UNTRANSLATED `CronTrigger.from_crontab("0 3 * * 0")` (standard-crontab
    Sunday) computes its next fire time on APScheduler's day_of_week=0,
    which is MONDAY, not Sunday; and a POSIX-legal "7" raises outright
    (APScheduler's day_of_week max is 6). This function runs BEFORE the
    cron string ever reaches `from_crontab`, fixing both at the source
    rather than relying on upstream translation that doesn't exist.

    Supports exactly the charset `_CRON_RE` allows for a cron field --
    digits, `*`, `,`, `/`, `-` -- i.e. bare values, comma-lists, ranges, and
    step values, in any combination (e.g. "1-5", "0,6", "*/2"). Any field
    this can't parse, or that resolves to a value outside 0-7, raises
    ValueError -- callers (`validate_lens`, `server.register_lens_schedules`)
    catch this per-lens so one broken cron never blocks the others / gets
    persisted.
    """
    field = field.strip()
    if field == "*":
        return "*"
    crontab_days: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty day_of_week token in {field!r}")
        step = 1
        base = part
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"non-positive step in {part!r}")
        if base == "*":
            lo, hi = 0, 7
        elif "-" in base:
            lo_s, hi_s = base.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
        else:
            lo = hi = int(base)
        if lo > hi:
            raise ValueError(f"backwards range in {part!r}")
        v = lo
        while v <= hi:
            crontab_days.add(v)
            v += step
    if not crontab_days or any(d < 0 or d > 7 for d in crontab_days):
        raise ValueError(f"day_of_week value out of range 0-7 in {field!r}")
    # 0 and 7 both denote Sunday in standard crontab -- collapse them onto
    # the SAME APScheduler day (6) rather than two separate ones.
    normalized = {0 if d == 7 else d for d in crontab_days}
    apscheduler_days = sorted((d - 1) % 7 for d in normalized)
    return ",".join(str(d) for d in apscheduler_days)


def to_apscheduler_crontab(cron: str) -> str:
    """Rewrite a whitelist-validated 5-field standard-crontab string
    (`_CRON_RE` already confirmed the charset/shape) into the equivalent
    string for `CronTrigger.from_crontab`, remapping ONLY the day_of_week
    field (`translate_cron_dow`) -- minute/hour/day/month use the same
    numbering in both conventions and pass through untouched. Raises
    ValueError if the field count is off (defensive -- the store's regex
    already guarantees exactly 5 whitespace-separated fields) or the
    day_of_week field doesn't parse; callers turn either into "reject this
    lens" (validate_lens) or "skip this lens" (server.register_lens_schedules)
    without crashing. Per-field VALUE validity of minute/hour/day/month
    (e.g. an out-of-range hour) is left to `CronTrigger.from_crontab`
    itself, raised at construction/`add_job` time and caught there."""
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(parts)}: {cron!r}")
    minute, hour, day, month, dow = parts
    return f"{minute} {hour} {day} {month} {translate_cron_dow(dow)}"


def _file(data_dir: str) -> str:
    return os.path.join(data_dir, _PATH)


def _is_number(v) -> bool:
    # bool is a subclass of int in Python; a lens threshold/interval must be
    # an actual number, not True/False leaking through. json.load() can also
    # hand us float('nan')/float('inf'): a NaN threshold with operator "!="
    # would make the detector always fire, and NaN/Infinity don't round-trip
    # through strict JSON, so both are rejected as "not a number" here.
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _clean_nonempty_str(v):
    if not isinstance(v, str):
        return None
    v = v.strip()
    return v or None


def _coerce_bool(v, default: bool) -> bool:
    # Only a real bool is trusted; anything else (e.g. the string "false",
    # which is truthy under bool()) falls back to the safe default instead
    # of silently flipping polarity.
    return v if isinstance(v, bool) else default


_THRESHOLD_STR_MAX_LEN = 64

# Sane floor for a scheduled lens's interval_min. Scheduled lenses run with
# cooldown_sec=0 (see module docstring) and each firing appends to an
# unbounded `events` table; without a floor a tiny/fractional interval would
# hog the event loop and grow the table without limit. 1 minute mirrors the
# coarsest HA/cron-adjacent scheduling grain used elsewhere in this module.
_INTERVAL_MIN_FLOOR = 1


def _validate_threshold(operator, threshold):
    """Validate `threshold` given its paired `operator` (already known to be
    a member of ALLOWED_OPERATORS). A finite number is always accepted.

    For the equality operators ("==" / "!=") a non-empty stripped string is
    ALSO accepted (capped to `_THRESHOLD_STR_MAX_LEN`, mirroring this
    file's general truncation policy) -- this is what makes state-matching
    lenses possible (e.g. "person.paolo != home", "lock.porta == unlocked",
    "binary_sensor.x == on"), which are core Home Assistant automations and
    were previously impossible because this validator forced threshold to
    be numeric. detectors.make_generic_detector already string-compares for
    "==" / "!=" (falling back to str(raw) == str(threshold)); only this
    validator was blocking it.

    Ordering operators (">", "<", ">=", "<=") keep the numeric-only rule: no
    total order is defined over arbitrary strings, so a string threshold
    there is rejected (present-but-invalid -> reject the whole lens, per
    this module's fail-safe-optional convention).

    Returns the cleaned threshold (the number as-is, or the stripped/
    truncated string) or None if `threshold` is not usable for `operator`.
    """
    if _is_number(threshold):
        return threshold
    if operator in ("==", "!=") and isinstance(threshold, str):
        v = threshold.strip()
        if v:
            return v[:_THRESHOLD_STR_MAX_LEN]
    return None


def _validate_condition(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    entity_id = _clean_nonempty_str(raw.get("entity_id"))
    operator = raw.get("operator")
    if entity_id is None or operator not in ALLOWED_OPERATORS:
        return None
    threshold = _validate_threshold(operator, raw.get("threshold"))
    if threshold is None:
        return None
    if not _ENTITY_ID_RE.match(entity_id):
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
        if entity_id is None or operator not in ALLOWED_OPERATORS:
            return None
        threshold = _validate_threshold(operator, raw.get("threshold"))
        if threshold is None:
            return None
        if not _ENTITY_ID_RE.match(entity_id):
            return None
        out = {"type": "event", "entity_id": entity_id, "operator": operator, "threshold": threshold}
        # attribute is optional: absent -> fine (compares the entity's main
        # state, per make_generic_detector). PRESENT but not a clean,
        # HA-attribute-shaped string (wrong type, empty/whitespace-only, or
        # outside the snake_case charset) -> reject the whole lens rather
        # than silently dropping it: a dropped attribute would rebind the
        # trigger to compare against the *state* instead of the intended
        # attribute -- wider than the user wrote, same failure shape as the
        # duration_min gate right below.
        if "attribute" in raw and raw.get("attribute") is not None:
            attribute = _clean_nonempty_str(raw.get("attribute"))
            if attribute is None or not _DOMAIN_SERVICE_RE.match(attribute):
                return None  # present but invalid -> reject
            out["attribute"] = attribute
        # duration_min is optional: absent -> fine (no duration gate).
        # PRESENT but not a finite non-negative number -> reject the whole
        # lens rather than silently dropping it (a dropped duration gate
        # would make the trigger fire on the very first sample, wider than
        # the user wrote).
        if "duration_min" in raw and raw.get("duration_min") is not None:
            duration_min = raw.get("duration_min")
            if not (_is_number(duration_min) and duration_min >= 0):
                return None
            out["duration_min"] = duration_min
        return out

    # schedule: exactly one of cron / interval_min, each validated if present.
    cron_present = "cron" in raw and raw.get("cron") is not None
    interval_present = "interval_min" in raw and raw.get("interval_min") is not None

    cron = None
    if cron_present:
        cron = _clean_nonempty_str(raw.get("cron"))
        if cron is None or not _CRON_RE.match(cron):
            return None  # present but malformed -> reject
        # Review L/1: _CRON_RE only checks SHAPE (5 numeric/*/,/-// fields);
        # a shape-valid but VALUE-invalid cron (e.g. hour=99) used to be
        # accepted here and only fail later, silently, at schedule
        # registration time (server.register_lens_schedules), leaving a
        # lens that looks saved/enabled but never actually runs with no
        # status surfaced. Reject-at-create instead: run it through the
        # exact same translation + CronTrigger construction the scheduler
        # itself uses, and fail the whole lens now if that raises.
        try:
            CronTrigger.from_crontab(to_apscheduler_crontab(cron))
        except Exception:
            return None  # present but value-invalid -> reject

    interval_min = None
    if interval_present:
        interval_min = raw.get("interval_min")
        if not (_is_number(interval_min) and interval_min >= _INTERVAL_MIN_FLOOR):
            return None  # present but invalid or below the floor -> reject

    if cron_present == interval_present:  # both present or neither -> not a valid XOR
        return None

    out = {"type": "schedule"}
    if cron_present:
        out["cron"] = cron
    else:
        out["interval_min"] = interval_min

    if "condition" in raw and raw.get("condition") is not None:
        condition = _validate_condition(raw.get("condition"))
        if condition is None:
            return None  # present but malformed -> reject
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
        if (
            not _DOMAIN_SERVICE_RE.match(domain)
            or not _DOMAIN_SERVICE_RE.match(service)
            or not _ENTITY_ID_RE.match(entity_id)
        ):
            return None  # charset gate: no path smuggling into the HA call
        out["domain"] = domain
        out["service"] = service
        out["entity_id"] = entity_id
    message = raw.get("message")
    if isinstance(message, str):
        out["message"] = message[:_MESSAGE_MAX_LEN]
    if "off_after_min" in raw and raw.get("off_after_min") is not None:
        off_after_min = raw.get("off_after_min")
        if not (_is_number(off_after_min) and off_after_min >= 0):
            return None  # present but invalid -> reject
        out["off_after_min"] = off_after_min
    return out


def _validate_reasoning(raw) -> dict:
    # reasoning missing/malformed -> safe default is zero-AI (enabled: False),
    # never an error: reasoning is inert (no side effects) unlike trigger/action.
    if not isinstance(raw, dict):
        return {"enabled": False}
    out = {"enabled": _coerce_bool(raw.get("enabled", False), False)}
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
    cron/interval_min, a present-but-invalid optional field, a domain/
    service/entity_id/cron that doesn't match Home Assistant's grammar).
    Unknown top-level and nested fields are silently dropped rather than
    causing rejection. NEVER raises.
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

        # severity: absent -> default "info"; PRESENT but not in the allowed
        # set -> reject the whole lens (don't silently coerce to "info",
        # which would understate a user-authored "alert").
        severity = raw.get("severity")
        if severity is not None:
            if severity not in ALLOWED_SEVERITIES:
                return None
        else:
            severity = "info"

        lens_id = raw.get("id")
        if not isinstance(lens_id, str) or not _ID_RE.match(lens_id):
            # Absent, wrong shape, or not the token_hex(6) format we mint ->
            # never trust an arbitrary client-supplied id, re-mint one.
            lens_id = secrets.token_hex(6)

        name = raw.get("name")
        name = name[:80] if isinstance(name, str) else ""

        # enabled: absent -> default True; PRESENT but not a real bool (e.g.
        # the string "false", 0, "no") -> reject the whole lens, mirroring
        # severity's absent-vs-present convention just above. Unlike
        # reasoning.enabled (inert, no side effects -- safe to lenient-
        # default to False), this flag gates whether the lens's action can
        # fire at all: silently coercing a present-but-invalid value to True
        # would invert a user's explicit disable intent.
        if "enabled" in raw and raw.get("enabled") is not None:
            enabled = raw.get("enabled")
            if not isinstance(enabled, bool):
                return None  # present but invalid -> reject
        else:
            enabled = True

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
        else:
            # Don't let a stored-but-now-invalid lens vanish silently: stricter
            # validation (e.g. an old interval_min below the floor, a non-bool
            # enabled, a value-invalid cron) would otherwise drop it with no
            # trace, and the next save persists the deletion.
            lid = item.get("id") if isinstance(item, dict) else None
            log.warning("load_lenses: dropping invalid stored lens id=%r", lid)
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
