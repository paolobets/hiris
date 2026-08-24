from __future__ import annotations

import logging

from ..casa.anagrafe import dominio_di

logger = logging.getLogger(__name__)

# `NOISE_DOMAINS` e' uscito con `get_all_useful`, il suo unico lettore.

# Messaggi per chi legge l'inventario quando l'inventario non e' leggibile.
# Un elenco vuoto direbbe "la casa e' vuota"; questi dicono "non ho potuto
# guardare", che e' l'unica frase vera. I due casi restano distinti perche'
# suggeriscono all'utente due cose diverse: uno e' configurazione mancante,
# l'altro passa da solo (il lavoro periodico di ricarica ritenta).
#
# Vivono qui, accanto alla bandiera `loaded` che li governa, perche' duplicarne
# il testo era esattamente il modo in cui il difetto e' sopravvissuto nei
# fratelli. Al momento in cui questi messaggi sono nati li usavano quattro
# moduli (dispatcher, ha_tools, briefing, api/handlers_entities): i primi tre
# sono usciti nella demolizione (rispettivamente 68d3670, bca1b85, 2441b7d) --
# oggi il solo lettore di produzione e' `api/handlers_entities.py`, via
# `inventario_non_leggibile()` sotto.
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


# Una lettura sola per tutti, in `casa/anagrafe.dominio_di`: era scritta sei
# volte, e due copie non erano d'accordo su un id senza punto.
_domain = dominio_di


_DOMAIN_ATTRS: dict[str, tuple[str, ...]] = {
    "climate": ("hvac_mode", "hvac_action", "current_temperature", "temperature", "preset_mode"),
    "light": ("brightness", "color_temp"),
    "cover": ("current_position",),
    "media_player": ("media_title", "media_artist", "source", "volume_level"),
    "vacuum": ("battery_level",),
    "fan": ("percentage", "preset_mode"),
    "water_heater": ("current_temperature", "temperature", "operation_mode"),
    "valve": ("current_position", "reports_position"),
    # Il meteo mancava, e non serviva nessuna chiamata nuova: temperatura,
    # umidita', vento e pressione sono ATTRIBUTI DI STATO dell'entita' meteo,
    # gia' dentro `get_states`. Senza questa riga `guarda` su un'entita'
    # `weather` rispondeva «sereno» e basta, buttando tutto il resto.
    # I nomi sono quelli veri di `components/weather/const.py`, verificati:
    # le unita' viaggiano in attributi propri (`temperature_unit`, ...) perche'
    # il meteo non usa `unit_of_measurement`.
    "weather": ("temperature", "temperature_unit", "humidity", "pressure",
                "pressure_unit", "wind_speed", "wind_speed_unit", "wind_bearing",
                "apparent_temperature", "cloud_coverage", "uv_index", "visibility"),
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
        # `state_class` (`measurement`, `total`, `total_increasing`) dice se un
        # numero e' una misura di adesso o un contatore che sale -- ed e' cio'
        # che dice a quali entita' si puo' chiedere una statistica, SENZA
        # doverlo domandare al recorder. Arrivava a ogni avvio dentro gli
        # attributi di ogni sensore, e questa proiezione lo buttava.
        # Il nome e' `sensor.const.ATTR_STATE_CLASS`, verificato.
        "state_class": attrs.get("state_class"),
        # `last_changed` arriva a OGNI cambio di stato e questa proiezione lo
        # buttava: HIRIS sapeva che in camera ci sono 22,4 gradi e non sapeva
        # da quando -- non poteva nemmeno dire «e' fermo da tre ore». Costa un
        # campo e zero chiamate a Home Assistant.
        # `last_changed` e non `last_updated`: il secondo si muove anche quando
        # cambia solo un attributo, e «da quando e' accesa» diventerebbe «da
        # quando qualcuno ne ha toccato la luminosita'».
        "last_changed": raw.get("last_changed"),
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
        # False finche' load() non ha completato almeno una volta. Serve a
        # distinguere "inventario non ancora pronto" da "casa senza entita'":
        # server.py logga e prosegue se il caricamento iniziale fallisce, e i
        # tool che leggono da qui rispondevano con un elenco vuoto in entrambi
        # i casi ("la casa e' vuota"). Il controllo comune era
        # `ToolDispatcher._cache_non_leggibile`, uscito -- fetta E2 Task 7.
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

    # fetta E3 Task 12 ("esce il ritratto"): `get_state` e' uscito -- ORFANO
    # DICHIARATO dal Task 9, il cui unico chiamante era
    # `TaskEngine._evaluate_condition`, cancellato per intero col Task
    # Engine. Verificato di nuovo qui (grep sull'intero repo, zero
    # chiamanti): nessun successore.

    # `get_minimal` e `get_by_domain` sono USCITI (censimento del 17/08/2026,
    # zero chiamanti di produzione: il secondo era l'unico lettore del primo).
    # `_by_domain` resta: lo popola e lo legge `_index`.

    # fetta E3 Task 12 ("esce il ritratto"): `domain_counts` e' uscito --
    # ORFANO DICHIARATO dal Task 7 (viveva per la UI della gateway policy,
    # cancellata insieme al semaforo). Verificato di nuovo qui: zero
    # chiamanti nell'intero repo.

    # `get_on` e `get_all_useful` sono USCITI (stesso censimento). Il secondo
    # era l'unico lettore di `NOISE_DOMAINS`, uscito con lui: quella lista
    # decideva cosa fosse "rumore" per un consumatore che non esiste piu', e la
    # domanda «cosa merita di essere detto» vive adesso in `casa/nucleo.py`, per
    # TIPOLOGIA e non per dominio (fetta «il vocabolario delle tipologie»).
    #
    # `load_area_registry`/`get_area_map` SONO usciti, insieme -- ed e' il
    # motivo per cui la nota di prima diceva "va deciso insieme, non a meta'":
    # il censimento segnalava l'accessore (zero letture di produzione) ma il
    # caricatore era chiamato davvero, due volte (avvio e riconnessione).
    # Lavoro morto fatto da codice vivo: due chiamate WebSocket a ogni avvio
    # per costruire una mappa che nessuno leggeva.
    #
    # E non era nemmeno una mappa giusta. Indicizzava per NOME dell'area --
    # due "Bagno" su piani diversi si fondevano in uno -- e ignorava l'area
    # EREDITATA dal dispositivo, che in una casa vera e' il caso normale, non
    # l'eccezione. `casa/anagrafe.gerarchia()` risponde alla stessa domanda
    # per id, con l'ereditarieta', e dichiarando quale registro non ha
    # risposto. Due risposte alla stessa domanda, una delle quali sbagliata e
    # letta da nessuno: NESSUN DOPPIONE.

    def get_all(self) -> list[dict]:
        return list(self._states.values())

    # fetta E3 Task 12 ("esce il ritratto"): `get_all_states` (la forma a
    # dizionario, entity_id -> stato) e' uscito -- ORFANO DICHIARATO dal
    # Task 2, il cui unico chiamante era `semantic_context_map`, cancellata
    # insieme alla context map. Verificato di nuovo qui: zero chiamanti.
    # Da non confondere con `all_states` (sotto), la forma a lista che
    # `api/handlers_casa.py` e l'inventario entita' usano ancora: quella
    # resta.

    def all_states(self) -> list[dict]:
        """Return all cached entity states as a list (read-only access for the entity inventory API)."""
        return list(self._states.values())


