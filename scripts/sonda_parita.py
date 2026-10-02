#!/usr/bin/env python3
"""HIRIS sonda di parita' — le copie VERE delle regole sugli ingressi veri.

## Perche' esiste

Lo sprint «Una fonte sola di verita'» chiude un doppione quando la copia e'
cancellata. Prima di cancellarla bisogna sapere se le due copie rispondono
uguale **sulla casa vera**: leggere il codice dice che possono divergere, solo
eseguirle dice se e quanto divergono. Questa sonda importa le funzioni del
prodotto -- nessuna regola e' riscritta qui -- le fa girare sugli stessi
ingressi congelati da `scripts/casa.py`, e conta dove non concordano.

L'attesa a fine sprint e' zero disaccordi su ogni domanda (spec §5, §8).

## Una domanda si rompe quando la sua copia sparisce, ed e' voluto

Le domande nominano funzioni private (`_entity_row`, `_enrich_entity`...):
sono le copie. Quando una tappa ne cancella una, quella domanda solleva; `run`
la dichiara «non eseguita» e il cancello la conta come un no. Chi cancella la
copia toglie dalla sonda la domanda che ha chiuso. Una sonda che ricopiasse la
regola per non rompersi confronterebbe il prodotto con se stesso di ieri.

## Cosa NON guarda, dichiarato

- **Il consumato** (`house_history._consumed` contro
  `operations._first_last_difference`): la seconda copia non e' raggiungibile
  dalla produzione (correzione a B-13 del registro) ed esce con la Tappa 0.
  Misurata il 01/10/2026 dall'analisi: 28 conti diversi su 272 su 7 giorni.
- **`Lookup.find`** come motore di ricerca per nome: nessun chiamante di
  produzione (M-08), esce con la Tappa 0.

Nasce da `docs/superpowers/audit-2026-10-01/sonda_parita.py` (01/10/2026).

Uso:
  python scripts/sonda_parita.py --ingressi ~/.hiris-sprint/ingressi/2026-10-01
  python scripts/sonda_parita.py --ingressi <cartella> --rapporto sonda.md
  python scripts/sonda_parita.py --ingressi <cartella> --cancello --attesi attesi.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import casa

from hiris.app.home_space import (
    briefing,
    ha_vocabulary,
    historian,
    house_query,
    queries,
    reader,
    topology,
    type_vocabulary,
)
from hiris.app.mind import observer, recipe_turn
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.entity_cache import _to_minimal

#: Il separatore dei campi nelle righe che osservatore e ricette mandano al
#: modello. **E' una copia, dichiarata**: il prodotto lo scrive in linea, non
#: ha una costante da chiedere (e' una delle forme che la Tappa 4 unifica).
#: Se cambiasse la, le righe non si spezzerebbero piu' e gli id letti non
#: sarebbero id: `_entity_ids` se ne accorge e ferma la domanda.
LINE_SEPARATOR = " · "
CASES_KEPT = 40


def build_inputs(source: Path | dict, *, clock: float | None = None) -> dict:
    """L'anagrafe e lo specchio, montati come li monta il prodotto.

    `source` e' la cartella degli ingressi congelati, oppure un dizionario con
    le stesse chiavi (le prove passano la casa sintetica). Lo specchio passa da
    `_to_minimal` e `live_mirror`, l'anagrafe da `reader.build_home_space` con
    classi e unita' vive: e' cio' che fa `HomeSpace.rebuild()`.
    """
    raw = source if isinstance(source, dict) else casa.read_inputs(source)
    rows = [_to_minimal(row) for row in raw["states"] if row.get("entity_id")]
    mirror = topology.live_mirror(rows)
    home_space = reader.build_home_space(raw["registries"], live_classes=mirror[3],
                                         live_units=mirror[2])
    return {"home_space": home_space, "mirror": mirror, "rows": rows,
            "raw_states": raw["states"], "registries": raw["registries"],
            "statistic_ids": set(raw["statistic_ids"]),
            "behavior": raw["behavior"], "ha_config": raw["ha_config"],
            "clock": time.time() if clock is None else clock}


def _verdict(cases: list, called: list[str], extra: dict | None = None) -> dict:
    """`extra` sono i conti di contorno, con le chiavi che il rapporto mostra."""
    return {"disaccordi": len(cases), "casi": cases[:CASES_KEPT], "chiamate": called,
            **(extra or {})}


def _entities(inputs: dict) -> dict[str, dict]:
    return {entity["id"]: entity for entity in inputs["home_space"]["entita"]}


def _entity_ids(lines: list[str], inputs: dict, where: str) -> list[str]:
    """Gli id in testa alle righe di `where`, verificati contro l'anagrafe.

    Una riga il cui primo campo non e' un'entita' vuol dire che la forma della
    riga e' cambiata: la domanda si FERMA. Proseguire darebbe «zero disaccordi»
    perche' non si confronta piu' niente -- parita' raggiunta, e falsa.
    """
    known = {entity["id"] for entity in inputs["home_space"]["entita"]}
    read = [line.split(LINE_SEPARATOR)[0] for line in lines]
    strangers = [key for key in read if key not in known]
    if strangers:
        raise ValueError(f"{where}: {len(strangers)} righe non cominciano con un id di "
                         "entita'. La forma della riga e' cambiata, la sonda va riletta.")
    return read


def _mirror_keywords(mirror) -> dict:
    return {"fallback_names": mirror[1], "reported_units": mirror[2],
            "reported_classes": mirror[3], "reported_since_when": mirror[4],
            "reported_attributes": mirror[5]}


# ── le domande ──────────────────────────────────────────────────────────────

def excluded(inputs: dict) -> dict:
    """«E' fuori?» -- chi include un'entita' che un'altra copia esclude.

    Quattro copie dichiarano la STESSA regola (digesto, complemento di
    `_excluded_from_comparison`, `search` senza opzioni, osservatore): ogni
    entita' su cui due di loro non concordano e' un disaccordo. In piu' il
    caso misurato: le righe che la ricetta manda al modello e che
    l'osservatore non guarda.
    """
    home_space, mirror, entities = inputs["home_space"], inputs["mirror"], _entities(inputs)
    selection = house_query.select_subjects(
        house_query.HouseFilters(), ("entita",), home_space, [], mirror,
        unavailable=(), now=inputs["clock"])
    copies = {
        "digest_visible_entity_ids": set(briefing.digest_visible_entity_ids(home_space)),
        "not _excluded_from_comparison": {
            key for key, entity in entities.items()
            if not topology._excluded_from_comparison(entity)},
        "select_subjects": {entry["id"] for entry, _area, _where in selection.entities},
        "observer.house_lines": set(_entity_ids(
            observer.house_lines(home_space), inputs, "observer.house_lines")),
    }
    names = sorted(copies)
    cases = []
    for position, first in enumerate(names):
        for second in names[position + 1:]:
            for key in sorted(copies[first] ^ copies[second]):
                cases.append({"id": key, "solo_in": first if key in copies[first] else second,
                              "non_in": second if key in copies[first] else first})
    recipe_lines: set[str] = set()
    for device in home_space["dispositivi"]:
        recipe_lines |= set(_entity_ids(
            recipe_turn.device_lines(home_space, device["id"]), inputs,
            "recipe_turn.device_lines"))
    for key in sorted(recipe_lines - copies["observer.house_lines"]):
        cases.append({"id": key, "solo_in": "recipe_turn.device_lines",
                      "non_in": "observer.house_lines"})
    return _verdict(cases, names + ["recipe_turn.device_lines"],
                    {"incluse": {name: len(members) for name, members in copies.items()},
                     "righe_della_ricetta": len(recipe_lines)})


def names(inputs: dict) -> dict:
    """«Come si chiama?» -- il nome della scheda contro il nome della riga di
    `search`, per la stessa entita'."""
    home_space, mirror = inputs["home_space"], inputs["mirror"]
    state, live_names = mirror[0], mirror[1]
    where = {entry["id"]: (entry, area, place)
             for entry, area, _floor, place in house_query._entity_entries(home_space, ())}
    cases = []
    for key, entity in _entities(inputs).items():
        detail = queries._enrich_entity(
            {"id": key, "nome": entity.get("nome"), "stato": state.get(key)},
            entity, live_names)
        card = (detail.get("nome") or "").strip() or (detail.get("nome_dedotto") or "").strip()
        entry, area, place = where[key]
        row = house_query._entity_row(entry, area, place, mirror, False)["nome"]
        if card != row:
            cases.append({"id": key, "scheda": card, "riga": row})
    return _verdict(cases, ["queries._enrich_entity", "house_query._entity_row"],
                    {"entita": len(where)})


def areas(inputs: dict) -> dict:
    """«In che area sta?» -- l'area che l'osservatore emette contro
    `topology.actual_area`, sulle entita' che l'osservatore guarda.

    I nomi delle aree sono sostituiti in copia da un marcatore, per leggere
    QUALE area la riga porta: la funzione chiamata e' la stessa.
    """
    home_space = inputs["home_space"]
    device_area = topology.device_areas(home_space["dispositivi"])
    marked = dict(home_space)
    marked["aree"] = [dict(area, nome=f"@@{area['id']}@@") for area in home_space["aree"]]
    emitted: dict[str, str | None] = {}
    lines = observer.house_lines(marked)
    for key, line in zip(_entity_ids(lines, inputs, "observer.house_lines"), lines,
                         strict=True):
        parts = line.split(LINE_SEPARATOR)
        marks = [part for part in parts[1:] if part.startswith("@@") and part.endswith("@@")]
        emitted[key] = marks[0][2:-2] if marks else None
    cases = []
    for key, entity in _entities(inputs).items():
        if key not in emitted:
            continue
        actual = topology.actual_area(entity, device_area)
        if emitted[key] != actual:
            cases.append({"id": key, "area_vera": actual, "area_emessa": emitted[key]})
    return _verdict(cases, ["topology.actual_area", "observer.house_lines"],
                    {"guardate": len(emitted)})


def values(inputs: dict) -> dict:
    """«E' un valore?» -- le entita' che `briefing._unreliable_state` legge
    come valore e il vocabolario (`unknown_states`) come non-valore.

    La copia del nucleo non e' chiamabile per una entita' sola: risponde per
    la casa intera («non ho letto niente»). La si chiama quindi su una casa
    di UNA entita' -- la funzione vera, non la sua riga riscritta qui: una
    prima versione ricopiava il confronto col letterale, e avrebbe continuato
    a dire 287 anche dopo che il prodotto fosse stato corretto.

    Divergenza di REGOLA: sull'esito della funzione pesa solo quando ogni
    entita' e' in quello stato (dopo la caduta di tutte le integrazioni).
    """
    home_space, state = inputs["home_space"], inputs["mirror"][0]
    unknown = type_vocabulary.unknown_states()
    cases = []
    for entity in home_space["entita"]:
        current = state.get(entity["id"])
        if entity.get("disabilitata") or current is None:
            continue
        alone = {**home_space, "entita": [entity]}
        read_by_briefing = not briefing._unreliable_state(
            alone, {entity["id"]: current}, True, ())
        read_by_vocabulary = current not in unknown
        if read_by_briefing != read_by_vocabulary:
            cases.append({"id": entity["id"], "stato": current})
    return _verdict(cases, ["type_vocabulary.unknown_states", "briefing._unreliable_state"],
                    {"esito_sulla_casa": briefing._unreliable_state(home_space, state, True, ())})


class _AlwaysWatching:
    """L'archivio dell'osservatore, ridotto a cio' che `watch_reading` chiede."""

    def is_watched(self, subject):
        return True

    def record(self, **_):
        return None

    def scope(self):
        return {}


def statistics(inputs: dict) -> dict:
    """«Ha statistiche?» -- tre risposte per entita': la regola sul
    `state_class`, cio' che il watcher crede coperto, cio' che Home Assistant
    tiene davvero."""
    watcher = Watcher(_AlwaysWatching(), now=lambda: inputs["clock"])
    truth = inputs["statistic_ids"]
    cases = []
    examined = 0
    for raw in inputs["raw_states"]:
        key = raw["entity_id"]
        attributes = raw.get("attributes") or {}
        state_class = attributes.get("state_class")
        if not (key.startswith("sensor.") or state_class or key in truth):
            continue
        examined += 1
        reading = {"state": "1", "attributes": dict(attributes),
                   "last_updated": "2026-10-01T10:00:00+00:00",
                   "last_changed": "2026-10-01T10:00:00+00:00"}
        event = {"entity_id": key, "new_state": reading,
                 "old_state": {"state": "0", "attributes": dict(attributes)}}
        answers = {"regola": ha_vocabulary.produces_statistics(state_class),
                   "watcher": not watcher.watch_reading(event),
                   "home_assistant": key in truth}
        if len(set(answers.values())) > 1:
            cases.append({"id": key, "state_class": state_class, **answers})
    return _verdict(cases, ["ha_vocabulary.produces_statistics", "Watcher.watch_reading"],
                    {"esaminate": examined})


def units(inputs: dict) -> dict:
    """«Che unita' e classe ha?» -- anagrafe, specchio vivo, riga di `search`."""
    home_space, mirror = inputs["home_space"], inputs["mirror"]
    live_units, live_classes = mirror[2], mirror[3]
    cases = []
    for entry, area, _floor, place in house_query._entity_entries(home_space, ()):
        key = entry["id"]
        row = house_query._entity_row(entry, area, place, mirror, True)
        unit = {entry.get("unita") or None, live_units.get(key) or None,
                row.get("unita") or None}
        kind = {entry.get("classe") or None, live_classes.get(key) or None,
                row.get("classe") or None}
        if len(unit) > 1 or len(kind) > 1:
            cases.append({"id": key, "unita": sorted(map(str, unit)),
                          "classe": sorted(map(str, kind))})
    return _verdict(cases, ["reader.build_home_space", "topology.live_mirror",
                            "house_query._entity_row"])


def _selected(inputs: dict, **filters) -> set[str]:
    selection = house_query.select_subjects(
        house_query.HouseFilters(include_hidden=True, include_service=True, **filters),
        ("entita",), inputs["home_space"], [], inputs["mirror"], unavailable=(),
        now=inputs["clock"])
    return {entry["id"] for entry, _area, _where in selection.entities}


def references(inputs: dict) -> dict:
    """I riferimenti scritti come li scrive una persona: maiuscole e spazi.

    Per un'area: `search(area=)` deve dare lo stesso insieme del nome esatto.
    Per un'integrazione: `search(integrazione=)` e la scheda devono concordare
    sul fatto di trovarla.
    """
    home_space, mirror = inputs["home_space"], inputs["mirror"]
    cases = []
    for area in home_space["aree"]:
        exact = _selected(inputs, area=area["nome"])
        if not exact:
            continue
        for label, text in (("minuscolo", area["nome"].lower()),
                            ("maiuscolo", area["nome"].upper()),
                            ("spazio in coda", area["nome"] + " ")):
            if _selected(inputs, area=text) != exact:
                cases.append({"genere": "area", "id": area["id"], "variante": label})
    platforms = sorted({entity["piattaforma"] for entity in home_space["entita"]
                        if entity.get("piattaforma")})
    for platform in platforms:
        for label, text in (("esatto", platform), ("capitalizzato", platform.capitalize()),
                            ("maiuscolo", platform.upper()), ("con spazi", f" {platform} ")):
            by_search = bool(_selected(inputs, platform=text))
            by_card = bool(queries.view(home_space, [], [], mirror[0], "integrazione", text,
                                        **_mirror_keywords(mirror)).get("esiste"))
            if by_search != by_card:
                cases.append({"genere": "integrazione", "id": platform, "variante": label,
                              "search": by_search, "scheda": by_card})
    return _verdict(cases, ["house_query.select_subjects", "queries.view"],
                    {"integrazioni": len(platforms), "aree": len(home_space["aree"])})


def today(inputs: dict, *, step_minutes: int = 10) -> dict:
    """«Oggi» -- l'etichetta di data che la chat mette alle sessioni passate,
    contro il giorno della casa, per ogni istante di un anno."""
    from hiris.app import chat_store
    from hiris.app.api import handlers_chat

    zone = historian.home_space_zone(inputs["ha_config"].get("time_zone") or "UTC")
    session: dict = {}
    replaced = (handlers_chat.get_past_summaries, handlers_chat.compose_briefing,
                handlers_chat._who_is_speaking)
    handlers_chat.get_past_summaries = lambda data_dir, *, thread, n=10: [session["row"]]
    handlers_chat.compose_briefing = lambda app: ("", {})
    handlers_chat._who_is_speaking = lambda *args, **kwargs: ""
    cases = []
    samples = 0
    try:
        instant = datetime(2026, 1, 1, tzinfo=UTC)
        while instant < datetime(2027, 1, 1, tzinfo=UTC):
            session["row"] = {"started_at": instant.strftime(chat_store._TS_FMT),
                              "summary": "x"}
            context = handlers_chat.compose_chat_context(None, "/nonexistent", thread=None,
                                                         soggetto=None)
            label = context.split("[", 1)[1].split("]", 1)[0]
            samples += 1
            if label != instant.astimezone(zone).date().isoformat():
                cases.append({"istante_utc": instant.isoformat(), "etichetta": label})
            instant += timedelta(minutes=step_minutes)
    finally:
        (handlers_chat.get_past_summaries, handlers_chat.compose_briefing,
         handlers_chat._who_is_speaking) = replaced
    return _verdict(cases, ["handlers_chat.compose_chat_context",
                            "historian.home_space_zone"], {"campioni": samples})


#: Le domande, per nome. E' un elenco di AMMISSIONE: una domanda esce di qui
#: quando la sua copia e' cancellata, nello stesso commit.
QUESTIONS = {"fuori": excluded, "nomi": names, "dove": areas, "valore": values,
             "statistiche": statistics, "unita": units, "riferimenti": references,
             "oggi": today}


def run(inputs: dict) -> dict[str, dict]:
    """Ogni domanda sugli stessi ingressi. Una domanda che solleva non ferma
    le altre: il suo verdetto porta l'errore, e conta come non eseguita."""
    result = {}
    for name, question in QUESTIONS.items():
        try:
            result[name] = question(inputs)
        except Exception as error:  # una domanda rotta si dichiara
            result[name] = {"disaccordi": None, "casi": [], "chiamate": [],
                            "errore": f"{type(error).__name__}: {error}"}
    return result


def worse_than_expected(result: dict[str, dict], expected: dict[str, int]) -> list[str]:
    """Le domande che danno PIU' disaccordi dell'atteso, o che non girano."""
    worse = []
    for name, verdict in result.items():
        found = verdict["disaccordi"]
        if found is None:
            worse.append(f"{name}: non eseguita ({verdict.get('errore')})")
        elif name not in expected:
            worse.append(f"{name}: nessun atteso scritto")
        elif found > expected[name]:
            worse.append(f"{name}: {found} disaccordi, attesi al massimo {expected[name]}")
    return worse


def _report(result: dict[str, dict], inputs: dict) -> str:
    lines = ["# Sonda di parita'", "",
             (f"Entita' in anagrafe: {len(inputs['home_space']['entita'])} · stati vivi: "
              f"{len(inputs['raw_states'])}."), ""]
    for name, verdict in result.items():
        lines += [f"## {name}", "", f"Disaccordi: **{verdict['disaccordi']}**", ""]
        extra = {key: value for key, value in verdict.items()
                 if key not in ("disaccordi", "casi", "chiamate")}
        if extra:
            lines += [json.dumps(extra, ensure_ascii=False), ""]
        lines += [f"Copie chiamate: {', '.join(verdict['chiamate'])}", ""]
        lines += [f"- {json.dumps(case, ensure_ascii=False)}" for case in verdict["casi"]]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ingressi", required=True, help="la cartella congelata da casa.py")
    parser.add_argument("--rapporto", help="dove scrivere il rapporto (porta nomi della casa)")
    parser.add_argument("--attesi", help="JSON {domanda: disaccordi attesi al massimo}")
    parser.add_argument("--cancello", action="store_true",
                        help="esce 1 se una domanda supera il suo atteso")
    args = parser.parse_args()

    inputs = build_inputs(Path(args.ingressi))
    result = run(inputs)
    for name, verdict in result.items():
        print(f"  {name:12} {verdict['disaccordi']}")
    if args.rapporto:
        casa.outside_repo(args.rapporto).write_text(_report(result, inputs),
                                                    encoding="utf-8")
    if args.cancello:
        if not args.attesi:
            raise SystemExit("sonda: --cancello vuole --attesi")
        expected = json.loads(Path(args.attesi).expanduser().read_text(encoding="utf-8"))
        worse = worse_than_expected(result, expected)
        for line in worse:
            print(f"sonda: {line}", file=sys.stderr)
        sys.exit(1 if worse else 0)


if __name__ == "__main__":
    main()
