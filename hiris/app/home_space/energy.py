"""La dashboard Energia: cio' che il proprietario ha dichiarato a Home
Assistant su chi e' rete, sole, batteria, gas, acqua -- un oggetto della casa
suo (piano degli attori, strato 2, Task 2.2; D6 «oggetto a parte», scelta
del proprietario il 03/10/2026).

**Perche' un oggetto a parte, e non un campo dell'entita'.** Il ruolo dentro
la riga dell'entita' dovrebbe comparire da TUTTE le porte che oggi rendono
un'entita' (fondamenta 3), e quelle porte si unificano alla Tappa 4: oggi
allargherebbe i doppioni che quella tappa toglie. Quindi la dashboard si
chiede qui, una volta, e chi la usa la cita a parte -- come il giro delle
ricette fa gia' per «queste entita' hanno una serie»
(`recipe_turn._series_block`).

**Mai dai nomi.** Il ruolo di un'entita' e' quello che la dashboard dichiara;
un'entita' che la dashboard non nomina non ha ruolo, qualunque cosa dica il
suo nome (CLAUDE.md: l'energia prodotta letta come «consumo» e' nata dal
nome). Home Assistant usa `device_class: energy` per la produzione E per il
prelievo: la classe non basta, il nome nemmeno.

**La forma, letta sul sorgente di Home Assistant al tag `2026.9.4` il
04/10/2026** (`components/energy/data.py`; non ancora misurata su questa casa:
Task 2.0). Le sorgenti hanno un `type` -- `grid`, `solar`, `battery`, `gas`,
`water` -- e i loro contatori in campi singoli: la rete `stat_energy_from`
(«kWh consumed from grid») e `stat_energy_to` («kWh returned to grid»),
entrambi anche `None`; il sole `stat_energy_from`; la batteria
`stat_energy_from` e `stat_energy_to` (scarica e carica: `stat_rate` e'
«positive when discharging»), e facoltativo `stat_soc` («battery state of
charge», in %); gas e acqua `stat_energy_from`. I consumi dei dispositivi
(`device_consumption`, `device_consumption_water`) hanno `stat_consumption` e,
facoltativo, `included_in_stat` («a device that includes this device's
consumption in its total»). La rete di PRIMA della migrazione
(`LegacyGridSourceType`: liste `flow_from`/`flow_to`) al tag letto non esce
piu', ma il client la passa com'e' (`HAClient.energy_prefs`), e qui si legge.

I valori sono **statistic_id**, non per forza entita': una statistica esterna
(`dominio:nome`) e' ammessa dallo schema (`_reject_price_for_external_stat`).
L'oggetto porta l'id com'e' (`statistica`) e l'entita' solo quando l'anagrafe
la conosce.

**Quando si rilegge.** Una volta per giro dell'anagrafe: la prima domanda
dopo una ricostruzione (`HomeSpace.hold`) la legge, le altre la riusano.
Home Assistant non annuncia il cambio delle preferenze sul bus -- letto al tag
`2026.9.4`: `EnergyManager.async_update` avvisa solo i propri ascoltatori
interni (`async_listen_updates`), e `websocket_api.py` non ha un comando
d'iscrizione -- quindi una dashboard cambiata si vede alla ricostruzione dopo.
"""
from __future__ import annotations

import logging

from .reader import clean_name

logger = logging.getLogger(__name__)

#: Da dove viene ogni ruolo: si dice con l'oggetto (fondamenta 1).
PROVENANCE = "dashboard Energia di Home Assistant"

#: Il ruolo di ogni campo che la dashboard dichiara, per `(type, campo)`. Le
#: chiavi sono i nomi di Home Assistant, i valori le parole del glossario
#: (`docs/GLOSSARIO.md`, «I valori di dominio»: produzione, immissione,
#: prelievo, carica, scarica, consumo), piu' «stato di carica» per `stat_soc`.
#:
#: **L'elenco E' il fatto** (CLAUDE.md, «Un cancello CHIEDE il suo elenco»):
#: e' la traduzione fra i due mondi, e vive qui sola. **Non sono ruoli,
#: dichiarato:** le potenze (`stat_rate`, `power_config`), i costi e i prezzi
#: (`stat_cost`, `stat_compensation`, `*_energy_price*`), la capacita' della
#: batteria e le previsioni del sole -- sono dichiarati, ma non sono l'energia
#: di un flusso, e il piano non li chiede.
ROLES: dict[tuple[str, str], str] = {
    ("grid", "stat_energy_from"): "prelievo",
    ("grid", "stat_energy_to"): "immissione",
    ("solar", "stat_energy_from"): "produzione",
    ("battery", "stat_energy_from"): "scarica",
    ("battery", "stat_energy_to"): "carica",
    ("battery", "stat_soc"): "stato di carica",
    ("gas", "stat_energy_from"): "consumo di gas",
    ("water", "stat_energy_from"): "consumo di acqua",
    ("device_consumption", "stat_consumption"): "consumo di un dispositivo",
    ("device_consumption_water", "stat_consumption"): "consumo di acqua di un dispositivo",
}

#: La rete di prima della migrazione: quale lista porta quale campo.
_LEGACY_GRID_LISTS = {"flow_from": "stat_energy_from", "flow_to": "stat_energy_to"}


def _role(kind: str, field: str, row: dict) -> dict | None:
    statistic = row.get(field)
    role = ROLES.get((kind, field))
    if role is None or not isinstance(statistic, str) or not statistic:
        return None
    out = {"ruolo": role, "statistica": statistic, "tipo": kind, "campo": field}
    # Il nome che il proprietario ha dato alla sorgente nei grafici: testo
    # suo, quindi sanificato come ogni nome dell'anagrafe.
    if isinstance(row.get("name"), str) and row["name"]:
        out["nome"] = clean_name(row["name"])
    if isinstance(row.get("included_in_stat"), str) and row["included_in_stat"]:
        out["compreso_in"] = row["included_in_stat"]
    return out


def declared_roles(prefs: dict) -> list[dict]:
    """I ruoli che le preferenze di Home Assistant dichiarano, uno per
    contatore, nell'ordine in cui la dashboard li elenca. Funzione pura."""
    found: list[dict | None] = []
    for source in prefs.get("energy_sources") or []:
        if not isinstance(source, dict):
            continue
        kind = source.get("type")
        found.extend(_role(kind, field, source)
                     for (role_kind, field) in ROLES if role_kind == kind)
        if kind == "grid":
            for key, field in _LEGACY_GRID_LISTS.items():
                found.extend(_role(kind, field, flow) for flow in source.get(key) or []
                             if isinstance(flow, dict))
    for kind in ("device_consumption", "device_consumption_water"):
        found.extend(_role(kind, "stat_consumption", row) for row in prefs.get(kind) or []
                     if isinstance(row, dict))
    return [role for role in found if role is not None]


def describe(held: dict | None, house,
             with_series: set[str] | None) -> dict | None:
    """L'oggetto intero: per ogni ruolo l'entita', la sua unita' e se ha
    statistiche.

    **L'unita' e' quella di adesso**, chiesta alla casa (`House.kind_of`: lo
    specchio, col registro come ripiego -- `topology.live_first`). Fino al
    04/10/2026 si leggeva dalla voce dell'anagrafe, che allora teneva l'unita'
    viva del momento della ricostruzione; dal Task 7 (B-17) l'anagrafe porta
    solo cio' che il registro dichiara (quasi mai un'unita'), e il vivo ha una
    casa sola. L'entita' e' tale quando l'anagrafe la conosce
    (`House.entity_ids`), come prima: una statistica esterna (`dominio:nome`)
    non ha ne' entita' ne' unita'.

    `ha_statistiche` e' la regola di oggi del giro delle ricette: l'id sta
    nell'elenco di `recorder/list_statistic_ids` (`server.statistic_ids_for_round`).
    Non e' una regola nuova: la regola unica di «ha statistiche» (B-12) la
    porta un'altra fetta, e quando c'e' si chiede a lei. `with_series` a
    `None` e' «non l'ho potuto chiedere», e il campo resta `None`.
    """
    if held is None:
        return None
    known = set(house.entity_ids())
    roles = []
    for role in held["ruoli"]:
        statistic = role["statistica"]
        kind = house.kind_of(statistic) if statistic in known else None
        roles.append({**role,
                      "entita": statistic if kind is not None else None,
                      "unita": (kind or {}).get("unita"),
                      "ha_statistiche": (None if with_series is None
                                         else statistic in with_series)})
    return {"provenienza": PROVENANCE, "dichiarata": held["dichiarata"],
            "letta_alle": held["letta_alle"], "ruoli": roles}


async def reread_energy(client, home_space) -> None:
    """Rilegge la dashboard da Home Assistant e la consegna all'anagrafe.

    Una casa SENZA dashboard (`not_found` / «No prefs», `ws_get_prefs`) e' un
    fatto e si tiene: «nessuna dashboard dichiarata». Ogni altro guasto non
    sostituisce niente -- si tiene la lettura di prima, e la prossima domanda
    richiede: «non ho potuto leggere» non e' «non c'e'».
    """
    prefs = await client.energy_prefs()
    if "errore" not in prefs:
        home_space.hold_energy(declared_roles(prefs))
    elif prefs.get("codice") == "not_found":
        home_space.hold_energy(None)
    else:
        logger.info("dashboard Energia non letta (%s): %s", prefs.get("causa"),
                    prefs.get("errore"))


async def energy_dashboard(client, home_space, house, *,
                           with_series: set[str] | None = None) -> dict | None:
    """Cosa dichiara la dashboard Energia di questa casa: la domanda della casa.

    Legge da Home Assistant solo se l'anagrafe e' stata ricostruita dopo
    l'ultima lettura buona; `None` se non e' mai stata letta. `home_space`
    tiene la dashboard (`HomeSpace.hold_energy`); `house`, la casa del giro
    (`home_space.house.House`), dice entita' e unita' dei suoi ruoli.
    """
    if not home_space.energy_current():
        await reread_energy(client, home_space)
    return describe(home_space.energy(), house, with_series)
