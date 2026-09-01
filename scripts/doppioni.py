#!/usr/bin/env python3
"""HIRIS doppioni — rilevatore meccanico di regole scritte due volte.

## Perche' esiste

`CLAUDE.md` §«La review totale» elenca cinque cose da verificare a ogni giro.
Quattro hanno un comando che le esegue; **«doppioni divergenti» era l'unica
che nessuno strumento copriva**, e si e' visto: la review indipendente del
2026-08-17 ne ha trovati dodici a mano, di cui uno -- il vocabolario di
`forza` scritto in Python e due volte in JavaScript -- CANCELLAVA DATI.

E' anche la fondamenta 2 di questo progetto, quella che dice «un fatto, o una
regola, scritto in due posti e' due posti che divergono». Una regola che si
puo' solo ricordare non e' una regola: e' una buona intenzione.

## Il difetto che questo strumento deve evitare di essere

Il difetto numero uno del progetto e' «un elenco che dice sempre qualcosa».
Uno strumento che a ogni giro ristampa gli stessi doppioni VOLUTI -- il codice
ne ha, motivati -- diventa rumore, e chi lo legge smette di leggerlo. Per
questo esiste il MARCATORE:

    # DOPPIONE DICHIARATO: il client HA non deve dipendere dallo storage
    _MAIN_DASHBOARD_KEY = "__principale__"

Il marcatore sta ACCANTO al codice e non in un elenco a parte, perche' un
elenco a parte sarebbe un secondo posto da tenere allineato -- cioe'
esattamente cio' che questo strumento caccia. Chi cancella il codice cancella
anche la dichiarazione, senza doversene ricordare.

Quanti ne salta e dove lo dichiara in coda: un filtro silenzioso sarebbe un
altro modo di mentire.

## Cosa NON sa fare, dichiarato

- **Due funzioni che rispondono alla stessa domanda con codice diverso.** E'
  il caso peggiore -- la mappa aree di `entity_cache` contro `gerarchia()`,
  che per giunta rispondeva peggio -- e non e' rilevabile staticamente: sono
  due algoritmi diversi, e nessuna impronta li avvicina. Resta agli occhi.
- **Una regola duplicata in PROSA**, dentro i commenti. Qui ce n'e' molta, ed
  e' preziosa; ma un commento che ripete una soglia scritta altrove non si
  distingue meccanicamente da uno che la spiega.
- **Duplicazioni fra Python e YAML o shell** (`config.yaml`, `run.sh`).
  Quelle le vede il censimento, dal lato delle opzioni mai lette.

Legge e stampa. Non modifica niente. Esce 0 (rapporto) o 1 (con `--cancello`,
se trova un doppione non dichiarato).

Uso:
  python scripts/doppioni.py
  python scripts/doppioni.py --cancello    # per .githooks/pre-push
"""
from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _comune import (
    APP,
    GIALLO,
    GRIGIO,
    RESET,
    TESTS,
    VERDE,
    Reperto,
    commenti_di,
    file_js,
    file_py,
    leggi,
    rel,
    riga_di,
)

MARCATORE = "DOPPIONE DICHIARATO"

_TITOLI: dict[str, str] = {
    "regex-ripetuta": "La stessa espressione regolare in piu' file",
    "funzione-gemella": "Funzioni con lo stesso corpo, scritte piu' volte",
    "vocabolario-parallelo": "Vocabolari chiusi che vivono in Python e in JavaScript",
    "predefinito-ripetuto": "Lo stesso valore predefinito per la stessa chiave, in piu' file",
}


# ── Il marcatore ────────────────────────────────────────────────────────────

def _righe_dichiarate(p: Path) -> set[int]:
    """Le righe coperte da un marcatore `DOPPIONE DICHIARATO`.

    Un marcatore copre la sua riga e le CINQUE successive: sta sopra il codice
    che dichiara, e fra i due possono esserci altre righe di commento (la
    ragione, che e' la parte che conta). Cinque perche' una ragione piu' lunga
    di cosi' vuole un commento di blocco sopra, non un marcatore allungato.
    """
    coperte: set[int] = set()
    for riga, testo in commenti_di(p).items():
        if MARCATORE in testo:
            coperte.update(range(riga, riga + 6))
    return coperte


def _dichiarato(p: Path, riga: int, cache: dict[Path, set[int]]) -> bool:
    if p not in cache:
        cache[p] = _righe_dichiarate(p)
    return riga in cache[p]


# ── 1. Espressioni regolari ripetute ────────────────────────────────────────

_RE_COMPILE = re.compile(r"re\.compile\(\s*r?(['\"])(.+?)\1", re.DOTALL)


def cerca_regex(files: list[Path]) -> list[Reperto]:
    """La stessa espressione regolare compilata in piu' file.

    E' il controllo con meno rumore che esista: due regex identiche in due
    moduli sono, quasi sempre, la stessa regola scritta due volte -- e quando
    divergono lo fanno di un carattere, che e' il modo in cui divergono le
    cose che nessuno confronta mai. Il caso vero: `_TOOL_LEAK_RE` tollerava
    uno spazio iniziale e `_TOXIC_ASSISTANT_RE` no, e la differenza contava
    sul disco, dove le righe gia' scritte tornavano al modello per sempre.
    """
    per_pattern: dict[str, list[str]] = collections.defaultdict(list)
    dichiarate: dict[Path, set[int]] = {}
    for p in files:
        testo = leggi(p)
        for m in _RE_COMPILE.finditer(testo):
            riga = riga_di(testo, m.start())
            if _dichiarato(p, riga, dichiarate):
                continue
            per_pattern[m.group(2)].append(f"{rel(p)}:{riga}")
    return [
        Reperto("regex-ripetuta", pattern, sorted(dove))
        for pattern, dove in sorted(per_pattern.items())
        if len({d.split(":")[0] for d in dove}) > 1
    ]


# ── 2. Funzioni gemelle ─────────────────────────────────────────────────────

class _Anonimizzatore(ast.NodeTransformer):
    """Toglie i NOMI e lascia la FORMA.

    Due funzioni sono gemelle se fanno la stessa cosa, non se si chiamano allo
    stesso modo: `_dominio`, `_domain` e `_dominio_entita` erano tre nomi per
    una riga sola. Si rinominano quindi variabili e argomenti in posizionali
    (`v0`, `v1`, ...) mantenendo l'identita' fra le occorrenze -- cosi' due
    funzioni che usano il proprio argomento nello stesso posto combaciano, e
    due che lo usano in posti diversi no.

    I nomi di ATTRIBUTO e di FUNZIONE CHIAMATA restano: `x.split(".")` e
    `x.partition(".")` sono due cose diverse, e appiattirle produrrebbe
    accoppiamenti falsi.
    """

    def __init__(self) -> None:
        self._mappa: dict[str, str] = {}

    def visit_Name(self, nodo: ast.Name):
        if nodo.id not in self._mappa:
            self._mappa[nodo.id] = f"v{len(self._mappa)}"
        return ast.copy_location(
            ast.Name(id=self._mappa[nodo.id], ctx=nodo.ctx), nodo)

    def visit_arg(self, nodo: ast.arg):
        if nodo.arg not in self._mappa:
            self._mappa[nodo.arg] = f"v{len(self._mappa)}"
        return ast.copy_location(ast.arg(arg=self._mappa[nodo.arg], annotation=None), nodo)


def _impronta(funzione: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, int]:
    """`(impronta, quante istruzioni)` del corpo, senza nomi e senza docstring."""
    corpo = list(funzione.body)
    if (corpo and isinstance(corpo[0], ast.Expr)
            and isinstance(corpo[0].value, ast.Constant)
            and isinstance(corpo[0].value.value, str)):
        corpo = corpo[1:]
    if not corpo:
        return "", 0
    finto = ast.Module(body=[ast.fix_missing_locations(ast.copy_location(
        ast.FunctionDef(name="f", args=funzione.args, body=corpo,
                        decorator_list=[], returns=None, type_params=[]),
        funzione))], type_ignores=[])
    anonimo = _Anonimizzatore().visit(finto)
    ast.fix_missing_locations(anonimo)
    return hashlib.sha256(ast.dump(anonimo).encode("utf-8")).hexdigest(), len(corpo)


# Sotto le due istruzioni non si guarda: `return x` e `return y` sono la stessa
# forma per costruzione, e segnalarli vorrebbe dire riempire il rapporto di
# accoppiamenti che nessuno andrebbe a unire. Le sei letture del dominio, che
# sono il caso vero, ne hanno una sola -- e infatti non le trova questo
# controllo ma la lettura umana: e' un limite, ed e' dichiarato in coda.
_MINIMO_ISTRUZIONI = 2


def cerca_funzioni_gemelle(files: list[Path]) -> list[Reperto]:
    per_impronta: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    dichiarate: dict[Path, set[int]] = {}
    for p in files:
        try:
            albero = ast.parse(leggi(p))
        except SyntaxError:
            continue
        for nodo in ast.walk(albero):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            impronta, quante = _impronta(nodo)
            if not impronta or quante < _MINIMO_ISTRUZIONI:
                continue
            if _dichiarato(p, nodo.lineno, dichiarate):
                continue
            per_impronta[impronta].append((nodo.name, f"{rel(p)}:{nodo.lineno}"))
    reperti = []
    for gruppo in per_impronta.values():
        if len({d.split(":")[0] for _n, d in gruppo}) < 2:
            continue
        nomi = sorted({n for n, _d in gruppo})
        reperti.append(Reperto(
            "funzione-gemella", " / ".join(nomi), sorted(d for _n, d in gruppo),
            "stesso corpo, nomi diversi" if len(nomi) > 1 else "stesso corpo"))
    return sorted(reperti, key=lambda r: r.nome)


# ── 3. Vocabolari paralleli Python ↔ JavaScript ─────────────────────────────

_MINIMO_MEMBRI = 3


def _presente_nel_js(membro: str, testo: str) -> bool:
    """Un membro compare nel JavaScript, in una delle tre forme che contano.

    Non basta cercarlo fra apici: in JavaScript le CHIAVI DI OGGETTO si
    scrivono senza (`{ preferenza: 'Preferenza' }`), ed e' esattamente la forma
    in cui era scritto `FORZA_LABELS` -- cioe' il caso che ha motivato questo
    strumento. Cercando solo le stringhe quotate, il rilevatore avrebbe mancato
    il difetto per cui e' nato, e sarebbe passato per buono.

    Le tre forme: `'x'`, `"x"`, e `x:` come chiave.
    """
    return (f"'{membro}'" in testo or f'"{membro}"' in testo
            or re.search(r"(?<![\w.$])" + re.escape(membro) + r"\s*:", testo) is not None)


def _vocabolari_python(p: Path) -> list[tuple[str, int, list[str]]]:
    """`(nome, riga, membri)` per ogni insieme chiuso di stringhe assegnato a
    una costante di modulo."""
    try:
        albero = ast.parse(leggi(p))
    except SyntaxError:
        return []
    trovati = []
    for nodo in albero.body:
        if not isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            continue
        bersagli = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
        nomi = [t.id for t in bersagli if isinstance(t, ast.Name)]
        if not nomi or nodo.value is None:
            continue
        valore = nodo.value
        if isinstance(valore, ast.Call) and isinstance(valore.func, ast.Name) \
                and valore.func.id in {"frozenset", "set", "tuple", "list"} and valore.args:
            valore = valore.args[0]
        for suffisso, membri in _membri_di(valore):
            if len(membri) >= _MINIMO_MEMBRI:
                trovati.append((nomi[0] + suffisso, nodo.lineno, membri))
    return trovati


def _membri_di(valore: ast.expr) -> list[tuple[str, list[str]]]:
    """`(suffisso, membri)` per un valore e per i suoi vocabolari ANNIDATI.

    Scende di un livello dentro i dizionari, e non e' un dettaglio: il difetto
    che ha motivato questo strumento -- le quattro forze di un ricordo -- non
    era una costante a se', era `VOCABOLARIO["forza"]`, un insieme dentro un
    dizionario di insiemi. Leggendo solo le chiavi di primo livello il
    rilevatore vedeva `{"forza", "tipo_ancora", ...}` e mancava esattamente
    cio' per cui era nato.

    Il suffisso (`["forza"]`) entra nel nome perche' chi legge il rapporto
    deve sapere QUALE pezzo, non solo quale costante.
    """
    def scarta(v):
        if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                and v.func.id in {"frozenset", "set", "tuple", "list"} and v.args):
            return v.args[0]
        return v

    valore = scarta(valore)
    trovati: list[tuple[str, list[str]]] = []
    if isinstance(valore, (ast.Set, ast.Tuple, ast.List)):
        trovati.append(("", [e.value for e in valore.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str)]))
    elif isinstance(valore, ast.Dict):
        trovati.append(("", [k.value for k in valore.keys
                             if isinstance(k, ast.Constant) and isinstance(k.value, str)]))
        for chiave, sotto in zip(valore.keys, valore.values):
            if not (isinstance(chiave, ast.Constant) and isinstance(chiave.value, str)):
                continue
            sotto = scarta(sotto)
            if isinstance(sotto, (ast.Set, ast.Tuple, ast.List)):
                trovati.append((f'["{chiave.value}"]',
                                [e.value for e in sotto.elts
                                 if isinstance(e, ast.Constant) and isinstance(e.value, str)]))
    return trovati


_RE_COSTANTE = re.compile(r"\b[A-Z_][A-Z0-9_]{2,}\b")


def _costanti_gia_legate(test: list[Path]) -> set[str]:
    """I nomi di costante che una PROVA lega gia' al frontend.

    Un vocabolario che vive in Python e in JavaScript non e' un difetto se
    esiste qualcosa che si rompe quando i due divergono: il difetto e' la
    divergenza SILENZIOSA. `FIXED_ORDER` e i tre preset sono duplicati da
    sempre, e sono in regola, perche' `test_models_frontend_wiring.py`
    confronta la stringa JS con la lista Python; `VOCABOLARIO["forza"]` non lo
    era, e l'ha pagata cancellando la forza dei ricordi.

    Il riconoscimento e' preciso: non basta che una prova NOMINI la costante
    (`test_memoria_interpretazione.py` lo faceva gia', e pinnava la sola
    versione Python -- non avrebbe visto nessuna divergenza). Serve che il
    file di prova nomini la costante E legga un `.js`: e' l'unica forma in cui
    puo' confrontarli davvero.
    """
    legate: set[str] = set()
    for p in test:
        testo = leggi(p)
        if ".js" not in testo:
            continue
        try:
            albero = ast.parse(testo)
        except SyntaxError:
            continue
        # I nomi si leggono dal CODICE, non dal testo grezzo: una costante
        # NOMINATA in una docstring non e' un legame. Ci sono cascato subito --
        # le prove di questo stesso strumento citano `VOCABOLARIO` a parole, e
        # tanto bastava a farlo passare per legato, cioe' a spegnere il
        # rilevatore proprio sul difetto per cui e' nato.
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Name) and _RE_COSTANTE.fullmatch(nodo.id):
                legate.add(nodo.id)
            elif isinstance(nodo, ast.alias) and _RE_COSTANTE.fullmatch(nodo.name):
                legate.add(nodo.name)
            elif isinstance(nodo, ast.Attribute) and _RE_COSTANTE.fullmatch(nodo.attr):
                legate.add(nodo.attr)
    return legate


def cerca_vocabolari_paralleli(files: list[Path], js: list[Path],
                               test: list[Path] | None = None) -> list[Reperto]:
    """Un vocabolario chiuso Python i cui membri compaiono TUTTI in un file JS.

    E' il controllo che trova il difetto peggiore della review: le quattro
    forze di un ricordo vivevano in `interpretazione.py` e -- due volte -- in
    `memoria-route.js`, senza niente che le legasse. Una quinta forza faceva
    ricadere la tendina su vuoto, e salvare una correzione qualunque
    CANCELLAVA la forza del ricordo.

    Si richiede che ci siano TUTTI: due o tre parole in comune capitano per
    caso (`"area"`, `"nome"`), l'insieme intero no. E si guarda solo la
    presenza come stringa quotata, non l'ordine: un vocabolario riordinato non
    e' un vocabolario diverso.
    """
    testi_js = {p: leggi(p) for p in js}
    legate = _costanti_gia_legate(test or [])
    dichiarate: dict[Path, set[int]] = {}
    # Raggruppati per INSIEME DI MEMBRI, non per costante.
    #
    # Al primo giro questo controllo ha prodotto dieci righe per una causa
    # sola: sette costanti Python diverse -- `_VALID_BACKENDS`, `_OSPITI`,
    # `DISPLAY_NAMES`, `FIXED_ORDER`, ... -- costruite tutte sugli stessi cinque
    # identificatori di provider, piu' la pagina che li nomina per renderli.
    # Dieci righe da leggere per decidere una cosa sola sono gia' il rumore
    # che questo strumento esiste per non produrre: il fatto e' «il
    # vocabolario dei provider vive di qua e di la'», e va detto una volta,
    # con dentro tutti i posti.
    per_membri: dict[tuple, dict] = {}
    for p in files:
        for nome, riga, membri in _vocabolari_python(p):
            if _dichiarato(p, riga, dichiarate) or nome.split("[")[0] in legate:
                continue
            for q, testo in testi_js.items():
                if all(_presente_nel_js(m, testo) for m in membri):
                    chiave = tuple(sorted(set(membri)))
                    voce = per_membri.setdefault(chiave, {"nomi": [], "dove": set()})
                    voce["nomi"].append(nome)
                    voce["dove"].add(f"{rel(p)}:{riga}")
                    voce["dove"].add(rel(q))
                    break
    reperti = []
    for membri, voce in per_membri.items():
        nomi = sorted(set(voce["nomi"]))
        quante = f"{len(nomi)} costanti Python" if len(nomi) > 1 else nomi[0]
        reperti.append(Reperto(
            "vocabolario-parallelo",
            "{" + ", ".join(membri) + "}",
            sorted(voce["dove"]),
            f"{quante}: {', '.join(nomi)}" if len(nomi) > 1 else
            f"{len(membri)} membri, tutti presenti nel JavaScript"))
    return sorted(reperti, key=lambda r: r.nome)


# ── 4. Predefiniti ripetuti ─────────────────────────────────────────────────

def _predefiniti(p: Path) -> list[tuple[str, str, int]]:
    """`(chiave, valore, riga)` per ogni `.get("chiave", VALORE)` letterale.

    Solo `.get` con un default letterale: e' la forma in cui i predefiniti si
    disperdono davvero (`.get("tetto_giornaliero", 50)` in un modulo e `50`
    nel dizionario dei predefiniti di un altro).
    """
    try:
        albero = ast.parse(leggi(p))
    except SyntaxError:
        return []
    trovati = []
    for nodo in ast.walk(albero):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "get" and len(nodo.args) == 2):
            continue
        chiave, predefinito = nodo.args
        if not (isinstance(chiave, ast.Constant) and isinstance(chiave.value, str)):
            continue
        if not (isinstance(predefinito, ast.Constant)
                and isinstance(predefinito.value, (int, float, str))
                and predefinito.value not in ("", 0, False)):
            continue
        trovati.append((chiave.value, repr(predefinito.value), nodo.lineno))
    return trovati


def cerca_predefiniti(files: list[Path]) -> list[Reperto]:
    """La stessa chiave con lo stesso predefinito letterale in piu' file.

    E' la forma del «debito F»: `scadenza_min` valeva 5 in quattro punti, e il
    giorno in cui uno dei quattro fosse cambiato gli altri tre avrebbero
    continuato a tagliare i turni a una soglia che la pagina non mostra piu'.

    Un predefinito vuoto (`""`, `0`, `False`) non si segnala: e' il «niente»,
    e capita ovunque per ragioni scollegate fra loro.
    """
    per_chiave: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    dichiarate: dict[Path, set[int]] = {}
    for p in files:
        for chiave, valore, riga in _predefiniti(p):
            if _dichiarato(p, riga, dichiarate):
                continue
            per_chiave[(chiave, valore)].append(f"{rel(p)}:{riga}")
    return [
        Reperto("predefinito-ripetuto", f"{chiave} = {valore}", sorted(dove))
        for (chiave, valore), dove in sorted(per_chiave.items())
        if len({d.split(":")[0] for d in dove}) > 1
    ]


# ── Rapporto ────────────────────────────────────────────────────────────────

_LIMITI = """
I limiti di questo strumento, dichiarati:
  - DUE FUNZIONI CHE RISPONDONO ALLA STESSA DOMANDA CON CODICE DIVERSO non si
    vedono. E' il caso peggiore -- la mappa aree di `entity_cache` contro
    `gerarchia()`, che per giunta rispondeva peggio -- e non e' rilevabile
    staticamente: sono due algoritmi, e nessuna impronta li avvicina. Resta
    agli occhi, e resta la ragione per cui la review a mano non e' facoltativa;
  - una regola duplicata in PROSA, dentro i commenti, non si distingue
    meccanicamente da un commento che la spiega;
  - sotto le due istruzioni le funzioni non si confrontano: `return x` e
    `return y` sono la stessa forma per costruzione. Le sei letture del
    dominio, che erano il caso vero, avevano UNA riga -- questo controllo non
    le avrebbe trovate;
  - i vocabolari paralleli si cercano solo fra Python e JavaScript, e solo per
    presenza dei membri: due vocabolari Python identici in due moduli non si
    vedono (li vede il censimento, se uno dei due e' orfano). Un vocabolario
    gia' LEGATO da una prova che confronta Python e JavaScript non si segnala:
    li' la divergenza non e' silenziosa, ed e' il silenzio il difetto;
  - i predefiniti si cercano solo nella forma `.get("chiave", VALORE)`. Un
    predefinito passato come argomento di funzione o scritto in un dizionario
    non si vede;
  - le duplicazioni fra Python e YAML o shell (`config.yaml`, `run.sh`) sono
    del censimento, non di qui."""


def stampa(reperti: list[Reperto], dichiarati: list[str]) -> None:
    if not reperti:
        print(f"{VERDE}Nessun doppione non dichiarato.{RESET}")
    for categoria, titolo in _TITOLI.items():
        gruppo = [r for r in reperti if r.categoria == categoria]
        if not gruppo:
            continue
        print(f"\n{GIALLO}{len(gruppo):3d}{RESET}  {titolo}")
        for r in gruppo:
            nota = f"  {GRIGIO}{r.nota}{RESET}" if r.nota else ""
            print(f"       {r.nome}{nota}")
            for dove in r.dove:
                print(f"         {GRIGIO}{dove}{RESET}")

    if dichiarati:
        print(f"\n{GRIGIO}Doppioni DICHIARATI e quindi saltati: {len(dichiarati)}{RESET}")
        for d in dichiarati:
            print(f"  {GRIGIO}{d}{RESET}")

    print(f"{GRIGIO}{_LIMITI}{RESET}")
    print(f"\nTotale reperti: {len(reperti)}")


def _elenco_dichiarati(files: list[Path]) -> list[str]:
    """Dove sono i marcatori, per dichiararli invece che nasconderli.

    Uno strumento che filtra in silenzio e' un altro modo di mentire: se
    domani qualcuno mettesse un marcatore per far tacere un doppione vero,
    questa riga lo mostrerebbe a chiunque legga il rapporto.
    """
    trovati = []
    for p in files:
        for riga, testo in sorted(commenti_di(p).items()):
            if MARCATORE in testo:
                ragione = testo.split(MARCATORE, 1)[1].lstrip(": ").strip()
                trovati.append(f"{rel(p)}:{riga}  {ragione or '(senza ragione scritta)'}")
    return trovati


def run(cancello: bool = False) -> int:
    py = file_py(APP)
    js = file_js()
    reperti = cerca_regex(py)
    reperti += cerca_funzioni_gemelle(py)
    reperti += cerca_vocabolari_paralleli(py, js, file_py(TESTS))
    reperti += cerca_predefiniti(py)
    stampa(reperti, _elenco_dichiarati(py))
    return 1 if (cancello and reperti) else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cancello", action="store_true",
        help="esce 1 se trova un doppione non dichiarato (per il pre-push)")
    sys.exit(run(parser.parse_args().cancello))


if __name__ == "__main__":
    main()
