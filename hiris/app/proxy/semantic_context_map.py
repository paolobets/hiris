from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .entity_cache import EntityCache
    from .knowledge_db import KnowledgeDB

logger = logging.getLogger(__name__)

ENTITY_TYPE_SCHEMA: dict[tuple[str, str | None], tuple[str, str]] = {
    ("climate", None): ("climate", "Termostato"),
    ("light", None): ("light", "Luce"),
    ("cover", None): ("cover", "Tapparella"),
    ("media_player", None): ("media_player", "Media"),
    ("lock", None): ("lock", "Serratura"),
    ("alarm_control_panel", None): ("alarm", "Allarme"),
    ("vacuum", None): ("vacuum", "Robot"),
    ("fan", None): ("fan", "Ventilatore"),
    ("water_heater", None): ("water_heater", "Scaldabagno"),
    ("switch", None): ("switch", "Interruttore"),
    ("input_boolean", None): ("switch", "Interruttore"),
    ("sensor", "temperature"): ("temperature", "Temperatura"),
    ("sensor", "humidity"): ("humidity", "Umidità"),
    ("sensor", "power"): ("power", "Potenza"),
    ("sensor", "energy"): ("energy", "Energia"),
    ("sensor", "battery"): ("battery", "Batteria"),
    ("sensor", "illuminance"): ("illuminance", "Luminosità"),
    ("sensor", "co2"): ("co2", "CO₂"),
    ("sensor", "pm25"): ("pm25", "PM2.5"),
    ("sensor", "pressure"): ("pressure", "Pressione"),
    ("sensor", "voltage"): ("voltage", "Tensione"),
    ("sensor", "current"): ("current", "Corrente"),
    ("sensor", "gas"): ("gas", "Gas"),
    ("sensor", "water"): ("water", "Acqua"),
    ("binary_sensor", "motion"): ("motion", "Presenza"),
    ("binary_sensor", "occupancy"): ("motion", "Presenza"),
    ("binary_sensor", "door"): ("door", "Porta"),
    ("binary_sensor", "window"): ("window", "Finestra"),
    ("binary_sensor", "presence"): ("presence", "Presenza"),
    ("binary_sensor", "smoke"): ("smoke", "Fumo"),
    ("binary_sensor", "moisture"): ("moisture", "Perdita"),
    ("binary_sensor", "vibration"): ("vibration", "Vibrazione"),
    ("binary_sensor", "connectivity"): ("connectivity", "Connessione"),
}

_DOMAIN_FALLBACK: dict[str, tuple[str, str]] = {
    "sensor": ("sensor", "Sensore"),
    "binary_sensor": ("binary", "Sensore"),
}

_EXCLUDED_DOMAINS = frozenset({
    "update", "button", "tag", "event", "ai_task", "todo", "conversation",
    "device_tracker", "persistent_notification", "scene", "script",
    "automation", "input_text", "input_number", "input_select",
    "input_datetime", "number", "select", "text", "image",
    "stt", "tts", "notify", "remote", "siren", "wake_word",
})

CONCEPT_TO_TYPES: dict[str, list[str]] = {
    "termostato": ["climate"], "riscaldamento": ["climate"],
    "raffreddamento": ["climate"], "clima": ["climate"],
    "caldo": ["climate", "temperature"], "freddo": ["climate", "temperature"],
    "gradi": ["climate", "temperature"], "temperatura": ["climate", "temperature"],
    "luce": ["light"], "luci": ["light"], "illuminazione": ["light"],
    "lampada": ["light"], "accesa": ["light"], "spenta": ["light"],
    "consumo": ["power", "energy"], "energia": ["energy"],
    "watt": ["power"], "kwh": ["energy"], "bolletta": ["energy"],
    "movimento": ["motion"], "presenza": ["motion", "presence"],
    "qualcuno": ["motion"], "persona": ["motion"],
    "porta": ["door"], "finestra": ["window"], "ingresso": ["door"],
    "aperta": ["door", "window", "cover"], "chiusa": ["door", "window", "cover"],
    "tapparella": ["cover"], "veneziana": ["cover"],
    "tenda": ["cover"], "avvolgibile": ["cover"],
    "tv": ["media_player"], "televisione": ["media_player"],
    "musica": ["media_player"], "volume": ["media_player"],
    "umidità": ["humidity"],
    "serratura": ["lock"], "chiave": ["lock"],
    "allarme": ["alarm"], "sicurezza": ["alarm"],
    "robot": ["vacuum"], "aspirapolvere": ["vacuum"],
    "lavatrice": ["switch"], "lavastoviglie": ["switch"],
    "interruttore": ["switch"],
}

# area_name (or None for unassigned) → entity_type → [entity_ids]
_MapType = dict[str | None, dict[str, list[str]]]


def classify_entity(domain: str, device_class: str | None) -> tuple[str, str]:
    """Return (entity_type, label_it). Returns ('other', domain) if unrecognised."""
    key = (domain, device_class)
    if key in ENTITY_TYPE_SCHEMA:
        return ENTITY_TYPE_SCHEMA[key]
    key_no_dc = (domain, None)
    if key_no_dc in ENTITY_TYPE_SCHEMA:
        return ENTITY_TYPE_SCHEMA[key_no_dc]
    if domain in _DOMAIN_FALLBACK:
        return _DOMAIN_FALLBACK[domain]
    return ("other", domain)


class SemanticContextMap:
    def __init__(self) -> None:
        self._map: _MapType = {}
        self._type_to_label: dict[str, str] = {}

    def build(
        self,
        entity_cache: EntityCache,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> None:
        persisted = knowledge_db.load_classifications() if knowledge_db else {}
        area_map = entity_cache.get_area_map() or {}

        eid_to_area: dict[str, str | None] = {}
        for area_name, eids in area_map.items():
            resolved = None if area_name == "__no_area__" else area_name
            for eid in eids:
                eid_to_area[eid] = resolved

        new_map: _MapType = {}
        for eid, entity_data in entity_cache._states.items():
            domain = entity_data.get("domain", eid.split(".")[0])
            if domain in _EXCLUDED_DOMAINS:
                continue
            device_class = entity_data.get("device_class")

            if eid in persisted and persisted[eid]["classified_by"] == "user":
                entity_type = persisted[eid]["entity_type"]
                label_it = persisted[eid]["label_it"]
            else:
                entity_type, label_it = classify_entity(domain, device_class)
                if entity_type == "other":
                    continue
                if knowledge_db and eid not in persisted:
                    knowledge_db.save_classification(
                        entity_id=eid,
                        area=eid_to_area.get(eid),
                        entity_type=entity_type,
                        label_it=label_it,
                        friendly_name=entity_data.get("name", ""),
                        domain=domain,
                        device_class=device_class,
                    )

            self._type_to_label[entity_type] = label_it
            area = eid_to_area.get(eid)
            new_map.setdefault(area, {}).setdefault(entity_type, []).append(eid)

        self._map = new_map
        n_areas = len([k for k in new_map if k is not None])
        n_entities = sum(len(eids) for t in new_map.values() for eids in t.values())
        logger.info("SemanticContextMap built: %d areas, %d entities", n_areas, n_entities)
