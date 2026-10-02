#!/usr/bin/env python3
"""HIRIS cancelli — i cancelli della fonte unica, da un comando solo.

## Perche' esiste

`censimento.py` e `doppioni.py` avevano una modalita' cancello dal giorno in
cui sono nati, e non giravano da nessuna parte: ne' nel pre-push ne' nella CI
(voce M-38 del registro, spec §1.5). Una disciplina scritta non e' una
disciplina eseguita. Questo comando e' cio' che il pre-push e la CI chiamano,
ed e' UNO: se i cancelli fossero elencati in due posti -- l'hook e il
workflow -- prima o poi uno dei due ne dimenticherebbe uno.

## Cosa lancia

Tutti INSIEME, non in fila: misurati il 01/10/2026 costano 0,5 + 23,5 + 19,2 +
17,5 secondi uno dopo l'altro, e un cancello da un minuto a ogni push e' un
cancello che qualcuno prima o poi spegne. Insieme costano quanto il piu'
lento. Ognuno dice il suo esito, e basta un no per fermare il push:

1. il registro dei doppioni e' leggibile e nessuna voce e' chiusa a meta';
2. nessun doppione nuovo fra quelli che `doppioni.py` sa vedere, e nessuno
   guarito rimasto nell'elenco dei noti;
3. il censimento: nessun codice morto nuovo (funzioni, rotte, opzioni,
   tabelle), nessuna regola strutturale rotta, e nessuna eccezione rimasta a
   coprire qualcosa che non c'e' piu' (`scripts/censimento_eccezioni.json`);
4. il cancello R19, che legge l'albero del codice (`tests/test_fonte_unica.py`),
   con le prove del registro.

Uso:
  python scripts/cancelli.py
"""
from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAIL_LINES = 25

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: (nome, comando). L'ordine e' quello del docstring, ed e' quello del rapporto.
GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("registro", ("scripts/registro.py", "verifica")),
    ("doppioni", ("scripts/doppioni.py", "--cancello", "--noti",
                  "scripts/doppioni_noti.json")),
    ("censimento", ("scripts/censimento.py", "--cancello")),
    ("fonte unica", ("-m", "pytest", "-q", "-p", "no:cacheprovider",
                     "tests/test_fonte_unica.py", "tests/test_registro.py")),
)


def run(gates=GATES, *, launch=subprocess.run) -> int:
    """Lancia i cancelli insieme. Torna 0 se passano tutti, 1 se anche uno
    solo ferma -- nominando ognuno che ha fermato, col comando per rivederlo."""
    def one(gate):
        _name, arguments = gate
        return launch((sys.executable, *arguments), cwd=ROOT, capture_output=True,
                      text=True, encoding="utf-8", errors="replace")

    with ThreadPoolExecutor(max_workers=len(gates)) as pool:
        outcomes = list(pool.map(one, gates))
    stopped = 0
    for (name, arguments), outcome in zip(gates, outcomes, strict=True):
        if outcome.returncode == 0:
            print(f"cancelli: {name} passa")
            continue
        stopped += 1
        lines = (outcome.stdout + outcome.stderr).strip().splitlines()
        for line in lines[-TAIL_LINES:]:
            print(line)
        print()
        print(f"cancelli: FERMATO da «{name}».")
        print(f"          Per rivederlo:  python {' '.join(arguments)}")
    return 1 if stopped else 0


if __name__ == "__main__":
    sys.exit(run())
