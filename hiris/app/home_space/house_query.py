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
from .privacy import redact_row

DETAIL_MEDIUM_MAX = 10
ROWS_MAX = 50
KINDS = ("entita", "area", "dispositivo", "automazione", "script",
         "ricordo", "integrazione")
ORDERS = ("nome", "ultimo_cambio", "valore")
_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400}
#: I generi che hanno uno stato nello specchio e un'ultima esecuzione.
_BEHAVIOR_KINDS = {"automazione": "automation", "script": "script"}
#: I generi che non si elencano: si chiedono per `riferimento` e rispondono
#: sempre col dettaglio completo di `queries.view`.
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
        """Solo `nome`/`riferimento`: si cerca in tutti i generi."""
        return self.kind is None and not any((
            self.domain, self.state, self.device_class, self.area, self.floor,
            self.platform, self.idle_for_s, self.changed_within_s,
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


def _entity_matches(f: HouseFilters, entry, area, floor, mirror, now) -> bool:
    stato, nomi, _unita, classi, da_quando, _attributi = mirror
    eid = entry["id"]
    domain = eid.split(".", 1)[0]
    if f.reference and eid != f.reference:
        return False
    if f.domain and domain != f.domain:
        return False
    if f.state and stato.get(eid) != f.state:
        return False
    if f.device_class and (classi.get(eid) or entry.get("classe")) != f.device_class:
        return False
    if f.area:
        wanted = f.area.strip().lower()
        if wanted == "senza area":
            if _area_name(area) is not None:
                return False
        elif (area.get("nome") or "").lower() != wanted and area.get("id") != wanted:
            return False
    if f.floor and (floor.get("nome") or "").lower() != f.floor.strip().lower():
        return False
    if f.platform and entry.get("piattaforma") != f.platform:
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
    return redact_row(row)


def _behavior_rows(f: HouseFilters, behavior, mirror, now, medium: bool):
    stato, _n, _u, _c, _d, attributi = mirror
    rows = []
    for item in behavior or []:
        kind = item.get("tipo")
        if f.kind and kind != f.kind:
            continue
        if f.reference and item.get("id") != f.reference:
            continue
        if f.name and not name_matches(f.name, item.get("nome") or ""):
            continue
        values = (attributi.get(item["id"]) or {}).get("values") or {}
        last = values.get("last_triggered")
        age = _age_s(last, now)
        if f.idle_for_s is not None and age is not None and age < f.idle_for_s:
            continue
        if f.changed_within_s is not None and (age is None or age > f.changed_within_s):
            continue
        if f.state and stato.get(item["id"]) != f.state:
            continue
        if f.running is not None and bool(values.get("current")) != f.running:
            continue
        row = {"id": item["id"], "nome": item.get("nome"), "genere": kind,
               "stato": stato.get(item["id"]),
               "ultima_esecuzione": last or "mai"}
        if medium:
            for key, label in (("mode", "modalita"), ("current", "in_esecuzione")):
                if key in values:
                    row[label] = values[key]
        rows.append(row)
    return rows


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


def _sort_key(order_by: str):
    if order_by == "ultimo_cambio":
        return lambda r: r.get("ultima_esecuzione") or r.get("ultimo_cambio") or ""
    if order_by == "valore":
        def key(r):
            try:
                return (0, float(r.get("stato")))
            except (TypeError, ValueError):
                return (1, 0.0)
        return key
    return lambda r: (r.get("nome") or r.get("id") or "").lower()


def query_house(home_space: dict, behavior, mirror, filters: HouseFilters, *,
                detail, unavailable=(), now: float | None = None) -> dict:
    now = time.time() if now is None else now
    f = filters
    excluded = {"nascoste": 0, "servizio": 0, "disabilitate": 0}
    if f.kind in _DETAIL_ONLY_KINDS:
        # Senza `riferimento` la voce di `queries.view` porta gia' `esiste: False`.
        return {"trovate": 1, "escluse": excluded, "profondita": "completa",
                "voci": [redact_row(detail(f.kind, f.reference or f.name or ""))]}
    kinds = KINDS if f.only_by_name else ((f.kind,) if f.kind else ("entita",))
    matched: list[tuple[str, dict, dict, dict, str | None]] = []
    if "entita" in kinds:
        for entry, area, floor, where in _entity_entries(home_space, unavailable):
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
            matched.append(("entita", entry, area, floor, where))
    total_entities = len(matched)
    extra: list[dict] = []
    for kind in kinds:
        if kind in _BEHAVIOR_KINDS:
            extra.extend(_behavior_rows(replace(f, kind=kind), behavior, mirror,
                                        now, medium=True))
        elif kind == "area":
            extra.extend(_area_rows(f, home_space, unavailable))
    found = total_entities + len(extra)
    result: dict = {"trovate": found, "escluse": excluded}
    if found == 1 and f.limit > 0:
        if matched:
            _k, entry, *_ = matched[0]
            voce = detail("entita", entry["id"])
        else:
            voce = detail(extra[0]["genere"], extra[0]["id"])
        result.update(profondita="completa", voci=[redact_row(voce)])
        return result
    medium = found <= DETAIL_MEDIUM_MAX
    rows = [_entity_row(entry, area, where, mirror, medium)
            for _k, entry, area, _floor, where in matched] + extra
    rows.sort(key=_sort_key(f.order_by))
    page = rows[f.offset:f.offset + min(f.limit, ROWS_MAX)]
    result.update(profondita="media" if medium else "corta", voci=page)
    left = len(rows) - f.offset - len(page)
    if left > 0 and f.limit > 0:
        result["oltre"] = {"restano": left, "salta": f.offset + len(page)}
    return result
