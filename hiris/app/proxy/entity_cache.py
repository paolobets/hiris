from __future__ import annotations

NOISE_DOMAINS = {"button", "update", "number", "select", "tag",
                 "event", "ai_task", "todo", "conversation"}


def _domain(entity_id: str) -> str:
    return entity_id.split(".")[0]


_CLIMATE_ATTRS = ("current_temperature", "temperature", "hvac_action")


def _to_minimal(raw: dict) -> dict:
    attrs = raw.get("attributes") or {}
    result: dict = {
        "id": raw["entity_id"],
        "state": raw.get("state", "unknown"),
        "name": attrs.get("friendly_name") or "",
        "unit": attrs.get("unit_of_measurement") or "",
    }
    if raw.get("entity_id", "").startswith("climate."):
        extra = {k: attrs[k] for k in _CLIMATE_ATTRS if k in attrs}
        if extra:
            result["attributes"] = extra
    return result


class EntityCache:
    def __init__(self) -> None:
        self._states: dict[str, dict] = {}
        self._by_domain: dict[str, list[str]] = {}
        self._area_map: dict[str, list[str]] | None = None  # None = not loaded yet

    async def load(self, ha_client) -> None:
        raw_states = await ha_client.get_states([])
        self._states = {}
        self._by_domain = {}
        for raw in raw_states:
            eid = raw.get("entity_id")
            if not eid:
                continue
            self._states[eid] = _to_minimal(raw)
            dom = _domain(eid)
            self._by_domain.setdefault(dom, []).append(eid)

    def on_state_changed(self, event_data: dict) -> None:
        new_state = event_data.get("new_state")
        if not new_state:
            return
        eid = new_state.get("entity_id")
        if not eid:
            return
        minimal = _to_minimal(new_state)
        if eid not in self._states:
            dom = _domain(eid)
            self._by_domain.setdefault(dom, []).append(eid)
        self._states[eid] = minimal

    def get_state(self, entity_id: str) -> dict | None:
        return self._states.get(entity_id)

    def get_minimal(self, entity_ids: list[str]) -> list[dict]:
        return [self._states[eid] for eid in entity_ids if eid in self._states]

    def get_by_domain(self, domain: str) -> list[dict]:
        ids = self._by_domain.get(domain, [])
        return self.get_minimal(ids)

    def get_on(self) -> list[dict]:
        return [e for e in self._states.values() if e["state"] == "on"]

    def get_all_useful(self) -> list[dict]:
        return [
            e for eid, e in self._states.items()
            if _domain(eid) not in NOISE_DOMAINS
        ]

    def get_all(self) -> list[dict]:
        return list(self._states.values())

    async def load_area_registry(self, ha_client) -> None:
        """Load area→entity mapping from HA registries. Cached until next call."""
        areas = await ha_client.get_area_registry()
        entities = await ha_client.get_entity_registry()
        area_lookup: dict[str, str] = {a["area_id"]: a["name"] for a in areas}
        result: dict[str, list[str]] = {}
        no_area: list[str] = []
        for entry in entities:
            eid = entry.get("entity_id", "")
            if not eid:
                continue
            area_id = entry.get("area_id")
            if area_id and area_id in area_lookup:
                result.setdefault(area_lookup[area_id], []).append(eid)
            else:
                no_area.append(eid)
        if no_area:
            result["__no_area__"] = no_area
        self._area_map = result

    def get_area_map(self) -> dict[str, list[str]] | None:
        """Return cached area→[entity_id] map. None if not yet loaded; {} if loaded but no areas."""
        return self._area_map
