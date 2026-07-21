from __future__ import annotations
import logging, time
from typing import Optional

log = logging.getLogger(__name__)
_ABSENT = {None, "unavailable", "unknown", ""}

def interpret_presence(state) -> Optional[bool]:
    if state in _ABSENT:
        return None
    s = str(state).strip().lower()
    if s in {"home", "on"}:
        return True
    try:
        return float(s) > 0
    except ValueError:
        return False

def _num(state_dict) -> Optional[float]:
    if not isinstance(state_dict, dict):
        return None
    raw = state_dict.get("state")
    if raw in _ABSENT:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

async def build_snapshot(deps: dict, cfg: dict) -> dict:
    snap = {"presence": {"present": None, "raw": None}, "outside_temp_c": None,
            "weather": {"condition": None, "rain_soon": None}, "alarm_state": None,
            "ha_health": None, "ts": None}
    # entità da leggere in un colpo
    want = {}
    pe = cfg.get("presence_entity")
    te = (cfg.get("hot_and_away") or {}).get("outside_temp_entity")
    ae = (cfg.get("away_alarm_off") or {}).get("alarm_entity")
    ids = [e for e in (pe, te, ae) if e]
    try:
        if ids:
            rows = await deps["get_states"](ids)
            want = {r.get("entity_id"): r for r in (rows or []) if isinstance(r, dict)}
    except Exception:
        log.exception("snapshot get_states failed")
    if pe:
        st = want.get(pe, {}).get("state") if pe in want else None
        snap["presence"] = {"present": interpret_presence(st), "raw": st}
    if te and te in want:
        snap["outside_temp_c"] = _num(want[te])
    if ae and ae in want:
        snap["alarm_state"] = want[ae].get("state")
    try:
        w = await deps["get_weather"]()
        hourly = (w or {}).get("hourly", [])[:6]
        if hourly:
            snap["weather"] = {
                "condition": hourly[0].get("cc"),
                "rain_soon": sum(float(h.get("r") or 0) for h in hourly) > 0.2,
            }
    except Exception:
        log.debug("snapshot weather unavailable")
    try:
        snap["ha_health"] = deps["get_health"]()
    except Exception:
        log.debug("snapshot health unavailable")
    snap["ts"] = time.time()
    return snap
