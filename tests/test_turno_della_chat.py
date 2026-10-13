"""La chat chiama la catena da un posto solo (D-17; Chiusura, 13/10/2026).

Il ramo sincrono e il ripiego a scadenza del ponte scrivevano ognuno i
dodici argomenti di `chain_turn`, la rete sul runner che solleva e la
scrittura della risposta: due copie che erano gia' divergenti (il
`thinking_budget`, la scrittura in cronologia). Ora le chiama
`_chain_chat_turn`, e questa prova lo chiede all'albero del sorgente.
"""
import ast
from pathlib import Path

_HANDLERS = (Path(__file__).resolve().parents[1] / "hiris" / "app" / "api"
             / "handlers_chat.py")


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", None)) == name]


def test_chain_turn_si_chiama_una_volta_sola_nella_chat():
    """Mutazione ESEGUITA il 13/10/2026: il ripiego a scadenza che torna a
    chiamare `chain_turn` da se' -- rossa."""
    tree = ast.parse(_HANDLERS.read_text(encoding="utf-8"))
    assert len(_calls(tree, "chain_turn")) == 1
    # Le due strade che fanno un turno di chat sulla catena.
    assert len(_calls(tree, "_chain_chat_turn")) == 2
