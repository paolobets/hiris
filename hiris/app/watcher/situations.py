from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass
class SituationSignal:
    kind: str
    severity: str
    evidence: dict
    suggested_action: Optional[dict] = None

def situation_hot_and_away(snap, cfg) -> Optional[SituationSignal]:
    temp = snap.get("outside_temp_c")
    if temp is None or temp < cfg.get("hot_threshold_c", 32):
        return None
    if (snap.get("presence") or {}).get("present") is not False:
        return None
    if cfg.get("skip_if_rain", True) and (snap.get("weather") or {}).get("rain_soon") is True:
        return None
    return SituationSignal(
        kind="hot_and_away", severity="info",
        evidence={"outside_temp_c": temp, "threshold": cfg.get("hot_threshold_c", 32)},
        suggested_action={"domain": "switch", "service": "turn_on",
                          "entity_id": cfg.get("valve_entity"), "data": {},
                          "off_after_min": cfg.get("run_minutes", 5)})

def situation_away_alarm_off(snap, cfg) -> Optional[SituationSignal]:
    if (snap.get("presence") or {}).get("present") is not False:
        return None
    if snap.get("alarm_state") not in cfg.get("disarmed_states", ["disarmed"]):
        return None
    return SituationSignal(kind="away_alarm_off", severity="warn",
                           evidence={"alarm_state": snap.get("alarm_state")},
                           suggested_action=None)

SITUATIONS: dict[str, Callable] = {
    "hot_and_away": situation_hot_and_away,
    "away_alarm_off": situation_away_alarm_off,
}
