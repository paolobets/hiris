"""Lo specchio e il runner delle prove sono UNO ciascuno (T-02, T-04, 14/10/2026).

**Cosa difende.** Fino al 14/10/2026 ogni file di prova si scriveva il suo
specchio dello stato e il suo modello: decine di classi con un `all_states()`
o un `chat()` scritti a mano, e `AsyncMock` assegnati a `runner.chat`. Ognuna
imitava la forma del vero, e quasi nessuna la aveva intera: specchi senza
`loaded` ne' le domande per id, runner senza gli attributi che il prodotto
legge dopo la chiamata (`last_tool_calls`, `last_unanswered`, ...), su cui i
segnali tacevano coperti dal ripiego di `getattr`. Da quel giorno le prove
usano `tests/_specchio_finto.py` (`SpecchioFinto` E' un `EntityCache`) e
`tests/_runner_finto.py` (`RunnerFinto`, verificato contro il sorgente da
`tests/test_runner_after_call.py`). E' il gemello di
`tests/test_finte_convergono.py`, che fa lo stesso per `HAClient`.

**Cosa vieta.** Una scansione AST di `tests/`, che fallisce se:

1. una classe DEFINISCE un nome di `vars(EntityCache)` senza discendere (per
   nome di base, anche attraverso altre classi dello stesso file) da
   `EntityCache` o da `SpecchioFinto`;
2. una classe definisce `chat` senza discendere da `RunnerFinto`;
3. un `AsyncMock`/`MagicMock`/`Mock`/`create_autospec` e' assegnato a un
   `.chat`, a una voce `["entity_cache"]`/`["claude_runner"]`/`["llm_router"]`,
   o passato come `cache=` o come runner al router (`claude=`, `openrouter=`,
   `openai=`, `ollama=`).

Una sottoclasse del finto condiviso che sovrascrive un metodo (per contare le
letture, per romperlo a comando) e' ammessa per costruzione: eredita tutto il
resto dal vero.

**I nomi si DERIVANO** da `vars(EntityCache)` (CLAUDE.md, «Un cancello CHIEDE
il suo elenco»): un metodo nuovo dello specchio entra nel cancello da solo.

**`GENERICI` e' una lista di AMMISSIONE**: i nomi dello specchio che anche
oggetti d'altro genere portano per ragioni loro.

**Cosa NON vede, dichiarato.** Un oggetto qualunque (`SimpleNamespace`, un
dizionario) passato dove si aspetta lo specchio o il runner senza essere una
classe col metodo: la scansione guarda le classi e i mock.
"""
from __future__ import annotations

import ast
from pathlib import Path

from hiris.app.proxy.entity_cache import EntityCache

ROOT = Path(__file__).resolve().parents[1]
MOCK_FACTORIES = frozenset({"AsyncMock", "MagicMock", "Mock", "create_autospec"})
CONDIVISI = {"tests/_specchio_finto.py", "tests/_runner_finto.py"}
BASI_SPECCHIO = frozenset({"EntityCache", "SpecchioFinto"})
BASI_RUNNER = frozenset({"RunnerFinto"})
VOCI = frozenset({"entity_cache", "claude_runner", "llm_router"})
ARGOMENTI = frozenset({"cache", "claude", "openrouter", "openai", "ollama"})

#: Lista di AMMISSIONE: nome di `EntityCache` -> perche' non identifica uno
#: specchio.
GENERICI: dict[str, str] = {
    "get": "e' il nome di ogni dizionario, sessione HTTP o negozio: misurato il "
           "14/10/2026, sei classi di prova lo definiscono e nessuna e' uno specchio",
}


def nomi_specchio() -> frozenset[str]:
    return frozenset(n for n in vars(EntityCache)
                     if not (n.startswith("__") and n.endswith("__"))) - set(GENERICI)


def _discende(nome: str, basi: dict[str, list[str]], radici: frozenset[str]) -> bool:
    visti, coda = set(), [nome]
    while coda:
        attuale = coda.pop()
        if attuale in radici:
            return True
        if attuale in visti:
            continue
        visti.add(attuale)
        coda += basi.get(attuale, [])
    return False


def _fabbrica(valore: ast.expr | None) -> bool:
    if not isinstance(valore, ast.Call):
        return False
    func = valore.func
    nome = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return nome in MOCK_FACTORIES


def _bersaglio_finto(t: ast.expr) -> bool:
    if isinstance(t, ast.Attribute):
        return t.attr == "chat"
    if isinstance(t, ast.Subscript):
        return isinstance(t.slice, ast.Constant) and t.slice.value in VOCI
    return False


def scansiona(sorgente: str, nomi: frozenset[str]) -> list[tuple[int, str, str]]:
    """`(riga, chi, cosa)` di ogni finta scritta a mano nel sorgente."""
    albero = ast.parse(sorgente)
    classi = [n for n in ast.walk(albero) if isinstance(n, ast.ClassDef)]
    basi = {c.name: [ast.unparse(b).split(".")[-1] for b in c.bases] for c in classi}
    trovate = []
    for classe in classi:
        for voce in classe.body:
            if not isinstance(voce, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if voce.name in nomi and not _discende(classe.name, basi, BASI_SPECCHIO):
                trovate.append((voce.lineno, classe.name, voce.name))
            if voce.name == "chat" and not _discende(classe.name, basi, BASI_RUNNER):
                trovate.append((voce.lineno, classe.name, voce.name))
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Assign) and _fabbrica(nodo.value):
            trovate += [(nodo.lineno, ast.unparse(t), "mock")
                        for t in nodo.targets if _bersaglio_finto(t)]
        elif isinstance(nodo, ast.Call):
            trovate += [(nodo.lineno, f"{k.arg}=", "mock") for k in nodo.keywords
                        if k.arg in ARGOMENTI and _fabbrica(k.value)]
    return trovate


def scansiona_prove() -> dict[tuple[str, str, str], int]:
    nomi = nomi_specchio()
    trovate = {}
    for percorso in sorted(ROOT.joinpath("tests").rglob("*.py")):
        relativo = percorso.relative_to(ROOT).as_posix()
        if "__pycache__" in percorso.parts or relativo in CONDIVISI:
            continue
        for riga, chi, cosa in scansiona(percorso.read_text(encoding="utf-8"), nomi):
            trovate[(relativo, chi, cosa)] = riga
    return trovate


def test_nessuno_specchio_ne_runner_scritto_a_mano():
    """Mutazione ESEGUITA (14/10/2026): rimessa in `tests/test_chat_sse.py`
    la coppia `AsyncMock()` + `.chat = AsyncMock(...)` -- rossa, col file e
    la riga; una classe `_Cache` con `all_states` in
    `tests/test_mind_compute.py` -- rossa."""
    trovate = scansiona_prove()
    assert trovate == {}, (
        "finte scritte a mano: "
        + "; ".join(f"{f}:{riga} {chi} -> {cosa}" for (f, chi, cosa), riga in trovate.items())
        + " -- usa `SpecchioFinto` (tests/_specchio_finto.py) o `RunnerFinto` "
          "(tests/_runner_finto.py); per contare o rompere un metodo, una loro "
          "sottoclasse.")


def test_la_derivazione_non_si_e_svuotata():
    nomi = nomi_specchio()
    assert {"all_states", "states_for", "loaded", "on_state_changed"} <= nomi, sorted(nomi)
    assert set(GENERICI) <= set(vars(EntityCache)), "un'ammissione nomina un nome uscito"
    file = [p for p in ROOT.joinpath("tests").rglob("*.py") if "__pycache__" not in p.parts]
    assert len(file) >= 100


def test_la_scansione_vede_le_forme_che_vieta():
    """Una scansione che non trova mai niente sembra viva e non guarda piu'
    niente: le forme vietate si trovano, quelle ammesse no."""
    sorgente = '''
class _Cache:
    def all_states(self):
        return []

class _Modello:
    async def chat(self, **kw):
        return "ok"

class _Contato(SpecchioFinto):
    def all_states(self):
        return super().all_states()

class _Nipote(_Contato):
    def states_for(self, ids=None):
        return {}

class _Lento(RunnerFinto):
    async def chat(self, **kw):
        return await super().chat(**kw)

class _Negozio:
    def get(self, chiave):
        return None

def f(app, runner):
    runner.chat = AsyncMock(return_value="x")
    app["claude_runner"] = MagicMock()
    app["altro"] = MagicMock()
    LLMRouter(claude=MagicMock(), model_chain=["claude"])
    ToolDispatcher(None, None, cache=MagicMock())
'''
    trovate = {(chi, cosa) for _riga, chi, cosa in scansiona(sorgente, nomi_specchio())}
    assert trovate == {("_Cache", "all_states"), ("_Modello", "chat"),
                       ("runner.chat", "mock"), ("app['claude_runner']", "mock"),
                       ("claude=", "mock"), ("cache=", "mock")}
