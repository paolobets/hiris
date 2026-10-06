"""La **ricetta al volo**: un conto su un periodo scelto, con il motore delle
ricette (decisione D6 del proprietario, 06/10/2026; piano degli attori,
strato 3, Task 3.1).

Chi chiede scrive passi con la stessa grammatica delle ricette -- `@entita`,
`$passo`, operazione, parametri -- e sceglie entita' e periodo. Questo modulo
li valida con `Recipe.validate` e li esegue con `Recipe.run`: **lo stesso
motore, le stesse forme, gli stessi rifiuti con la causa**. Un secondo motore
(una somma scritta qui, una grammatica di espressioni) sarebbe il doppione
che D6 ha scartato.

## Cosa sa consegnare in piu' di una ricetta

Una ricetta legge solo le statistiche orarie (`@entita` -> serie del
periodo). Lo strumento legge anche **gli stati** di un'entita', e da li'
`episodio` ritaglia il periodo in cui era in uno stato: e' la sorgente che la
presenza vuole (D7). Gli stati Home Assistant li conserva per circa otto
giorni (misura R0 del 03/10/2026); oltre, la copertura lo dice e l'operazione
rifiuta (`operations._episode`).

## I parametri del periodo li mette il codice

`period_start`, `period_end` ed `expected_parts` vengono dal periodo chiesto,
mai da chi scrive i passi: un periodo scritto due volte -- nella richiesta e
in un parametro -- e' un fatto con due case, e prima o poi una delle due
mente. Se li scrive lo stesso, la richiesta si rifiuta.

## Non si salva

Il risultato non e' il sapere della casa: e' una risposta. Nessun archivio,
nessuna ricetta scritta.

**Oggi non lo chiama nessuno**: lo strumento entra nel turno dell'analista
con il Task 3.6 (dopo la Tappa 6, T7 e T8). Fino ad allora la sua voce sta in
`scripts/censimento_eccezioni.json`, con la ragione.
"""
from __future__ import annotations

import inspect
import math

from ..home_space.historian import home_space_zone, instant_epoch, instant_out
from ..home_space.house_history import parse_query, read_bands, read_series
from .operations import (
    REGISTRY,
    SHAPE_READINGS,
    SHAPE_SERIES,
    Measurement,
    Period,
    Result,
)
from .recipes import ENTITY_MARK, Recipe, hourly_points, silent_entities, unread_series

#: Il nome dello strumento, quello che D5 mette nella lista dell'analista.
COMPUTE_TOOL_NAME = "compute"

#: Cio' che lo strumento sa leggere di un'entita': la serie delle statistiche
#: e gli stati.
ENTITY_SHAPES = (SHAPE_SERIES, SHAPE_READINGS)

#: I parametri che vengono dal periodo chiesto, e che quindi mette il codice.
#: Lista di AMMISSIONE: un parametro nuovo del registro che dipende dal periodo
#: entra qui, con la ragione, o resta da scrivere a chi chiede.
#:
#: - `period_start`, `period_end` -- dove comincia e finisce il periodo
#:   (`episodio`);
#: - `expected_parts` -- quante ore il periodo ha nelle statistiche
#:   (`somma_periodo`, `media_min_max`, `per_ora`): vedi `expected_hours`.
PERIOD_PARAMS = ("period_start", "period_end", "expected_parts")


def offered() -> list[str]:
    """Le operazioni che lo strumento offre: si chiedono al registro."""
    return sorted(name for name, op in REGISTRY.items() if op.offered_to_tool)


def tool_def() -> dict:
    """Lo schema dello strumento, **derivato dal registro**.

    Le operazioni sono quelle offribili allo strumento
    (`Operation.offered_to_tool`), e per ognuna la descrizione dice gli
    ingressi, la forma che vogliono e i parametri da scrivere -- letti dalla
    firma, tolti quelli che mette il codice. Un'operazione nuova nel registro
    entra qui senza toccare niente.
    """
    lines = []
    for name in offered():
        op = REGISTRY[name]
        params = [p for p in op.required_params if p not in PERIOD_PARAMS]
        lines.append(
            f"- {name}: {op.returns}. Ingressi: {', '.join(op.takes)}"
            + (f". Parametri: {', '.join(params)}" if params else ""))
    return {
        "name": COMPUTE_TOOL_NAME,
        "description": (
            "Fa un conto su un periodo con il motore delle ricette: passi con "
            "nome, operazione, ingressi (`@entita` per i dati di un'entita', "
            "`$passo` per il risultato di un passo precedente) e parametri. "
            "Ogni numero esce con la sua unita' e la sua copertura, o con il "
            "perche' non si calcola. Il periodo si dice con da/a o con ore, "
            "come in `history`; inizio, fine e ore attese li mette il codice. "
            "Gli stati di un'entita' arrivano a circa otto giorni.\n"
            "Operazioni:\n" + "\n".join(lines)),
        "input_schema": {
            "type": "object",
            "properties": {
                "perche": {"type": "string",
                           "description": "cosa vuoi sapere, in una frase"},
                "passi": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "operation": {"type": "string", "enum": offered()},
                            "inputs": {"type": "array", "items": {"type": "string"}},
                            "params": {"type": "object"},
                        },
                        "required": ["name", "operation", "inputs"],
                    },
                },
                "da": {"type": "string"},
                "a": {"type": "string"},
                "ore": {"type": "number"},
            },
            "required": ["perche", "passi"],
        },
    }


def expected_hours(start_ts: float, end_ts: float) -> int:
    """Quante righe orarie di statistiche cadono nel periodo.

    Home Assistant le seleziona con `start_ts >= inizio` e `start_ts < fine`
    (`recorder/statistics.py`, `_generate_statistics_during_period_stmt`,
    letto sul ramo `dev` il 06/10/2026), e una riga oraria comincia allo
    scoccare dell'ora: sono le ore piene che cominciano dentro il periodo.
    """
    return max(0, math.ceil(end_ts / 3600) - math.ceil(start_ts / 3600))


def prepare(arguments: dict, *, now: float, timezone: str | None):
    """La richiesta validata: `(ricetta, finestra)`, o `{"errore", ...}`.

    Il periodo si legge come in `history` (`house_history.parse_query`): le
    stesse parole, gli stessi limiti, gli stessi errori -- una sola lettura
    della finestra per le due porte (fondamenta 3).
    """
    a = dict(arguments or {})
    window = {key: a[key] for key in ("da", "a", "ore") if key in a}
    query = parse_query({**window, "genere": "valori"}, now=now, timezone=timezone)
    if isinstance(query, dict):
        return query
    start_ts, end_ts = query.start.timestamp(), query.end.timestamp()
    steps = a.get("passi")
    if not isinstance(steps, list):
        return {"errore": "passi vuole un elenco di passi, come in una ricetta"}

    problems = []
    filled = []
    context = {"period_start": start_ts, "period_end": end_ts,
               "expected_parts": expected_hours(start_ts, end_ts)}
    for number, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            filled.append(step)
            continue
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        written = sorted(p for p in PERIOD_PARAMS if p in params)
        if written:
            problems.append(
                f"il passo {number} scrive {', '.join(written)}: li mette il "
                "codice dal periodo chiesto, non si scrivono")
        op = REGISTRY.get(str(step.get("operation") or "").strip())
        wanted = op.required_params if op is not None else ()
        optional = _optional_params(op)
        added = {p: context[p] for p in PERIOD_PARAMS
                 if p not in params and (p in wanted or p in optional)}
        filled.append({**step, "params": {**params, **added}})

    recipe = Recipe({"why": a.get("perche"), "steps": filled},
                    entity_shapes=ENTITY_SHAPES)
    named = recipe.entities()
    problems.extend(recipe.validate(entities=named).problems)
    if problems:
        return {"errore": "la richiesta non si esegue: " + " · ".join(problems),
                "problemi": problems}
    return recipe, query


def _optional_params(op) -> tuple[str, ...]:
    """I parametri per nome che l'operazione accetta senza pretenderli."""
    if op is None:
        return ()
    return tuple(name for name, p in inspect.signature(op.run).parameters.items()
                 if p.kind is p.KEYWORD_ONLY and p.default is not p.empty)


def needs(recipe: Recipe) -> tuple[list[str], list[str]]:
    """Quali entita' vogliono la serie delle statistiche e quali gli stati.

    Lo dice la forma che l'operazione del passo vuole in quel posto: la stessa
    entita' puo' servire in tutte e due le forme.
    """
    series, states = set(), set()
    for step in recipe.steps:
        op = REGISTRY[str(step["operation"]).strip()]
        for given, wanted in zip(step.get("inputs") or [], op.takes):
            if isinstance(given, str) and given.startswith(ENTITY_MARK):
                (states if wanted == SHAPE_READINGS else series).add(given[1:])
    return sorted(series), sorted(states)


def state_readings(points) -> list[tuple[float, str]]:
    """Gli stati dello storico (`{"quando", "valore"}`) come `(istante, stato)`,
    in ordine. Un istante che non si legge si scarta: non si inventa."""
    out = []
    for point in points or []:
        if not isinstance(point, dict):
            continue
        when = instant_epoch(point.get("quando"))
        if when is not None:
            out.append((when, point.get("valore")))
    return sorted(out, key=lambda pair: pair[0])


def answer(recipe: Recipe, results: dict[str, Result], *, start_ts: float,
           end_ts: float, timezone: str | None, states_from: dict | None = None,
           truncated: bool = False) -> dict:
    """La risposta: ogni passo col suo numero, unita' e copertura, o col perche'.

    `states_from` dice da quando gli stati letti cominciano davvero, per
    entita': e' il limite della finestra degli stati, detto col fatto misurato
    invece che con un numero scritto qui.
    """
    zone = home_space_zone(timezone)
    out = {"perche": recipe.why, "da": instant_out(start_ts, zone),
           "a": instant_out(end_ts, zone), "passi": []}
    for step in recipe.steps:
        name = str(step["name"]).strip()
        result = results[name]
        row = {"nome": name, "operazione": str(step["operation"]).strip()}
        if isinstance(result, Measurement):
            row.update(valore=_value_out(result.value, zone), unita=result.unit,
                       copertura=result.coverage)
        else:
            row.update(non_calcolabile=result.reason, causa=result.cause)
        out["passi"].append(row)
    if states_from:
        out["stati_dal"] = {entity: instant_out(when, zone)
                            for entity, when in sorted(states_from.items())}
    if truncated:
        out["stati_troncati"] = True
    return out


def _value_out(value, zone):
    """Un periodo esce come le sue finestre, con gli istanti della casa."""
    if isinstance(value, Period):
        return {"finestre": [[instant_out(a, zone), instant_out(b, zone)]
                             for a, b in value.windows]}
    return value


async def compute(arguments: dict, *, ha, house, now: float,
                  timezone: str | None) -> dict:
    """Esegue la richiesta: la risposta (`answer`) o `{"errore", ...}`.

    Le letture sono quelle di `history`, dal loro unico proprietario
    (`house_history.read_bands` e `read_series`; R1 di `tests/test_fonte_unica.py`).
    L'elenco delle statistiche arriva con la casa (`House.with_statistics`,
    dalla lettura condivisa `server.statistic_ids_for_round`): senza, nessuna
    entita' si dice «senza statistiche» -- chi non ha potuto chiedere non lo
    afferma.
    """
    prepared = prepare(arguments, now=now, timezone=timezone)
    if isinstance(prepared, dict):
        return prepared
    recipe, query = prepared
    start_ts, end_ts = query.start.timestamp(), query.end.timestamp()
    series_ids, state_ids = needs(recipe)

    series: dict[str, list] = {}
    silent: dict = {}
    if series_ids:
        silent = silent_entities(house, series_ids) or {}
        report = await read_bands(ha, series_ids, query)
        if "errore" in report:
            refusal = unread_series(str(report["errore"]))
            silent = {**{e: refusal for e in series_ids}, **silent}
        else:
            series = {e: hourly_points(report["serie"].get(e) or [])
                      for e in series_ids}

    readings: dict[str, list] = {}
    truncated = False
    states_from: dict[str, float] = {}
    if state_ids:
        story = await read_series(ha, state_ids, query)
        if "errore" in story:
            return story
        truncated = story["troncato"]
        for entity in state_ids:
            readings[entity] = state_readings(story["serie"].get(entity))
            if readings[entity]:
                states_from[entity] = max(readings[entity][0][0], start_ts)

    results = recipe.run(series={e: series.get(e, []) for e in series_ids},
                         silent=silent, readings=readings)
    return answer(recipe, results, start_ts=start_ts, end_ts=end_ts,
                  timezone=timezone, states_from=states_from, truncated=truncated)
