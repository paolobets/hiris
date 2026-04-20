from __future__ import annotations
from datetime import datetime, timezone
from .entity_cache import EntityCache


def generate_home_profile(entity_cache: EntityCache) -> str:
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
    climate_str = (
        ", ".join(f"{(e.get('name') or e['id'])}: {e['state']}" for e in climate[:3])
        if climate else "n/a"
    )

    return (
        f"CASA [aggiornato {now}]:\n"
        f"Accesi({on_count}): {on_summary}\n"
        f"Clima: {climate_str}"
    )
