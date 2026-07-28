from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import health_checks as hc
from .health_checks import CHECK_IDS

logger = logging.getLogger(__name__)


def _iso(now: datetime | None) -> str:
    dt = now or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def run_health_scan(*, ha_client, entity_cache, tiers, entity_tiers, store,
                          now=None, unavailable_days: int = 2,
                          battery_pct: int = 15) -> dict:
    now = now or datetime.now(timezone.utc)

    raw_states = []
    try:
        raw_states = await ha_client.get_states([])
    except Exception:
        logger.warning("health_scan: get_states failed", exc_info=True)

    minimal = []
    try:
        if entity_cache is not None:
            minimal = entity_cache.all_states() or []
    except Exception:
        logger.warning("health_scan: cache states failed", exc_info=True)

    automations = []
    try:
        automations = await ha_client.get_automations()
    except Exception:
        logger.warning("health_scan: get_automations failed", exc_info=True)

    no_area = []
    try:
        area_map = entity_cache.get_area_map() if entity_cache is not None else None
        if area_map is None and entity_cache is not None:
            await entity_cache.load_area_registry(ha_client)
            area_map = entity_cache.get_area_map()
        no_area = (area_map or {}).get("__no_area__", [])
    except Exception:
        logger.warning("health_scan: area map failed", exc_info=True)

    candidates = []
    candidates += hc.check_entity_unavailable(raw_states, now=now, days=unavailable_days)
    candidates += hc.check_low_battery(minimal, threshold=battery_pct)
    candidates += hc.check_automation_broken(automations)
    candidates += hc.check_dangerous_domain_green(tiers or {}, entity_tiers or {})
    candidates += hc.check_entity_no_area(no_area)

    return store.reconcile(candidates, CHECK_IDS, now=_iso(now))
