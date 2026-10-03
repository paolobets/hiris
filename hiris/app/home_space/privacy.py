"""Il filtro di riservatezza della porta che legge la casa (spec
`2026-09-29-una-porta-sola-per-la-casa.md` §3).

**Un punto solo**, e sulla PORTA, non sullo specchio: lo specchio serve anche
a chi agisce e a chi verifica, che hanno bisogno dello stato vero. Cio' che
qui si toglie e' cio' che il modello non deve ricevere, in nessuna
profondita' -- decisione del proprietario, 29/09/2026:

- le credenziali mai (la cesta `credentials` di `_to_minimal`, dove lo
  specchio mette gia' anche `ip`, `mac`, `host_name`);
- la posizione della casa si' (`zone.home`): serve a sole, meteo, orari;
- di persone e dispositivi che si spostano, solo in casa / fuori casa: niente
  coordinate, niente zone, e il nome di una zona («Lavoro») diventa
  `not_home`, perche' direbbe gia' dove sono.
"""
from __future__ import annotations

from ..proxy.entity_cache import CREDENTIALS
from .queries import WITHHELD_BASKET
from .type_vocabulary import domains_by_genre

#: I due soli domini il cui genere e' "presenza", ricavati dalla dichiarazione
#: nel vocabolario dei tipi.
MOVING_DOMAINS = domains_by_genre("presenza")
#: Le chiavi che dicono DOVE si trova una persona o un dispositivo. Le usano
#: anche gli argomenti salvati nel registro dei turni (`usage/store.py`, spec
#: §7: «dallo stesso filtro di §3»): `gps` e `location_name` sono i campi di
#: `device_tracker.see`, e `location_name` porta il nome di una zona.
POSITION_ATTRIBUTES = frozenset({"latitude", "longitude", "gps_accuracy",
                                 "in_zones", "gps", "location_name"})
HOME_ZONE = "zone.home"
#: Gli stati che non dicono dove si trova qualcuno: restano come sono.
_NEUTRAL_STATES = frozenset({"home", "not_home", "unavailable", "unknown"})


def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def redact_state(entity_id: str, state: str | None) -> str | None:
    if state is None or _domain(entity_id) not in MOVING_DOMAINS:
        return state
    return state if state in _NEUTRAL_STATES else "not_home"


#: Le chiavi che portano credenziali o i loro NOMI, nelle due forme in cui
#: gli attributi arrivano alla porta: le ceste dello specchio (`_to_minimal`)
#: e il dettaglio di `queries.view` (`valori`, `campo_di_manovra`,
#: `non_interpretati`, `trattenuti`).
_NEVER_BASKETS = frozenset({CREDENTIALS, WITHHELD_BASKET})


def _hides_position(entity_id: str) -> bool:
    """Chi perde le coordinate: persone e dispositivi che si spostano, e zone
    che non siano `zone.home` (le altre direbbero dove vanno le persone). Un
    punto solo per `redact_attributes` e `redact_nested` (30/09/2026)."""
    domain = _domain(entity_id)
    return domain in MOVING_DOMAINS or (domain == "zone" and entity_id != HOME_ZONE)


def redact_attributes(entity_id: str, attributes: dict | None) -> dict | None:
    if not attributes:
        return attributes
    redact_position = _hides_position(entity_id)
    kept: dict = {}
    for basket, values in attributes.items():
        if basket in _NEVER_BASKETS:
            continue
        if redact_position and isinstance(values, dict):
            values = {k: v for k, v in values.items()
                      if k not in POSITION_ATTRIBUTES}
            if not values:
                continue
        kept[basket] = values
    return kept


#: Le chiavi che portano gli attributi di UNA voce: il filtro li passa da
#: `redact_attributes`, non li attraversa come elenchi di righe.
_ATTRIBUTE_KEYS = ("attributi", "attributes")
#: Lo stato in parole accanto al grezzo (`queries._enrich_entity`). Quando il
#: grezzo si riduce a `not_home`, la resa del grezzo non vale piu' e il suo
#: motivo potrebbe ripeterlo: escono con lui.
_RENDERED_STATE_KEYS = ("stato_leggibile", "stato_non_reso")


def redact_row(row: dict) -> dict:
    """Il filtro su UNA voce, e -- ricorsivo -- su ogni riga che la voce porta
    dentro di se'.

    **In tutte le profondita'** (spec §3), e il dettaglio completo ne ha piu'
    d'una: un dispositivo, un'area o un'integrazione portano le loro entita'
    in `entita` e `entita_nascoste`, righe con il loro `id` e il loro `stato`
    grezzo. Fino al 30/09/2026 il filtro guardava solo il primo livello, e
    `search(nome="iphone")` -- un telefono con l'app di Home Assistant ha
    SEMPRE un `device_tracker` -- consegnava «Lavoro» dentro il dispositivo
    (review finale della fetta, C1). Un punto solo resta un punto solo: la
    discesa e' qui, non in ogni ramo che costruisce un elenco."""
    entity_id = str(row.get("id") or "")
    out = dict(row)
    if "stato" in out:
        seen = redact_state(entity_id, out["stato"])
        if seen != out["stato"]:
            for key in _RENDERED_STATE_KEYS:
                out.pop(key, None)
        out["stato"] = seen
    for key, value in out.items():
        if key in _ATTRIBUTE_KEYS:
            out[key] = redact_attributes(entity_id, value)
        elif isinstance(value, list):
            out[key] = [redact_row(item) if isinstance(item, dict) else item
                        for item in value]
    return out


def redact_nested(value):
    """Ogni stato di Home Assistant annidato in una struttura, ridotto.

    La traccia di un'esecuzione porta `trigger.to_state`/`from_state` interi,
    e li ripete nelle `changed_variables` dei passi: la zona di chi si muove
    come stato, e le coordinate fra gli attributi (spec «la storia» §5,
    Review Focus 1, 30/09/2026). `redact_row` guarda le righe della porta,
    con `id` e `stato`; qui si guarda la forma di Home Assistant (`entity_id`,
    `state`, `attributes`) a ogni profondita', e si restituisce una copia.

    Le stesse fonti di `redact_attributes`, nessuna seconda lista:
    `MOVING_DOMAINS` per lo stato, `_hides_position` e `POSITION_ATTRIBUTES`
    per le coordinate -- anche quelle della zona di un innesco `zone`."""
    if isinstance(value, list | tuple):
        return [redact_nested(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {key: redact_nested(item) for key, item in value.items()}
    entity_id = out.get("entity_id")
    if not isinstance(entity_id, str):
        return out
    if "state" in out and isinstance(out["state"], str | None):
        out["state"] = redact_state(entity_id, out["state"])
    if _hides_position(entity_id) and isinstance(out.get("attributes"), dict):
        out["attributes"] = {key: item for key, item in out["attributes"].items()
                             if key not in POSITION_ATTRIBUTES}
    return out


#: Perche' il corpo di un'automazione non va a chi non amministra. Verificato
#: il 27/09/2026 su Core 2026.9.3 (fix round 1 del Task 2, L-2):
#: `automation/config` (`components/automation/__init__.py`) e'
#: `@websocket_api.require_admin`; `script/config` no, e il corpo degli
#: script resta visibile a tutti.
AUTOMATION_BODY_ADMIN_ONLY = ("Home Assistant mostra il corpo delle "
                              "automazioni solo agli amministratori: si sa "
                              "che c'e' e come si chiama, non cosa fa")


def cover_automation_body(entry: dict, *, kind: str) -> dict:
    """La voce com'e' per chi non amministra: un'automazione col corpo lo
    perde e dice perche'. Tutto il resto -- uno script, un'automazione di cui
    il corpo non si conosce -- resta com'e': «coperto» e «non letto» sono due
    fatti diversi.

    **Una regola, due porte**: la chiamano lo strumento della chat
    (`tools.py`, il dettaglio di `view`) e la rotta `GET /api/home-space`,
    che fino alla 3.73.0 consegnava i corpi a un servizio firmato «lettore».
    """
    if kind != "automazione" or entry.get("corpo") is None:
        return entry
    return {**entry, "corpo": None, "corpo_non_disponibile": AUTOMATION_BODY_ADMIN_ONLY}
