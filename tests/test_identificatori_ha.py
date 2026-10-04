"""La forma di un `entity_id` e il suo dominio: una casa sola ciascuno (B-24).

Tappa 3, Task 7, 04/10/2026. Prima di quel giorno l'espressione dell'id viveva
in tre copie (client, osservatore, plance) piu' una quarta che importava il
nome privato del client; tre la provavano con `.match`, che con l'ancora `$`
accetta un `\\n` finale, la quarta con `.fullmatch`. E il dominio si ricavava in
linea (`split(".")[0]`) in dodici punti accanto a `domain_of`.

Il cancello sul dominio CHIEDE i file alla cartella del prodotto e cerca la
FORMA per albero sintattico (un `split(".")`/`partition(".")` preso all'indice
0): nessun elenco di file da ricopiare. Le eccezioni sono una lista di
AMMISSIONE, ognuna con la ragione, e possono solo diminuire.

Mutazione ESEGUITA: in `mind/facts.py::_is_on` rimesso
`domain = subject.split(".")[0]` -- rossa (`mind/facts.py` fra i file con un
dominio in linea).
Mutazione ESEGUITA: `ENTITY_ID_SHAPE.fullmatch` -> `.match` con l'ancora `$`
rimessa nell'espressione -- rossa sul `\\n` finale.
"""
import ast
from pathlib import Path

from hiris.app.home_space import ha_vocabulary
from hiris.app.home_space.ha_vocabulary import domain_of, is_entity_id

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

#: Chi possiede la lettura: il modulo della funzione, chiesto alla funzione.
OWNER = Path(ha_vocabulary.__file__).resolve().relative_to(APP).as_posix()

#: Le copie in linea AMMESSE, file -> quante, con la ragione. Chiude per
#: difetto: una copia nuova e' rossa finche' qualcuno non la scrive qui.
AMMESSE = {
    # File in mano alla fetta di `House` (Tappa 3, Task 1 e seguenti) mentre
    # questo task girava: il brief del 04/10/2026 chiedeva di non toccarli.
    # Escono quando `House` li libera.
    "home_space/house_history.py": 3,
    "home_space/house_query.py": 1,
    # Non sono entity_id: sono i nomi dei logger di Home Assistant
    # (`homeassistant.components.hydrawise`), che hanno un'altra grammatica.
    "mind/report.py": 2,
}


def _inline_domains(tree) -> int:
    """Quante volte `x.split(".")[0]`, `x.split(".", 1)[0]` o
    `x.partition(".")[0]` compaiono nell'albero."""
    found = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant) and node.slice.value == 0):
            continue
        call = node.value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr in ("split", "partition")
                and call.args and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == "."):
            found += 1
    return found


def _counts() -> dict[str, int]:
    counts = {}
    for path in sorted(APP.rglob("*.py")):
        found = _inline_domains(ast.parse(path.read_text(encoding="utf-8")))
        if found:
            counts[path.relative_to(APP).as_posix()] = found
    return counts


def test_il_dominio_si_chiede_a_domain_of():
    counts = _counts()
    owned = counts.pop(OWNER, 0)
    assert owned == 1, (
        f"il cancello non vede piu' la lettura nel suo proprietario ({OWNER}: "
        f"{owned}): la ricerca della forma si e' rotta, e guarderebbe il vuoto")
    assert counts == AMMESSE, (
        "dominio ricavato in linea fuori da `ha_vocabulary.domain_of` "
        f"(o un'eccezione che non serve piu'): {counts} contro {AMMESSE}")


def test_l_id_si_prova_intero():
    assert is_entity_id("light.cucina")
    assert not is_entity_id("light.cucina\n")
    assert not is_entity_id("Light.cucina")
    assert not is_entity_id("light")
    assert not is_entity_id(None)


def test_l_espressione_vive_in_un_posto_solo():
    text = ha_vocabulary.ENTITY_ID_SHAPE.pattern
    copies = [path.relative_to(APP).as_posix() for path in sorted(APP.rglob("*.py"))
              if text in path.read_text(encoding="utf-8")]
    assert copies == [OWNER], copies


def test_domain_of_su_un_id_senza_punto_rende_l_id():
    assert domain_of("sensor.x.y") == "sensor"
    assert domain_of("rotto") == "rotto"
