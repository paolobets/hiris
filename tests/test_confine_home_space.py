"""`home_space` non importa da `mind`: la conoscenza sta sotto, il cervello sopra.

La regola era scritta (`home_space/historian.py` la dichiara) e nessuno la
controllava: il 03/10/2026 il piano della Tappa 3 ha contato tre importazioni
al contrario -- `house_history` prendeva `integration_of` da `mind/report.py`,
`queries` prendeva `type_subject` e `MEANING_FIELD` da `mind/knowledge.py`,
dentro una funzione (B-35). Il 04/10/2026 (Task 7) le due regole sono
traslocate in `home_space` (`log_source.py`, `type_judgments.py`) e questo
cancello e' nato.

I moduli si CHIEDONO alla cartella, e le importazioni si cercano per albero
sintattico in tutto il corpo, funzioni comprese: un'importazione dentro una
funzione e' la stessa dipendenza, solo meno visibile. Le eccezioni sono una
lista di AMMISSIONE, ognuna con la ragione, e possono solo diminuire.

Mutazione ESEGUITA: in `home_space/queries.py` aggiunto
`from ..mind.report import as_page` dentro `_class_meaning` -- rossa
(`home_space/queries.py` fra i trasgressori).
Mutazione ESEGUITA: tolta l'importazione di `integration_of` da
`home_space/house_history.py` (nella copia di lavoro, non nel commit) -- rossa
(l'eccezione ammessa non serve piu', e il cancello lo dice).
"""
import ast
from pathlib import Path

from hiris.app import home_space

FOLDER = Path(home_space.__file__).resolve().parent
APP = FOLDER.parent

#: I moduli di `home_space` AMMESSI a importare da `mind`, con la ragione.
AMMESSI = {
    # `integration_of` e' traslocata in `home_space/log_source.py` il
    # 04/10/2026 (B-35), ma questo file era riservato alla fetta di `House`
    # (Tappa 3, Task 1 e seguenti) e il brief chiedeva di non toccarlo:
    # `mind/report.py` la riesporta. Il giorno che lo si apre, l'import passa
    # a `.log_source` e questa riga esce.
    "house_history.py",
}


def _imports_mind(tree) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 2 and (module == "mind" or module.startswith("mind.")):
                return True
            if module == "hiris.app.mind" or module.startswith("hiris.app.mind."):
                return True
            # `from .. import mind`
            if node.level == 2 and not module and any(a.name == "mind" for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.startswith("hiris.app.mind") for a in node.names):
                return True
    return False


def _modules() -> list[Path]:
    return sorted(FOLDER.rglob("*.py"))


def test_la_cartella_si_legge():
    # Un cancello che non trova moduli guarda il vuoto e resta verde.
    names = {p.name for p in _modules()}
    assert {"briefing.py", "queries.py", "type_judgments.py", "log_source.py"} <= names


def test_home_space_non_importa_da_mind():
    offenders = {p.relative_to(FOLDER).as_posix() for p in _modules()
                 if _imports_mind(ast.parse(p.read_text(encoding="utf-8")))}
    assert offenders == AMMESSI, (
        "home_space importa da mind (o un'eccezione ammessa non serve piu'): "
        f"{sorted(offenders)} contro {sorted(AMMESSI)}")


def test_il_rilevatore_vede_le_forme():
    for source in ("from ..mind.report import x", "from ..mind import report",
                   "from .. import mind", "import hiris.app.mind.knowledge",
                   "def f():\n    from ..mind.knowledge import y\n"):
        assert _imports_mind(ast.parse(source)), source
    for source in ("from .mind_like import x", "from ..memory import y",
                   "from . import queries"):
        assert not _imports_mind(ast.parse(source)), source
