"""La cartella dei dati si legge in un modo solo: `app["data_dir"]` (D-27).

Fino alla Tappa 8 si leggeva in quattro forme -- `app["data_dir"]`,
`app.get("data_dir")`, `app.get("data_dir", "/data")`, e una guardia `if not
data_dir` a valle -- che divergevano sulla stringa vuota e sull'app che non
l'aveva: una forma ripiegava sulla cartella di produzione, un'altra taceva.
L'avvio la scrive per prima (`server._on_startup`, da `HIRIS_DATA_DIR`), e
da li' in poi c'e' sempre: un ripiego non protegge niente, nasconde
un'app montata male.

Il cancello: nessuna chiamata `.get("data_dir", ...)` nel prodotto.
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
KEY = "data_dir"


def _is_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == KEY


def readings(tree: ast.AST) -> tuple[int, int]:
    """`(letture col ripiego, letture dirette)` della chiave in un albero:
    `x.get("data_dir", ...)` contro `x["data_dir"]`."""
    soft = direct = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args and _is_key(node.args[0])):
            soft += 1
        elif isinstance(node, ast.Subscript) and _is_key(node.slice):
            direct += 1
    return soft, direct


def _product() -> dict[str, ast.AST]:
    return {path.relative_to(ROOT).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
            for path in sorted(APP.rglob("*.py"))}


def test_il_cancello_riconosce_le_due_forme():
    tree = ast.parse('a = app.get("data_dir")\nb = app.get("data_dir", "/data")\n'
                     'c = app["data_dir"]\nd = cfg.get("altro")\n')
    assert readings(tree) == (2, 1)


def test_nessuna_lettura_della_cartella_col_ripiego():
    """Mutazione ESEGUITA (08/10/2026): rimesso `app.get("data_dir")` in
    `reasoning/consegna.close_expired_promise` -- rossa, col file."""
    found = {where: readings(tree) for where, tree in _product().items()}
    soft = {where: n for where, (n, _direct) in found.items() if n}
    direct = sum(d for _soft, d in found.values())
    # Diciassette letture dirette, misurate l'08/10/2026: un pavimento, non
    # un conto -- sotto, il cancello ha smesso di guardare.
    assert direct >= 10, f"il cancello non vede piu' le letture dirette ({direct})"
    assert not soft, f"la cartella dei dati letta col ripiego: {soft}"
