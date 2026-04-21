from __future__ import annotations
import time
from datetime import datetime, timezone
from .entity_cache import EntityCache

# ── module-level cache ────────────────────────────────────────────────────────
_cached_profile: str = ""
_cached_at: float = 0.0


def _now() -> float:
    """Indirection for monkeypatching in tests."""
    return time.monotonic()


def _reset_profile_cache() -> None:
    """Force cache invalidation — used in tests."""
    global _cached_profile, _cached_at
    _cached_profile = ""
    _cached_at = 0.0


# ── public API ────────────────────────────────────────────────────────────────

def generate_home_profile(entity_cache: EntityCache) -> str:
    """Generate fresh profile string (no caching). Used internally and in tests."""
    now = datetime.now(timezone.utc).strftime("%H:%M")
    entities = entity_cache.get_all_useful()

    on_entities = [e for e in entities if e.get("state") == "on"]
    on_by_domain: dict[str, int] = {}
    for e in on_entities:
        domain = e["id"].split(".")[0]
        on_by_domain[domain] = on_by_domain.get(domain, 0) + 1

    on_count = len(on_entities)
    on_summary = (
        ", ".join(f"{d}({n})" for d, n in sorted(on_by_domain.items()))
        if on_by_domain else "nessuno"
    )

    climate = [e for e in entities if e["id"].startswith("climate.")]
    if climate:
        parts = []
        for e in climate[:4]:
            name = e.get("name") or e["id"]
            seg = f"{name}: {e['state']}"
            a = e.get("attributes") or {}
            curr = a.get("current_temperature")
            setp = a.get("temperature")
            if curr is not None:
                seg += f" {curr}°C"
            if setp is not None:
                seg += f"→{setp}°C"
            parts.append(seg)
        climate_str = ", ".join(parts)
    else:
        climate_str = "n/a"

    return (
        f"CASA [aggiornato {now}] — snapshot di orientamento, usa i tool per valori precisi:\n"
        f"Accesi({on_count}): {on_summary}\n"
        f"Clima: {climate_str}"
    )


def get_cached_home_profile(entity_cache: EntityCache, ttl: float = 60.0) -> str:
    """Return HOME_PROFILE, regenerating at most once per `ttl` seconds.

    Keeping the system prompt string stable within the TTL window maximises
    Anthropic API prompt-cache hits, cutting cached-input token cost by ~90%.
    TTL defaults to 60 s (aligned with the HH:MM timestamp granularity).
    """
    global _cached_profile, _cached_at
    ts = _now()
    if _cached_profile and (ts - _cached_at) < ttl:
        return _cached_profile
    _cached_profile = generate_home_profile(entity_cache)
    _cached_at = ts
    return _cached_profile
