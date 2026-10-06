"""Il dato fermo: una fonte che smette di parlare, giudicata con le sue sorelle.

Piano degli strati 1-2 degli attori, Task 1.1 e 1.3; il caso e' quello del
30/09/2026 (BACKLOG, «Un contatore CONGELATO non si distingue da un giorno a
zero»): l'inverter ha smesso di mandare dati, Home Assistant ha tenuto gli
ultimi valori, e il resoconto ha scritto produzione 0 con copertura 1.0.

**Perche' il gruppo e non la serie** (proposta del 06/10/2026, dopo la
revisione del giro 4 e la misura dello sprint). La prima forma giudicava ogni
serie da sola contro la sua storia (la meta' «la sua storia» della D3 del
03/10): sulle catture dal 03/09 al 03/10 dava 360 rifiuti, 325 falsi. Da sola
una serie non distingue «la fonte ha smesso di parlare» da «oggi la casa ha
fatto altro» -- uno scaldabagno spento, un'ora piatta di un termometro. Una
fonte che tace, invece, tace con tutte le sue sorelle. La forma di adesso,
rigiocata dallo sprint sulle stesse catture: 73 rifiuti, 58 veri su 58, 15
falsi (13 forse veri), nessun blocco perso.

**La regola.** Il gruppo e' `House.sibling_group`: il dispositivo, o
l'istanza dell'integrazione per un'entita' sola sul suo dispositivo. Un'ora e':

1. **ferma per il gruppo** se tutte le sue entita' hanno un punto e nessuna
   varia (cambio 0 per un contatore, `minimo == massimo` per una misura
   istantanea), e almeno una misura istantanea e' ferma su un valore
   **diverso da zero**: lo zero e' anche il riposo di un apparecchio spento,
   10 W a mezzogiorno o la batteria al 74% per un giorno no. Un gruppo di una
   sola entita', o di soli contatori, non si giudica: non c'e' una prova;
2. **anomala** se il resto della casa, in quell'ora, si muove (se si ferma
   tutto e' il sistema, Task 1.4), e se alla stessa ora dei giorni prima --
   con l'ora prima e l'ora dopo, `NEIGHBOUR_HOURS` -- il gruppo non e' mai
   stato fermo. La notte di un fotovoltaico senza batteria e' ferma ogni notte,
   e si spiega da se'.

Un **tratto** sono ore ferme per il gruppo consecutive, sull'intera finestra
letta (storia e giorno): un blocco cominciato tre giorni fa e' un tratto solo
che arriva a oggi. Conta se ha almeno un'ora anomala. Le misure del giorno si
rifiutano (D4) se un tratto «ferma» lo tocca; per un CONTATORE solo se il
tratto arriva all'ultima ora della finestra: un blocco che recupera prima di
sera non toglie niente al totale (G4-2).

**Nessuna soglia sulla casa.** `NEIGHBOUR_HOURS` e' la risoluzione della
griglia oraria delle statistiche, non quanto deve durare un blocco;
`HISTORY_DAYS` e' il costo della lettura.

**Funzione pura**: le serie arrivano da chi chiama, nella forma di
`server._punti_orari`. `server._report_ingredients` legge in UNA richiesta il
giorno e la sua storia, per le entita' delle ricette e per le loro sorelle, e
passa i rifiuti fra le entita' che tacciono (`silent`), la strada che
`Recipe.run` conosce gia'. Notte, recupero e riparazione d'avvio passano
dagli stessi ingredienti.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from datetime import UTC

from ..home_space.historian import instant_epoch, instant_out
from .operations import FROZEN, NotComputable

_DAY_S = 86400
_HOUR_S = 3600

#: Quanti giorni di storia legge il resoconto per giudicare un giorno: il costo
#: della lettura, non una soglia -- la finestra delle statistiche passa da un
#: giorno a otto, in UNA richiesta per giro (R16). Una settimana perche' ogni
#: giorno della settimana ci compare una volta. Un blocco cominciato prima
#: della finestra non ha ore anomale dentro, e non esce.
HISTORY_DAYS = 7

#: Quante ore prima e dopo valgono come «la stessa ora» dei giorni passati. E'
#: la risoluzione della griglia oraria: il bordo di un tramonto che anticipa,
#: o il cambio dell'ora, spostano un'abitudine di una casella. Misurato dallo
#: sprint il 06/10/2026: con 1 spariscono 22 falsi (i 20 di bordo di due
#: sensori di luce e i 2 del 17/09) e i 58 blocchi veri restano.
NEIGHBOUR_HOURS = 1


def _still(point: dict) -> bool | None:
    """Se l'ora non varia: `True`, `False`, o `None` se di lei non si sa niente."""
    value = point.get("valore")
    if value is not None:
        return value == 0
    low, high = point.get("minimo"), point.get("massimo")
    if low is not None and high is not None:
        return low == high
    return None


def _index(series: Mapping[str, list]):
    """`{entita': {istante: ferma}}`, i contatori, e le ore in cui una misura
    istantanea e' ferma su un valore diverso da zero."""
    hours_of: dict[str, dict[float, bool]] = {}
    counters: set[str] = set()
    held: set[tuple[str, float]] = set()
    for entity_id, points in (series or {}).items():
        hours: dict[float, bool] = {}
        for point in points or []:
            if not isinstance(point, dict):
                continue
            start, still = instant_epoch(point.get("inizio")), _still(point)
            if start is None or still is None:
                continue
            hours[start] = still
            if point.get("valore") is not None:
                counters.add(entity_id)
            elif still and point.get("minimo") != 0:
                held.add((entity_id, start))
        hours_of[entity_id] = hours
    return hours_of, counters, held


def split_at(points, instant_ts: float) -> tuple[list[dict], list[dict]]:
    """I punti divisi in `(prima, da li' in poi)` rispetto a `instant_ts`.

    Il resoconto legge giorno e storia in una richiesta sola: questa e' la
    riga che li separa. Un punto senza un istante leggibile resta col giorno,
    dove stava prima del Task 1.3.
    """
    before: list[dict] = []
    after: list[dict] = []
    for point in points or []:
        start = instant_epoch(point.get("inizio")) if isinstance(point, dict) else None
        (before if start is not None and start < instant_ts else after).append(point)
    return before, after


def frozen_stretches(series: Mapping[str, list],
                     groups: Mapping[str, Hashable | None]) -> dict[Hashable, list[dict]]:
    """I tratti «ferma» di ogni gruppo sull'intera finestra:
    `{gruppo: [{"dal", "al", "giorni_di_storia"}]}` con gli istanti in epoch.

    `series` sono i punti di TUTTA la finestra letta, per ogni entita'; `groups`
    dice il gruppo di ognuna (`House.sibling_group`, `None` = senza gruppo).
    """
    hours_of, _counters, held = _index(series)
    members: dict[Hashable, list[str]] = {}
    for entity_id, group in groups.items():
        if group is not None and entity_id in hours_of:
            members.setdefault(group, []).append(entity_id)
    every_hour = sorted({ts for hours in hours_of.values() for ts in hours})
    if not every_hour:
        return {}
    found: dict[Hashable, list[dict]] = {}
    for group, entities in members.items():
        if len(entities) < 2:
            continue
        outside = [e for e in hours_of if groups.get(e) != group]
        stretches = _group_stretches(entities, outside, hours_of, held, every_hour)
        if stretches:
            found[group] = stretches
    return found


def _group_stretches(entities, outside, hours_of, held, every_hour) -> list[dict]:
    """I tratti «ferma» di un gruppo (vedi il docstring del modulo)."""
    first = every_hour[0]

    def group_still(ts):
        return (all(hours_of[e].get(ts) is True for e in entities)
                and any((e, ts) in held for e in entities))

    def has_data(ts):
        return all(ts in hours_of[e] for e in entities)

    def rest_moves(ts):
        return any(hours_of[e].get(ts) is False for e in outside)

    stretches: list[dict] = []
    run: list[float] = []
    days_seen = 0

    def close() -> None:
        nonlocal days_seen
        if run and days_seen:
            stretches.append({"dal": run[0], "al": run[-1] + _HOUR_S,
                              "giorni_di_storia": days_seen})
        run.clear()
        days_seen = 0

    previous: float | None = None
    for ts in every_hour:
        # Un'ora mancante fra due presenti spezza il tratto.
        if previous is not None and ts != previous + _HOUR_S:
            close()
        previous = ts
        if not group_still(ts):
            close()
            continue
        run.append(ts)
        judged = [p for p in (ts - k * _DAY_S for k in range(1, HISTORY_DAYS + 1))
                  if p >= first and has_data(p)]
        near = [q for p in judged
                for q in range(int(p) - NEIGHBOUR_HOURS * _HOUR_S,
                               int(p) + NEIGHBOUR_HOURS * _HOUR_S + 1, _HOUR_S)
                if has_data(q)]
        if rest_moves(ts) and judged and not any(group_still(q) for q in near):
            days_seen = max(days_seen, len(judged))
    close()
    return stretches


def frozen_refusals(series: Mapping[str, list],
                    groups: Mapping[str, Hashable | None], *,
                    day_start_ts: float, entity_ids=None,
                    zone=UTC) -> dict[str, NotComputable]:
    """Il rifiuto delle misure del giorno per le entita' ferme:
    `{entity_id: NotComputable(..., cause=FROZEN)}`.

    `entity_ids` sono quelle di cui si chiede (le entita' delle ricette); le
    altre servono solo da sorelle e da «resto della casa». La frase parla
    nell'ora della casa (G4-4).
    """
    _hours, counters, _held = _index(series)
    last = max((ts for hours in _hours.values() for ts in hours), default=None)
    refusals: dict[str, NotComputable] = {}
    wanted = set(series) if entity_ids is None else set(entity_ids)
    for group, stretches in frozen_stretches(series, groups).items():
        siblings = sorted(e for e, g in groups.items() if g == group and e in series)
        for stretch in stretches:
            if stretch["al"] <= day_start_ts:
                continue
            reaches_end = last is not None and stretch["al"] >= last + _HOUR_S
            said_start = instant_out(stretch["dal"], zone)
            said_end = instant_out(stretch["al"], zone)
            for entity_id in siblings:
                if entity_id not in wanted or entity_id in refusals:
                    continue
                if entity_id in counters and not reaches_end:
                    continue
                refusals[entity_id] = NotComputable(
                    f"{entity_id} e' ferma: dalle {said_start} alle {said_end} non "
                    f"varia nessuna delle {len(siblings)} entita' del suo gruppo "
                    f"({', '.join(siblings)}), mentre il resto della casa si muove, "
                    f"e a quell'ora il gruppo non era mai fermo nei "
                    f"{stretch['giorni_di_storia']} giorni di storia", cause=FROZEN)
    return refusals
