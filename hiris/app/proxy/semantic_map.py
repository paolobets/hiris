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

    def build_from_cache(self, entity_cache: Any) -> list[str]:
        """Classify all entities not yet in the map. Returns list of ambiguous entity IDs needing LLM."""
        known = self.get_all_entity_ids()
        all_entities = entity_cache.get_all_useful()
        ambiguous: list[str] = []
        for e in all_entities:
            eid = e["id"]
            if eid in known:
                continue
            role = classify_by_rules(eid)
            if role:
                label = e.get("name") or eid.split(".")[-1]
                unit = e.get("unit") or ""
                self._add_entity(eid, role, label, unit=unit, classified_by="rules")
            else:
                self._add_entity(eid, "unknown", e.get("name") or eid, classified_by="pending")
                ambiguous.append(eid)
        if all_entities:
            self.save()
        return ambiguous

    def on_entity_added(self, entity_id: str, attributes: dict) -> None:
        """Called when HA fires entity_registry_updated for a new entity."""
        if entity_id in self.get_all_entity_ids():
            return
        role = classify_by_rules(entity_id)
        label = attributes.get("friendly_name") or entity_id.split(".")[-1]
        if role:
            self._add_entity(entity_id, role, label, classified_by="rules")
            logger.info("SemanticMap: auto-classified %s → %s", entity_id, role)
        else:
            self._add_entity(entity_id, "unknown", label, classified_by="pending")
            logger.info("SemanticMap: %s queued for LLM classification", entity_id)
            if self._router:
                asyncio.create_task(
                    self._classify_unknown_batch(),
                    name=f"classify_{entity_id}",
                )
        self.save()

    def get_prompt_snippet(self, entity_cache: Any) -> str:
        """Return compact home context string for injection into system prompt."""
        now = datetime.now(timezone.utc).strftime("%H:%M")

        parts = [f"CASA [mappa agg. {now}]"]

        # Energy meters
        energy_ids = (
            self.get_category("energy_meter") +
            self.get_category("solar_production") +
            self.get_category("grid_import")
        )
        if energy_ids:
            labels = []
            for eid in energy_ids[:6]:
                meta = self._entity_meta.get(eid, {})
                unit = meta.get("unit") or "?"
                labels.append(f"{eid}({unit})")
            parts.append("Energia: " + ", ".join(labels))

        # Climate — eid(curr°→setp°C hvac_action) for climate.*, eid(value°C) for sensor.*
        climate_ids = self.get_category("climate_sensor")
        if climate_ids:
            segs = []
            for eid in climate_ids[:4]:
                domain = eid.split(".")[0]
                state_data = entity_cache.get_state(eid) or {}
                state = state_data.get("state", "")
                a = state_data.get("attributes") or {}
                if domain == "climate":
                    curr = a.get("current_temperature")
                    setp = a.get("temperature")
                    hvac_action = a.get("hvac_action", "")
                    if curr is not None and setp is not None:
                        seg = f"{eid}({curr}°→{setp}°C{' ' + hvac_action if hvac_action else ''})"
                    elif curr is not None:
                        seg = f"{eid}({curr}°C)"
                    else:
                        seg = f"{eid}({state})"
                else:
                    seg = f"{eid}({state}°C)" if state else f"{eid}(unknown)"
                segs.append(seg)
            if segs:
                parts.append("Clima: " + ", ".join(segs))

        # Presence
        presence_ids = self.get_category("presence")
        if presence_ids:
            states = entity_cache.get_minimal(presence_ids[:3])
            segs = [f"{e.get('name') or e['id']}({e['state']})" for e in states]
            if segs:
                parts.append("Presenze: " + ", ".join(segs))

        # Lighting — N entità / M stanze (unique non-empty areas)
        lighting_ids = self.get_category("lighting")
        if lighting_ids:
            areas = {self._entity_meta.get(eid, {}).get("area", "") for eid in lighting_ids}
            area_count = len({a for a in areas if a})
            parts.append(f"Luci: {len(lighting_ids)} entità / {area_count} stanze")

        # Appliances — use entity IDs directly (Claude needs them for service calls)
        appliance_ids = self.get_category("appliance")
        if appliance_ids:
            parts.append("Elettrodomestici: " + ", ".join(appliance_ids[:4]))

        # Unknown pending classification
        unknown_count = len([
            eid for eid in self._categories.get("unknown", [])
            if self._entity_meta.get(eid, {}).get("classified_by") == "pending"
        ])
        if unknown_count:
            parts.append(f"Sconosciuti: {unknown_count} entità in attesa classificazione")

        return "\n".join(parts)

    async def _classify_unknown_batch(self) -> None:
        """Classify all 'unknown'/'pending' entities via LLM router in batches of 20."""
        if not self._router:
            return
        pending = [
            eid for eid in self._categories.get("unknown", [])
            if self._entity_meta.get(eid, {}).get("classified_by") == "pending"
        ]
        if not pending:
            return
        BATCH = 20
        for i in range(0, len(pending), BATCH):
            batch_ids = pending[i:i + BATCH]
            entities = [
                {"id": eid, **self._entity_meta.get(eid, {})}
                for eid in batch_ids
            ]
            try:
                results = await self._router.classify_entities(entities)
                for eid, meta in results.items():
                    if eid not in self._entity_meta:
                        continue
                    role = meta.get("role", "other")
                    label = meta.get("label", eid.split(".")[-1])
                    confidence = float(meta.get("confidence", 0.8))
                    self._add_entity(
                        eid, role, label,
                        classified_by="claude",
                        confidence=confidence,
                    )
                self.save()
            except Exception as exc:
                logger.warning("LLM batch classification failed: %s", exc)
