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
POSITION_ATTRIBUTES = frozenset({"latitude", "longitude", "gps_accuracy",
                                 "in_zones"})
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


def redact_attributes(entity_id: str, attributes: dict | None) -> dict | None:
    if not attributes:
        return attributes
    domain = _domain(entity_id)
    #: Rimuove coordinate da: persone e dispositivi che si spostano, e zone
    #: che non siano zone.home (altre zone rivelerebbero dove vanno le persone).
    redact_position = (domain in MOVING_DOMAINS or
                       (domain == "zone" and entity_id != HOME_ZONE))
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


def redact_row(row: dict) -> dict:
    entity_id = str(row.get("id") or "")
    out = dict(row)
    if "stato" in out:
        out["stato"] = redact_state(entity_id, out["stato"])
    for key in ("attributi", "attributes"):
        if key in out:
            out[key] = redact_attributes(entity_id, out[key])
    return out
