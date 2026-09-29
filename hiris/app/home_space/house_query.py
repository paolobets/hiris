"""La porta che interroga la casa (spec `2026-09-29-una-porta-sola-per-la-casa.md`).

Una funzione pura: l'albero dell'anagrafe (`topology.hierarchy`) e lo
specchio degli stati (`topology.live_mirror`) entrano, un insieme di voci
esce. La profondita' la decide lo strumento, dal numero di voci trovate:
una -> il dettaglio completo (`detail`, che il dispatcher lega a
`queries.view`); fino a `DETAIL_MEDIUM_MAX` -> media; oltre -> corta, al
massimo `ROWS_MAX` righe e poi `oltre`.

**Nessun riepilogo** (decisione del proprietario, 29/09/2026): niente conti
per stato. Si dichiara solo cio' che NON e' stato dato -- `escluse` e
`oltre` -- perche' senza, «nessuna luce accesa» e' una risposta falsa data
con sicurezza quando le accese sono nascoste.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, replace
from datetime import datetime

from ..memory.resolver import name_matches
from . import topology
from .privacy import redact_row, redact_state
from .queries import ROWS_MAX

DETAIL_MEDIUM_MAX = 10
KINDS = ("entita", "area", "dispositivo", "automazione", "script",
         "ricordo", "integrazione")
ORDERS = ("nome", "ultimo_cambio", "valore")
_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400}
#: I generi che hanno uno stato nello specchio e un'ultima esecuzione.
_BEHAVIOR_KINDS = {"automazione": "automation", "script": "script"}
#: Il dominio di Home Assistant -> il genere: `tipo=automation` senza
#: `genere` e' una domanda sulle automazioni, e per loro conta l'ultima
#: esecuzione, non l'ultimo cambio di stato (spec §2.2).
_BEHAVIOR_DOMAINS = {v: k for k, v in _BEHAVIOR_KINDS.items()}
#: I generi che si chiedono per `riferimento` e rispondono col dettaglio
#: completo di `queries.view`. Un dispositivo senza `riferimento` si cerca
#: invece per nome, come faceva il vecchio `search` («la lavatrice»).
_DETAIL_ONLY_KINDS = ("dispositivo", "ricordo", "integrazione")


@dataclass(frozen=True)
class HouseFilters:
    kind: str | None = None
    name: str | None = None
    reference: str | None = None
    domain: str | None = None
    state: str | None = None
    device_class: str | None = None
    area: str | None = None
    floor: str | None = None
    platform: str | None = None
    idle_for_s: int | None = None
    changed_within_s: int | None = None
    above: float | None = None
    below: float | None = None
    running: bool | None = None
    include_hidden: bool = False
    include_service: bool = False
    order_by: str = "nome"
    limit: int = ROWS_MAX
    offset: int = 0

    @property
    def only_by_name(self) -> bool:
        """Solo `nome`/`riferimento`: si cerca in tutti i generi. Una
        domanda vuota non lo e': il genere di default e' `entita` (spec §2.1)."""
        return bool(self.name or self.reference) and self.kind is None and not any((
            self.domain, self.state, self.device_class, self.area, self.floor,
            self.platform, self.idle_for_s is not None,
            self.changed_within_s is not None,
            self.above is not None, self.below is not None,
            self.running is not None))


def _seconds(text) -> int | None:
    m = _DURATION.match(str(text))
    return int(m.group(1)) * _UNIT_S[m.group(2)] if m else None


def parse_filters(arguments: dict) -> HouseFilters | dict:
    a = dict(arguments or {})
    fields: dict = {}
    for key, attr in (("genere", "kind"), ("nome", "name"),
                      ("riferimento", "reference"), ("tipo", "domain"),
                      ("stato", "state"), ("classe", "device_class"),
                      ("area", "area"), ("piano", "floor"),
                      ("integrazione", "platform"), ("ordina", "order_by")):
        if a.get(key) not in (None, ""):
            fields[attr] = str(a[key])
    if fields.get("kind") and fields["kind"] not in KINDS:
        return {"errore": f"genere «{fields['kind']}» sconosciuto: "
                          f"{', '.join(KINDS)}"}
    if fields.get("order_by") and fields["order_by"] not in ORDERS:
        return {"errore": f"ordina accetta {', '.join(ORDERS)}"}
    for key, attr in (("fermo_da", "idle_for_s"),
                      ("cambiato_da", "changed_within_s")):
        if a.get(key) is not None:
            s = _seconds(a[key])
            if s is None:
                return {"errore": f"{key} vuole una durata come 30d, 2h, 15m"}
            fields[attr] = s
    for key, attr in (("sopra", "above"), ("sotto", "below")):
        if a.get(key) is not None:
            try:
                fields[attr] = float(a[key])
            except (TypeError, ValueError):
                return {"errore": f"{key} vuole un numero"}
    for key, attr in (("in_esecuzione", "running"),
                      ("includi_nascoste", "include_hidden"),
                      ("includi_servizio", "include_service")):
        if a.get(key) is not None:
            fields[attr] = bool(a[key])
    for key, attr, top in (("limite", "limit", ROWS_MAX), ("salta", "offset", None)):
        if a.get(key) is not None:
            try:
                n = int(a[key])
            except (TypeError, ValueError):
                return {"errore": f"{key} vuole un intero"}
            if n < 0 or (top is not None and n > top):
                return {"errore": f"{key} va da 0 a {top}" if top
                        else f"{key} non puo' essere negativo"}
            fields[attr] = n
    return HouseFilters(**fields)


def _age_s(iso: str | None, now: float) -> float | None:
    if not iso:
        return None
    try:
        return now - datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def _entity_entries(home_space: dict, unavailable) -> list[tuple[dict, dict, dict, str]]:
    """(entry, area, piano, dove) per ogni entita' dell'albero; `dove` e'
    `visibile`, `nascosta` o `disabilitata`."""
    out = []
    for floor in topology.hierarchy(home_space, unavailable):
        for area in floor.get("aree") or []:
            for key, where in (("entita", "visibile"),
                               ("entita_nascoste", "nascosta"),
                               ("entita_disabilitate", "disabilitata")):
                for entry in area.get(key) or []:
                    if isinstance(entry, dict) and entry.get("id"):
                        out.append((entry, area, floor, where))
    return out


def _area_name(area: dict) -> str | None:
    return None if str(area.get("id", "")).startswith("__") else area.get("nome")


def _place_matches(f: HouseFilters, entry: dict, area: dict, floor: dict) -> bool:
    """`area`, `piano`, `integrazione`: dove sta e da dove viene. Vale per le
    entita' e per automazioni e script, che li prendono dalla propria entita'
    di registro."""
    if f.area:
        wanted = f.area.strip().lower()
        if wanted == "senza area":
            if _area_name(area) is not None:
                return False
        elif (area.get("nome") or "").lower() != wanted and area.get("id") != wanted:
            return False
    if f.floor and (floor.get("nome") or "").lower() != f.floor.strip().lower():
        return False
    return not (f.platform and entry.get("piattaforma") != f.platform)


def _entity_matches(f: HouseFilters, entry, area, floor, mirror, now) -> bool:
    stato, nomi, _unita, classi, da_quando, _attributi = mirror
    eid = entry["id"]
    domain = eid.split(".", 1)[0]
    if f.reference and eid != f.reference:
        return False
    if f.domain and domain != f.domain:
        return False
    # Lo stato che il lettore VEDE, non quello grezzo: «Lavoro» di una
    # persona esce come `not_home`, e `stato=not_home` deve trovarla.
    if f.state and redact_state(eid, stato.get(eid)) != f.state:
        return False
    if f.device_class and (classi.get(eid) or entry.get("classe")) != f.device_class:
        return False
    if not _place_matches(f, entry, area, floor):
        return False
    if f.name and not name_matches(f.name, nomi.get(eid) or entry.get("nome") or eid):
        return False
    age = _age_s(da_quando.get(eid), now)
    if f.idle_for_s is not None and (age is None or age < f.idle_for_s):
        return False
    if f.changed_within_s is not None and (age is None or age > f.changed_within_s):
        return False
    if f.above is not None or f.below is not None:
        try:
            value = float(stato.get(eid))
        except (TypeError, ValueError):
            return False
        if f.above is not None and value <= f.above:
            return False
        if f.below is not None and value >= f.below:
            return False
    return True


def _entity_row(entry, area, where, mirror, medium: bool) -> dict:
    stato, nomi, unita, classi, da_quando, attributi = mirror
    eid = entry["id"]
    row = {"id": eid, "nome": nomi.get(eid) or entry.get("nome") or eid,
           "area": _area_name(area), "stato": stato.get(eid),
           "ultimo_cambio": da_quando.get(eid)}
    if where == "nascosta":
        row["nascosta"] = True
    if medium:
        row["genere"] = "entita"
        if unita.get(eid):
            row["unita"] = unita[eid]
        if classi.get(eid) or entry.get("classe"):
            row["classe"] = classi.get(eid) or entry.get("classe")
        if entry.get("piattaforma"):
            row["integrazione"] = entry["piattaforma"]
        if attributi.get(eid):
            row["attributi"] = attributi[eid]
    return row


#: Dove sta un'automazione che il registro delle entita' non conosce: in
#: nessuna area, su nessun piano, da nessuna integrazione.
_NOWHERE = ({}, {"id": "__senza_area__"}, {})


def _behavior_matches(f: HouseFilters, behavior, mirror, now,
                      places: dict) -> list[tuple[dict, dict]]:
    """(voce, valori dello specchio) per ogni automazione o script che passa
    i filtri: la riga si scrive dopo, quando si sa quante sono. `places` e'
    `{id: (entry, area, piano)}` dell'albero: area, piano e integrazione di
    un'automazione sono quelli della sua entita' di registro."""
    stato, _n, _u, _c, _d, attributi = mirror
    out = []
    for item in behavior or []:
        if f.kind and item.get("tipo") != f.kind:
            continue
        if f.reference and item.get("id") != f.reference:
            continue
        if f.name and not (name_matches(f.name, item.get("nome") or "")
                           or name_matches(f.name, item["id"])):
            continue
        if not _place_matches(f, *places.get(item["id"], _NOWHERE)):
            continue
        values = (attributi.get(item["id"]) or {}).get("values") or {}
        age = _age_s(values.get("last_triggered"), now)
        if f.idle_for_s is not None and age is not None and age < f.idle_for_s:
            continue
        if f.changed_within_s is not None and (age is None or age > f.changed_within_s):
            continue
        if f.state and stato.get(item["id"]) != f.state:
            continue
        if f.running is not None and bool(values.get("current")) != f.running:
            continue
        out.append((item, values))
    return out


def _behavior_row(item, values, mirror, medium: bool) -> dict:
    row = {"id": item["id"], "nome": item.get("nome"), "genere": item.get("tipo"),
           "stato": mirror[0].get(item["id"]),
           "ultima_esecuzione": values.get("last_triggered") or "mai"}
    if medium:
        for key, label in (("mode", "modalita"), ("current", "in_esecuzione")):
            if key in values:
                row[label] = values[key]
    return row


def _area_rows(f: HouseFilters, home_space, unavailable):
    rows = []
    for floor in topology.hierarchy(home_space, unavailable):
        for area in floor.get("aree") or []:
            if str(area.get("id", "")).startswith("__"):
                continue
            if f.reference and area.get("id") != f.reference:
                continue
            if f.name and not name_matches(f.name, area.get("nome") or ""):
                continue
            rows.append({"id": area["id"], "nome": area.get("nome"),
                         "genere": "area", "piano": floor.get("nome")})
    return rows


def _device_rows(f: HouseFilters, home_space, excluded: dict) -> list[dict]:
    """I dispositivi del registro, per nome: il vecchio `search` trovava «la
    lavatrice», la porta nuova non deve perderla (decisione 29/09/2026). I
    disabilitati fuori e contati, come le entita'."""
    area_names = {a.get("id"): a.get("nome") for a in home_space.get("aree") or []}
    rows = []
    for device in home_space.get("dispositivi") or []:
        if not device.get("id"):
            continue
        if f.reference and device["id"] != f.reference:
            continue
        if f.name and not name_matches(f.name, device.get("nome") or ""):
            continue
        if device.get("disabilitato"):
            excluded["disabilitate"] += 1
            continue
        rows.append({"id": device["id"], "nome": device.get("nome"),
                     "genere": "dispositivo",
                     "area": area_names.get(device.get("area_id"))})
    return rows


def _sort_key(order_by: str):
    if order_by == "ultimo_cambio":
        # «mai» prima di tutto: un'automazione mai eseguita e' la piu' ferma (#31).
        def since(r):
            last = r.get("ultima_esecuzione")
            return "" if last == "mai" else (last or r.get("ultimo_cambio") or "")
        return since
    if order_by == "valore":
        def key(r):
            try:
                return (0, float(r.get("stato")))
            except (TypeError, ValueError):
                return (1, 0.0)
        return key
    return lambda r: (r.get("nome") or r.get("id") or "").lower()


def _select(f: HouseFilters, home_space, behavior, mirror, detail, unavailable,
            now, excluded: dict) -> tuple[int, str, list[dict], dict | None]:
    """(trovate, profondita, voci NON ancora filtrate, oltre)."""
    if f.kind in _DETAIL_ONLY_KINDS and (f.reference or f.kind != "dispositivo"):
        # Senza `riferimento` la voce di `queries.view` porta gia' `esiste: False`.
        return 1, "completa", [detail(f.kind, f.reference or f.name or "")], None
    kinds = KINDS if f.only_by_name else ((f.kind,) if f.kind else ("entita",))
    entries = _entity_entries(home_space, unavailable)
    # La riga di comportamento rappresenta gia' l'automazione: la sua entita'
    # di registro sarebbe un doppione. SOLO quelle che il comportamento
    # conosce: un'automazione che non c'e' resta un'entita', non sparisce.
    searching_behavior = any(k in _BEHAVIOR_KINDS for k in kinds)
    shadowed = {b.get("id") for b in behavior or []} if searching_behavior else set()
    matched = []
    if "entita" in kinds:
        for entry, area, floor, where in entries:
            if entry["id"] in shadowed:
                continue
            if not _entity_matches(f, entry, area, floor, mirror, now):
                continue
            if where == "disabilitata":
                excluded["disabilitate"] += 1
                continue
            if where == "nascosta" and not f.include_hidden:
                excluded["nascoste"] += 1
                continue
            if entry.get("categoria") and not f.include_service:
                excluded["servizio"] += 1
                continue
            matched.append((entry, area, where))
    places = {entry["id"]: (entry, area, floor) for entry, area, floor, _w in entries}
    behaving = []
    others: list[dict] = []
    for kind in kinds:
        if kind in _BEHAVIOR_KINDS:
            behaving.extend(_behavior_matches(replace(f, kind=kind), behavior,
                                              mirror, now, places))
        elif kind == "area":
            others.extend(_area_rows(f, home_space, unavailable))
        elif kind == "dispositivo":
            others.extend(_device_rows(f, home_space, excluded))
    found = len(matched) + len(behaving) + len(others)
    if found == 1 and f.limit > 0:
        if matched:
            return 1, "completa", [detail("entita", matched[0][0]["id"])], None
        item = behaving[0][0] if behaving else others[0]
        kind = item.get("tipo") if behaving else item["genere"]
        return 1, "completa", [detail(kind, item["id"])], None
    medium = found <= DETAIL_MEDIUM_MAX
    rows = ([_entity_row(entry, area, where, mirror, medium)
             for entry, area, where in matched]
            + [_behavior_row(item, values, mirror, medium) for item, values in behaving]
            + others)
    rows.sort(key=_sort_key(f.order_by))
    page = rows[f.offset:f.offset + min(f.limit, ROWS_MAX)]
    left = len(rows) - f.offset - len(page)
    beyond = ({"restano": left, "salta": f.offset + len(page)}
              if left > 0 and f.limit > 0 else None)
    return found, "media" if medium else "corta", page, beyond


def query_house(home_space: dict, behavior, mirror, filters: HouseFilters, *,
                detail, unavailable=(), now: float | None = None) -> dict:
    now = time.time() if now is None else now
    f = filters
    if f.kind is None and f.domain in _BEHAVIOR_DOMAINS:
        f = replace(f, kind=_BEHAVIOR_DOMAINS[f.domain], domain=None)
    # Qui convergono `genere=automazione` e `tipo=automation`: un filtro che
    # su automazioni e script non ha senso si dice, non si ignora -- ignorato,
    # darebbe con sicurezza TUTTE le automazioni (spec §2.4).
    if f.kind in _BEHAVIOR_KINDS and (f.device_class or f.above is not None
                                      or f.below is not None):
        return {"errore": "classe, sopra e sotto non valgono per automazioni "
                          "e script: filtra per area, piano, integrazione, "
                          "stato, fermo_da, cambiato_da, in_esecuzione"}
    excluded = {"nascoste": 0, "servizio": 0, "disabilitate": 0}
    found, depth, page, beyond = _select(f, home_space, behavior, mirror, detail,
                                         unavailable, now, excluded)
    # Il filtro di riservatezza, in un punto solo: ogni voce, di ogni genere e
    # di ogni profondita', passa di qui prima di uscire.
    result: dict = {"trovate": found, "escluse": excluded, "profondita": depth,
                    "voci": [redact_row(v) for v in page]}
    if beyond:
        result["oltre"] = beyond
    return result


