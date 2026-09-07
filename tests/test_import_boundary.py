"""Il prodotto si importa da se' con percorsi RELATIVI, mai col nome del repo.

Nel container l'add-on e' installato sotto `/usr/lib/hiris/app/` e girato come
pacchetto `app`: il nome `hiris` **non esiste**. Un `from hiris.app...` funziona
qui -- dove la radice del repo e' nel percorso e `hiris` E' un pacchetto -- e
muore all'avvio in produzione con `ModuleNotFoundError: No module named 'hiris'`,
**prima di qualunque riga di log dell'applicazione**.

E' successo davvero: una riga sola in `home_space/appointments.py` ha impedito
l'avvio della **v3.22.0** sulla casa vera (07/09/2026), e nessuna delle 3.465
prove l'ha vista -- perche' tutte girano da qui, dove quell'import funziona.
La suite non poteva accorgersene guardando il comportamento: doveva guardare la
FORMA. Questo file e' quel cancello.

**Perche' non basta il linter**: `ruff` non conosce il nome sotto cui il
pacchetto verra' installato, quindi per lui `from hiris.app.x import y` e'
un import assoluto legittimo come un altro.
"""
from __future__ import annotations

import ast
import pathlib

_PRODUCT = pathlib.Path(__file__).parent.parent / "hiris"


def _absolute_self_imports(tree: ast.AST) -> list[str]:
    """I nomi importati con `hiris...` in forma assoluta.

    `ast.ImportFrom` con `level > 0` e' relativo (`from .x`, `from ..y`) e non
    ci riguarda: quella e' la forma giusta.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] == "hiris":
                found.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "hiris":
                    found.append(f"import {alias.name}")
    return found


def test_the_product_never_imports_itself_by_the_repository_name():
    """Nel container il pacchetto si chiama `app`, non `hiris`: un import
    assoluto col nome del repo e' un avvio che non parte, e la suite non lo
    vede perche' qui quel nome esiste.

    Mutazione: rimettere `from hiris.app.home_space.historian import
    home_space_zone` in `hiris/app/home_space/appointments.py` -- il test
    torna rosso su `assert colpevoli == []`, nominando il file e la riga.
    """
    colpevoli: list[str] = []
    for sorgente in sorted(_PRODUCT.rglob("*.py")):
        tree = ast.parse(sorgente.read_text(encoding="utf-8"), filename=str(sorgente))
        for riga in _absolute_self_imports(tree):
            colpevoli.append(f"{sorgente.relative_to(_PRODUCT.parent)}: {riga}")
    assert colpevoli == [], (
        "il prodotto importa se stesso col nome del repository: nel container "
        "quel nome non esiste e l'avvio muore prima del primo log. "
        "Usa un import relativo (`from .x import y`). Trovati: " + "; ".join(colpevoli))


def test_the_guard_recognises_the_shape_it_forbids():
    """La prova sopra e' verde quando il prodotto e' pulito -- cioe' quasi
    sempre -- e una prova che passa perche' non c'e' niente da trovare non
    dimostra di saper trovare. Qui la si mette davanti alla forma vietata e
    alle due forme lecite, su sorgenti scritti a mano.

    Mutazione: togliere il controllo su `node.level == 0` in
    `_absolute_self_imports` -- il test torna rosso su
    `assert _absolute_self_imports(ast.parse(relativo)) == []`, perche' un
    import relativo verrebbe scambiato per assoluto.
    """
    vietato = "from hiris.app.home_space.historian import home_space_zone"
    relativo = "from .historian import home_space_zone"
    risalita = "from ..proxy.ha_client import HAClient"
    estraneo = "from datetime import datetime"

    assert _absolute_self_imports(ast.parse(vietato)) == [
        "from hiris.app.home_space.historian import ..."]
    assert _absolute_self_imports(ast.parse("import hiris.app.server")) == [
        "import hiris.app.server"]
    assert _absolute_self_imports(ast.parse(relativo)) == []
    assert _absolute_self_imports(ast.parse(risalita)) == []
    assert _absolute_self_imports(ast.parse(estraneo)) == []
