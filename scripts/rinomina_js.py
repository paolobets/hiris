#!/usr/bin/env python3
"""Il rinominatore del frontend: propone, e applica solo cio' che e' deciso.

Stessa legge del gemello Python (`scripts/rinomina.py`): **non indovina**. Ma
il JavaScript ha due difetti che il Python non ha, e questo strumento nasce
sapendoli perche' sono stati MISURATI, non temuti.

**1. Il nome non e' il legame.** 1.542 dichiarazioni portano 704 nomi
distinti: `corpo` e' dichiarato 34 volte in 7 file, `testo` 25 in 10. Uno
strumento a token le rinomina insieme. Per questo la sorgente di verita' non
e' un tokenizzatore ma `scripts/legami_js.mjs`, che con `acorn` ricostruisce
gli ambiti e restituisce i LEGAMI. Il controllo di collisione in ambito -- il
gemello che `rinomina.Collisione` dichiara di non avere, e che il 1o settembre
e' costato un 500 su ogni asset -- qui c'e', e ci sta perche' l'AST lo rende
possibile in poche righe.

**2. Una proprieta' rinominata da un lato solo non lancia: da' `undefined`.**
In Python un attributo sbagliato e' un `AttributeError` rumoroso. Qui e'
silenzio. Provato per mutazione su 41 casi: 37 li prende la suite, 4 no -- e
tutti e quattro hanno la stessa forma, OGNI lettura in posizione di verita'
(`!x`, `x ||`, `x ? :`), dove `undefined` diventa semplicemente `false`. Il
predicato le trova con l'AST, e questo strumento le DICHIARA senza applicarle.

**VINCOLO DI PROGETTO: questo strumento tocca i LEGAMI, mai le chiavi.**
Non e' una limitazione da togliere quando ci sara' tempo, e' cio' che tiene in
piedi due proprieta' che il progetto ha misurato.

La prima: le chiavi di un oggetto letterale e le proprieta' lette per punto
sono, quasi sempre, i campi che viaggiano sul filo -- e quelli li decide la
fetta delle rotte, non questa. Su `models-route.js` le 29 occorrenze di
`riordinabile`, `connettore`, `provenienza` sono rimaste intatte mentre la
variabile che le porta diventava `data`, ed e' esattamente il confine giusto.

La seconda, misurata: i commenti di `static/` citano fra backtick soprattutto
il filo. Su `models-route.js` sedici citazioni nominano una parola che questa
fetta ha rinominato e **nessuna e' scaduta**, perche' citano campi del payload
(`dove`, `rifiuta`, `diagnosi[].testo`) o chiavi ancora intatte
(`{ id, dati, errore, filtro }`, riga 422). Il giorno in cui questo strumento
imparasse a toccare le chiavi, quelle sedici diventerebbero **sedici puntatori
falsi in un colpo**, e la nona rete (`rinomina.citazioni`) andrebbe puntata sul
JavaScript prima, non dopo.

Uso:
    node scripts/legami_js.mjs > /tmp/legami.json
    python scripts/rinomina_js.py --legami /tmp/legami.json [--percorso config]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rinomina

# Le parole che la fetta di vocabolario del frontend ha deciso, e che il
# glossario non aveva. Finche' non sono scritte in `docs/GLOSSARIO.md` questo
# file resta vuoto: lo strumento non porta un vocabolario proprio, o sarebbe
# il doppione che `doppioni.py` esiste per trovare.
VOCABOLARIO_FRONTEND: dict[str, str] = {}


# **La guardia sulla FORMA NUDA, che il gemello Python chiama `_pericoloso`.**
# Il glossario decide `classe -> class`, e la decisione e' giusta: e' la parola
# inglese per quel concetto. Ma applicata a un identificatore NUDO produce
# `var class = ...`, che in JavaScript non e' un nome ombreggiato -- e' un
# errore di sintassi. Misurato dal vivo il 02/09 su `config/usage-route.js:61`:
# tre cancelli sono andati rossi insieme (`node --check`, oxlint, la suite), il
# che e' un buon segno, ma un'ora prima la stessa parola sarebbe passata in un
# file che nessun test carica. La stessa classe era gia' costata un guasto nel
# Python (`cervello/pavimento.py`, `class = _text(...)`, trovato solo da
# `py_compile`): li' esiste `_pericoloso`, qui mancava.
#
# Due insiemi, e la distinzione conta. Le PAROLE RISERVATE non si possono usare
# e basta. I GLOBALI del browser si possono usare -- `var name = 'x'` e'
# legale -- ma ombreggiano qualcosa che il codice intorno potrebbe leggere,
# ed e' la meta' silenziosa del difetto: `name`, `status`, `length`, `top`,
# `parent`, `event`, `origin`, `closed` sono proprieta' di `window` e un
# ombreggiamento non fa arrossire niente.
_RISERVATE = frozenset([
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "export", "extends",
    "false", "finally", "for", "function", "if", "implements", "import",
    "in", "instanceof", "interface", "let", "new", "null", "package",
    "private", "protected", "public", "return", "static", "super",
    "switch", "this", "throw", "true", "try", "typeof", "var", "void",
    "while", "with", "yield", "await", "eval", "arguments",
])

_GLOBALI_PERICOLOSI = frozenset([
    "window", "document", "console", "location", "history", "navigator",
    "screen", "top", "parent", "self", "frames", "event", "name",
    "status", "length", "closed", "origin", "opener", "alert", "confirm",
    "prompt", "fetch", "localStorage", "sessionStorage", "Array",
    "Object", "String", "Number", "Boolean", "Function", "Date", "RegExp",
    "Math", "JSON", "Promise", "Map", "Set", "Symbol", "Error",
    "Infinity", "NaN", "undefined", "setTimeout", "setInterval",
    "clearTimeout", "clearInterval",
])


def pericoloso(nome: str, globale: bool) -> str:
    """La ragione per cui `nome` non si puo' usare qui, o stringa vuota.

    **`globale` cambia il verdetto, e la prima stesura non lo guardava.** Una
    parola riservata non si puo' usare mai. Un globale del browser, invece,
    dipende da DOVE: `var name` dentro una funzione e' un ombreggiamento
    locale, legale e innocuo -- rifiutarlo vorrebbe dire rifiutare ogni
    `nome -> name`, che e' la rinomina piu' comune della fetta. Al livello di
    modulo, in uno script classico, lo stesso `var name` non ombreggia niente:
    ASSEGNA a `window.name`, e quello e' il difetto. La differenza la sa
    `acorn`, non io, ed e' il campo `globale` dei legami.
    """
    if nome in _RISERVATE:
        return "e' una parola riservata di JavaScript: `var " + nome + "` non compila"
    if globale and nome in _GLOBALI_PERICOLOSI:
        return ("al livello di modulo `var " + nome + "` non ombreggia il globale "
                "del browser: gli si SCRIVE sopra")
    return ""


def _pezzi_decisi(nome: str, g: rinomina.Glossario, ambito: str):
    """(inglese, ragione) -- `None` se lo strumento non e' autorizzato."""
    pezzi = rinomina.spezza(nome)
    fuori = []
    for p in pezzi:
        low = p.lower()
        en = g.per(low, ambito)
        if en is None and low in g.alias:
            en = g.per(g.alias[low], ambito)
        if en is None:
            en = VOCABOLARIO_FRONTEND.get(low)
        if en is None:
            return None, f"«{low}» non e' deciso da nessuna tabella"
        fuori.append(en)
    if len(pezzi) > 1:
        return None, ("composto: l'inglese inverte l'ordine e questo strumento "
                      f"non lo sa -- pezzi: {'+'.join(fuori)}")
    nuovo = fuori[0]
    # la maiuscola iniziale e il camelCase si conservano
    if nome[:1].isupper():
        nuovo = nuovo[:1].upper() + nuovo[1:]
    return nuovo, ""


def proprieta_cieche(dati: dict) -> set[str]:
    """Le proprieta' che una rinomina di un lato solo NON fa arrossire.

    La forma, misurata su 41 mutazioni: ogni lettura per attributo sta in
    posizione di verita' (`!x`, `x || y`, `x ? a : b`, `if (x)`), dove una
    lettura orfana restituisce `undefined` e `undefined` diventa `false` senza
    che niente lanci. Tutti e quattro i casi ciechi hanno questa forma; nessuno
    dei ventotto casi provati fuori da questa forma e' cieco.

    Serve un lato-definizione (chiave di oggetto o scrittura per attributo):
    una proprieta' che nessuno definisce non ha un lato da lasciare indietro.
    """
    from collections import defaultdict
    lati = defaultdict(lambda: {"chiave": 0, "scrittura": 0, "lettura": 0, "verita": 0})
    for v in dati.values():
        for pr in v.get("proprieta", []):
            lati[pr["nome"]][pr["lato"]] += 1
            if pr["lato"] == "lettura" and pr.get("verita"):
                lati[pr["nome"]]["verita"] += 1
    return {n for n, x in lati.items()
            if x["lettura"] > 0 and x["lettura"] == x["verita"]
            and (x["chiave"] + x["scrittura"]) > 0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--legami", required=True, help="il JSON di legami_js.mjs")
    p.add_argument("--percorso", default="", help="filtra: es. 'config' o 'chat'")
    p.add_argument("--json", metavar="FILE",
                   help="scrive le decisioni in JSON, con gli OFFSET esatti che "
                        "`acorn` ha dato per ogni legame. Non applica niente: chi "
                        "applica e' un altro passo, e la separazione e' il punto -- "
                        "questo strumento propone, e un test lo pinna")
    p.add_argument("--ambito", default="static",
                   help="l'ambito con cui interrogare il glossario. Il valore giusto per "
                        "questo albero e' `static`, e non e' un dettaglio: otto parole sono "
                        "qualificate `(static)` e con l'ambito vuoto `Glossario.per` "
                        "risponderebbe None su tutte e otto, in silenzio")
    a = p.parse_args(argv)

    dati = json.loads(Path(a.legami).read_text(encoding="utf-8"))
    g = rinomina.g_corrente()
    cieche = proprieta_cieche(dati)

    applicabili: list[tuple] = []
    proposte: list[tuple] = []
    collisioni: list[tuple] = []

    for rel, v in sorted(dati.items()):
        if a.percorso and not rel.startswith(a.percorso):
            continue
        if "errore" in v:
            print(f"!! {rel}: {v['errore']}")
            continue
        legami = v["legami"]
        per_ambito = defaultdict(dict)
        for l in legami:
            per_ambito[l["ambito"]][l["nome"]] = l
        for l in legami:
            nome = l["nome"]
            nuovo, ragione = _pezzi_decisi(nome, g, a.ambito)
            if nuovo is None:
                if any(rinomina.spezza(nome)) and ragione.startswith("composto"):
                    proposte.append((rel, nome, ragione, len(l["rif"])))
                continue
            if nuovo == nome:
                continue
            # 0. il nome nuovo e' usabile nudo in JavaScript?
            perche = pericoloso(nuovo, l.get("globale", False))
            if perche:
                collisioni.append((rel, nome, nuovo, perche))
                continue
            # 1. il nome nuovo e' gia' legato nello STESSO ambito?
            if nuovo in per_ambito[l["ambito"]]:
                collisioni.append((rel, nome, nuovo, "gia' legato nello stesso ambito"))
                continue
            # 2. il nome nuovo esiste altrove nel file: ombreggiamento possibile
            altrove = [x for x in legami if x["nome"] == nuovo and x["ambito"] != l["ambito"]]
            if altrove:
                collisioni.append((rel, nome, nuovo,
                                   f"esiste in {len(altrove)} altri ambiti del file"))
                continue
            applicabili.append((rel, nome, nuovo, len(l["dich"]), len(l["rif"]),
                                sorted(l["dich"] + l["rif"])))

    print(f"== APPLICABILI: {len(applicabili)} legami")
    for rel, vecchio, nuovo, nd, nr, _pos in applicabili[:200]:
        print(f"   {rel}: {vecchio} -> {nuovo}  ({nd} dich, {nr} rif)")
    print(f"\n== PROPOSTE (composti: lo strumento non indovina): {len(proposte)}")
    for rel, nome, ragione, nr in proposte[:60]:
        print(f"   {rel}: {nome}  -- {ragione}")
    print(f"\n== COLLISIONI in ambito (la classe di server.py, 1 settembre): {len(collisioni)}")
    for rel, vecchio, nuovo, perche in collisioni:
        print(f"   {rel}: {vecchio} -> {nuovo}  RIFIUTATO: {perche}")
    print(f"\n== PROPRIETA' CIECHE: {len(cieche)} -- a mano, col test scritto PRIMA")
    print("   (ogni lettura in posizione di verita': una rinomina di un lato solo")
    print("    non fa arrossire niente. Misurato: 4 casi su 41 mutazioni, e tutti e")
    print("    quattro hanno questa forma; nessuno dei 28 provati fuori ce l'ha.)")
    for n in sorted(cieche):
        print(f"   {n}")
    print("\nnessuna riga e' stata scritta: questo strumento non applica.")
    if a.json:
        Path(a.json).write_text(json.dumps({
            "applicabili": [{"file": r, "vecchio": v, "nuovo": n, "posizioni": pos}
                            for r, v, n, _nd, _nr, pos in applicabili],
            "cieche": sorted(cieche),
            # La misura del testo che `legami_js.mjs` ha letto viaggia INSIEME
            # agli offset, non in un secondo file: chi applica non deve poter
            # ricevere una coppia disallineata. Un offset senza la misura del
            # testo su cui e' stato calcolato e' un numero senza unita'.
            "misure": {r: v["misura"] for r, v in dati.items() if "misura" in v},
        }), encoding="utf-8")
        print(f"decisioni scritte in {a.json} -- ma NON nei sorgenti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
