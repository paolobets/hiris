from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

NOISE_DOMAINS = {"button", "update", "number", "select", "tag",
                 "event", "ai_task", "todo", "conversation"}

# Messaggi per chi legge l'inventario quando l'inventario non e' leggibile.
# Un elenco vuoto direbbe "la casa e' vuota"; questi dicono "non ho potuto
# guardare", che e' l'unica frase vera. I due casi restano distinti perche'
# suggeriscono all'utente due cose diverse: uno e' configurazione mancante,
# l'altro passa da solo (il lavoro periodico di ricarica ritenta).
#
# Vivono qui, accanto alla bandiera `loaded` che li governa, perche' li usano
# quattro moduli diversi (dispatcher, ha_tools, briefing, api/handlers_entities)
# e duplicarne il testo era esattamente il modo in cui il difetto e'
# sopravvissuto nei fratelli.
ERRORE_INVENTARIO_ASSENTE = (
    "Non sono riuscito a leggere lo stato della casa: l'inventario delle "
    "entità non è disponibile. Non posso dire che non ci sia nulla, solo che "
    "non ho potuto controllare."
)
ERRORE_INVENTARIO_NON_PRONTO = (
    "Non sono riuscito a leggere lo stato della casa: l'inventario delle "
    "entità non è ancora pronto (la lettura iniziale da Home Assistant non è "
    "andata a buon fine o è ancora in corso). Riprova fra poco."
)


def inventario_leggibile(cache) -> bool:
    """True quando dalla cache si puo' leggere un inventario che vale come
    fotografia della casa.

    `getattr(..., True)`: una cache finta senza l'attributo `loaded` (i doppi
    usati nei test e nel cablaggio esistente) e' considerata pronta, cosi'
    questa distinzione non ne rompe nessuna.
    """
    return cache is not None and bool(getattr(cache, "loaded", True))


def inventario_non_leggibile(cache) -> dict | None:
    """None se l'inventario e' utilizzabile, altrimenti l'errore da restituire
    subito al chiamante.

    Tre casi, due esiti. Cache assente (mai cablata) e cache presente ma mai
    caricata sono entrambe un guasto: non abbiamo potuto guardare. Cache
    caricata e vuota e' invece un risultato legittimo -- una casa senza
    entita', o senza luci accese, esiste davvero -- e prosegue.
    """
    if cache is None:
        logger.warning("lettura entita' rifiutata: nessun inventario configurato")
        return {"error": ERRORE_INVENTARIO_ASSENTE}
    if not inventario_leggibile(cache):
        logger.warning("lettura entita' rifiutata: inventario non ancora caricato")
        return {"error": ERRORE_INVENTARIO_NON_PRONTO}
    return None


def _domain(entity_id: str) -> str:
    return entity_id.split(".")[0]


_DOMAIN_ATTRS: dict[str, tuple[str, ...]] = {
    "climate": ("hvac_mode", "hvac_action", "current_temperature", "temperature", "preset_mode"),
    "light": ("brightness", "color_temp"),
    "cover": ("current_position",),
    "media_player": ("media_title", "media_artist", "source", "volume_level"),
    "vacuum": ("battery_level",),
    "fan": ("percentage", "preset_mode"),
    "water_heater": ("current_temperature", "temperature", "operation_mode"),
    "valve": ("current_position", "reports_position"),
}


def _to_minimal(raw: dict) -> dict:
    attrs = raw.get("attributes") or {}
    eid = raw["entity_id"]
    dom = _domain(eid)
    result: dict = {
        "id": eid,
        "state": raw.get("state", "unknown"),
        "name": attrs.get("friendly_name") or "",
        "unit": attrs.get("unit_of_measurement") or "",
        "domain": dom,
        "device_class": attrs.get("device_class"),
    }
    domain_keys = _DOMAIN_ATTRS.get(dom, [])
    if domain_keys:
        extra = {k: attrs[k] for k in domain_keys if k in attrs}
        if extra:
            result["attributes"] = extra
    return result


class EntityCache:
    def __init__(self) -> None:
        self._states: dict[str, dict] = {}
        self._by_domain: dict[str, list[str]] = {}
        self._area_map: dict[str, list[str]] | None = None  # None = not loaded yet
        # False finche' load() non ha completato almeno una volta. Serve a
        # distinguere "inventario non ancora pronto" da "casa senza entita'":
        # server.py logga e prosegue se il caricamento iniziale fallisce, e i
        # tool che leggono da qui rispondevano con un elenco vuoto in entrambi
        # i casi ("la casa e' vuota"). Vedi ToolDispatcher._cache_non_leggibile.
        self._loaded = False

    @property
    def loaded(self) -> bool:
        """True quando `load()` e' andata a buon fine almeno una volta.

        Solo allora un inventario vuoto significa davvero "nessuna entita'".
        `on_state_changed` NON alza questa bandiera di proposito: gli eventi
        arrivati dopo un caricamento fallito descrivono le poche entita' che si
        sono mosse, non la casa, e spacciarli per inventario completo
        riaprirebbe -- in forma piu' subdola -- lo stesso "la casa e' vuota".
        """
        return self._loaded

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
        # Solo dopo che la lettura e' arrivata in fondo: se get_states solleva,
        # la cache resta dichiaratamente non pronta.
        self._loaded = True

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

    def domain_counts(self) -> dict:
        """Map of domain -> number of cached entities (for the gateway policy UI)."""
        return {d: len(v) for d, v in self._by_domain.items()}

    def get_on(self) -> list[dict]:
        return [e for e in self._states.values() if e["state"] == "on"]

    def get_all_useful(self) -> list[dict]:
        return [
            e for eid, e in self._states.items()
            if _domain(eid) not in NOISE_DOMAINS
        ]

    def get_all(self) -> list[dict]:
        return list(self._states.values())

    def get_all_states(self) -> dict[str, dict]:
        return dict(self._states)

    def all_states(self) -> list[dict]:
        """Return all cached entity states as a list (read-only access for the entity inventory API)."""
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

