"""L'istantanea della casa: anagrafe e specchio, letti UNA volta per turno
(R18; Tappa 3, Task 4, 04/10/2026).

**Il punto di giunzione** fra l'anagrafe (i registri: `HomeSpace.read()`) e
lo specchio (gli stati: `topology.read_mirror`). Fino a quel giorno ogni
porta se li rifaceva da se': misurato sulla casa sintetica, un turno di
chat col nucleo, tre `search` e una `history` costruiva la gerarchia dieci
volte e lo specchio cinque (`tests/test_casa_per_turno.py`). Una `search`
per nome ne costruiva tre (entita', aree, dispositivi), quattro se trovava
un'area.

**Vale un turno, o un giro di un attore, e basta.** Non si tiene mai in
`app[...]` e non passa al turno dopo: una casa vecchia di un turno e' il
difetto che R12 vieta (nessuna copia invecchia in silenzio). Chi la tiene
per un turno -- `ToolDispatcher`, che nasce a ogni turno -- la butta quando
la casa cambia sotto di lui: l'anagrafe ricostruita (un altro oggetto da
`HomeSpace.read()`), o un suo comando eseguito (vedi `ToolDispatcher`).

I metodi del §4.1 della spec (`visibility`, `name`, `where`, `kind_of`,
`source`...) arrivano con i task che seguono; qui ci sono la gerarchia e la
scelta di «di chi» (`select`, l'ex `house_query.select_subjects`).
"""
from __future__ import annotations

from dataclasses import replace

from . import topology
from .house_query import (
    _BEHAVIOR_KINDS,
    Selection,
    _behavior_matches,
    _entity_matches,
)
from .topology import Mirror, read_mirror


class House:
    """L'anagrafe, lo specchio e i registri caduti di UN momento, con la
    gerarchia calcolata alla prima richiesta e tenuta.

    `home_space` e' l'oggetto che `HomeSpace.read()` ha restituito (non una
    copia: il lettore lo dichiara di sola lettura, e il dispatcher lo
    confronta per identita' per sapere se l'anagrafe e' stata ricostruita).
    """

    def __init__(self, home_space: dict, mirror: Mirror,
                 unavailable: tuple[str, ...] = ()) -> None:
        self.home_space = home_space
        self.mirror = mirror
        self.unavailable = tuple(unavailable)
        self._floors: list[dict] | None = None

    @classmethod
    def read(cls, home_space_store, cache) -> House:
        """La casa di adesso, dagli archivi vivi. Senza archivio, una casa
        vuota (non inventata): chi la legge lo dichiara, come faceva prima
        ciascuno per conto suo."""
        if home_space_store is None:
            return cls({}, read_mirror(cache))
        return cls(home_space_store.read(), read_mirror(cache),
                   tuple(home_space_store.unavailable()))

    def hierarchy(self) -> list[dict]:
        """L'albero piano -> area -> entita' di `topology.hierarchy`, con i
        registri caduti applicati. Calcolato una volta: chi lo riceve lo
        legge, non lo modifica (le porte costruiscono dizionari loro)."""
        if self._floors is None:
            self._floors = topology.hierarchy(self.home_space, self.unavailable)
        return self._floors

    def entity_entries(self) -> list[tuple[dict, dict, dict, str]]:
        """(voce, area, piano, dove) per ogni entita' dell'albero; `dove` e'
        `visibile`, `nascosta` o `disabilitata`."""
        out = []
        for floor in self.hierarchy():
            for area in floor.get("aree") or []:
                for key, where in (("entita", "visibile"),
                                   ("entita_nascoste", "nascosta"),
                                   ("entita_disabilitate", "disabilitata")):
                    for entry in area.get(key) or []:
                        if isinstance(entry, dict) and entry.get("id"):
                            out.append((entry, area, floor, where))
        return out

    def select(self, f, kinds: tuple[str, ...], behavior, *, now: float) -> Selection:
        """Le entita' e i comportamenti che passano i filtri, per i generi dati.

        Le disabilitate sono sempre fuori e contate; le nascoste e quelle di
        servizio fuori e contate, salvo `includi_nascoste`/`includi_servizio`.
        La riga di comportamento rappresenta gia' l'automazione: quando si
        cercano anche automazioni o script, la loro entita' di registro sarebbe
        un doppione e non si sceglie (solo quelle che il comportamento conosce:
        un'automazione che non c'e' resta un'entita').

        `search` e `history` scelgono con questa STESSA funzione (spec «la
        storia» §2): fino al 04/10/2026 era `house_query.select_subjects`, che
        resta come rimando fino al Task 13."""
        entries = self.entity_entries()
        searching_behavior = any(k in _BEHAVIOR_KINDS for k in kinds)
        shadowed = {b.get("id") for b in behavior or []} if searching_behavior else set()
        excluded = {"nascoste": 0, "servizio": 0, "disabilitate": 0}
        matched = []
        if "entita" in kinds:
            for entry, area, floor, where in entries:
                if entry["id"] in shadowed:
                    continue
                if not _entity_matches(f, entry, area, floor, self.mirror, now):
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
        for kind in kinds:
            if kind in _BEHAVIOR_KINDS:
                behaving.extend(_behavior_matches(replace(f, kind=kind), behavior,
                                                  self.mirror, now, places))
        return Selection(matched, behaving, excluded)
