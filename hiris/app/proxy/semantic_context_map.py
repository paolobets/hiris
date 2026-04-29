from __future__ import annotations
import asyncio
import fnmatch
import json
import logging
import os
from datetime import datetime
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
    # Irrigation / outdoor
    ("sensor", "precipitation"): ("precipitation", "Precipitazione"),
    ("sensor", "moisture"): ("soil_moisture", "Umidità suolo"),
    ("weather", None): ("weather", "Meteo"),
}

_DOMAIN_FALLBACK: dict[str, tuple[str, str]] = {
    "sensor": ("sensor", "Sensore"),
    "binary_sensor": ("binary", "Sensore"),
}

# Superset of entity_cache.NOISE_DOMAINS — keep in sync when adding noise domains.
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
    "ventilatore": ["fan"], "co2": ["co2"], "anidride": ["co2"],
    "batteria": ["battery"], "luminosità": ["illuminance"], "lux": ["illuminance"],
    "pm25": ["pm25"], "polveri": ["pm25"],
    "pressione": ["pressure"], "tensione": ["voltage"], "corrente": ["current"],
    "gas": ["gas"], "acqua": ["water"], "perdita": ["moisture"],
    "fumo": ["smoke"], "vibrazione": ["vibration"], "connessione": ["connectivity"],
    "scaldabagno": ["water_heater"], "boiler": ["water_heater"],
    # Irrigation / outdoor
    "irrigazione": ["switch", "soil_moisture"],
    "irrigare": ["switch", "soil_moisture"],
    "sprinkler": ["switch"],
    "pioggia": ["precipitation", "weather"],
    "piovuto": ["precipitation", "weather"],
    "precipitazione": ["precipitation"],
    "umidità suolo": ["soil_moisture"],
    "giardino": ["switch", "soil_moisture", "precipitation"],
    "meteo": ["weather"],
    "previsioni": ["weather"],
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


_NO_AREA_KEY = "__no_area__"


class SemanticContextMap:
    def __init__(self, cache_path: str | None = None) -> None:
        self._map: _MapType = {}
        self._type_to_label: dict[str, str] = {}
        self._cache_path = cache_path

    def save(self) -> None:
        if not self._cache_path:
            return
        serialized_map = {
            (_NO_AREA_KEY if k is None else k): v
            for k, v in self._map.items()
        }
        data = {"version": "1", "map": serialized_map, "type_to_label": dict(self._type_to_label)}
        tmp = self._cache_path + ".tmp"
        cache_path = self._cache_path

        def _write() -> None:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp, cache_path)
                logger.debug("SemanticContextMap saved to %s", cache_path)
            except Exception as exc:
                logger.warning("SemanticContextMap save failed: %s", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _write)
        except RuntimeError:
            _write()

    def load(self) -> bool:
        if not self._cache_path:
            return False
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("map", {})
            self._map = {
                (None if k == _NO_AREA_KEY else k): {et: list(eids) for et, eids in types.items()}
                for k, types in raw.items()
            }
            self._type_to_label = data.get("type_to_label", {})
            n = sum(len(eids) for t in self._map.values() for eids in t.values())
            logger.info("SemanticContextMap loaded from cache: %d entities", n)
            return True
        except FileNotFoundError:
            return False
        except Exception as exc:
            logger.warning("SemanticContextMap load failed: %s", exc)
            return False

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
        for eid, entity_data in entity_cache.get_all_states().items():
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

        n_areas = len([k for k in new_map if k is not None])
        n_entities = sum(len(eids) for t in new_map.values() for eids in t.values())
        if n_entities == 0:
            logger.warning("SemanticContextMap.build(): entity cache empty, keeping previous map")
            return
        self._map = new_map
        logger.info("SemanticContextMap built: %d areas, %d entities", n_areas, n_entities)
        self.save()

    def _get_label(self, entity_type: str) -> str:
        return self._type_to_label.get(entity_type, entity_type)

    def _format_state(self, entity_type: str, entity_data: dict) -> str:
        state = entity_data.get("state", "")
        attrs = entity_data.get("attributes") or {}
        if entity_type == "climate":
            cur = attrs.get("current_temperature", "?")
            sp = attrs.get("temperature", "?")
            mode = attrs.get("hvac_mode", state)
            action = attrs.get("hvac_action", "")
            action_str = f" · {action}" if action and action not in ("idle", "off") else ""
            return f"{mode} · {cur}°C → {sp}°C{action_str}"
        if entity_type == "light":
            if state == "off":
                return "spenta"
            b = attrs.get("brightness")
            return f"accesa {round(b / 255 * 100)}%" if b is not None else "accesa"
        if entity_type == "cover":
            pos = attrs.get("current_position")
            return f"{state} {pos}%" if pos is not None else state
        if entity_type == "media_player":
            if state in ("off", "standby", "idle"):
                return state
            title = attrs.get("media_title", "")
            vol = attrs.get("volume_level")
            vol_str = f" vol:{round(vol * 100)}%" if vol is not None else ""
            return f"{state} · {title}{vol_str}" if title else f"{state}{vol_str}"
        if entity_type in ("motion", "presence"):
            return "rilevato" if state == "on" else "assente"
        if entity_type == "door":
            return "aperta" if state == "on" else "chiusa"
        if entity_type == "window":
            return "aperta" if state == "on" else "chiusa"
        if entity_type == "switch":
            return "acceso" if state == "on" else "spento"
        unit = entity_data.get("unit", "")
        return f"{state} {unit}".strip() if unit else state

    def _filter_by_allowed(self, allowed_entities: list[str] | None) -> _MapType:
        if not allowed_entities:
            return self._map
        result: _MapType = {}
        for area, types in self._map.items():
            filtered: dict[str, list[str]] = {}
            for et, eids in types.items():
                ok = [e for e in eids if any(fnmatch.fnmatch(e, p) for p in allowed_entities)]
                if ok:
                    filtered[et] = ok
            if filtered:
                result[area] = filtered
        return result

    def _format_overview(self, filtered: _MapType, now: str) -> str:
        named = {k: v for k, v in filtered.items() if k is not None}
        unassigned = filtered.get(None, {})
        lines = [f"CASA — {len(named)} aree [agg. {now}]"]
        for area in sorted(named):
            parts = []
            for et, eids in sorted(named[area].items()):
                label = self._get_label(et)
                parts.append(f"{label}×{len(eids)}" if len(eids) > 1 else label)
            lines.append(f"  {area}: {' · '.join(parts)}")
        if unassigned:
            ua = [self._get_label(et) for et in unassigned]
            lines.append(f"[Non assegnate: {' · '.join(ua)}]")
        return "\n".join(lines)

    def _format_detail(
        self,
        filtered: _MapType,
        entity_cache: EntityCache,
        areas: list[str | None],
        types: set[str] | None,
        knowledge_db: Optional[KnowledgeDB] = None,
        now: str = "",
    ) -> str:
        sections = []
        for area in areas:
            area_types = filtered.get(area, {})
            relevant = {
                et: eids for et, eids in area_types.items()
                if types is None or et in types
            }
            if not relevant:
                continue
            header = (area or "Non assegnate").upper()
            lines = [f"{header} [agg. {now}]"]
            for et, eids in relevant.items():
                label = self._get_label(et)
                for eid in eids:
                    ed = entity_cache.get_state(eid)
                    if ed is None:
                        logger.debug("get_state returned None for %s (cache/map desync?)", eid)
                        continue
                    state_str = self._format_state(et, ed)
                    name = ed.get("name") or eid
                    lines.append(f"  {label:<14} {name:<32} {state_str}")
                    if knowledge_db:
                        for annot in knowledge_db.get_annotations(eid)[:1]:
                            lines.append(
                                f"    [Nota: {annot['annotation']} — {annot['source']}]"
                            )
            if len(lines) > 1:
                sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def get_context(
        self,
        query: str,
        entity_cache: EntityCache,
        allowed_entities: list[str] | None = None,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> tuple[str, frozenset[str]]:
        filtered = self._filter_by_allowed(allowed_entities)
        visible_ids = frozenset(
            eid
            for types in filtered.values()
            for eids in types.values()
            for eid in eids
        )
        now = datetime.now().strftime("%H:%M")
        q = query.lower()
        area_matches = [a for a in filtered if a is not None and a.lower() in q]
        type_matches: set[str] = set()
        for concept, ctypes in CONCEPT_TO_TYPES.items():
            if concept in q:
                type_matches.update(ctypes)
        overview = self._format_overview(filtered, now)
        if area_matches or type_matches:
            expand = area_matches if area_matches else [a for a in filtered if a is not None]
            detail = self._format_detail(
                filtered, entity_cache, expand, type_matches or None, knowledge_db, now
            )
            context = f"{overview}\n\n{detail}" if detail else overview
        else:
            context = overview
        return context, visible_ids

    def add_entity(
        self,
        entity_id: str,
        domain: str,
        device_class: str | None,
        area: str | None,
        knowledge_db: Optional[KnowledgeDB] = None,
    ) -> None:
        if domain in _EXCLUDED_DOMAINS:
            return
        entity_type, label_it = classify_entity(domain, device_class)
        if entity_type == "other":
            return
        self._type_to_label[entity_type] = label_it
        bucket = self._map.setdefault(area, {}).setdefault(entity_type, [])
        if entity_id not in bucket:
            bucket.append(entity_id)

    def remove_entity(self, entity_id: str) -> None:
        for area_types in self._map.values():
            for eids in area_types.values():
                if entity_id in eids:
                    eids.remove(entity_id)
                    return
