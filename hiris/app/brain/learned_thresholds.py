"""Deterministic, bounded computation of auto-learned detector thresholds.

Pure function module: no I/O, no HistoryStore, no LLM, no network. Given a
numeric baseline (as produced by ``HistoryStore.baseline_for``) and a
detector's current config, propose a new threshold value — or ``None`` if
there isn't enough signal, the result would be degenerate, or the change
isn't worth applying.

Ordering contract (read this before touching the math below):
    1. Compute the raw candidate (``mean * factor``) and CLAMP it first into
       both the relative bounds (``[current*0.5, current*3]``) and the
       absolute bounds (``[_ABS_MIN_WATT, _ABS_MAX_WATT]``).
    2. THEN compare the *clamped* value against the current threshold using
       the hysteresis percentage (``_HYSTERESIS_PCT``). If the clamped value
       is too close to the current one, return ``None``.
    This order matters: comparing the *raw* (unclamped) candidate against
    the current value first could reject changes that, after clamping, would
    actually land far enough away to be worth applying (or vice versa —
    accept a "big" raw change that clamps down to something negligibly
    different from the current value). Clamp-then-compare uses the number
    that would actually be written to config, which is the only number that
    matters for the hysteresis decision.
"""

import math
from typing import Callable, Optional

# Minimum number of day-buckets of history required before we trust a
# baseline enough to learn from it.
_MIN_DAYS = 7

# Relative clamp bounds: the new threshold may not move the current value by
# more than these multiples.
_REL_CLAMP_LOW_FACTOR = 0.5
_REL_CLAMP_HIGH_FACTOR = 3.0

# Absolute clamp bounds (watts), regardless of the current value.
_ABS_MIN_WATT = 100
_ABS_MAX_WATT = 20000

# Fallback used when current_cfg/max_watt is missing or invalid.
_DEFAULT_MAX_WATT = 3000

# If the clamped candidate differs from the current value by this fraction
# (or less), it's not worth applying — avoid config churn for noise.
_HYSTERESIS_PCT = 0.15


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _learn_power(baseline: dict, current_cfg: dict, factor: float) -> Optional[dict]:
    if not isinstance(baseline, dict):
        return None

    n_days = baseline.get("n_days")
    if not _is_finite_number(n_days) or n_days < _MIN_DAYS:
        return None

    mean = baseline.get("mean")
    if not _is_finite_number(mean) or mean <= 0:
        return None

    if not _is_finite_number(factor) or factor <= 0:
        return None

    if isinstance(current_cfg, dict):
        current_max = current_cfg.get("max_watt", _DEFAULT_MAX_WATT)
    else:
        current_max = _DEFAULT_MAX_WATT
    if not _is_finite_number(current_max) or current_max <= 0:
        current_max = _DEFAULT_MAX_WATT

    raw_new = mean * factor
    if not _is_finite_number(raw_new):
        return None

    # Step 1: clamp first (relative bounds intersected with absolute bounds).
    lower = max(current_max * _REL_CLAMP_LOW_FACTOR, _ABS_MIN_WATT)
    upper = min(current_max * _REL_CLAMP_HIGH_FACTOR, _ABS_MAX_WATT)
    if lower > upper:
        # Degenerate bounds (shouldn't happen with sane config, but never crash).
        return None

    clamped = min(max(raw_new, lower), upper)
    new_max_watt = int(round(clamped))

    # Step 2: hysteresis compare against the *clamped* value.
    diff_pct = abs(new_max_watt - current_max) / current_max
    if diff_pct <= _HYSTERESIS_PCT:
        return None

    return {"max_watt": new_max_watt}


LEARNABLE: dict[str, Callable[[dict, dict, float], Optional[dict]]] = {
    "power": _learn_power,
}


def learned_threshold(
    detector: str, baseline: dict, current_cfg: dict, factor: float = 2.0
) -> Optional[dict]:
    """Propose a new threshold config for `detector`, or None.

    Pure and deterministic: same inputs always produce the same output.
    Never raises — any missing/None/NaN field in `baseline` or `current_cfg`,
    or an unlearnable `detector`, simply yields None.
    """
    fn = LEARNABLE.get(detector)
    if fn is None:
        return None
    try:
        return fn(baseline, current_cfg, factor)
    except Exception:
        return None
