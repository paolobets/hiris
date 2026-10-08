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
   sola entita', o di soli contatori, non si giudica: non c'e' una prova.
   Una sorella senza punti in quell'ora rende il gruppo non fermo (G7-3,
   bassa: quanti gruppi lo subiscono lo conta la rimisura dello sprint);
2. **anomala** se il resto di cio' che il resoconto legge -- le altre entita'
   delle ricette e le loro sorelle, non la casa intera (G7-2: con le ricette
   di un solo dispositivo la regola non scatta mai) -- in quell'ora si muove
   (se si ferma tutto e' il sistema, Task 1.4), e se alla stessa ora dei
   giorni prima -- con l'ora prima e l'ora dopo, `NEIGHBOUR_HOURS` -- il
   gruppo non e' mai stato fermo. La notte di un fotovoltaico senza batteria e' ferma ogni notte,
   e si spiega da se'.

Un **tratto** sono ore ferme per il gruppo consecutive, sull'intera finestra
letta (storia e giorno): un blocco cominciato tre giorni fa e' un tratto solo
che arriva a oggi. Conta se ha almeno un'ora anomala. Cosa toglie al giorno
(`frozen_day`):

- a una MISURA ISTANTANEA, le sole ore del tratto (decisione del
  proprietario, 08/10/2026). Fino ad allora la misura si rifiutava per intero
  (D4), e il 06/10 un'ora ferma di una stazione ha cancellato la giornata di
  temperatura e umidita' della stanza. Ora la misura si fa sul resto, e
  dichiara le ore che ha lasciato fuori (`operations.Exclusion`);
- a un CONTATORE, tutto, ma solo se il tratto arriva all'ultima ora della
  finestra: un blocco che recupera prima di sera non toglie niente al totale
  (G4-2), e un totale con un buco in fondo non si sa quanto valga.

**Nessuna soglia sulla casa.** `NEIGHBOUR_HOURS` e' la risoluzione della
griglia oraria delle statistiche, non quanto deve durare un blocco;
`HISTORY_DAYS` e' il costo della lettura.

**Funzione pura**: le serie arrivano da chi chiama, nella forma di
`recipes.hourly_points`. `server._report_ingredients` legge in UNA richiesta il
giorno e la sua storia, per le entita' delle ricette e per le loro sorelle;
passa i rifiuti dei contatori fra le entita' che tacciono (`silent`), e segna
le ore escluse sui punti del giorno (`mark_excluded`): tutte e due le strade
le conosce `Recipe.run`. Notte, recupero e riparazione d'avvio passano dagli
stessi ingredienti.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from datetime import UTC

from ..home_space.historian import instant_epoch, instant_out
from .operations import FROZEN, Exclusion, NotComputable
from .recipes import EXCLUDED_MARK

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


def frozen_day(series: Mapping[str, list],
               groups: Mapping[str, Hashable | None], *,
               day_start_ts: float, entity_ids=None, zone=UTC
               ) -> tuple[dict[str, NotComputable], dict[str, list[Exclusion]]]:
    """Cosa il dato fermo toglie al giorno: `(rifiuti, esclusioni)`.

    - `rifiuti`, `{entity_id: NotComputable(..., cause=FROZEN)}`: i CONTATORI
      il cui tratto fermo arriva all'ultima ora della finestra. Il loro totale
      non e' recuperato, e una parte non si toglie da un totale (G4-2);
    - `esclusioni`, `{entity_id: [Exclusion]}`: le MISURE ISTANTANEE toccate
      da un tratto fermo, con le sole ore del tratto che cadono nel giorno
      (decisione del proprietario, 08/10/2026). Il 06/10 un'ora ferma di una
      stazione faceva rifiutare la giornata intera; ora esce solo quell'ora,
      e la misura si fa sul resto (`recipes.Recipe.run`).

    Un contatore che recupera prima di sera non perde niente: le ore ferme
    portano un cambio 0 e quella della ripresa porta il recupero, il totale
    e' giusto cosi'.

    `entity_ids` sono quelle di cui si chiede (le entita' delle ricette); le
    altre servono solo da sorelle e da «resto della casa». La frase parla
    nell'ora della casa (G4-4), ed e' la stessa per il rifiuto e per
    l'esclusione: e' il fatto del gruppo, non della misura.
    """
    hours, counters, _held = _index(series)
    last = max((ts for by_hour in hours.values() for ts in by_hour), default=None)
    refusals: dict[str, NotComputable] = {}
    exclusions: dict[str, list[Exclusion]] = {}
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
                reason = (
                    f"{entity_id} e' ferma: dalle {said_start} alle {said_end} non "
                    f"varia nessuna delle {len(siblings)} entita' del suo gruppo "
                    f"({', '.join(siblings)}), mentre il resto della casa si muove, "
                    f"e a quell'ora il gruppo non era mai fermo nei "
                    f"{stretch['giorni_di_storia']} giorni di storia")
                if entity_id in counters:
                    if reaches_end:
                        refusals[entity_id] = NotComputable(reason, cause=FROZEN)
                    continue
                # Solo le ore del giorno: un tratto cominciato ieri toglie a
                # oggi le ore da mezzanotte, e la frase dice il tratto intero.
                start_ts = max(stretch["dal"], day_start_ts)
                said_from = instant_out(start_ts, zone)
                exclusions.setdefault(entity_id, []).append(Exclusion(
                    start_ts=start_ts, end_ts=stretch["al"],
                    start=said_from, end=said_end,
                    reason=reason, cause=FROZEN,
                    summary=_summary(group, said_from, said_end)))
    return refusals, exclusions


def _clock(said: str, *, end: bool = False) -> str:
    """L'ora di un istante gia' detto nell'ora della casa (`instant_out`):
    «2026-10-06T01:00:00+02:00» -> «01:00». La mezzanotte che chiude un
    tratto e' la fine del giorno, e si dice «24:00»."""
    clock = said[11:16]
    return "24:00" if end and clock == "00:00" else clock


def _summary(group, said_from: str, said_end: str) -> str:
    """La frase per chi legge la pagina, nella sua lingua (parere di
    ux-ui-specialist, 08/10/2026): niente id, niente vocabolario interno. Il
    gruppo e' `House.sibling_group`: un dispositivo, o l'istanza
    dell'integrazione per le entita' sole sul loro dispositivo."""
    who = ("tutti i dispositivi di questa integrazione"
           if isinstance(group, tuple) and group[:1] == ("istanza",)
           else "tutti i sensori di questo dispositivo")
    return (f"Dalle {_clock(said_from)} alle {_clock(said_end, end=True)} {who} "
            "sono rimasti uguali mentre il resto della casa si muoveva: quelle ore "
            "non entrano nel calcolo.")


def mark_excluded(points, exclusions) -> list[dict]:
    """I punti del giorno, con l'esclusione accanto a quelli che le ore
    escluse coprono (`recipes.EXCLUDED_MARK`).

    Il punto resta com'e', col suo valore: lo toglie dal conto
    `Recipe.run`, che sa anche dire se senza quelle ore la copertura sarebbe
    bastata. Un punto porta cosi' il perche' del suo stesso buco, invece di
    una seconda mappa da tenere allineata alla serie (fondamenta 1 e 2).
    """
    if not exclusions:
        return list(points or [])
    marked = []
    for point in points or []:
        start = instant_epoch(point.get("inizio")) if isinstance(point, dict) else None
        found = next((x for x in exclusions if start is not None and x.covers(start)), None)
        marked.append(point if found is None else {**point, EXCLUDED_MARK: found})
    return marked
