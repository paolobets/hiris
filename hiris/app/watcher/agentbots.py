"""User-defined Sentinella "Agentbot" rules -- store + strict whitelist validation.

An Agentbot is a user-authored rule on top of the Sentinella pipeline
(Slice 5b; renamed from "lens" in SP-4 Fase A Task 3): a trigger (event or
schedule), optional AI reasoning, an action, and a severity. Agentbots are
persisted as `agentbots.json` (a JSON list), independent from
`sentinel_policy.json` (see watcher.policy). A legacy `sentinel_lenses.json`
sidecar from before the rename is migrated one-time by `load_agentbots`
(see its docstring).

Validation is fail-safe by construction, mirroring
brain.suggestions.validate_coverage / brain.coverage_review.parse_suggestions:
every field is whitelisted and unknown keys are silently dropped. Malformed
*required* fields make the whole Agentbot invalid (returns None). Optional
fields follow the rule "absent -> default, PRESENT but invalid -> reject the
whole Agentbot" (never silently dropped) -- this is a fail-safe gate in
front of an LLM prompt and a semaphore-gated Home Assistant action, so a
malformed optional must never cause the action to fire *more* broadly than
the user wrote. validate_agentbot() NEVER raises.

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

_PATH = "agentbots.json"
# Pre-rename sidecar filename (SP-4 Fase A Task 3). Migrated one-time by
# load_agentbots() the first time it runs against a data_dir that still has
# this legacy file but no agentbots.json yet.
_LEGACY_PATH = "sentinel_lenses.json"

# Guards the load_agentbots -> mutate -> save_agentbots critical sections in
# upsert_agentbot/delete_agentbot against a concurrent save_agentbots call
# (e.g. two web UI requests racing). Single process only, mirrors
# watcher.policy._POLICY_LOCK. Reentrant because upsert_agentbot/
# delete_agentbot call save_agentbots while already holding it.
_AGENTBOTS_LOCK = threading.RLock()

ALLOWED_OPERATORS = {">", "<", ">=", "<=", "==", "!="}
ALLOWED_TRIGGER_TYPES = {"event", "schedule"}
ALLOWED_ACTION_TYPES = {"notify", "service"}
ALLOWED_SEVERITIES = {"info", "warn", "alert"}
ALLOWED_MODES = frozenset({"rule", "objective"})
# The ceiling an objective Agentbot can reach WITHOUT asking. "red" always
# asks (see security.semaphore.gate_action) and "off" means nothing is
# allowed at all -- neither is a coherent "how far without asking" value, so
# both are excluded from the ceiling's own value space, not just left unset.
ALLOWED_MAX_TIERS = frozenset({"green", "yellow"})

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
    every SCHEDULE-trigger user Agentbot is authored against, and what
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
    ValueError -- callers (`validate_agentbot`, `server.register_agentbot_schedules`)
    catch this per-Agentbot so one broken cron never blocks the others / gets
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
    Agentbot" (validate_agentbot) or "skip this Agentbot"
    (server.register_agentbot_schedules) without crashing. Per-field VALUE
    validity of minute/hour/day/month
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
    Agentbots possible (e.g. "person.paolo != home", "lock.porta == unlocked",
    "binary_sensor.x == on"), which are core Home Assistant automations and
    were previously impossible because this validator forced threshold to
    be numeric. detectors.make_generic_detector already string-compares for
    "==" / "!=" (falling back to str(raw) == str(threshold)); only this
    validator was blocking it.

    Ordering operators (">", "<", ">=", "<=") keep the numeric-only rule: no
    total order is defined over arbitrary strings, so a string threshold
    there is rejected (present-but-invalid -> reject the whole Agentbot, per
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
        # outside the snake_case charset) -> reject the whole Agentbot rather
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
        # Agentbot rather than silently dropping it (a dropped duration gate
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
        # registration time (server.register_agentbot_schedules), leaving an
        # Agentbot that looks saved/enabled but never actually runs with no
        # status surfaced. Reject-at-create instead: run it through the
        # exact same translation + CronTrigger construction the scheduler
        # itself uses, and fail the whole Agentbot now if that raises.
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
        return {"enabled": False, "model": "auto"}
    out = {"enabled": _coerce_bool(raw.get("enabled", False), False)}
    # Task 4B: per-Agentbot model, threaded end-to-end into reason(model=...).
    # Absent/non-string/empty -> "auto" (same convention as the brain's
    # per-agent model field): never reject the Agentbot over a malformed model.
    model = raw.get("model", "auto")
    if not isinstance(model, str) or not model:
        model = "auto"
    out["model"] = model
    prompt = raw.get("prompt")
    if isinstance(prompt, str) and prompt:
        out["prompt"] = prompt[:2000]
    return out


# Sane per-execution ceilings for an objective Agentbot that declares no
# explicit budget/deadline. 4096 mirrors claude_runner.MAX_TOKENS (the
# reasoner's own default output cap), and 5 mirrors BRIDGE_DEADLINE_MIN's
# default (handlers_chat.py) -- both already-established "sensible single
# turn" numbers elsewhere in this codebase, reused here rather than invented.
_PERIMETER_BUDGET_TOKENS_DEFAULT = 4096
_PERIMETER_DEADLINE_MIN_DEFAULT = 5


def is_positive_int(v) -> bool:
    # Same bool-is-an-int-subclass trap _is_number already guards against.
    # budget_tokens/deadline_min are per-execution ceilings, not "amount used
    # so far" -- 0 or negative is not a smaller ceiling, it's a nonsensical
    # one, so the floor is a real minimum of 1, not >=0.
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


# Rejection sentinel for `_validate_str_list`. `None` is now a MEANINGFUL
# RETURN VALUE for those fields ("absent -> no restriction on this axis"), so
# it can no longer double as the "present but invalid" signal the way it does
# for the other validators in this module.
_INVALID_STR_LIST = object()


def _validate_str_list(raw, key):
    """Validate a perimeter allow-list field (`allowed_entities` /
    `allowed_services` of `raw`, keyed by `key`).

    The two possible "empty" outcomes are OPPOSITE and must never be
    collapsed into each other -- this is the single semantics the whole
    chain agrees on. The chain used to be `tools/dispatcher.py` -> Task ->
    `task_engine._run_action`; the dispatcher hop is gone (fetta E2 Task 7),
    an emitted Task still lands on `task_engine._run_action` the same way:

      * Absent (missing key, or explicit `null`) -> `None` = NO RESTRICTION
        on this axis. The Agentbot is still confined by the semaforo
        (denylist + tier), but this particular allow-list imposes no extra
        boundary.
      * An EXPLICITLY empty list (`[]`) stays `[]` = DENY EVERYTHING. The
        user wrote "grant nothing", and nothing is what gets granted; it is
        never widened into `None`.

    PRESENT but not a list, or containing any item that isn't a clean
    non-empty string (`_clean_nonempty_str`), -> `_INVALID_STR_LIST`, i.e.
    present-but-invalid -> reject the WHOLE Agentbot, not just drop the bad
    item -- same fail-safe-optional convention `_validate_perimeter`'s own
    docstring describes for every one of its fields."""
    values_raw = raw.get(key)
    if values_raw is None:
        return None  # absent -> no restriction on this axis
    if not isinstance(values_raw, list):
        return _INVALID_STR_LIST
    values = []
    for item in values_raw:
        cleaned_item = _clean_nonempty_str(item)
        if cleaned_item is None:
            # present but invalid item -> reject the whole Agentbot
            return _INVALID_STR_LIST
        values.append(cleaned_item)
    return values


def _validate_perimeter(raw) -> dict | None:
    """Validate the `perimeter` block (Agenti v1.1 Fase 2 Task 2): the scope
    an objective Agentbot is allowed to reason/act over -- entities,
    services, the autonomy ceiling (`max_tier`), and a per-execution budget/
    deadline.

    ONE list governs BOTH SIGHT AND TOUCH (Fase 2, deliberate). Along the
    whole chain the SAME `allowed_entities` list used to filter what the
    agent may READ (`tools/dispatcher.py`: `get_entity_states`,
    `get_history`, `get_home_status`, `get_entities_on`,
    `get_entities_by_domain`, `get_area_entities`) and to gate what it may
    ACT ON (`call_ha_service`, `set_input_helper`, `trigger_automation`,
    `toggle_automation`, and the Tasks it emits, enforced at execution time
    by `task_engine._run_action`). fetta E2 Task 7: that dispatcher is gone,
    so an objective Agentbot's reasoning no longer reads/acts through it
    either -- the READ half of this docstring is now a historical
    description, not a live behaviour; the ACT half (Tasks emitted and
    checked by `task_engine._run_action`) is unaffected, since Tasks never
    went through the dispatcher to be enforced. There is no separate
    "readable" axis: an entity that is not listed is not merely
    un-actuatable, it is NOT EVEN VISIBLE to the agent's reasoning -- while
    that reasoning could still reach the dispatcher. So an Agentbot with
    `allowed_entities: ["light.cucina"]` could not read `sensor.consumo_cucina`
    -- if the agent needed to SEE something to decide, that something had to
    be listed too. `allowed_services` is action-only (there is nothing to read
    through a service).

    The empty-vs-absent distinction is the same everywhere in the chain (see
    `_validate_str_list`): `None` = no restriction on that axis, `[]` =
    deny everything on that axis. They are opposites, never interchangeable.

    Absent (missing key, or explicit `null` -- same convention as `mode`/
    `severity`/`enabled`) -> a fully-populated block of explicit defaults,
    never a rejection: an objective Agentbot with no declared perimeter is
    still confined by the semaforo, but that confinement must be made
    VISIBLE rather than silently implied -- hence the block is ALWAYS
    materialized, with the un-restricted allow-lists spelled out as explicit
    `None`s rather than omitted. This mirrors `_validate_reasoning` in that
    "absent" always normalizes rather than raising/rejecting.

    PRESENT but malformed (wrong shape, or any single field with a value
    outside its allowed space, e.g. `max_tier: "red"`) -> None, i.e. reject
    the WHOLE Agentbot -- unlike `_validate_reasoning` (always inert, never
    rejects), a perimeter directly caps what an objective Agentbot may do
    without asking, so a malformed value must never be smoothed into some
    default that could turn out wider than the user intended. This mirrors
    how the rest of this module already treats `severity`/`enabled`/`mode`:
    present-but-invalid -> reject, not silently coerce.

    Unknown nested keys are dropped, not rejected -- consistent with this
    module's general whitelist policy (see module docstring)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None

    allowed_entities = _validate_str_list(raw, "allowed_entities")
    if allowed_entities is _INVALID_STR_LIST:
        return None  # present but invalid -> reject the whole Agentbot

    allowed_services = _validate_str_list(raw, "allowed_services")
    if allowed_services is _INVALID_STR_LIST:
        return None  # present but invalid -> reject the whole Agentbot

    # max_tier: validato e persistito ({green,yellow}, default green). In Fase
    # 2.5 e' onorato FINO AL VERDE: l'auto resta clampato al verde (il verde e'
    # l'unico `allow` del semaforo), quindi max_tier="yellow" NON abilita il
    # giallo-auto -- sarebbe fiducia progressiva, vietata in questa fase. Il
    # campo discrimina davvero (sblocco auto per tier piu' alti) solo in Fase 3.
    # Pinnato da test_max_tier_yellow_does_not_grant_yellow_auto_in_this_phase.
    max_tier = raw.get("max_tier")
    if max_tier is None:
        max_tier = "green"
    elif max_tier not in ALLOWED_MAX_TIERS:
        return None  # includes "red"/"off"/anything else -> reject

    budget_tokens = raw.get("budget_tokens")
    if budget_tokens is None:
        budget_tokens = _PERIMETER_BUDGET_TOKENS_DEFAULT
    elif not is_positive_int(budget_tokens):
        return None

    deadline_min = raw.get("deadline_min")
    if deadline_min is None:
        deadline_min = _PERIMETER_DEADLINE_MIN_DEFAULT
    elif not is_positive_int(deadline_min):
        return None

    return {
        "allowed_entities": allowed_entities,
        "allowed_services": allowed_services,
        "max_tier": max_tier,
        "budget_tokens": budget_tokens,
        "deadline_min": deadline_min,
    }


def validate_agentbot(raw: dict) -> dict | None:
    """Whitelist-validate a single raw Agentbot dict against the Slice 5b schema.

    Returns a cleaned, fully-shaped Agentbot dict, or None if the Agentbot is
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

        # mode: absent -> "rule" (content-sniffed migration: every pre-1.1
        # Agentbot is a rule, since "objective" didn't exist yet). Present
        # but not in the allowed set -> reject the whole record, mirroring
        # severity/enabled's absent-vs-present convention. Fase 1 fix-wave
        # MINOR 1: an explicit `"mode": null` must behave the SAME as an
        # absent key (mirrors enabled's own `"enabled" in raw and raw.get(
        # "enabled") is not None` form just below) -- `raw.get("mode",
        # "rule")` used to return `None` (not the default) for a
        # present-but-null key, which then failed the ALLOWED_MODES check
        # and rejected the whole Agentbot. An LLM proposal emitting `"mode":
        # null` must not lose the entire Agentbot over this.
        if "mode" in raw and raw.get("mode") is not None:
            mode = raw.get("mode")
        else:
            mode = "rule"
        if mode not in ALLOWED_MODES:
            return None

        # action: required in mode="rule" (unchanged 1.0 invariant -- a rule
        # with no action is unsalvageable). Forbidden in mode="objective": an
        # objective Agentbot's actions are born downstream as Tasks, so a
        # declared action here is a contradiction, not an oversight to
        # silently drop.
        if mode == "rule":
            action = _validate_action(raw.get("action"))
            if action is None:
                return None
        else:  # objective
            if raw.get("action") is not None:
                return None
            action = None

        # objective: same shape as action's rule/objective split, mirrored --
        # required and non-empty in mode="objective" (an objective Agentbot
        # with nothing to accomplish is unsalvageable, same reasoning as a
        # rule with no action); forbidden in mode="rule" (present -> reject:
        # a rule has no objective of its own, declaring one is a
        # contradiction, not an oversight to silently drop -- same reasoning
        # as `action` above). Truncated to 2000 chars, mirroring
        # reasoning.prompt's own bound.
        if mode == "objective":
            objective = _clean_nonempty_str(raw.get("objective"))
            if objective is None:
                return None
            objective = objective[:2000]
        else:  # rule
            # Fase 1 fix-wave MINOR 2: use the non-empty check here too (the
            # same `_clean_nonempty_str` the objective branch above already
            # uses), not a bare `is not None` -- an empty/whitespace-only
            # string is not a "declared" objective, it's the absence of one.
            # A form that always serializes `objective: ''` for rules would
            # otherwise 400 the whole Agentbot with no field-level cause.
            if _clean_nonempty_str(raw.get("objective")) is not None:
                return None
            objective = None

        # Cross-field gate (first one in this validator -- every other check
        # here is single-field). Design decision: HA events stay the domain
        # of RULE mode, where they cost nothing (the watcher is already
        # subscribed to the event bus). An objective Agentbot is heavier --
        # it runs an LLM turn -- so it is deliberately NOT allowed to hang
        # off an event directly; it is launched manually, on a schedule, or
        # invoked BY a rule/the Brain. Placed here, after both `mode` and
        # `trigger` are already resolved, so both operands of the check are
        # in scope and validated; a reader hitting this for the first time
        # should not mistake it for an arbitrary restriction.
        if mode == "objective" and trigger["type"] == "event":
            return None

        # severity: absent -> default "info"; PRESENT but not in the allowed
        # set -> reject the whole Agentbot (don't silently coerce to "info",
        # which would understate a user-authored "alert").
        severity = raw.get("severity")
        if severity is not None:
            if severity not in ALLOWED_SEVERITIES:
                return None
        else:
            severity = "info"

        agentbot_id = raw.get("id")
        if not isinstance(agentbot_id, str) or not _ID_RE.match(agentbot_id):
            # Absent, wrong shape, or not the token_hex(6) format we mint ->
            # never trust an arbitrary client-supplied id, re-mint one.
            agentbot_id = secrets.token_hex(6)

        name = raw.get("name")
        name = name[:80] if isinstance(name, str) else ""

        # enabled: absent -> default True; PRESENT but not a real bool (e.g.
        # the string "false", 0, "no") -> reject the whole Agentbot, mirroring
        # severity's absent-vs-present convention just above. Unlike
        # reasoning.enabled (inert, no side effects -- safe to lenient-
        # default to False), this flag gates whether the Agentbot's action can
        # fire at all: silently coercing a present-but-invalid value to True
        # would invert a user's explicit disable intent.
        if "enabled" in raw and raw.get("enabled") is not None:
            enabled = raw.get("enabled")
            if not isinstance(enabled, bool):
                return None  # present but invalid -> reject
        else:
            enabled = True

        reasoning = _validate_reasoning(raw.get("reasoning"))

        # Agenti v1.1 Fase 2 Task 7: in mode="objective" il ragionamento NON
        # e' opzionale. `agentbot_runner._on_wake` porta identita' e perimetro
        # al modello SOLO nel ramo `if reasoning.get("enabled")`; un agente-
        # obiettivo con reasoning spento non entra mai in quel ramo, quindi
        # non ragiona e non emette Task: cade nel ramo zero-AI, che costruisce
        # una `Decision` con `action=None` (in objective l'azione e' None per
        # costruzione, vedi il gate `action` qui sopra) e chiama
        # `executor.execute`, il quale per un'azione vuota NOTIFICA e ritorna
        # "notify". Non e' quindi silenzio: e' una notifica generica, e da
        # quando il Task 4 di questa fase ha smesso di filtrare le
        # pianificazioni per `mode` un agente cosi' ottiene un vero job dello
        # scheduler e ripete quella notifica a ogni scatto (con
        # `cooldown_sec=0`, `server._run_scheduled_agentbot`). Un agente-
        # obiettivo che non ragiona non ha motivo di esistere -- e nella forma
        # peggiore fa rumore invece di lavoro -- quindi lo chiudiamo qui,
        # con lo STESSO schema che questo file usa gia' per gli altri
        # cross-field di `mode`:
        #   - assente / null -> MATERIALIZZA a True, esattamente come
        #     `_validate_perimeter` materializza il perimetro assente in
        #     objective (e come il gate `enabled` top-level defaulta a True):
        #     non si rigetta per un'assenza.
        #   - PRESENTE ma non `True` (un `false` dichiarato, o un non-bool
        #     tipo "false"/"yes"/0/1) -> RIGETTA l'intero record, e (fix-wave
        #     MINOR 3) lo stesso vale quando e' l'INTERO blocco `reasoning` a
        #     non essere un dict: `{"reasoning": false}` (o `"off"`, o una
        #     lista) dichiara "questo agente-obiettivo non ragiona" tanto
        #     quanto `{"reasoning": {"enabled": false}}`, mentre leggere
        #     `enabled` solo dentro un dict lo appiattiva in silenzio su True
        #     -- esattamente la coercizione che questo gate esiste per
        #     vietare. E' la stessa
        #     famiglia di `action` dichiarata in objective, `objective`/
        #     `perimeter` dichiarati in rule, e il gate `enabled` top-level
        #     present-but-invalid: una contraddizione DICHIARATA non si
        #     appiattisce in silenzio su True (sarebbe la coercizione che il
        #     resto del file vieta), la si rifiuta con causa esplicita.
        # In mode="rule" nulla cambia: `_validate_reasoning` resta la sola
        # autorita', assente->spento, `false` accettato, non-bool degradato al
        # default sicuro -- byte per byte come prima.
        if mode == "objective":
            raw_reasoning = raw.get("reasoning")
            if raw_reasoning is None:
                # assente o null -> non e' una dichiarazione -> materializza
                reasoning["enabled"] = True
            elif not isinstance(raw_reasoning, dict):
                return None  # `reasoning: false`/"off"/[...] -> contraddizione
            else:
                raw_enabled = raw_reasoning.get("enabled")
                if raw_enabled is None:
                    reasoning["enabled"] = True
                elif raw_enabled is not True:
                    return None  # dichiarato ma non True -> contraddizione

        # perimeter: same rule/objective split as action/objective above --
        # forbidden in mode="rule" (a rule already declares its own entity
        # via trigger/action; a perimeter block there is a contradiction,
        # not an oversight to silently drop -- reject on ANY declared value,
        # even a well-formed or empty one, mirroring the `action` check in
        # objective mode just above). Materialized (never merely optional)
        # in mode="objective": _validate_perimeter itself turns "absent" into
        # explicit defaults rather than None, so an objective Agentbot's
        # perimeter is always visible in the returned dict; only a
        # PRESENT-but-malformed perimeter rejects the whole Agentbot.
        if mode == "rule":
            if raw.get("perimeter") is not None:
                return None
            perimeter = None
        else:  # objective
            perimeter = _validate_perimeter(raw.get("perimeter"))
            if perimeter is None:
                return None

        return {
            "id": agentbot_id,
            "name": name,
            "enabled": enabled,
            "trigger": trigger,
            "reasoning": reasoning,
            "action": action,
            "severity": severity,
            "mode": mode,
            "objective": objective,
            "perimeter": perimeter,
        }
    except Exception:
        log.warning("validate_agentbot: unsalvageable Agentbot, dropping", exc_info=True)
        return None


def load_agentbots(data_dir: str) -> list[dict]:
    """Read+validate agentbots.json. Missing file -> []. Unreadable
    (corrupted JSON, wrong top-level type, I/O error) -> [] (logged).
    Invalid individual Agentbots are dropped, valid ones are kept.

    One-time migration (SP-4 Fase A Task 3): if agentbots.json doesn't exist
    yet but the pre-rename sidecar `sentinel_lenses.json` does, rename it in
    place (os.replace, same filesystem so this is atomic) before reading.
    Wrapped in try/except and logged, never fatal -- a migration failure
    (e.g. permissions) just leaves the legacy file in place and this call
    falls through to "file not found" -> [] like any other missing store.
    """
    path = _file(data_dir)
    legacy = os.path.join(data_dir, _LEGACY_PATH)
    if not os.path.exists(path) and os.path.exists(legacy):
        try:
            os.replace(legacy, path)
            log.info("Migrated %s -> %s", _LEGACY_PATH, _PATH)
        except Exception:
            log.warning("agentbots migration failed", exc_info=True)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except (ValueError, OSError):
        log.warning("load_agentbots: %s unreadable/corrupted, treating as empty", path, exc_info=True)
        return []

    if not isinstance(data, list):
        log.warning("load_agentbots: %s is not a JSON list, treating as empty", path)
        return []

    out = []
    for item in data:
        cleaned = validate_agentbot(item)
        if cleaned is not None:
            out.append(cleaned)
        else:
            # Don't let a stored-but-now-invalid Agentbot vanish silently:
            # stricter validation (e.g. an old interval_min below the floor,
            # a non-bool enabled, a value-invalid cron) would otherwise drop
            # it with no trace, and the next save persists the deletion.
            lid = item.get("id") if isinstance(item, dict) else None
            log.warning("load_agentbots: dropping invalid stored Agentbot id=%r", lid)
    return out


def save_agentbots(data_dir: str, agentbots: list) -> list[dict]:
    """Validate every Agentbot, then atomically persist the cleaned list
    (tmp file + os.replace, under _AGENTBOTS_LOCK). Returns the cleaned list."""
    clean = []
    if isinstance(agentbots, list):
        for item in agentbots:
            cleaned = validate_agentbot(item)
            if cleaned is not None:
                clean.append(cleaned)

    os.makedirs(data_dir, exist_ok=True)
    tmp = _file(data_dir) + ".tmp"
    with _AGENTBOTS_LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _file(data_dir))
    return clean


def upsert_agentbot(data_dir: str, agentbot: dict) -> list[dict]:
    """Validate `agentbot` and insert it, or replace the existing Agentbot
    with the same id. An invalid `agentbot` is a no-op (current store is
    returned unchanged)."""
    with _AGENTBOTS_LOCK:
        cleaned = validate_agentbot(agentbot)
        if cleaned is None:
            return load_agentbots(data_dir)
        current = load_agentbots(data_dir)
        for i, existing in enumerate(current):
            if existing.get("id") == cleaned["id"]:
                current[i] = cleaned
                break
        else:
            current.append(cleaned)
        return save_agentbots(data_dir, current)


def delete_agentbot(data_dir: str, agentbot_id: str) -> list[dict]:
    """Remove the Agentbot with id == agentbot_id, if present. No-op otherwise."""
    with _AGENTBOTS_LOCK:
        current = load_agentbots(data_dir)
        current = [a for a in current if a.get("id") != agentbot_id]
        return save_agentbots(data_dir, current)
