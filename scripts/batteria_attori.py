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

I soggetti morti e le misure non calcolabili si contano anche **per causa**,
dal campo `causa` della riga quando c'e'. Il campo nasce col Task 1.2 (le
misure) e col Task 1.5 (i soggetti): prima, tutto finisce sotto «senza causa»,
ed e' il numero che lo strato 1 deve portare a zero. Le misure «ferme» sono i
rifiuti con la causa del dato fermo.

## Cosa NON misura, dichiarato

- **Il giudizio sulle osservazioni** («vera, banale, artefatto»): l'ha dato
  una persona leggendo, e resta a mano.
- **La troncatura vera**: i turni non registrano perche' si sono fermati. Si
  conta troncato un turno la cui uscita e' ESATTAMENTE il tetto di chi non ne
  dichiara uno (`claude_runner.MAX_TOKENS`). Un attore col tetto suo non e'
  visto: e' la voce D-58 del registro, e si chiude alla Tappa 6.

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
#: L'etichetta di chi non porta una causa. E' della batteria, non del prodotto:
#: il prodotto non ha una causa che si chiami cosi'.
UNCAUSED = "senza causa"
#: La causa del dato fermo. Vive nel prodotto, nella regola del dato fermo (il
#: suo `FROZEN`, Task 1.1, su un ramo non ancora unito): finche' il vocabolario
#: non c'e', e' scritta qui. Il Task 1.7, passo 2, la CHIEDE al vocabolario e
#: toglie questa copia.
FROZEN = "ferma"


def _by_cause(rows) -> dict[str, int]:
    """Quante righe per causa; una causa assente o vuota e' «senza causa»."""
    return dict(Counter(str(row.get("causa") or "") or UNCAUSED for row in rows))


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
        row["troncati"] += 1 if turn.get("output_tokens") == output_ceiling else 0
        row["falliti"] += 0 if turn.get("outcome") == SUCCEEDED else 1
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
        "soggetti_morti_per_causa": _by_cause(dead),
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
