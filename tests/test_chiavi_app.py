"""Le chiavi di `app` sono `web.AppKey`, mai stringhe (X-32, Chiusura dello sprint).

Fino al 14/10/2026 nessuna delle sessanta e piu' chiavi di `app` era una
`web.AppKey`: ognuna era una stringa scritta in ogni punto che la leggeva, e
aiohttp lo segnala con un avviso a ogni scrittura. Una stringa sbagliata in un
lettore non e' un errore: e' un `None` silenzioso (`app.get("observation")`).
Una `web.AppKey` vive nel modulo che la possiede, e chi la sbaglia scrive un
nome che non esiste -- `NameError` all'import, non un `None` a meta' giro.

**Il cancello, chiesto al sorgente.** Per ogni modulo di `hiris/app`: nessuna
lettura o scrittura di `app` con una chiave stringa (`app["x"]`,
`app.get("x")`, `app.setdefault("x", ...)`, `app.pop("x")`, `"x" in app`), e
ogni costante MAIUSCOLA usata come chiave e' davvero una `web.AppKey`
dichiarata da un modulo del prodotto (`_NOMI_LEGALI` le chiede ai moduli).
"App" e' il nome `app`, ogni nome che finisce in `_app`, e l'attributo `.app`
(`request.app`) o `.config_dict`.

**Cosa non vede, dichiarato.** Una chiave passata per variabile (`app[key]`,
in `api/shell.py` e `api/servizi.py`) non si giudica dal testo: il valore viene
da una tupla di costanti accanto, che questo cancello vede quando sono usate
come chiave altrove, non li'. Un'app con un altro nome (`casa`, `ctx`) non e'
vista: nel prodotto non ce n'e' nessuna, misurato il 14/10/2026.
"""
import ast
import functools
import importlib
import pathlib

from aiohttp import web

RADICE = pathlib.Path(__file__).resolve().parents[1]
APP = RADICE / "hiris" / "app"


def _is_app(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.Name):
        return nodo.id in ("app", "application") or nodo.id.endswith("_app")
    if isinstance(nodo, ast.Attribute):
        return nodo.attr in ("app", "config_dict")
    return False


def chiavi_usate(albero: ast.AST) -> list[tuple[int, ast.AST]]:
    """`(riga, nodo della chiave)` per ogni lettura o scrittura di `app`."""
    trovate = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Subscript) and _is_app(nodo.value):
            trovate.append((nodo.lineno, nodo.slice))
        elif (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
              and nodo.func.attr in ("get", "setdefault", "pop")
              and _is_app(nodo.func.value) and nodo.args):
            trovate.append((nodo.lineno, nodo.args[0]))
        elif (isinstance(nodo, ast.Compare) and len(nodo.ops) == 1
              and isinstance(nodo.ops[0], (ast.In, ast.NotIn))
              and _is_app(nodo.comparators[0])):
            trovate.append((nodo.lineno, nodo.left))
    return trovate


def _moduli() -> dict[str, ast.AST]:
    return {percorso.relative_to(APP).as_posix(): ast.parse(percorso.read_text(encoding="utf-8"))
            for percorso in sorted(APP.rglob("*.py")) if "__pycache__" not in percorso.parts}


@functools.cache
def _nomi_legali() -> frozenset[str]:
    """I nomi che un modulo del prodotto lega a una `web.AppKey`: chiesti ai
    moduli importati, non elencati qui."""
    nomi = set()
    for percorso in sorted(APP.rglob("*.py")):
        if "__pycache__" in percorso.parts:
            continue
        modulo = importlib.import_module(
            ".".join(percorso.relative_to(RADICE).with_suffix("").parts))
        nomi |= {nome for nome, valore in vars(modulo).items()
                 if isinstance(valore, web.AppKey)}
    return frozenset(nomi)


def difetti(moduli: dict[str, ast.AST]) -> list[str]:
    trovati = []
    for dove, albero in moduli.items():
        for riga, chiave in chiavi_usate(albero):
            if isinstance(chiave, ast.Constant) and isinstance(chiave.value, str):
                trovati.append(f"{dove}:{riga}: chiave stringa {chiave.value!r}")
            elif (isinstance(chiave, ast.Name) and chiave.id.isupper()
                  and chiave.id not in _nomi_legali()):
                trovati.append(f"{dove}:{riga}: {chiave.id} non e' una web.AppKey")
    return trovati


def test_il_cancello_riconosce_le_forme():
    albero = ast.parse(
        'a = app["x"]\nb = request.app.get("y")\nc = "z" in app\n'
        'd = cfg_app.setdefault("w", 1)\ne = app[OBSERVATIONS_KEY]\n'
        'f = altro["x"]\ng = app[STRANA]\n')
    assert difetti({"prova.py": albero}) == [
        "prova.py:1: chiave stringa 'x'", "prova.py:2: chiave stringa 'y'",
        "prova.py:3: chiave stringa 'z'", "prova.py:4: chiave stringa 'w'",
        "prova.py:7: STRANA non e' una web.AppKey"]


def test_nessuna_chiave_di_app_e_una_stringa():
    """Mutazione ESEGUITA (14/10/2026): `app.get(OBSERVATIONS_KEY)` rimessa come
    `app.get("observations")` in `mind/view.py` -- rossa, col file e la riga."""
    moduli = _moduli()
    usi = sum(len(chiavi_usate(albero)) for albero in moduli.values())
    # Piu' di quattrocento, misurati il 14/10/2026: un pavimento, non un conto.
    # Sotto, il cancello ha smesso di guardare.
    assert usi >= 300, f"il cancello vede solo {usi} usi di app: la derivazione si e' rotta"
    assert len(_nomi_legali()) >= 50, sorted(_nomi_legali())
    assert not difetti(moduli), "\n".join(difetti(moduli))
