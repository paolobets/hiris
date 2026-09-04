#!/usr/bin/env python3
"""Il cancello che un linter non puo' fare: le sponde FRA file del JavaScript.

**Perche' `no-undef` non basta, misurato invece che supposto.**
`hiris/app/static/` non ha moduli: i file si caricano con `<script src>` in
ordine fisso e si parlano per variabile globale. Un linter lavora un file per
volta, quindi per restare verde su un albero sano gli si deve DICHIARARE che
`HirisRouter` e `fmtNum` esistono -- e quella dichiarazione e' esattamente cio'
che lo rende cieco il giorno in cui qualcuno rinomina chi li produce.
Provato: rinominato `window.HirisRouter` da un lato solo, oxlint col cancello
tace, come tace senza. Idem per `function fmtNum` di `config/api.js`.

Questo script chiude l'anello. Non guarda dentro un file: guarda i file
INSIEME, e verifica tre cose che nessun altro cancello verifica.

  1. Ogni nome dichiarato globale in `.oxlintrc.json` e' DAVVERO prodotto da un
     file di `static/`. Se sparisce dai produttori, la dichiarazione e'
     diventata una bugia -- ed e' il sintomo di una rinomina lasciata a meta'.
  2. Ogni nome prodotto e letto da un ALTRO file e' dichiarato nel config.
     Senza questo il config invecchia in silenzio e il punto 1 non protegge
     piu' niente.
  3. Chi legge un nome altrui e' caricato DOPO chi lo produce, secondo
     l'ordine dei `<script src>` dei due `.html`. E' l'unica dichiarazione di
     dipendenza che questo frontend possieda, e oggi non la legge nessuno.

I due cancelli si sorvegliano a vicenda: la lista `globals` smette di essere
una concessione al linter e diventa una dichiarazione che qualcuno verifica.

Uscita 0 se tutto torna, 1 con l'elenco altrimenti.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "hiris" / "app" / "static"
CONFIG = ROOT / ".oxlintrc.json"

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_KW = frozenset([
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "extends", "finally", "for", "function",
    "if", "in", "instanceof", "new", "return", "super", "switch", "this",
    "throw", "try", "typeof", "var", "void", "while", "with", "yield", "let",
    "await", "null", "true", "false",
])


def _tokens(src: str) -> list[tuple[str, str]]:
    """(specie, valore), saltando commenti, stringhe e regex.

    Non e' un parser: serve solo a NON scambiare una stringa o un commento per
    un identificatore. E' la stessa ragione per cui `rinomina.py` usa
    `tokenize` invece di una regex -- «lo strumento di misura sbaglia piu' del
    giudizio» vale anche qui, e una regex su `\\bHirisRouter\\b` troverebbe le
    citazioni nei commenti.
    """
    fuori: list[tuple[str, str]] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n\f\v﻿":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise SyntaxError("commento di blocco non chiuso")
            i = j + 2
            continue
        if c in "'\"`":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                j += 1
            i = j + 1
            continue
        if c == "/":
            prec = fuori[-1] if fuori else None
            divisione = prec is not None and (
                prec[0] in ("name", "num") or prec[1] in (")", "]"))
            if not divisione:
                j, in_classe = i + 1, False
                while j < n and src[j] != "\n":
                    if src[j] == "\\":
                        j += 2
                        continue
                    if src[j] == "[":
                        in_classe = True
                    elif src[j] == "]":
                        in_classe = False
                    elif src[j] == "/" and not in_classe:
                        break
                    j += 1
                if j < n and src[j] == "/":
                    i = j + 1
                    while i < n and src[i].isalpha():
                        i += 1
                    continue
            fuori.append(("punct", "/"))
            i += 1
            continue
        m = _IDENT.match(src, i)
        if m:
            w = m.group(0)
            fuori.append(("kw" if w in _KW else "name", w))
            i = m.end()
            continue
        if c.isdigit():
            j = i
            while j < n and (src[j].isalnum() or src[j] in "._"):
                j += 1
            fuori.append(("num", src[i:j]))
            i = j
            continue
        fuori.append(("punct", c))
        i += 1
    return fuori


def profilo(percorso: Path) -> tuple[set[str], set[str]]:
    """(nomi che questo file PRODUCE per gli altri, nomi che usa LIBERI).

    «Prodotto» e' `window.X = ...` oppure una dichiarazione di modulo (fuori
    da ogni graffa e da ogni parentesi): in uno script classico quest'ultima
    e' un globale, che i venti file avvolti in una IIFE non producono e
    `config/api.js` si'.
    """
    t = _tokens(percorso.read_text(encoding="utf-8"))
    prodotti: set[str] = set()
    legati: set[str] = set()
    usati: set[str] = set()
    profondita = 0
    for i, (k, v) in enumerate(t):
        if k == "punct" and v in "{(":
            profondita += 1
        elif k == "punct" and v in "})":
            profondita -= 1
        if k != "name":
            continue
        prec = t[i - 1] if i else None
        succ = t[i + 1] if i + 1 < len(t) else None
        if (prec and prec[1] == "." and i >= 2 and t[i - 2][1] == "window"
                and succ and succ[1] == "="):
            prodotti.add(v)
            continue
        if prec and prec[1] in (".", "?."):
            continue
        if prec and prec[0] == "kw" and prec[1] in ("function", "class"):
            legati.add(v)
            if profondita == 0:
                prodotti.add(v)
            continue
        if prec and prec[0] == "kw" and prec[1] in ("var", "let", "const"):
            legati.add(v)
            if profondita == 0:
                prodotti.add(v)
            continue
        if prec and prec[0] == "kw" and prec[1] == "catch":
            legati.add(v)
            continue
        if succ and succ[1] == ":" and prec and prec[1] in ("{", ","):
            continue
        usati.add(v)
    return prodotti, usati - legati


_TAG = re.compile(r'<script\s+src="static/([^"?]+)')


def sequenza_script() -> dict[str, list[str]]:
    """Per ogni pagina, i file nell'ordine in cui il browser li carica.

    E' l'UNICA dichiarazione di dipendenza che questo frontend possieda: senza
    moduli, «chi viene prima» e' scritto solo qui, nei `<script src>` dei due
    `.html`. Prima di questo cancello non la leggeva nessuno -- spostare
    `config/api.js` dopo chi lo usa non faceva arrossire niente.
    """
    fuori = {}
    for html in sorted(STATIC.glob("*.html")):
        fuori[html.name] = _TAG.findall(html.read_text(encoding="utf-8"))
    return fuori


def leggi_config(percorso: Path) -> dict:
    """`.oxlintrc.json` e' JSONC: oxlint ammette i commenti, e li' dentro c'e'
    la ragione per cui due globali NON sono dichiarati. `json.loads` non li
    ammette -- leggere quel file con lo strumento sbagliato faceva morire
    questo cancello con uno stack trace invece che con un verdetto. Si tolgono
    i `//` che stanno FUORI dalle stringhe: dentro una stringa un `//` e' un
    URL, non un commento.
    """
    testo = percorso.read_text(encoding="utf-8")
    fuori, i, n, in_stringa = [], 0, len(testo), False
    while i < n:
        c = testo[i]
        if in_stringa:
            if c == "\\":
                fuori.append(testo[i:i + 2])
                i += 2
                continue
            if c == chr(34):
                in_stringa = False
            fuori.append(c)
            i += 1
            continue
        if c == chr(34):
            in_stringa = True
            fuori.append(c)
            i += 1
            continue
        if testo.startswith("//", i):
            j = testo.find("\n", i)
            i = n if j < 0 else j
            continue
        fuori.append(c)
        i += 1
    return json.loads("".join(fuori))


def main() -> int:
    if not CONFIG.exists():
        print(f"manca {CONFIG.name}: questo cancello non ha niente da verificare")
        return 1
    dichiarati = set(leggi_config(CONFIG).get("globals", {}))
    file = sorted(STATIC.rglob("*.js"))
    produttore: dict[str, str] = {}
    utilizzi: dict[str, set[str]] = {}
    for f in file:
        rel = f.relative_to(STATIC).as_posix()
        prod, usa = profilo(f)
        utilizzi[rel] = usa
        for n in prod:
            produttore.setdefault(n, rel)

    guai: list[str] = []

    for n in sorted(dichiarati - set(produttore)):
        letto = sorted(r for r, u in utilizzi.items() if n in u)
        guai.append(
            f"«{n}» e' dichiarato globale in {CONFIG.name} ma NESSUN file di "
            f"static/ lo produce piu'"
            + (f" -- lo legge ancora: {', '.join(letto)}" if letto else ""))

    for n, dove in sorted(produttore.items()):
        altrove = sorted(r for r, u in utilizzi.items() if r != dove and n in u)
        if altrove and n not in dichiarati:
            guai.append(f"«{n}» (prodotto da {dove}) e' letto da "
                        f"{', '.join(altrove)} ma non e' dichiarato in {CONFIG.name}")

    for pagina, sequenza in sequenza_script().items():
        posto = {rel: i for i, rel in enumerate(sequenza)}
        for rel in sequenza:
            for n in sorted(utilizzi.get(rel, ())):
                dove = produttore.get(n)
                if dove is None or dove == rel or dove not in posto:
                    continue
                if posto[dove] > posto[rel]:
                    guai.append(f"{pagina}: {rel} legge «{n}» ma {dove}, che lo "
                                f"produce, e' caricato DOPO")

    if guai:
        print(f"sponde fra file: {len(guai)} da sistemare")
        for g in guai:
            print(f"  - {g}")
        return 1
    print(f"sponde fra file: {len(dichiarati)} globali dichiarati, tutti prodotti "
          f"e tutti letti dopo il loro produttore -- {len(file)} file esaminati")
    return 0


if __name__ == "__main__":
    sys.exit(main())
