"""B-22 (Tappa 8, D8): i nomi dei campi del sapere vivono in un modulo solo,
`home_space/type_judgments.py`, e fuori da li' non si scrivono per esteso.

**Il cancello CHIEDE i suoi elenchi** (CLAUDE.md, I-0):

- i nomi dei campi li chiede a `type_judgments.KNOWLEDGE_FIELD_NAMES`;
- le porte dell'archivio che ricevono un campo le chiede alle FIRME di
  `KnowledgeStore` (un parametro `field` o `fields`), non a una lista;
- le migrazioni le riconosce dal nome (`_migration_<n>`), che e' come
  `storage.init_schema` le riceve.

**Dove guarda** -- le tre forme in cui un campo del sapere si nomina in
`hiris/app`: la parola chiave `field=` (un `Fact`), l'argomento `field` o
`fields` di una porta di `KnowledgeStore` (`store.get("tipo", s, "significato")`),
e il testo SQL `field = '...'` / `field IN (...)`.

**Cosa NON vede, dichiarato**: un nome che arriva da una variabile, e le
chiavi delle risposte HTTP (`detail["significato"]` in `queries`), che sono
un'altra cosa -- la parola con cui una porta consegna un dato, non il nome di
un campo dell'archivio. Ne' il JavaScript della pagina, che traduce i campi in
etichette (`static/config/watcher-sapere.js`).

**Le ammissioni** chiudono per difetto: una voce nuova e' vietata finche'
qualcuno non la scrive qui, con la ragione.

Mutazioni ESEGUITE (08/10/2026): in `home_space/queries.py`
`knowledge.get("tipo", "sensor", "significato")` -- rossa; in
`mind/recipe_turn.py` `field="ricetta"` al posto di `field=RECIPE_FIELD` --
rossa; in `mind/knowledge.py` una query `WHERE field = 'attributi'` fuori da una
migrazione -- rossa; una costante `*_FIELD` nuova in `type_judgments` fuori da
`KNOWLEDGE_FIELD_NAMES` -- rossa la prova della derivazione.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import re

from hiris.app.home_space import type_judgments
from hiris.app.home_space.type_judgments import KNOWLEDGE_FIELD_NAMES
from hiris.app.mind.knowledge import KnowledgeStore

RADICE = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"
CASA = "home_space/type_judgments.py"

#: Le funzioni, fuori dalle `_migration_<n>`, che scrivono un nome per esteso,
#: con la ragione. (file, funzione) -> perche'.
AMMESSI = {
    ("mind/knowledge.py", "_drop_unrunnable_recipes"): (
        "e' il corpo condiviso delle migrazioni 4, 5 e 6: una migrazione deve "
        "dire fra due anni la stessa cosa che dice adesso, anche se la costante "
        "venisse rinominata"),
}

_MIGRATION = re.compile(r"_migration_\d+$")


def _porte() -> dict[str, tuple[int, str]]:
    """Le porte di `KnowledgeStore` che ricevono un campo: nome -> (posizione
    dell'argomento senza `self`, nome del parametro). Chieste alle firme."""
    porte = {}
    for name, member in inspect.getmembers(KnowledgeStore, inspect.isfunction):
        params = [p for p in inspect.signature(member).parameters if p != "self"]
        for wanted in ("field", "fields"):
            if wanted in params:
                porte[name] = (params.index(wanted), wanted)
    return porte


def _nomi_in(node) -> list[str]:
    """I nomi di campo scritti per esteso dentro `node`: una stringa, o una
    tupla/lista/insieme di stringhe."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if node.value in KNOWLEDGE_FIELD_NAMES else []
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [n for e in node.elts for n in _nomi_in(e)]
    return []


def _sql(text: str) -> list[str]:
    nomi = "|".join(sorted(map(re.escape, KNOWLEDGE_FIELD_NAMES)))
    trovati = re.findall(rf"field\s*=\s*'({nomi})'", text)
    for gruppo in re.findall(r"field\s+IN\s*\(([^)]*)\)", text, re.IGNORECASE):
        trovati += [n for n in re.findall(r"'([^']*)'", gruppo) if n in KNOWLEDGE_FIELD_NAMES]
    return trovati


class _Cercatore(ast.NodeVisitor):
    def __init__(self, rel: str, porte) -> None:
        self.rel, self.porte, self.funzioni, self.trovati = rel, porte, [], []

    def _dentro(self, node) -> None:
        self.funzioni.append(node.name)
        self.generic_visit(node)
        self.funzioni.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _dentro

    def _ammesso(self) -> bool:
        return any(_MIGRATION.match(f) or (self.rel, f) in AMMESSI for f in self.funzioni)

    def _segna(self, node, nomi) -> None:
        if nomi and not self._ammesso():
            self.trovati.append(f"{self.rel}:{node.lineno} {sorted(set(nomi))}")

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg in ("field", "fields"):
                self._segna(node, _nomi_in(kw.value))
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.porte:
            index, _ = self.porte[node.func.attr]
            if index < len(node.args):
                self._segna(node, _nomi_in(node.args[index]))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self._segna(node, _sql(node.value))


def _sparsi() -> list[str]:
    porte = _porte()
    trovati = []
    for path in sorted(RADICE.rglob("*.py")):
        rel = path.relative_to(RADICE).as_posix()
        if rel == CASA:
            continue
        cercatore = _Cercatore(rel, porte)
        cercatore.visit(ast.parse(path.read_text(encoding="utf-8")))
        trovati += cercatore.trovati
    return trovati


def test_la_derivazione_non_si_e_rotta():
    """Un elenco improvvisamente piccolo e' un cancello che sembra vivo e non
    guarda piu' niente. Ogni costante `*_FIELD` di `type_judgments` e' nel suo
    elenco, e l'elenco non ha nomi senza costante."""
    costanti = {value for name, value in vars(type_judgments).items()
                if name.endswith("_FIELD") and isinstance(value, str)}
    assert costanti == KNOWLEDGE_FIELD_NAMES
    assert type_judgments.JUDGMENT_FIELD_NAMES < KNOWLEDGE_FIELD_NAMES
    porte = _porte()
    # Le porte che oggi ricevono un campo: se la firma cambiasse nome al
    # parametro, il cancello smetterebbe di guardarle in silenzio.
    assert {"get", "forget", "forget_and_seed", "device_answers"} <= set(porte)


def test_le_ammissioni_non_sono_scadute():
    """Un'ammissione che non ammette piu' niente si toglie: altrimenti e' una
    porta aperta per chi verra' dopo."""
    for rel, funzione in AMMESSI:
        albero = ast.parse((RADICE / rel).read_text(encoding="utf-8"))
        assert any(isinstance(n, ast.FunctionDef) and n.name == funzione
                   for n in ast.walk(albero)), (rel, funzione)


def test_nessun_nome_campo_scritto_sparsi():
    trovati = _sparsi()
    assert not trovati, (
        "nomi di campi del sapere scritti per esteso fuori da "
        f"`{CASA}` -- si importano da li': {trovati}")
