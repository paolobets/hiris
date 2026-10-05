"""La specie «attuatore» si scrive in un posto solo: `steering` (C-28).

Il letterale si cerca nell'albero sintattico di ogni modulo del prodotto (le
stringhe, non i commenti: un commento che nomina l'attuatore non e' un
doppione). Il valore da cercare si CHIEDE a `steering.ACTUATOR_SPECIES`, i
file alla cartella: nessun elenco ricopiato (CLAUDE.md, I-0).

Mutazione ESEGUITA (05/10/2026): rimesso `specie="attuatore"` nella misura del
turno in `server.py` -- rossa, col file e la riga.
"""
import ast
from pathlib import Path

from hiris.app import steering

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


def _modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p.name != "steering.py"
                  or p.parent != APP)


def _literals(value: str) -> list[str]:
    found = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == value:
                found.append(f"{path.relative_to(APP)}:{node.lineno}")
    return found


def test_specie_attuatore_appartiene_specie():
    assert steering.ACTUATOR_SPECIES in steering.SPECIE


def test_specie_attuatore_non_si_ricopia_fuori_steering():
    copie = _literals(steering.ACTUATOR_SPECIES)
    assert copie == [], (
        "«attuatore» scritto come letterale invece di "
        f"`steering.ACTUATOR_SPECIES`: {copie}")


def test_derivazione_guarda_prodotto():
    """La prova della derivazione: i moduli ci sono, e il letterale si trova
    dove c'e' (in `steering` stesso, escluso dalla ricerca qui sopra)."""
    assert len(_modules()) > 100
    assert any(isinstance(n, ast.Constant) and n.value == steering.ACTUATOR_SPECIES
               for n in ast.walk(ast.parse((APP / "steering.py").read_text(
                   encoding="utf-8"))))
