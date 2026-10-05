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

`valore` confrontava `briefing._unreliable_state` col vocabolario
(`unknown_states`): e' uscita col Task 8 della Tappa 3 (04/10/2026, B-08),
quando il nucleo ha smesso di contare il solo `unknown` (e in minuscolo) e
chiede al vocabolario. Sui congelati del 03/10 contava 145; dopo, 0.

## Le domande della Tappa 3

Entrate prima del codice che le chiude (piano della Tappa 3, Task 1):
`fonte` chiede a tre porte perche' una fonte tace, e confronta la loro
risposta con i fatti del registro (B-25, B-26, B-04). `fuori_con_causa`
chiedeva la classe del fuori alle SEI copie della regola (B-01): e' uscita
col Task 5 (04/10/2026), quando le sei copie sono diventate
`topology.visibility` -- ora la sorveglia il cancello `regola-del-fuori`
(`tests/test_fonte_unica.py`). `fuori`, `nomi` e `dove`
sono uscite col Task 12 (04/10/2026), quando l'osservatore e le ricette hanno
smesso di scorrere l'anagrafe e chiedono alla casa chi guardare
(`House.visible_entities`, `House.entities_of`), come si chiama (`House.name`)
e dove sta (`House.where`). Sulla casa sintetica, prima di toglierle:
`fuori` e `dove` 0 disaccordi; `nomi` contava 8 perche' il suo marcatore sul
nome del registro non compare piu' in nessuna riga -- confrontata a mano la
riga con `House.name`, 0 su 8. La sorveglianza passa al cancello
`tests/test_attori_compongono.py`. `unita` confrontava l'anagrafe, lo
specchio e la riga di `search`: e' uscita col Task 7 (B-17, 04/10/2026), quando
l'anagrafe ha smesso di congelare classe e unita' e `search` le chiede con la
regola di `House.kind_of` (`topology.live_first`). `statistiche` confrontava la
regola sullo `state_class`, il watcher e l'elenco di Home Assistant: e' uscita
con B-12 (04/10/2026), quando il watcher e la casa hanno smesso di avere una
formula loro e chiedono `ha_vocabulary.has_statistics` (l'elenco, e la regola
del sorgente solo come ripiego).

Nasce da `docs/superpowers/audit-2026-10-01/sonda_parita.py` (01/10/2026).

Uso:
  python scripts/sonda_parita.py --ingressi ~/.hiris-sprint/ingressi/2026-10-01
  python scripts/sonda_parita.py --ingressi <cartella> --rapporto sonda.md
  python scripts/sonda_parita.py --ingressi <cartella> --cancello --attesi attesi.json
"""
from __future__ import annotations

import argparse
import asyncio
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

from hiris.app.action.registry import ServiceRegistry
from hiris.app.action.verification import verification
from hiris.app.home_space import (
    briefing,
    ha_vocabulary,
    historian,
    house_query,
    queries,
    reader,
    topology,
)
from hiris.app.home_space.house import House
from hiris.app.mind.recipes import ENTITY_MARK, Recipe, silent_entities
from hiris.app.proxy.entity_cache import _to_minimal

#: Le parole con cui due porte dicono la causa di una fonte muta. **Sono
#: copie, dichiarate**: la causa la porta `House.source`, ma alle porte arriva
#: come testo. Se il testo cambia, `fonte` non vede piu' la pretesa e conta
#: zero: chi cambia quel testo rilegge la domanda (riletta il 04/10/2026, Tappa
#: 3, Task 8: `verification` nega l'esistenza solo di cio' che la casa non
#: conosce; il motivo delle ricette incolpa lo `state_class` con questa frase,
#: in `recipes.silence`).
DENIES_EXISTENCE = "non esiste"
BLAMES_STATE_CLASS = "non dichiara uno `state_class`"
CASES_KEPT = 40


def build_inputs(source: Path | dict, *, clock: float | None = None) -> dict:
    """L'anagrafe e lo specchio, montati come li monta il prodotto.

    `source` e' la cartella degli ingressi congelati, oppure un dizionario con
    le stesse chiavi (le prove passano la casa sintetica). Lo specchio passa da
    `_to_minimal` e `live_mirror`, l'anagrafe da `reader.build_home_space`: e'
    cio' che fa `HomeSpace.rebuild()`. Le classi e le unita' vive non entrano
    nell'anagrafe dal 04/10/2026 (B-17): le dice `House.kind_of`.
    """
    raw = source if isinstance(source, dict) else casa.read_inputs(source)
    rows = [_to_minimal(row) for row in raw["states"] if row.get("entity_id")]
    mirror = topology.live_mirror(rows)
    home_space = reader.build_home_space(raw["registries"])
    return {"home_space": home_space, "mirror": mirror, "rows": rows,
            "raw_states": raw["states"], "registries": raw["registries"],
            "statistic_ids": set(raw["statistic_ids"]),
            "services": raw.get("services"),
            "behavior": raw["behavior"], "ha_config": raw["ha_config"],
            "clock": time.time() if clock is None else clock}


def _verdict(cases: list, called: list[str], extra: dict | None = None) -> dict:
    """`extra` sono i conti di contorno, con le chiavi che il rapporto mostra."""
    return {"disaccordi": len(cases), "casi": cases[:CASES_KEPT], "chiamate": called,
            **(extra or {})}


# ── le domande ──────────────────────────────────────────────────────────────

class _Services:
    """Il client, ridotto alla sola lettura che il registro dei servizi fa."""

    def __init__(self, services) -> None:
        self._services = services

    async def get_services(self):
        return self._services


def _house(inputs: dict) -> House:
    """La casa del prodotto sugli ingressi, con l'elenco delle statistiche."""
    return House(inputs["home_space"], inputs["mirror"],
                 statistic_ids=inputs["statistic_ids"])


def _verifier(inputs: dict):
    """La verifica di una chiamata (`action/verification.py`) su un'entita'
    sola, col registro dei servizi riempito dalla sua funzione vera. Il
    servizio si sceglie fra quelli del dominio universale e poi del dominio
    dell'entita': senza nessuno dei due la porta non si puo' interrogare
    (torna `None`), e la domanda lo conta."""
    if not isinstance(inputs.get("services"), list):
        raise TypeError("fonte: gli ingressi non portano i servizi, la verifica non "
                         "si puo' interrogare")
    registry = ServiceRegistry()
    failure = asyncio.run(registry.refresh(_Services(inputs["services"])))
    if failure is not None or not registry.domains():
        raise ValueError(f"fonte: il registro dei servizi non si e' riempito ({failure})")
    states = {row["id"]: row for row in inputs["rows"]}
    # La causa dalla casa, come la passa la porta (`ActionActuator`, D8).
    source = _house(inputs).source

    def verify(key: str):
        for domain in ("homeassistant", ha_vocabulary.domain_of(key)):
            names = registry.services_for(domain) if domain in registry.domains() else []
            if names:
                call = {"servizio": f"{domain}.{min(names)}",
                        "bersaglio": {"entita": [key]}}
                return verification(call, registry, states, source=source)
        return None
    return verify


def _recipe_reason(house: House, key: str) -> str:
    """Il motivo che una ricetta da' per un'entita' fuori da `statistic_ids`:
    una ricetta di un passo, eseguita con la funzione vera, col perche' che
    il resoconto le passa (`recipes.silent_entities`, come
    `server._report_ingredients`)."""
    recipe = Recipe({"why": "sonda", "steps": [
        {"name": "misura", "operation": "somma_periodo",
         "inputs": [f"{ENTITY_MARK}{key}"], "params": {"unit": "h"}}]})
    return recipe.run(series={key: []},
                      silent=silent_entities(house, [key]))["misura"].reason


def source(inputs: dict) -> dict:
    """«Perche' questa fonte tace?» -- la causa che danno tre porte, contro i
    fatti che Home Assistant scrive.

    I fatti si LEGGONO, non si deducono: `disabled_by` della riga grezza del
    registro, l'assenza dagli stati, `state_class` vivo, l'appartenenza a
    `statistic_ids`. Le porte si CHIAMANO:

    - **il digesto** dice «dentro»: e' falso per un'entita' disabilitata o
      che negli stati non c'e' (sparita);
    - **la verifica di un comando** nominato dal modello: quando dice che
      l'entita' non esiste, e' falso per ogni entita' del registro (trovato 2
      del piano, S-27);
    - **il motivo delle ricette** per le entita' fuori da `statistic_ids`:
      quando incolpa il `state_class`, e' falso per un'entita' che lo
      dichiara, che e' disabilitata o che negli stati non c'e' (B-26, X-12).

    - **la casa** (`House.source`, Tappa 3, Task 8): quando dice «viva»,
      «non disponibile» o «senza valore» di un'entita' disabilitata nel
      registro, o non dice «spenta» di una che lo e', o dice «sparita» di
      una che negli stati c'e'.

    Le entita' che stanno negli stati e non nel registro si chiedono alla
    verifica, alle ricette e alla casa; il digesto non le conosce.
    """
    registry_rows = {row["entity_id"]: row for row in inputs["registries"]["entita"]
                     if row.get("entity_id")}
    states = {row["entity_id"]: row for row in inputs["raw_states"] if row.get("entity_id")}
    statistic = inputs["statistic_ids"]
    visible = briefing.digest_visible_entity_ids(inputs["home_space"])
    verify = _verifier(inputs)
    house = _house(inputs)
    cases = []
    asked = {"digesto": 0, "verification": 0, "ricette": 0, "casa": 0}
    not_askable = 0
    for key in sorted(set(registry_rows) | set(states)):
        row, live = registry_rows.get(key), states.get(key)
        facts = {"nel_registro": row is not None,
                 "disabled_by": (row or {}).get("disabled_by"),
                 "negli_stati": live is not None,
                 "state_class": ((live or {}).get("attributes") or {}).get("state_class"),
                 "statistiche": key in statistic}
        silent_for_other_reasons = bool(facts["disabled_by"]) or not facts["negli_stati"]
        if row is not None:
            asked["digesto"] += 1
            if key in visible and silent_for_other_reasons:
                cases.append({"id": key, "porta": "digesto", "dice": "dentro",
                              "fatti": facts})
        asked["casa"] += 1
        said = (house.source(key) or {}).get("stato")
        switched_off = str(said or "").startswith("spenta_")
        if facts["disabled_by"]:
            wrong = not switched_off
        elif facts["negli_stati"]:
            wrong = switched_off or said == "sparita"
        else:
            wrong = said not in ("sparita", "integrazione_ferma")
        if wrong:
            cases.append({"id": key, "porta": "casa", "dice": said, "fatti": facts})
        verdict = verify(key)
        if verdict is None:
            not_askable += 1
        else:
            asked["verification"] += 1
            if (row is not None and not verdict.ok and key in verdict.reason
                    and DENIES_EXISTENCE in verdict.reason):
                cases.append({"id": key, "porta": "verification",
                              "dice": verdict.reason, "fatti": facts})
        if not facts["statistiche"]:
            asked["ricette"] += 1
            reason = _recipe_reason(house, key)
            if BLAMES_STATE_CLASS in reason and (facts["state_class"]
                                                 or silent_for_other_reasons):
                cases.append({"id": key, "porta": "ricette", "dice": reason,
                              "fatti": facts})
    return _verdict(cases, ["briefing.digest_visible_entity_ids",
                            "verification.verification", "Recipe.run",
                            "House.source"],
                    {"chieste": asked, "non_interrogabili_dalla_verifica": not_askable,
                     "per_porta": {port: sum(1 for case in cases if case["porta"] == port)
                                   for port in asked}})


def _selected(inputs: dict, **filters) -> set[str]:
    selection = House(inputs["home_space"], inputs["mirror"]).select(
        house_query.HouseFilters(include_hidden=True, include_service=True, **filters),
        ("entita",), [], now=inputs["clock"])
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
            by_card = bool(queries.view(House(home_space, mirror), [], [], "integrazione",
                                        text).get("esiste"))
            if by_search != by_card:
                cases.append({"genere": "integrazione", "id": platform, "variante": label,
                              "search": by_search, "scheda": by_card})
    return _verdict(cases, ["House.select", "queries.view"],
                    {"integrazioni": len(platforms), "aree": len(home_space["aree"])})


def today(inputs: dict, *, step_minutes: int = 10) -> dict:
    """«Oggi» -- l'etichetta di data che la chat mette alle sessioni passate,
    contro il giorno della casa, per ogni istante di un anno."""
    from hiris.app import chat_store
    from hiris.app.api import handlers_chat

    timezone = inputs["ha_config"].get("time_zone") or "UTC"
    zone = historian.home_space_zone(timezone)

    class _Frame:
        """L'anagrafe, per la sola domanda che la chat le fa qui: il fuso. La
        chat lo chiede a `historian.house_timezone` (Tappa 3, Task 10), che
        lo legge da `reference_frame()`."""

        def reference_frame(self):
            return {"fuso": timezone}

    session: dict = {}
    replaced = (handlers_chat.get_past_summaries, handlers_chat.compose_briefing,
                handlers_chat._who_is_speaking)
    handlers_chat.get_past_summaries = lambda data_dir, *, thread, n=10: [session["row"]]
    handlers_chat.compose_briefing = lambda app, house=None: ("", {})
    handlers_chat._who_is_speaking = lambda *args, **kwargs: ""
    cases = []
    samples = 0
    try:
        instant = datetime(2026, 1, 1, tzinfo=UTC)
        while instant < datetime(2027, 1, 1, tzinfo=UTC):
            session["row"] = {"started_at": instant.strftime(chat_store._TS_FMT),
                              "summary": "x"}
            context = handlers_chat.compose_chat_context(
                {"home_space_store": _Frame()}, "/nonexistent", thread=None, soggetto=None)
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
QUESTIONS = {"riferimenti": references, "oggi": today, "fonte": source}


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
