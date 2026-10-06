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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Un soggetto che e' un'entita': `dominio.oggetto`. Gli altri (`log:...`,
#: `integrazione:...`) non hanno uno stato in Home Assistant da cercare.
_ENTITY_SUBJECT = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
SUCCEEDED = "riuscito"
#: L'esito del turno troncato: si CHIEDE al prodotto, che lo scrive
#: (`steering.misura_turno`). La batteria e' un attrezzo e puo' importarlo,
#: come fa gia' con `MAX_TOKENS`.
from hiris.app.steering import TRUNCATED

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


def measure(*, data: list, watching: list[dict], reports: list[dict],
            live_ids: set[str], output_ceiling: int) -> dict:
    """I numeri della batteria. `data` e' cio' che `misure._leggi_remoto`
    restituisce: una coppia (turno, carichi) per turno."""
    actors: dict[str, dict] = {}
    durations: dict[str, list[float]] = {}
    for turn, loads in data:
        species = turn.get("species") or "(senza specie)"
        row = actors.setdefault(species, {
            "turni": 0, "giri": 0, "token_ingresso": 0, "token_uscita": 0,
            "troncati": 0, "falliti": 0, "giri_senza_token": 0})
        row["turni"] += 1
        row["giri"] += len(loads)
        row["token_uscita"] += turn.get("output_tokens") or 0
        outcome = turn.get("outcome")
        truncated = (outcome == TRUNCATED
                     or (outcome == SUCCEEDED
                         and turn.get("output_tokens") == output_ceiling))
        row["troncati"] += 1 if truncated else 0
        row["falliti"] += 0 if outcome in (SUCCEEDED, TRUNCATED) else 1
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

    # Una porta sola verso la casa: anche i turni passano da `casa.hiris_get`.
    data = misure.turns_with_loads(
        json.loads(casa.hiris_get(f"/api/misure?giorni={int(args.giorni)}")))
    watching = json.loads(casa.hiris_get("/api/mind/watching")).get("watching") or []
    reports = json.loads(casa.hiris_get("/api/mind/report")).get("resoconti") or []
    states = asyncio.run(casa.ha_read("get_states", []))
    result = measure(data=data, watching=watching, reports=reports,
                     live_ids={row["entity_id"] for row in states},
                     output_ceiling=MAX_TOKENS)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not result["turni_letti"]:
        print("batteria: nessun turno nella finestra. Non sono zeri: non c'e' "
              "niente da misurare.", file=sys.stderr)
    if args.esiti:
        casa.outside_repo(args.esiti).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
