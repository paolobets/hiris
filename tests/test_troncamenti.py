"""Un testo tagliato si dichiara in un modo solo: `truncate_with_marker` (C-55).

Fino al 05/10/2026 cinque punti tagliavano a mano con un marcatore proprio
(«…», «…[troncato]») accanto alla funzione della casa, che scrive
« [troncato]» e tiene il marcatore DENTRO il tetto. Due marcatori per lo
stesso fatto, e tetti superati di un carattere.

La prova scorre l'albero di ogni modulo del prodotto (la cartella, non un
elenco) e cerca la forma del taglio a mano: una fetta di testo
(`testo[:n]`, anche ripulita, `testo[:n].rstrip()`) a cui si attacca un
letterale o una costante. Fuori da `proxy/_sanitize.py`, che e' la casa del taglio, e' una
copia.

Mutazione ESEGUITA (05/10/2026): rimesso `text[:MESSAGE_MAX - 1] + "…"` in
`house_history._short` -- rossa, col file e la riga.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
HOME = "proxy/_sanitize.py"


def _is_cut(node: ast.AST) -> bool:
    """Una fetta dall'inizio (`x[:n]`), anche dentro una chiamata su di lei."""
    return any(isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Slice)
               and sub.slice.lower is None and sub.slice.upper is not None
               for sub in ast.walk(node))


def _is_marker(node: ast.AST) -> bool:
    """Cio' che si attacca al taglio: un letterale, o una costante col nome
    (come `_TRUNCATED` nella casa)."""
    return ((isinstance(node, ast.Constant) and isinstance(node.value, str))
            or isinstance(node, ast.Name))


def _cuts() -> list[str]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                    and _is_marker(node.right) and _is_cut(node.left)):
                found.append(f"{path.relative_to(APP).as_posix()}:{node.lineno}")
    return found


def test_nessun_troncamento_mano():
    copie = [c for c in _cuts() if not c.startswith(HOME + ":")]
    assert copie == [], f"un taglio scritto a mano invece di truncate_with_marker: {copie}"


def test_derivazione_trova_taglio_casa():
    """La prova della derivazione: il taglio vero, in `_sanitize`, si trova."""
    assert [c for c in _cuts() if c.startswith(HOME + ":")]
