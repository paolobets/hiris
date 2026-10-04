"""Le finte convergono: Home Assistant, nelle prove, e' UNO -- la casa finta.

**Cosa difende** (Tappa 2, Task 12, T-01). Le prove avevano una finta di
`HAClient` per ogni bisogno: classi che imitavano a mano i suoi metodi
(`FintoClient`, `FintoHA`, `_ClienteLegami`, ...) e `MagicMock` assegnati al
client. Ognuna riscriveva la forma delle risposte, il filtro, la busta
dell'errore -- e poteva mentire: misurato il 03/10/2026, diciassette finte
ignoravano il filtro di `get_states` e quattro sollevavano dove il vero non
solleva. Dal 04/10/2026 nessuna: le prove usano `scripts/casa_finta.py`, che
E' il client vero col trasporto sostituito, e sa dire cio' per cui le finte
esistevano (le scritture registrate e non eseguite, i rifiuti nella forma di
Home Assistant, i silenzi, le sequenze, i ritardi).

**Cosa vieta.** Una scansione AST di `tests/`, che fallisce se:

1. una classe DEFINISCE -- come metodo, o come attributo di classe che lo
   ombreggia (`add_state_listener = None`) -- un nome di `vars(HAClient)`;
2. un `AsyncMock`/`MagicMock`/`Mock`/`create_autospec` e' assegnato a un nome
   di client: `ha`, `ha_client`, `mock_ha`, `client`, un attributo
   `.ha_client`, una voce `[...]["ha_client"]`.

**I nomi si DERIVANO** da `vars(HAClient)`, non si ricopiano (CLAUDE.md, «Un
cancello CHIEDE il suo elenco»): un metodo nuovo del client entra nel
cancello da solo. Restano fuori i dunder: `__init__` costruisce, non parla
con Home Assistant -- la stessa scelta di `tests/test_casa_finta.py`.

**`ADMITTED` e' una lista di AMMISSIONE**: enuncia il cancello, non ricopia
niente. Una voce nuova e' vietata finche' qualcuno non la scrive li', con la
ragione. Il 04/10/2026 e' vuota: le prove del trasporto
(`tests/test_ha_client_invio.py`, `tests/test_costi_avvio.py`) danno al
client vero la connessione finta di `scripts/casa_finta.py`
(`SilentConnection`), che e' fuori da `tests/` e non imita nessun metodo.

**Cosa NON vede, dichiarato.** Un trasporto finto messo con
`monkeypatch.setattr(client, "_ws_send", ...)`: non e' una classe ne' un
mock. Il 04/10/2026 lo fanno quattro file di prove del client
(`test_ha_client_configuration.py`, `test_ha_client_helper_labels.py`,
`test_ha_client_statistics.py`, `test_ha_client_time_reads.py`, coi
costruttori di `tests/_ha_fakes.py`), e un attributo d'istanza messo a `None`
per provare un ramo difensivo (`tests/test_action_targets.py::_without`, che
controlla il nome su `HAClient`).

Mutazione ESEGUITA (04/10/2026): aggiunta a `tests/test_entity_cache.py` una
classe `_Ghost` con `async def get_states(self, entity_ids)` -- rossa, col
messaggio che nomina file, riga, classe e metodo; poi una funzione con
`app["ha_client"] = MagicMock()` -- rossa allo stesso modo. Ripristinato il
file dalla copia, identico byte per byte (`cmp`).
"""
import ast
import sys
from pathlib import Path

from hiris.app.proxy.ha_client import HAClient

ROOT = Path(__file__).resolve().parents[1]

#: Le classi di mock che, assegnate a un client, ne fanno una finta.
MOCK_FACTORIES = frozenset({"AsyncMock", "MagicMock", "Mock", "create_autospec"})

#: I nomi con cui le prove chiamano il client di Home Assistant.
CLIENT_NAMES = frozenset({"ha", "ha_client", "mock_ha", "client"})

#: Lista di AMMISSIONE: `(file relativo a tests/, classe o bersaglio, nome) ->
#: ragione`. Vuota il 04/10/2026 (vedi il docstring).
ADMITTED: dict[tuple[str, str, str], str] = {}


def client_methods() -> frozenset[str]:
    """I nomi di `HAClient` che una finta imiterebbe: tutto `vars(HAClient)`
    meno i dunder."""
    return frozenset(name for name in vars(HAClient)
                     if not (name.startswith("__") and name.endswith("__")))


def _class_members(node: ast.ClassDef) -> list[tuple[str, int]]:
    """I nomi che il corpo di una classe definisce: metodi e attributi."""
    members = []
    for item in node.body:
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            members.append((item.name, item.lineno))
        elif isinstance(item, ast.Assign):
            members += [(t.id, item.lineno) for t in item.targets if isinstance(t, ast.Name)]
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            members.append((item.target.id, item.lineno))
    return members


def _is_client_target(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return target.id in CLIENT_NAMES
    if isinstance(target, ast.Attribute):
        return target.attr == "ha_client"
    if isinstance(target, ast.Subscript):
        return isinstance(target.slice, ast.Constant) and target.slice.value == "ha_client"
    return False


def _mock_factory(value: ast.expr | None) -> str | None:
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name if name in MOCK_FACTORIES else None


def scan_source(source: str, methods: frozenset[str]) -> list[tuple[int, str, str, str]]:
    """Le finte di un sorgente: `(riga, genere, classe o bersaglio, nome)`,
    genere `"class"` (una classe che definisce un nome del client) o `"mock"`
    (un mock assegnato a un client)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef):
            found += [(line, "class", node.name, name)
                      for name, line in _class_members(node) if name in methods]
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            factory = _mock_factory(node.value)
            if factory is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found += [(node.lineno, "mock", ast.unparse(t), factory)
                      for t in targets if _is_client_target(t)]
    return found


def scan_tests() -> dict[tuple[str, str, str], int]:
    """Le finte di `tests/`, per `(file, classe o bersaglio, nome)` -> riga."""
    methods = client_methods()
    found = {}
    for path in sorted(ROOT.joinpath("tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT / "tests").as_posix()
        for line, _kind, owner, name in scan_source(path.read_text(encoding="utf-8"),
                                                    methods):
            found[(relative, owner, name)] = line
    return found


def test_nessuna_finta_di_haclient_fuori_dalla_casa_finta():
    found = scan_tests()
    new = sorted(set(found) - set(ADMITTED))
    gone = sorted(set(ADMITTED) - set(found))
    assert not new, (
        "finte di HAClient fuori da `scripts/casa_finta.py`: "
        + "; ".join(f"tests/{file}:{found[(file, owner, name)]} {owner} -> {name}"
                    for file, owner, name in new)
        + " -- una classe che imita un metodo del client, o un mock al posto del "
          "client, riscrive a mano cio' che il client vero fa (forma, filtro, "
          "busta dell'errore). Usa `CasaFinta(inputs, answers=..., refuse=..., "
          "silence=..., delay=...)`; se e' davvero una prova del trasporto, "
          "scrivila in `ADMITTED` con la ragione.")
    assert not gone, (
        f"voci ammesse che non ci sono piu': {gone} -- toglile da `ADMITTED`: "
        "un'ammissione dimenticata riaprirebbe il buco in silenzio")


def test_la_derivazione_non_si_e_svuotata():
    """(a) L'insieme dei nomi viene dal client, ed e' quello di oggi: non
    piccolo, con le letture, le scritture e il trasporto dentro."""
    methods = client_methods()
    assert len(methods) >= 60, sorted(methods)
    assert {"get_states", "call_service", "save_configuration", "related",
            "add_state_listener", "_ws_send", "_rest_get"} <= methods
    assert not any(name.startswith("__") for name in methods)
    # Il perimetro e' tutto `tests/`, e la scansione legge davvero: i file ci
    # sono, e questo stesso file ne fa parte.
    files = [p for p in ROOT.joinpath("tests").rglob("*.py") if "__pycache__" not in p.parts]
    assert len(files) >= 100 and Path(__file__).resolve() in {p.resolve() for p in files}


def test_la_scansione_vede_le_forme_che_vieta():
    """(b) La scansione trova cio' che vieta, in ogni forma: con
    `ADMITTED` vuota non c'e' una voce ammessa su cui provarla, e una
    scansione che non trova mai niente sarebbe un cancello che sembra vivo e
    non guarda piu' niente. E non vede cio' che non vieta: una classe con un
    nome che il client non ha, un mock dato a qualcos'altro."""
    source = '''
class FakeClient:
    async def get_states(self, entity_ids):
        return []
    remove_state_listener = None
    def helper(self):
        return 1

class Unrelated:
    def chat(self):
        return "ok"

def build(app, runner):
    ha = AsyncMock()
    mock_ha = unittest.mock.MagicMock()
    client = create_autospec(HAClient)
    app["ha_client"] = Mock()
    runner.ha_client = MagicMock()
    runner._client = MagicMock()
    openai_client = MagicMock()
    ha_client: object = AsyncMock()
'''
    found = {(kind, owner, name) for _line, kind, owner, name
             in scan_source(source, client_methods())}
    assert found == {
        ("class", "FakeClient", "get_states"),
        ("class", "FakeClient", "remove_state_listener"),
        ("mock", "ha", "AsyncMock"),
        ("mock", "mock_ha", "MagicMock"),
        ("mock", "client", "create_autospec"),
        ("mock", "app['ha_client']", "Mock"),
        ("mock", "runner.ha_client", "MagicMock"),
        ("mock", "ha_client", "AsyncMock"),
    }


def test_la_casa_finta_e_fuori_dal_perimetro_e_dentro_la_derivazione():
    """La sola classe che ridefinisce nomi del client vive in `scripts/`, ed
    e' cio' che `TRANSPORT` di `scripts/casa_finta.py` ammette: la scansione,
    puntata su di lei, la vede -- cioe' il perimetro, non la cecita', e' cio'
    che la lascia passare."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import casa_finta

    source = ROOT.joinpath("scripts", "casa_finta.py").read_text(encoding="utf-8")
    seen = {name for _line, kind, owner, name in scan_source(source, client_methods())
            if kind == "class" and owner == "CasaFinta"}
    assert seen == set(casa_finta.TRANSPORT)
