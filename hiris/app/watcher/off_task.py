from __future__ import annotations
from typing import Optional


def build_off_task(action: dict) -> Optional[dict]:
    if not isinstance(action, dict):
        return None
    mins = action.get("off_after_min")
    eid = action.get("entity_id")
    if not mins or mins <= 0 or not eid or action.get("service") != "turn_on":
        return None
    domain = action.get("domain") or eid.split(".", 1)[0]
    return {"label": f"sentinel-off:{eid}",
            "trigger": {"type": "delay", "minutes": int(mins)},
            "actions": [{"type": "call_ha_service", "domain": domain,
                         "service": "turn_off", "data": {"entity_id": eid}}],
            "one_shot": True}
