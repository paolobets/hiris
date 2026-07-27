"""Shared truthy-env parsing (SP-2 tech-debt: unify the ~13 duplicated idioms)."""
from __future__ import annotations

import os

_TRUTHY = ("1", "true", "yes", "on")


def env_bool(name: str, default: bool = False) -> bool:
    """Return True when env var `name` is a truthy string.

    Empty/unset → `default`. Comparison is case- and whitespace-insensitive
    against ("1","true","yes","on"). Replaces the mix of bare `in (...)`,
    `.strip().lower() in (...)`, and `== "true"` checks scattered across
    server.py / handlers_models.py.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUTHY
