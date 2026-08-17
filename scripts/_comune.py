#!/usr/bin/env python3
"""Cio' che gli strumenti di lettura del progetto condividono.

Esiste per una ragione sola, ed e' la stessa che ha fatto nascere
`doppioni.py`: `censimento.py` e `doppioni.py` leggono gli stessi file, nello
stesso modo, e devono chiamarli con lo stesso nome. Due copie di `_rel` o di
`_file_py` sarebbero il primo reperto che lo strumento nuovo dovrebbe
segnalare su se stesso.

Non fa analisi: apre, ripulisce, nomina. Chi analizza sono gli strumenti.
"""
from __future__ import annotations

import io
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
APP = ROOT / "hiris" / "app"
STATIC = ROOT / "hiris" / "app" / "static"
TESTS = ROOT / "tests"

VERDE = "\033[32m"
GIALLO = "\033[33m"
GRIGIO = "\033[90m"
RESET = "\033[0m"


@dataclass
class Reperto:
    """Una cosa che uno strumento ha trovato e che qualcuno deve giudicare.

    `dove` e' una LISTA e non una stringa: un doppione non sta in un punto,
    sta in due o piu' -- ed e' l'unica cosa che lo rende un doppione. Un
    reperto con un posto solo qui dentro sarebbe una contraddizione, e
    `censimento.Reperto` (che ne ha uno solo, giustamente) resta una forma
    diversa perche' risponde a una domanda diversa.
    """
    categoria: str
    nome: str
    dove: list[str] = field(default_factory=list)
    nota: str = ""


def rel(p: Path) -> str:
    """Il percorso dalla radice del progetto, con le barre giuste ovunque."""
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return p.name


def riga_di(testo: str, offset: int) -> int:
    return testo.count("\n", 0, offset) + 1


def file_py(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def file_js(base: Path = STATIC) -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.js") if "__pycache__" not in p.parts)


def leggi(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def commenti_di(p: Path) -> dict[int, str]:
    """riga -> testo del commento, per ogni commento Python del file.

    Serve a leggere i MARCATORI (`DOPPIONE DICHIARATO`) senza doverli cercare
    con una regex sul testo grezzo, che confonderebbe un marcatore vero con la
    stessa frase citata dentro una stringa.

    Si usa `tokenize` e non una regex per lo stesso motivo per cui il
    censimento lo usa: `#` dentro un letterale non e' un commento, e nessuna
    espressione regolare sa la differenza.
    """
    per_riga: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(leggi(p)).readline):
            if tok.type == tokenize.COMMENT:
                per_riga[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Un file che non si tokenizza non ha marcatori leggibili: si va
        # avanti senza, invece di far fallire l'intero strumento su un file.
        return {}
    return per_riga
