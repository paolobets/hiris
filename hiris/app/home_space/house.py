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

I metodi del §4.1 della spec arrivano un task alla volta: qui ci sono la
gerarchia, la scelta di «di chi» (`select`, l'ex `house_query.select_subjects`),
la VISIBILITA' con la causa (`visibility`) e l'IDENTITA' (`name`), dal Task 5, e
il dove (`where`), dal Task 6. Le regole stanno in `topology` (`visibility`,
`live_name`, `device_name`), che sta SOTTO questo modulo: la gerarchia le applica
e non puo' importare la casa.
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

#: La chiave di `escluse` per ogni classe del fuori (`topology.visibility`).
_EXCLUDED_KEY = {"disabilitata": "disabilitate", "nascosta": "nascoste",
                 "servizio": "servizio"}


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
        self._places: dict[str, tuple[dict, dict, dict]] | None = None
        self._device_index: dict[str, dict] | None = None
        self._entities: dict[str, dict] | None = None

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

    def where(self, entity_id: str) -> dict | None:
        """DOVE sta un'entita' (spec §4.1; Tappa 3, Task 6, B-10, D3): area,
        se l'area e' ereditata dal dispositivo, piano, dispositivo e
        integrazione. `None` se il registro delle entita' non la conosce.

        **Compone, non decide.** Il posto viene dall'albero di `hierarchy()`,
        che lo calcola con `topology.actual_area` -- l'area propria, altrimenti
        quella del dispositivo: la regola di Home Assistant -- e che sa gia'
        dire «Dispositivi non letti» o «Aree non lette» quando un registro non
        ha risposto. Rifare qui quelle cause sarebbe una seconda copia della
        regola, la stessa che `observer.house_lines` ha (legge il solo
        `area_id` proprio: 194 entita' guardate su 324 senza area, cattura del
        01/10/2026) e che il Task 12 toglie.

        Ogni parte porta `id` e `nome` (atomicita': un id senza nome e' un
        frammento, un nome senza id e' un vicolo cieco per `search` e `view`).
        Una pseudo-area resta col suo id (`view("area", "__senza_area__")` la
        ritrova) e il piano allora tace: il contenitore «Fuori dalle aree»
        ripeterebbe solo che l'area non c'e'. `area_ereditata` e' vera solo
        quando l'area c'e', e' vera, e la voce non ne dichiara una propria.
        """
        place = self._entity_places().get(entity_id)
        if place is None:
            return None
        entry, area, floor = place
        pseudo = topology.is_pseudo_area(area.get("id"))
        device_id = entry.get("dispositivo_id")
        device = self._devices().get(device_id) if device_id else None
        return {
            "area": {"id": area.get("id"), "nome": area.get("nome")},
            "area_ereditata": not pseudo and not entry.get("area_id"),
            "piano": None if pseudo else {"id": floor.get("id"), "nome": floor.get("nome")},
            "dispositivo": ({"id": device_id, "nome": (device or {}).get("nome")}
                            if device_id else None),
            "integrazione": entry.get("piattaforma"),
        }

    def _entity_places(self) -> dict[str, tuple[dict, dict, dict]]:
        if self._places is None:
            self._places = {entry["id"]: (entry, area, floor)
                            for entry, area, floor, _w in self.entity_entries()}
        return self._places

    def _devices(self) -> dict[str, dict]:
        if self._device_index is None:
            self._device_index = {d["id"]: d for d in self.home_space.get("dispositivi") or []
                                  if isinstance(d, dict) and d.get("id")}
        return self._device_index

    def select(self, f, kinds: tuple[str, ...], behavior, *, now: float) -> Selection:
        """Le entita' e i comportamenti che passano i filtri, per i generi dati.

        Le disabilitate sono sempre fuori e contate; le nascoste e quelle di
        servizio fuori e contate, salvo `includi_nascoste`/`includi_servizio`.
        La riga di comportamento rappresenta gia' l'automazione: quando si
        cercano anche automazioni o script, la loro entita' di registro sarebbe
        un doppione e non si sceglie (solo quelle che il comportamento conosce:
        un'automazione che non c'e' resta un'entita').

        `search` e `history` scelgono con questa STESSA funzione (spec «la
        storia» §2): fino al 04/10/2026 era `house_query.select_subjects`,
        uscita col Task 13 quando la storia ha smesso di chiamarla."""
        entries = self.entity_entries()
        searching_behavior = any(k in _BEHAVIOR_KINDS for k in kinds)
        shadowed = {b.get("id") for b in behavior or []} if searching_behavior else set()
        excluded = {"nascoste": 0, "servizio": 0, "disabilitate": 0}
        # Le classi che questa porta conta (D7): le disabilitate mai, le
        # nascoste e quelle di servizio a richiesta. Un'entita' fuori per
        # piu' ragioni si conta sotto la PRIMA che la porta non ammette.
        admitted = ({"nascosta"} if f.include_hidden else set()) | (
            {"servizio"} if f.include_service else set())
        matched = []
        if "entita" in kinds:
            for entry, area, floor, where in entries:
                if entry["id"] in shadowed:
                    continue
                if not _entity_matches(f, entry, area, floor, self.mirror, now):
                    continue
                refused = next((cls for cls, _cause in topology.visibility_classes(entry)
                                if cls not in admitted), None)
                if refused is not None:
                    excluded[_EXCLUDED_KEY[refused]] += 1
                    continue
                matched.append((entry, area, where))
        places = {entry["id"]: (entry, area, floor) for entry, area, floor, _w in entries}
        behaving = []
        for kind in kinds:
            if kind in _BEHAVIOR_KINDS:
                behaving.extend(_behavior_matches(replace(f, kind=kind), behavior,
                                                  self.mirror, now, places))
        return Selection(matched, behaving, excluded)

    def _entity(self, entity_id: str) -> dict | None:
        """La voce dell'anagrafe di un'entita', per id; l'indice si fa una volta."""
        if self._entities is None:
            self._entities = {e["id"]: e for e in self.home_space.get("entita") or []
                              if isinstance(e, dict) and e.get("id")}
        return self._entities.get(entity_id)

    def visibility(self, entity_id: str) -> tuple[str, str | None] | None:
        """VISIBILITA' (§4.1): la classe di un'entita' con la sua causa --
        `("disabilitata", "user")`, `("servizio", "diagnostic")`,
        `("visibile", None)` -- dalla regola unica, `topology.visibility`.
        `None` per un id che l'anagrafe non conosce: non e' «visibile»."""
        entry = self._entity(entity_id)
        return None if entry is None else topology.visibility(entry)

    def name(self, kind: str, identifier: str) -> str | None:
        """IDENTITA' (§4.1): come si chiama una cosa della casa, per genere.

        Entita', automazioni e script col nome vivo (D1, `topology.live_name`):
        hanno tutti un `entity_id`, e il nome che Home Assistant mostra sta
        nello specchio per tutti e tre. Dispositivi col nome, altrimenti l'id
        (`topology.device_name`); aree e piani col nome dell'anagrafe, che il
        lettore riempie gia' con l'id quando manca. `None` per un dispositivo,
        un'area o un piano che l'anagrafe non conosce."""
        if kind in ("entita", *_BEHAVIOR_KINDS):
            entry = self._entity(identifier) or {}
            return topology.live_name(identifier, entry.get("nome"), self.mirror)
        table = {"dispositivo": "dispositivi", "area": "aree", "piano": "piani"}.get(kind)
        if table is None:
            raise ValueError(f"genere sconosciuto: {kind!r}")
        row = next((r for r in self.home_space.get(table) or []
                    if isinstance(r, dict) and r.get("id") == identifier), None)
        if row is None:
            return None
        return topology.device_name(row) if kind == "dispositivo" else row.get("nome")
