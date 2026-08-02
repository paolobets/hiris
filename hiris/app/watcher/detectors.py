from __future__ import annotations
import logging
from typing import Any, Callable, Optional
from .signals import Signal

log = logging.getLogger(__name__)

# HA's no-data sentinels: an entity flapping to one of these (HA restart,
# wifi drop) is not "real data" and must never be treated as a matched
# value by any operator -- mirrors _num()'s own no-data mapping below, but
# _num() only kicks in on the numeric path; the "==" / "!=" string-fallback
# path in make_generic_detector needs the same guard applied explicitly.
_NO_DATA_STATES = ("unavailable", "unknown", "")

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

# Ripiego quando `cfg` non porta `min_pct` (policy scritta a mano, override
# parziale passato a Guardian.set_policy): stesso numero di
# DEFAULT_POLICY["detectors"]["battery"]["min_pct"] e di
# brain/health_checks.SOGLIA_BATTERIA_PCT. Letterale e non importato per non
# invertire la dipendenza watcher->brain; un test verifica che i tre valori
# coincidano. Il rilevatore resta un meccanismo distinto dal controllo del
# Brain -- opt-in su entita' scelte, in tempo reale, contro un'igiene sempre
# attiva su tutta la casa -- ma i due non devono partire da numeri diversi.
_MIN_PCT_PREDEFINITA = 15


def detect_low_battery(entity_id, old, new, cfg, now) -> Optional[Signal]:
    soglia = (cfg or {}).get("min_pct", _MIN_PCT_PREDEFINITA)
    pct = _num(new)
    if pct is None or pct >= soglia:
        return None
    return Signal(kind="battery", entity_id=entity_id, severity="info",
                  evidence={"pct": pct, "min_pct": soglia}, ts=now)

DETECTORS: dict[str, Callable] = {
    "opening": detect_open,
    "fridge_temp": detect_fridge_temp,
    "power": detect_power_anomaly,
    "battery": detect_low_battery,
}

_ORDER_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


def make_generic_detector(trigger: dict) -> Callable[[str, Any, Any, dict, float], Optional[Signal]]:
    """Build a Guardian-compatible detector for a user-defined lens's event
    trigger (Slice 5b). `trigger` is the already whitelist-validated dict
    produced by ``watcher.agentbots.validate_agentbot``/``_validate_trigger``:
    ``{entity_id, attribute?, operator, threshold, duration_min?}`` --
    ``operator`` in ``{">","<",">=","<=","==","!="}``; ``threshold`` a finite
    number for every operator, OR (for ``==``/``!=`` only) a non-empty
    string up to 64 chars for state-matching lenses (e.g. "home",
    "unlocked"); ``duration_min`` (if present) a finite non-negative number.

    Returns a callable with the SAME signature as the built-in detectors
    (``fn(entity_id, old, new, cfg, now) -> Optional[Signal]``) so the
    Guardian can dispatch user lenses through the existing DETECTORS
    machinery (Task 4) -- `old`/`cfg` are accepted only for signature
    compatibility (the built-ins don't use `old` either); `cfg` is read once,
    for an optional `severity` override (mirrors the built-ins' `cfg.get(...)`
    pattern for their own tunables), defaulting to "warn".

    Never raises: any odd input (missing attribute, non-numeric state,
    `new` that is None/not a dict) safely yields None instead of firing or
    crashing.
    """
    attribute = trigger.get("attribute")
    operator = trigger.get("operator")
    threshold = trigger.get("threshold")
    duration_min = trigger.get("duration_min")

    def _raw_value(new) -> Any:
        if not isinstance(new, dict):
            return None
        if attribute:
            attrs = new.get("attributes")
            if not isinstance(attrs, dict):
                return None
            return attrs.get(attribute)
        return new.get("state")

    def detect_user_agentbot(entity_id, old, new, cfg, now) -> Optional[Signal]:
        try:
            raw = _raw_value(new)
            if raw is None:
                return None
            if raw in _NO_DATA_STATES:
                # No-data guard for ALL operators (not just the numeric
                # path): without this, a temp sensor "!= 20" lens would
                # spuriously fire every time the entity goes briefly
                # "unavailable", because the string-fallback below would
                # compare str("unavailable") != str(20) and match.
                return None

            num = _num({"state": raw})

            if operator in ("==", "!="):
                if num is not None and isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
                    lhs, rhs = num, threshold
                else:
                    lhs, rhs = str(raw), str(threshold)
                matched = (lhs == rhs) if operator == "==" else (lhs != rhs)
            else:
                op_fn = _ORDER_OPS.get(operator)
                if op_fn is None:
                    return None  # unreachable for a validated trigger; safe default
                if num is None or not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
                    return None  # non-numeric -> ordering ops can't fire, no crash
                matched = op_fn(num, threshold)

            if not matched:
                return None

            # Severity vocabulary mismatch note: watcher.agentbots.ALLOWED_SEVERITIES
            # is {"info","warn","alert"} but watcher.signals.SEVERITIES is
            # ("info","warn","critico"). This is ALREADY handled --
            # `normalize_agentbot_severity` (watcher/agentbot_runner.py, renamed
            # from "lens" in SP-4 Fase A Task 3) maps "alert"->"critico"
            # (falling back to "info" for anything unrecognized) when an
            # Agentbot fires. This detector's own Signal.severity (computed
            # below from `cfg`, always `{}` on the guardian's event-Agentbot
            # path -- see guardian.py's `_dispatch_user_agentbots`) is
            # discarded anyway: only `sig.evidence` is forwarded to
            # `run_agentbot`, which re-derives severity straight from
            # `agentbot["severity"]` via `normalize_agentbot_severity`. So
            # the value assigned here never reaches a notification/decision.
            severity = "warn"
            if isinstance(cfg, dict):
                # `cfg.get("severity", "warn")` alone is not enough: a key
                # present with value None (e.g. {"severity": None}) would
                # return None here, not the default -- `or` catches that.
                severity = cfg.get("severity") or "warn"

            evidence: dict = {
                "entity_id": entity_id,
                "value": num if num is not None else raw,
                "operator": operator,
                "threshold": threshold,
            }
            if attribute:
                evidence["attribute"] = attribute
            if duration_min is not None:
                evidence["needs_duration"] = True
                evidence["threshold_min"] = duration_min

            return Signal(kind="user_agentbot", entity_id=entity_id, severity=severity,
                          evidence=evidence, ts=now)
        except Exception:
            # fail-safe: a user lens must never crash the Guardian, but a
            # silent swallow makes a broken lens undiagnosable -- log it.
            log.debug("make_generic_detector: user lens failed for %s, returning None",
                      entity_id, exc_info=True)
            return None

    return detect_user_agentbot
