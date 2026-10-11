#!/usr/bin/env python3
"""HIRIS batteria degli attori — i loro numeri, letti e non innescati.

## Perche' esiste

L'audit del 01/10/2026 ha guardato a mano cosa fanno osservatore, analista e
attuatore sulla casa vera. Lo sprint «Una fonte sola di verita'» chiede che
quell'audit sia RIPETIBILE (spec §5, garanzia 6): prima e dopo ogni tappa, gli
stessi numeri, calcolati allo stesso modo.

## Legge, non innesca

Questa batteria non fa partire nessun turno: gli attori girano da soli, e qui
si leggono i turni che hanno fatto. E' una scelta (decisione D13 del piano
della Tappa 0): innescarli vorrebbe dire scrivere negli archivi di HIRIS, e la
regola verso la casa e' «solo letture».

- `GET /api/misure` -- i turni e i loro carichi: token, tempi, esiti;
- `GET /api/mind/watching` -- cosa l'osservatore guarda;
- `GET /api/mind/report` -- i resoconti, con le misure non calcolabili;
- gli stati vivi di Home Assistant -- per sapere quali soggetti guardati non
  esistono piu'.

## Le cause (piano degli strati 1-2 degli attori, Task 1.7)

Le misure non calcolabili si contano anche **per causa**, dal campo `causa`
della riga quando c'e' (Task 1.2): prima, tutto finisce sotto «senza causa»,
ed e' il numero che lo strato 1 deve portare a zero. Le misure «ferme» sono i
rifiuti con la causa del dato fermo.

I soggetti morti (guardati, e senza uno stato in Home Assistant) si dividono
in **marcati e non marcati** (Task 1.5): marcato e' chi porta la `fonte` che
la pagina dell'osservatore chiede a `House.source`. Si contano anche per
stato della fonte (`fonte.stato`); `fonte: None` -- ne' registro ne' stati lo
conoscono -- ha un'etichetta sua, `NOT_IN_HA`. Il criterio di chiusura dello
strato 1 e' «non marcati = 0».

## Cosa NON misura, dichiarato

- **Il giudizio sulle osservazioni** («vera, banale, artefatto»): l'ha dato
  una persona leggendo, e resta a mano.
## La troncatura (Tappa 6, Task 3; D-58)

Dal 05/10/2026 il registro dei turni scrive l'esito `troncato`
(`steering.TRUNCATED`), letto da cio' che il provider ha dichiarato: un turno
si conta troncato da QUEL campo, col tetto proprio di ogni mestiere -- quale
fosse il tetto non conta piu'. I turni registrati PRIMA non hanno quell'esito
(si dicevano «riusciti»): per loro resta la regola di prima, l'uscita
ESATTAMENTE uguale al tetto di chi non ne dichiara uno
(`claude_runner.MAX_TOKENS`). E' la regola che ha misurato i 7 su 8
dell'analista, e serve a confrontare il dopo con quel prima. Un troncato non
e' un fallito: le due colonne non si sommano.

## L'analista (piano degli attori, strati 3-4, Task 3.8)

I criteri di chiusura dello strato 3 si leggono qui, sotto `analista`:

- **osservazioni con letture**: le analisi archiviate (`GET
  /api/mind/analysis`) portano `letture`, le chiamate di strumento del turno
  prese dal registro del runner (Task 3.5). Il turno non dice quale lettura
  e' servita a quale osservazione, quindi un'osservazione «ha letture» quando
  le ha la sua analisi. Gli strumenti si contano per nome, senza gli
  ingressi;
- **ripetizioni per impronta e prova**: per ogni giorno della finestra, la
  memoria e' cio' che le analisi PRECEDENTI hanno detto, e il giudizio e'
  quello del prodotto (`analyst.previous_observations`, `analyst.novelty`):
  la regola dell'impronta e della prova non si ricopia qui. «stessa prova» e'
  l'etichetta della batteria per il `None` di `novelty`: il prodotto toglie
  quelle osservazioni prima di archiviare, e il numero che deve restare zero
  e' proprio questo. La memoria arriva fin dove arriva la rotta (le ultime
  `RECENT_DAYS` analisi): per i giorni piu' vecchi della finestra e' piu'
  corta di quella che il giro aveva;
- **risposte rifiutate per motivo**: le righe `scartato` del registro dei
  turni (D10) portano i `problems` della risposta. Il prodotto non da' un
  codice del motivo, solo la frase, e la frase porta i numeri e le parti
  citate di quella risposta: si conta la sua **forma** -- numeri, «citazioni»,
  [parentesi] e {parentesi} coperti -- non il testo;
- **troncati col tetto proprio**: dal 05/10/2026 il troncato e' l'esito
  `troncato`, scritto col tetto che il turno ha dichiarato. La riga porta
  accanto, in `tetto`, il tetto che il mestiere dichiara OGGI
  (`analyst_turn.MAX_ANSWER_TOKENS` per l'analista; gli altri il tetto di
  fabbrica). La regola dei turni registrati PRIMA di quell'esito resta quella
  del paragrafo sopra, col tetto di fabbrica: e' il tetto con cui quei turni
  hanno girato (il tetto dichiarato dell'analista nasce in b76b44d0, dopo
  l'esito). Usare il tetto di oggi farebbe sparire il «prima» il giorno in
  cui il tetto si alza (rilievo G49-1 del revisore, 06/10/2026).

Le specie si chiedono a `steering.SPECIE`: una riga del registro con un nome
che il registro non conosce piu' (l'«attuatore» archiviato prima del 06/10)
si conta, e il suo nome esce in `specie_fuori_registro`.

Uso:
  HIRIS_URL=http://casa:8099 HIRIS_HOUSE_URL=http://casa:8123 \\
      python scripts/batteria_attori.py --giorni 1 --esiti attori.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Un soggetto che e' un'entita': `dominio.oggetto`. Gli altri (`log:...`,
#: `integrazione:...`) non hanno uno stato in Home Assistant da cercare.
_ENTITY_SUBJECT = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
#: Gli esiti del turno e i nomi dei mestieri: si CHIEDONO al prodotto, che li
#: scrive (`steering.misura_turno`, `steering.declare_refused`). La batteria e'
#: un attrezzo e puo' importarli, come fa gia' con `MAX_TOKENS`. Fino al
#: 06/10/2026 «riuscito» era una copia scritta qui.
from hiris.app.mind import analyst
from hiris.app.steering import ANALYST_SPECIES, REFUSED, SPECIE, SUCCEEDED, TRUNCATED

#: L'etichetta di chi non porta una causa. E' della batteria, non del prodotto:
#: il prodotto non ha una causa che si chiami cosi'.
UNCAUSED = "senza causa"
#: La causa del dato fermo si CHIEDE al vocabolario delle cause del prodotto
#: (`mind.operations`, Task 1.2 e 1.3): fino al 06/10/2026 era una copia
#: scritta qui, nata quando quel vocabolario non c'era ancora (Task 1.7,
#: passo 2).
from hiris.app.mind.operations import FROZEN

#: L'etichetta di un soggetto marcato con `fonte: None` (`House.source` non lo
#: trova ne' nel registro ne' negli stati). Della batteria, non del prodotto:
#: il vocabolario della fonte non ha una parola per lui (domanda del Task 1.5).
NOT_IN_HA = "ne' nel registro ne' negli stati"

#: L'etichetta di un'osservazione gia' detta con la stessa prova: e' il `None`
#: di `analyst.novelty`, che nel vocabolario del prodotto (`analyst.NOVELTY`)
#: non ha una parola perche' il prodotto la toglie. Della batteria.
SAME_EVIDENCE = "stessa prova"

#: Cio' che si copre nella frase di un rifiuto per averne la forma: le parti
#: citate e le parentesi (dove la frase mette la risposta del modello o un
#: elenco), poi i numeri. L'ordine conta: dentro una citazione i numeri
#: spariscono con lei.
_QUOTED = (("«…»", re.compile(r"«[^»]*»")), ("[…]", re.compile(r"\[[^\]]*\]")),
           ("{…}", re.compile(r"\{[^}]*\}")), ("N", re.compile(r"\d+")))


def _by_cause(rows) -> dict[str, int]:
    """Quante righe per causa; una causa assente o vuota e' «senza causa»."""
    return dict(Counter(str(row.get("causa") or "") or UNCAUSED for row in rows))


def _by_source(rows) -> dict[str, int]:
    """Quanti soggetti per stato della fonte: «senza causa» chi non porta la
    `fonte` (non marcato), `NOT_IN_HA` chi la porta vuota."""
    def _label(row) -> str:
        if "fonte" not in row:
            return UNCAUSED
        source = row["fonte"]
        if source is None:
            return NOT_IN_HA
        return str(source.get("stato") or "") or UNCAUSED
    return dict(Counter(_label(row) for row in rows))


def _shape(problem) -> str:
    """La forma della frase di un rifiuto: le parti di QUELLA risposta coperte."""
    text = str(problem)
    for mask, pattern in _QUOTED:
        text = pattern.sub(mask, text)
    return text


def _truncated(turn: dict, ceiling: int) -> bool:
    """Un turno troncato: dall'esito, o -- per i turni registrati prima che
    l'esito esistesse -- dall'uscita ESATTAMENTE uguale al tetto."""
    outcome = turn.get("outcome")
    return (outcome == TRUNCATED
            or (outcome == SUCCEEDED and turn.get("output_tokens") == ceiling))


def _analyst(data: list, analyses: list[dict], since_day: str) -> dict:
    """I conti dell'analista che non stanno nella sua riga di `attori`."""
    reasons = Counter(_shape(problem)
                      for turn, _loads in data
                      if turn.get("species") == ANALYST_SPECIES
                      and turn.get("outcome") == REFUSED
                      for problem in (turn.get("problems") or [UNCAUSED]))
    ordered = sorted(analyses, key=lambda a: str(a.get("giorno") or ""))
    window = [a for a in ordered if str(a.get("giorno") or "") >= since_day]
    novelty: Counter = Counter()
    written: Counter = Counter()
    observations = with_readings = 0
    tools: Counter = Counter()
    for analysis in window:
        day = str(analysis.get("giorno") or "")
        seen = [o for o in analysis.get("osservazioni") or [] if isinstance(o, dict)]
        readings = [r for r in analysis.get("letture") or [] if isinstance(r, dict)]
        observations += len(seen)
        with_readings += len(seen) if readings else 0
        tools.update(str(r.get("tool")) for r in readings)
        previous = analyst.previous_observations(
            [a for a in ordered if str(a.get("giorno") or "") < day], [], today=day)
        for observation in seen:
            novelty[analyst.novelty(observation, previous) or SAME_EVIDENCE] += 1
            written[str(observation.get("novita") or UNCAUSED)] += 1
    return {
        "analisi": len(window),
        "osservazioni": observations,
        "osservazioni_con_letture": with_readings,
        "analisi_con_letture": sum(1 for a in window if a.get("letture")),
        "letture_per_strumento": dict(tools),
        "osservazioni_per_novita": dict(novelty),
        "novita_scritta_dal_prodotto": dict(written),
        "rifiuti_per_motivo": dict(reasons),
    }


def measure(*, data: list, watching: list[dict], reports: list[dict],
            live_ids: set[str], output_ceiling: int,
            ceilings: dict[str, int] | None = None,
            analyses: list[dict] | None = None, since_day: str = "") -> dict:
    """I numeri della batteria. `data` e' cio' che `misure._leggi_remoto`
    restituisce: una coppia (turno, carichi) per turno.

    `ceilings` sono i tetti propri dei mestieri che ne dichiarano uno, da
    portare accanto ai troncati (gli altri portano `output_ceiling`, che e'
    anche il tetto della regola dei turni di prima); `analyses` le analisi archiviate,
    contate dal giorno `since_day` (`AAAA-MM-GG`) in poi."""
    actors: dict[str, dict] = {}
    durations: dict[str, list[float]] = {}
    for turn, loads in data:
        species = turn.get("species") or "(senza specie)"
        ceiling = (ceilings or {}).get(species, output_ceiling)
        row = actors.setdefault(species, {
            "turni": 0, "giri": 0, "token_ingresso": 0, "token_uscita": 0,
            "troncati": 0, "tetto": ceiling, "rifiutati": 0, "falliti": 0,
            "giri_senza_token": 0})
        row["turni"] += 1
        row["giri"] += len(loads)
        row["token_uscita"] += turn.get("output_tokens") or 0
        outcome = turn.get("outcome")
        # La regola di prima col tetto di allora, quello di fabbrica (G49-1).
        row["troncati"] += 1 if _truncated(turn, output_ceiling) else 0
        row["rifiutati"] += 1 if outcome == REFUSED else 0
        row["falliti"] += 0 if outcome in (SUCCEEDED, TRUNCATED, REFUSED) else 1
        durations.setdefault(species, []).append((turn.get("duration_ms") or 0) / 1000)
        for load in loads:
            if load.get("input_tokens") is None:
                row["giri_senza_token"] += 1
                continue
            row["token_ingresso"] += (load["input_tokens"]
                                      + (load.get("cache_read_tokens") or 0)
                                      + (load.get("cache_write_tokens") or 0))
    for species, row in actors.items():
        row["secondi_mediani"] = round(statistics.median(durations[species]), 1)
        measured = row["giri"] - row["giri_senza_token"]
        row["token_ingresso_per_giro"] = (round(row["token_ingresso"] / measured)
                                          if measured else None)

    subjects = [row.get("soggetto") or "" for row in watching]
    entities = [subject for subject in subjects if _ENTITY_SUBJECT.match(subject)]
    dead = [row for row in watching
            if _ENTITY_SUBJECT.match(row.get("soggetto") or "")
            and row.get("soggetto") not in live_ids]
    ordered = sorted(reports, key=lambda report: report.get("giorno") or "")
    uncomputable = [sum(1 for item in report.get("misure") or []
                        if item.get("non_calcolabile")) for report in ordered]
    refusals = _by_cause(item for report in ordered
                         for item in report.get("misure") or []
                         if item.get("non_calcolabile"))
    result = {
        "turni_letti": len(data),
        "attori": actors,
        "soggetti_guardati": len(subjects),
        "soggetti_entita": len(entities),
        "soggetti_morti": len(dead),
        "soggetti_morti_marcati": sum(1 for row in dead if "fonte" in row),
        "soggetti_morti_non_marcati": sum(1 for row in dead if "fonte" not in row),
        "soggetti_morti_per_causa": _by_source(dead),
        "resoconti": len(ordered),
        "misure_totali": sum(len(report.get("misure") or []) for report in ordered),
        "misure_non_calcolabili": sum(uncomputable),
        "misure_non_calcolabili_per_causa": refusals,
        "misure_ferme": refusals.get(FROZEN, 0),
        "specie_fuori_registro": sorted(set(actors) - SPECIE),
        "analista": _analyst(data, analyses or [], since_day),
    }
    if ordered:
        result["ultimo_giorno"] = {"giorno": ordered[-1].get("giorno"),
                                   "misure": len(ordered[-1].get("misure") or []),
                                   "non_calcolabili": uncomputable[-1]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--giorni", type=int, default=1)
    parser.add_argument("--esiti", help="dove salvare i numeri (solo numeri)")
    args = parser.parse_args()

    import casa
    import misure

    from hiris.app.claude_runner import MAX_TOKENS
    from hiris.app.mind.analyst_turn import MAX_ANSWER_TOKENS

    # Una porta sola verso la casa: anche i turni passano da `casa.hiris_get`.
    data = misure.turns_with_loads(
        json.loads(casa.hiris_get(f"/api/misure?giorni={int(args.giorni)}")))
    watching = json.loads(casa.hiris_get("/api/mind/watching")).get("watching") or []
    reports = json.loads(casa.hiris_get("/api/mind/report")).get("resoconti") or []
    analyses = json.loads(casa.hiris_get("/api/mind/analysis")).get("analisi") or []
    states = asyncio.run(casa.ha_read("get_states", []))
    # La finestra in giorni di calendario, col fuso di chi la lancia (il PC di
    # casa, lo stesso della casa): `--giorni 1` e' oggi.
    today = datetime.now().astimezone().date()
    since = today - timedelta(days=max(1, int(args.giorni)) - 1)
    result = measure(data=data, watching=watching, reports=reports,
                     live_ids={row["entity_id"] for row in states},
                     output_ceiling=MAX_TOKENS,
                     ceilings={ANALYST_SPECIES: MAX_ANSWER_TOKENS},
                     analyses=analyses, since_day=since.isoformat())
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not result["turni_letti"]:
        print("batteria: nessun turno nella finestra. Non sono zeri: non c'e' "
              "niente da misurare.", file=sys.stderr)
    if args.esiti:
        casa.outside_repo(args.esiti).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
