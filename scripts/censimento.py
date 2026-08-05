#!/usr/bin/env python3
"""HIRIS censimento — rilevatore meccanico di codice morto.

Rende eseguibile la «review totale» del Refactor 2.0 (vedi CLAUDE.md): in un
progetto di demolizione la domanda non e' «cio' che hai aggiunto e' corretto?»
ma «cosa hai lasciato orfano?», e le righe morte non stanno dentro il diff.

Legge e stampa. Non modifica niente, ed esce sempre 0: e' uno strumento di
lettura, non un cancello di CI.

Uso:
  python scripts/censimento.py
"""
import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
APP = ROOT / "hiris" / "app"
TESTS = ROOT / "tests"

_VERDE = "\033[32m"
_GIALLO = "\033[33m"
_GRIGIO = "\033[90m"
_RESET = "\033[0m"


@dataclass
class Reperto:
    """Una cosa che il censimento ha trovato e che qualcuno deve giudicare."""
    categoria: str
    nome: str
    dove: str
    nota: str = ""


_TITOLI: dict[str, str] = {
    "tabella-mai-toccata":       "Tabelle create e mai toccate",
    "tabella-scritta-mai-letta": "Tabelle scritte e mai lette",
    "tabella-letta-mai-scritta": "Tabelle lette e mai scritte",
}


# ── Helper ──────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return p.name


def _riga(testo: str, offset: int) -> int:
    return testo.count("\n", 0, offset) + 1


def _file_py(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _leggi(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# ── Tabelle ─────────────────────────────────────────────────────────────────
# Le parole chiave SQL si cercano MAIUSCOLE e case-sensitive: la codebase
# scrive CREATE TABLE 25 volte su 25. Cercare "from" senza distinzione di
# maiuscole farebbe combaciare «from pathlib import Path» e una tabella morta
# di nome `pathlib` sembrerebbe viva.

_RE_CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?(\w+)")
_RE_INSERT = re.compile(r"(?:INSERT|REPLACE)(?:\s+OR\s+\w+)?\s+INTO\s+[\"'`]?(\w+)")
_RE_UPDATE = re.compile(r"UPDATE\s+[\"'`]?(\w+)[\"'`]?\s+SET")
_RE_DELETE = re.compile(r"DELETE\s+FROM\s+[\"'`]?(\w+)")
_RE_LETTURA = re.compile(r"(?:FROM|JOIN)\s+[\"'`]?(\w+)")


def censisci_tabelle(files: list[Path]) -> list[Reperto]:
    """Tabelle dichiarate con CREATE TABLE, confrontate con chi le usa."""
    create: dict[str, str] = {}
    scritte: set[str] = set()
    lette: set[str] = set()

    for f in files:
        testo = _leggi(f)
        for m in _RE_CREATE.finditer(testo):
            create.setdefault(m.group(1).lower(), f"{_rel(f)}:{_riga(testo, m.start())}")
        for rx in (_RE_INSERT, _RE_UPDATE, _RE_DELETE):
            for m in rx.finditer(testo):
                scritte.add(m.group(1).lower())
        # Le letture si cercano DOPO aver rimosso i DELETE FROM, che
        # altrimenti conterebbero come letture pur essendo scritture.
        for m in _RE_LETTURA.finditer(_RE_DELETE.sub(" ", testo)):
            lette.add(m.group(1).lower())

    reperti: list[Reperto] = []
    for nome, dove in sorted(create.items()):
        if nome in scritte and nome in lette:
            continue
        if nome not in scritte and nome not in lette:
            reperti.append(Reperto("tabella-mai-toccata", nome, dove))
        elif nome not in lette:
            reperti.append(Reperto("tabella-scritta-mai-letta", nome, dove,
                                   "si riempie e nessuno la interroga"))
        else:
            reperti.append(Reperto("tabella-letta-mai-scritta", nome, dove,
                                   "la si interroga e nessuno la riempie"))
    return reperti


# ── Report ──────────────────────────────────────────────────────────────────

def stampa(reperti: list[Reperto]) -> None:
    per_categoria: dict[str, list[Reperto]] = {}
    for r in reperti:
        per_categoria.setdefault(r.categoria, []).append(r)

    for categoria, titolo in _TITOLI.items():
        gruppo = per_categoria.get(categoria, [])
        if not gruppo:
            print(f"{_VERDE}  0{_RESET}  {titolo}")
            continue
        print(f"\n{_GIALLO}{len(gruppo):>3}{_RESET}  {titolo}")
        for r in sorted(gruppo, key=lambda x: x.nome):
            nota = f"  {_GRIGIO}{r.nota}{_RESET}" if r.nota else ""
            print(f"       {r.nome}  {_GRIGIO}({r.dove}){_RESET}{nota}")

    print(f"\nTotale reperti: {len(reperti)}")


def run() -> int:
    file_app = _file_py(APP)
    reperti = censisci_tabelle(file_app)
    stampa(reperti)
    return 0


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ).parse_args()
    sys.exit(run())


if __name__ == "__main__":
    main()
