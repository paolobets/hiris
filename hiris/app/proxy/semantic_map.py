from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ALL_ROLES = [
    "energy_meter", "solar_production", "grid_import",
    "climate_sensor", "presence", "lighting", "door_window",
    "appliance", "electrical", "diagnostic", "other", "unknown",
]

_RULES: list[tuple[str, str]] = [
    # Solar/PV must come before generic _power/_energy to avoid false positives
    ("_solar",          "solar_production"),
    ("_pv",             "solar_production"),
    ("_photovoltaic",   "solar_production"),
    ("_power",          "energy_meter"),
    ("_energy",         "energy_meter"),
    ("_consumption",    "energy_meter"),
    ("_watt",           "energy_meter"),
    ("_grid",           "grid_import"),
    ("_import",         "grid_import"),
    ("_export",         "grid_import"),
    ("_temp",           "climate_sensor"),
    ("_temperature",    "climate_sensor"),
    ("_motion",         "presence"),
    ("_presence",       "presence"),
    ("_occupancy",      "presence"),
    ("_door",           "door_window"),
    ("_window",         "door_window"),
    ("_lavatrice",      "appliance"),
    ("_lavastoviglie",  "appliance"),
    ("_forno",          "appliance"),
    ("_boiler",         "appliance"),
    ("_voltage",        "electrical"),
    ("_current",        "electrical"),
    ("_cfgchanged",     "diagnostic"),
    ("config_",         "diagnostic"),
]

_DOMAIN_RULES: dict[str, str] = {
    "light":    "lighting",
    "climate":  "climate_sensor",
    "update":   "diagnostic",
}


def classify_by_rules(entity_id: str) -> Optional[str]:
    """Return a role string if the entity_id matches a known pattern, else None.

    Patterns use a leading ``_`` as word-boundary marker. The function checks
    against the full entity_id AND against ``_<name>`` so that patterns like
    ``_motion`` also match entities whose name *starts* with ``motion``, e.g.
    ``binary_sensor.motion_salotto``.
    """
    domain = entity_id.split(".")[0]
    if domain in _DOMAIN_RULES:
        return _DOMAIN_RULES[domain]
    name = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
    # Build a composite search string: full entity_id + "_" + name
    # This ensures patterns like "_motion" match both "foo_motion_bar" and "domain.motion_bar"
    lower_full = entity_id.lower()
    lower_name = "_" + name.lower()
    for pattern, role in _RULES:
        if pattern in lower_full or pattern in lower_name:
            return role
    return None


class SemanticMap:
    def __init__(self, data_dir: str) -> None:
        self._path = os.path.join(data_dir, "home_semantic_map.json")
        self._categories: dict[str, list[str]] = {role: [] for role in ALL_ROLES}
        self._entity_meta: dict[str, dict] = {}
        self._router: Any = None
        self._classify_task: Optional[asyncio.Task] = None
        self._generated_at: Optional[str] = None
        self._last_updated: Optional[str] = None

    def set_router(self, router: Any) -> None:
        self._router = router

    def _add_entity(
        self,
        entity_id: str,
        role: str,
        label: str,
        area: str = "",
        unit: str = "",
        classified_by: str = "rules",
        confidence: float = 1.0,
    ) -> None:
        if role not in self._categories:
            role = "other"
        # Remove from any previous category to avoid duplicates across categories
        for cat_ids in self._categories.values():
            if entity_id in cat_ids:
                cat_ids.remove(entity_id)
        if entity_id not in self._categories[role]:
            self._categories[role].append(entity_id)
        self._entity_meta[entity_id] = {
            "label": label,
            "role": role,
            "area": area,
            "unit": unit,
            "classified_by": classified_by,
            "confidence": confidence,
        }

    def get_category(self, role: str) -> list[str]:
        return list(self._categories.get(role, []))

    def get_all_entity_ids(self) -> list[str]:
        return list(self._entity_meta.keys())

    def load(self) -> bool:
        if not os.path.exists(self._path):
            return False
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._generated_at = data.get("generated_at")
            self._last_updated = data.get("last_updated")
            self._categories = {role: [] for role in ALL_ROLES}
            for role, ids in data.get("categories", {}).items():
                self._categories[role] = list(ids)
            self._entity_meta = data.get("entity_meta", {})
            return True
        except Exception as exc:
            logger.warning("SemanticMap load failed: %s", exc)
            return False

    def save(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self._generated_at:
            self._generated_at = now
        self._last_updated = now
        data = {
            "version": "1",
            "generated_at": self._generated_at,
            "last_updated": self._last_updated,
            "categories": self._categories,
            "entity_meta": self._entity_meta,
        }
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.error("SemanticMap save failed: %s", exc)
