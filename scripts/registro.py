#!/usr/bin/env python3
"""HIRIS registro — il registro dei doppioni, letto da un programma.

## Perche' esiste

`docs/design/2026-10-01-registro-dei-doppioni.md` e' la lista di lavoro dello
sprint «Una fonte sola di verita'» (requisito R20): una riga per voce, e una
voce si chiude **solo quando la copia e' cancellata**. Finche' era solo un
documento portava in coda una tabella di conti scritta a mano, e quei conti
non coincidevano con quelli della spec che li citava -- la stessa cosa scritta
in due posti, cioe' esattamente cio' che il registro caccia.

Qui i conti si CHIEDONO, e una voce si chiude con un comando che la sposta:
non resta un posto in cui una voce possa essere insieme aperta e chiusa.

## Come e' fatto il documento

- un capitolo comincia a una riga `## X. ...`, con X una lettera sola;
- una voce e' una riga di tabella il cui primo campo ha la forma `X-NN`;
- tutto cio' che sta sotto `## Chiuse` e' chiuso, e il capitolo di una voce
  chiusa e' la lettera del suo id.

Le righe di tabella fuori da un capitolo e fuori da `## Chiuse` (le sezioni
«in coda»: correzioni, tracciabilita') NON sono voci, e non si leggono.

## Fatta nel ramo, non ancora rilasciata

Una voce si chiude con una versione: finche' il lavoro sta solo nel ramo, la
voce resta aperta e porta in coda all'ultima colonna il segno

    **chiudibile al rilascio** `abc1234`, `def5678`: cosa e' uscito

(i commit che hanno tolto la copia, poi la nota che andra' fra le chiuse). Al
rilascio `rilascia --versione X.Y.Z` chiude in un colpo le voci segnate, e da'
la versione anche alle voci chiuse prima del rilascio (quelle con «Tappa 6,
Task 7» o «da rilasciare» al posto della versione): e' lo stesso fatto, «fatto
ma non uscito», e ha un comando solo. Un segno che il lettore non capisce
ferma `verifica`: altrimenti al rilascio quella voce resterebbe aperta in
silenzio.

Uso:
  python scripts/registro.py conta
  python scripts/registro.py chiudi M-13 --versione 3.73.0 --commit abc1234 \\
      --nota "costante cancellata"
  python scripts/registro.py verifica
  python scripts/registro.py chiudibili
  python scripts/registro.py rilascia --versione 3.78.0
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "design" / "2026-10-01-registro-dei-doppioni.md"

CLOSED_HEADING = "## Chiuse"
_CHAPTER = re.compile(r"^## ([A-Z])\. ")
_ENTRY_ID = re.compile(r"^([A-Z])-\d{2,}$")


class Entry(NamedTuple):
    """Una voce del registro: cio' che serve a dire quale e', e se e' chiusa."""
    id: str
    chapter: str
    text: str
    closed: bool
    line: int
    cells: tuple[str, ...]


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def read_entries(path: Path = REGISTER) -> list[Entry]:
    """Le voci del documento, aperte e chiuse, nell'ordine in cui compaiono."""
    entries: list[Entry] = []
    chapter: str | None = None
    closed = False
    for number, row in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if row.startswith("#"):
            closed = row.strip() == CLOSED_HEADING
            found = _CHAPTER.match(row)
            chapter = found.group(1) if found else None
            continue
        if not row.startswith("|") or (chapter is None and not closed):
            continue
        cells = _cells(row)
        shaped = _ENTRY_ID.match(cells[0]) if len(cells) >= 2 else None
        if not shaped:
            continue
        if not closed and shaped.group(1) != chapter:
            raise SystemExit(f"registro: la voce {cells[0]} (riga {number}) sta nel "
                             f"capitolo {chapter}: una voce sta nel capitolo della sua lettera")
        entries.append(Entry(id=cells[0], chapter=cells[0][0] if closed else chapter,
                             text=cells[1], closed=closed, line=number,
                             cells=tuple(cells)))
    return entries


def count(entries: list[Entry]) -> dict[str, dict[str, int]]:
    """Per capitolo: quante voci aperte e quante chiuse."""
    tally: dict[str, dict[str, int]] = {}
    for entry in entries:
        row = tally.setdefault(entry.chapter, {"aperte": 0, "chiuse": 0})
        row["chiuse" if entry.closed else "aperte"] += 1
    return tally


#: I capitoli dei doppioni veri e propri: i soli le cui righe portano uno
#: `Stato` e un `Unirla`. M, X e S hanno altre colonne (lo dice la legenda
#: in testa al documento), quindi qui non si contano.
DUPLICATE_CHAPTERS = "ABCDEFGT"
TWO_VERDICTS = "due verdetti"


def verdicts(entries: list[Entry]) -> dict[str, dict[str, int]]:
    """Per le voci APERTE dei capitoli dei doppioni: quante per `Stato`
    (E, D, NV) e quante per `Unirla` (PS, CC, DP)."""
    tally: dict[str, dict[str, int]] = {"stato": {}, "unirla": {}}
    for entry in entries:
        if entry.closed or entry.chapter not in DUPLICATE_CHAPTERS:
            continue
        for name, cell in (("stato", entry.cells[2]), ("unirla", entry.cells[3])):
            key = TWO_VERDICTS if "CONTRADDIZIONE" in cell else cell
            tally[name][key] = tally[name].get(key, 0) + 1
    return tally


def close(path: Path, entry_id: str, *, version: str, commit: str, note: str) -> None:
    """Sposta la voce sotto `## Chiuse`: non resta nel suo capitolo.

    Rifiuta una voce che non c'e' e una gia' chiusa: chiudere due volte
    vorrebbe dire che qualcuno ha contato due volte lo stesso lavoro.
    """
    matching = [entry for entry in read_entries(path) if entry.id == entry_id]
    if not matching:
        raise SystemExit(f"registro: la voce {entry_id} non esiste")
    entry = matching[0]
    if entry.closed:
        raise SystemExit(f"registro: la voce {entry_id} e' gia' chiusa")
    rows = path.read_text(encoding="utf-8").splitlines()
    del rows[entry.line - 1]
    stripped = [row.strip() for row in rows]
    if CLOSED_HEADING not in stripped:
        raise SystemExit(f"registro: nel documento manca la sezione `{CLOSED_HEADING}`")
    # La riga va in coda alla tabella di «Chiuse», ovunque stia la sezione: la
    # prima intestazione dopo di lei (o la fine del file) ne segna il confine.
    start = stripped.index(CLOSED_HEADING)
    end = next((index for index in range(start + 1, len(rows))
                if rows[index].startswith("#")), len(rows))
    while end > start + 1 and not rows[end - 1].strip():
        end -= 1
    rows.insert(end, f"| {entry_id} | {entry.text} | {version} | {commit} | {note} |")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


RELEASABLE_MARK = "**chiudibile al rilascio**"
_RELEASABLE = re.compile(r"\*\*chiudibile al rilascio\*\* "
                         r"(`[0-9a-f]{7,40}`(?:, `[0-9a-f]{7,40}`)*): (.+)$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class Releasable(NamedTuple):
    """Cio' che il segno di una voce aperta dice: chi l'ha fatta, e la nota."""
    commits: list[str]
    note: str


def releasable(entry: Entry) -> Releasable | None:
    """Il segno «chiudibile al rilascio» di una voce aperta, o None."""
    if entry.closed:
        return None
    found = _RELEASABLE.search(entry.cells[-1])
    if not found:
        return None
    return Releasable(commits=re.findall(r"`([0-9a-f]{7,40})`", found.group(1)),
                      note=found.group(2).strip())


def malformed(entries: list[Entry]) -> list[str]:
    """Le voci che nominano il segno ma non nella forma che si legge."""
    return [entry.id for entry in entries
            if not entry.closed and RELEASABLE_MARK in entry.cells[-1]
            and releasable(entry) is None]


def closed_early(entries: list[Entry]) -> list[Entry]:
    """Le voci chiuse con un nome di lavoro al posto della versione."""
    return [entry for entry in entries
            if entry.closed and len(entry.cells) >= 3
            and not _VERSION.match(entry.cells[2])]


def pending(entries: list[Entry]) -> list[str]:
    """Gli id che `release` toccherebbe, nell'ordine del documento: le voci
    segnate e le chiuse in anticipo. E' cio' che un rilascio in prova stampa."""
    early = {entry.id for entry in closed_early(entries)}
    return [entry.id for entry in entries
            if entry.id in early or releasable(entry) is not None]


def release(path: Path, *, version: str) -> list[str]:
    """Al rilascio: chiude le voci segnate e da' la versione alle chiuse in
    anticipo. Restituisce gli id toccati, nell'ordine del documento."""
    if not _VERSION.match(version):
        raise SystemExit(f"registro: «{version}» non e' una versione (X.Y.Z)")
    entries = read_entries(path)
    early = closed_early(entries)
    if early:
        rows = path.read_text(encoding="utf-8").splitlines()
        for entry in early:
            cells = list(entry.cells)
            cells[2] = version
            rows[entry.line - 1] = "| " + " | ".join(cells) + " |"
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    marked = [(entry.id, releasable(entry)) for entry in entries]
    for entry_id, sign in marked:
        if sign is not None:
            close(path, entry_id, version=version, commit=", ".join(sign.commits),
                  note=sign.note)
    return pending(entries)


def unfinished(entries: list[Entry]) -> list[str]:
    """Le voci chiuse senza versione o senza commit: chiuse a parole."""
    return [entry.id for entry in entries
            if entry.closed and (len(entry.cells) < 4 or not entry.cells[2]
                                 or not entry.cells[3])]


def _print_count(entries: list[Entry]) -> None:
    tally = count(entries)
    for chapter in sorted(tally):
        row = tally[chapter]
        print(f"  {chapter}  aperte {row['aperte']:>3} · chiuse {row['chiuse']:>3}")
    opened = sum(row["aperte"] for row in tally.values())
    closed = sum(row["chiuse"] for row in tally.values())
    print(f"  Totale: {opened + closed} voci · aperte {opened} · chiuse {closed}")
    marked = [entry for entry in entries if releasable(entry) is not None]
    print(f"  Fatte nel ramo, chiudibili al rilascio: {len(marked)} · "
          f"aperte vere: {opened - len(marked)} · "
          f"chiuse prima della versione: {len(closed_early(entries))}")
    for name, row in verdicts(entries).items():
        listed = " · ".join(f"{key} {row[key]}" for key in sorted(row))
        print(f"  Doppioni aperti (A-G e T) per {name}: {listed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("conta", help="quante voci aperte e chiuse, per capitolo")
    commands.add_parser("verifica", help="esce 1 se una voce e' chiusa a meta' "
                                         "o porta un segno storto")
    commands.add_parser("chiudibili", help="le voci fatte nel ramo, da chiudere al rilascio")
    releasing = commands.add_parser("rilascia", help="al rilascio: chiude le voci "
                                    "segnate e da' la versione alle chiuse in anticipo")
    releasing.add_argument("--versione", required=True)
    closing = commands.add_parser("chiudi", help="sposta una voce sotto «Chiuse»")
    closing.add_argument("id")
    closing.add_argument("--versione", required=True)
    closing.add_argument("--commit", required=True)
    closing.add_argument("--nota", required=True)
    args = parser.parse_args()

    if args.command == "chiudi":
        close(REGISTER, args.id, version=args.versione, commit=args.commit, note=args.nota)
        print(f"registro: {args.id} chiusa con la {args.versione} ({args.commit})")
        return
    if args.command == "rilascia":
        touched = release(REGISTER, version=args.versione)
        print(f"registro: {len(touched)} voci con la {args.versione}: {touched}")
        return
    entries = read_entries(REGISTER)
    if args.command == "chiudibili":
        for entry in entries:
            sign = releasable(entry)
            if sign is not None:
                print(f"  {entry.id}  {', '.join(sign.commits)}  {sign.note}")
        for entry in closed_early(entries):
            print(f"  {entry.id}  chiusa con «{entry.cells[2]}» ({entry.cells[3]})")
        return
    if args.command == "conta":
        _print_count(entries)
        return
    half_closed = unfinished(entries)
    if half_closed:
        print(f"registro: voci chiuse senza versione o commit: {half_closed}",
              file=sys.stderr)
        sys.exit(1)
    crooked = malformed(entries)
    if crooked:
        print(f"registro: segno «chiudibile al rilascio» illeggibile in: {crooked}",
              file=sys.stderr)
        sys.exit(1)
    print(f"registro: {len(entries)} voci lette, nessuna chiusa a meta'")


if __name__ == "__main__":
    main()
