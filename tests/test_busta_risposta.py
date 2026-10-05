"""La busta di una risposta di selezione si monta in un posto solo (C-31).

`trovate`, `escluse`, `profondita`, `voci` (e la `nota` sulle escluse) sono la
forma che `search` e `history` danno a ogni risposta. Fino al 05/10/2026 il
dizionario era scritto a mano in tre posti (`house_query.search`,
`house_history._frame`, la lettura del registro di sistema): tre copie della
stessa forma, libere di divergere alla prima chiave aggiunta a una sola.

La prova scorre l'albero di ogni modulo del prodotto (la cartella, non un
elenco) e cerca un dizionario letterale che porti insieme le quattro chiavi:
fuori da `house_query.envelope` e' una copia.

Mutazione ESEGUITA (05/10/2026): rimesso il dizionario a mano in
`house_history._frame` -- rossa, col file e la riga.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
ENVELOPE_KEYS = {"trovate", "escluse", "profondita", "voci"}
HOME = ("home_space/house_query.py", "envelope")


def _envelopes() -> list[tuple[str, str, int]]:
    """`(modulo, funzione, riga)` di ogni dizionario letterale con le quattro
    chiavi della busta."""
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.Dict):
                    continue
                keys = {k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                if ENVELOPE_KEYS <= keys:
                    found.append((path.relative_to(APP).as_posix(), function.name,
                                  node.lineno))
    return found


def test_busta_montata_solo_envelope():
    copie = [f"{module}:{line} ({name})" for module, name, line in _envelopes()
             if (module, name) != HOME]
    assert copie == [], f"la busta di una risposta montata a mano: {copie}"


def test_derivazione_trova_busta():
    """La prova della derivazione: la busta vera si trova, quindi la ricerca
    guarda davvero dove la busta vive."""
    assert [(m, n) for m, n, _line in _envelopes()].count(HOME) == 1
