"""Il cancello della Tappa 1: nessuna prova nuova legge il testo di `server.py`.

**Perche' esiste.** Una prova che cerca una stringa nel sorgente di
`hiris/app/server.py`, o ne confronta due indici, difende la POSIZIONE di un
testo, non un comportamento: quando le tappe 2-8 dello sprint «Una fonte sola
di verita'» spostano codice fuori da quel file, la prova si rompe senza che
niente sia cambiato -- o peggio, se cerca l'assenza di qualcosa, resta verde
guardando un file da cui il codice e' gia' uscito. La Tappa 1 le converte
sull'app avviata (`tests/_avvio.py`); questo cancello impedisce che ne
nascano di nuove mentre si convertono le vecchie.

**Cosa guarda.** Una scansione AST di `tests/test_*.py`. Una prova legge il
testo di `server.py` quando:

1. chiama `inspect.getsource` (o `getsourcelines`, `getfile`,
   `getsourcefile`, `findsource`) su `server`, su un suo attributo, o su un
   nome importato `from hiris.app.server`;
2. usa `server.__file__` per qualcosa che non sia trovarne la CARTELLA
   (`.parent`, `.parents`, `dirname`): chi cammina su tutto `hiris/app`
   guarda il prodotto, non un file;
3. costruisce un percorso che finisce in `server.py` (`/`, `Path`, `open`,
   `os.path.join`), salvo dentro una cartella temporanea della prova
   (`tmp_path`, `tmpdir`): li' `server.py` e' un file finto che la prova
   stessa scrive;
4. passa uno dei riferimenti del punto 1 a una funzione dello STESSO file che
   chiama `getsource` sul proprio parametro (`_real_calls(server._on_startup)`).

Una costante di modulo che costruisce il percorso (`_SERVER = ... / "server.py"`)
si attribuisce alle funzioni che la usano: la lettura vera e' li'.

**La lista di AMMISSIONE e' scritta a mano, e chiude per difetto** (CLAUDE.md,
«Un cancello CHIEDE il suo elenco, non lo ricopia»: le liste di ammissione
non ricopiano niente, enunciano il cancello). Una lettura nuova e' vietata
finche' qualcuno non la ammette per iscritto, con la ragione. Le ammesse di
oggi sono le prove che gli altri task della Tappa 1 devono ancora
convertire: la lista **puo' solo accorciarsi**, e la seconda prova qui sotto
pretende che ogni ammissione serva ancora -- una prova convertita che resta
nella lista e' un buco che aspetta una lettura nuova con lo stesso nome.

**Fuori dal cancello, e dichiarate.** Le prove che leggono il sorgente di
ALTRI moduli del prodotto (`ClaudeRunner.chat`, `ActionActuator.execute`,
`handlers_chat`, i middleware, ...): si convertono nelle tappe che spostano
quei moduli (5-7), non qui. Misurato il 03/10/2026: 26 chiamate a
`getsource` su altri moduli, in 20 file (le letture con `read_text` di altri
file non sono contate).

**Cio' che non riconosce gli sfugge**, e lo si dice: una lettura costruita in
modi che i quattro punti sopra non descrivono -- un riferimento passato per
due funzioni, un percorso composto in un altro modulo -- passa il cancello.
"""
import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

SERVER_MODULE = "hiris.app.server"
SOURCE_READERS = {"getsource", "getsourcelines", "getfile", "getsourcefile", "findsource"}
PATH_BUILDERS = {"Path", "PurePath", "open", "join"}
FOLDER_ANCHORS = {"parent", "parents", "dirname"}
TEMPORARY_ROOTS = {"tmp_path", "tmpdir"}

_TASK_5 = "da convertire, Task 5 della Tappa 1 (estrai ed esegui un lavoro periodico)"
_TASK_6 = "da convertire, Task 6 della Tappa 1 (estrai ed esegui un blocco d'avvio)"
_TASK_7 = "da convertire, Task 7 della Tappa 1 (cancello buono che guarda un file solo)"
_NOT_IN_PLAN = ("da convertire nella Tappa 1, ma il piano non la nomina: "
                "la assegna lo sprint")

#: `«file»::«funzione»` -> perche' oggi puo' ancora leggere il testo di
#: `server.py`. Si accorcia, non si allunga.
ADMITTED: dict[str, str] = {
    "test_mind_actuator_guards.py::"
    "test_il_grafo_su_tutto_il_prodotto_contiene_quello_del_solo_server":
        ("prova che la derivazione allargata a tutto hiris/app (Task 7) contiene "
         "quella vecchia del solo server.py: legge server.py per costruire il "
         "termine di paragone, e resta vera anche quando il file si svuota"),
    "test_agent_runner_inaddon.py::"
    "test_le_intestazioni_del_ponte_portano_SOLO_la_credenziale_di_turno": _TASK_7,
    "test_archivi_chiusi.py::_corpo_pulizia":
        _NOT_IN_PLAN + " (il Task 2 ha allargato la costruzione degli archivi; "
                       "il corpo di `_on_cleanup` si legge ancora)",
    "test_background_tasks_wiring.py::"
    "test_spawn_body_adds_to_background_tasks_and_wires_done_callback":
        _NOT_IN_PLAN + " (il corpo di `_spawn`, letterale)",
    "test_bridge_success_occurrence.py::_load_real_submit_chat_reply": _TASK_6,
    "test_chat_subscription_path.py::test_lo_stesso_gate_governa_la_spazzata_e_l_instradamento":
        _TASK_7,
    "test_chat_subscription_path.py::"
    "test_gli_avvisi_del_ponte_vengono_STAMPATI_e_non_solo_composti":
        _NOT_IN_PLAN + " (letterale di una chiamata in `_on_startup`)",
    "test_chat_subscription_path.py::"
    "test_il_ponte_non_ha_piu_nessuna_leva_nelle_opzioni_dell_addon":
        _NOT_IN_PLAN + " (variabili d'ambiente cercate nel solo `server.py`)",
    "test_config_page.py::test_chat_policy_e_uscita_da_tutti_e_cinque_i_posti": _TASK_7,
    "test_submit_chat_reply_guards.py::_load_real_submit_chat_reply": _TASK_6,
}


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def _dotted(expr: ast.expr) -> str | None:
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    return ".".join(reversed([*parts, expr.id]))


def _leftmost(expr: ast.expr) -> ast.expr:
    while isinstance(expr, ast.BinOp):
        expr = expr.left
    return expr


def readings(source: str) -> set[tuple[str, int]]:
    """`{(«chi legge», riga)}`: dove questo sorgente di prova legge il testo
    di `server.py`. «Chi legge» e' la funzione di primo livello (o
    `Classe.metodo`) che contiene la lettura, `<modulo>` fuori da ogni
    funzione."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree)
               for child in ast.iter_child_nodes(node)}

    modules: set[str] = set()
    objects: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "hiris.app":
            modules |= {a.asname or a.name for a in node.names if a.name == "server"}
        elif isinstance(node, ast.ImportFrom) and node.module == SERVER_MODULE:
            objects |= {a.asname or a.name for a in node.names}
        elif isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name == SERVER_MODULE}

    def refers_to_server(expr: ast.expr) -> bool:
        dotted = _dotted(expr) or ""
        return (any(dotted == m or dotted.startswith(m + ".") for m in modules)
                or dotted.split(".")[0] in objects)

    def up_to_statement(node: ast.AST):
        while node in parents and not isinstance(node, ast.stmt):
            node = parents[node]
            yield node

    def owner(node: ast.AST) -> str:
        chain = []
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                chain.append(node.name)
        chain.reverse()
        if not chain:
            return "<modulo>"
        return ".".join(chain[:2]) if chain[0][:1].isupper() and len(chain) > 1 else chain[0]

    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef,
                                    ast.AsyncFunctionDef, ast.ClassDef))
                  and n.body and isinstance(n.body[0], ast.Expr)}

    # Le funzioni di questo file che leggono il sorgente del PROPRIO parametro
    # (punto 4 del docstring): chi passa loro un riferimento a `server` legge.
    source_helpers: dict[str, int] = {}
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = [a.arg for a in function.args.args]
        for call in ast.walk(function):
            if (isinstance(call, ast.Call) and _called_name(call.func) in SOURCE_READERS
                    and call.args and isinstance(call.args[0], ast.Name)
                    and call.args[0].id in params):
                source_helpers[function.name] = params.index(call.args[0].id)

    found: set[tuple[str, ast.AST]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node.func)
            reads_directly = (name in SOURCE_READERS and node.args
                              and refers_to_server(node.args[0]))
            reads_via_helper = (name in source_helpers
                                      and len(node.args) > source_helpers[name]
                                      and refers_to_server(node.args[source_helpers[name]]))
            if reads_directly or reads_via_helper:
                found.add((owner(node), node))
        elif (isinstance(node, ast.Attribute) and node.attr == "__file__"
                and refers_to_server(node.value)):
            anchored = any((isinstance(a, ast.Attribute) and a.attr in FOLDER_ANCHORS)
                           or (isinstance(a, ast.Call) and _called_name(a.func) in FOLDER_ANCHORS)
                           for a in up_to_statement(node))
            if not anchored:
                found.add((owner(node), node))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value.replace("\\", "/").rsplit("/", 1)[-1] == "server.py"):
            builders = [a for a in up_to_statement(node)
                        if (isinstance(a, ast.BinOp) and isinstance(a.op, ast.Div))
                        or (isinstance(a, ast.Call) and _called_name(a.func) in PATH_BUILDERS)]
            temporary = any(isinstance(_leftmost(a), ast.Name)
                            and _leftmost(a).id in TEMPORARY_ROOTS
                            for a in builders if isinstance(a, ast.BinOp))
            if builders and not temporary:
                found.add((owner(node), node))

    # Una costante di modulo che costruisce il percorso: legge chi la usa.
    result: set[tuple[str, int]] = set()
    for who, node in found:
        statement = node
        while not isinstance(statement, ast.stmt):
            statement = parents[statement]
        targets = ([t.id for t in statement.targets if isinstance(t, ast.Name)]
                   if who == "<modulo>" and isinstance(statement, ast.Assign) else [])
        users = {owner(n) for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and n.id in targets
                 and isinstance(n.ctx, ast.Load)}
        if users:
            result |= {(user, node.lineno) for user in users}
        else:
            result.add((who, node.lineno))
    return result


def scan(folder: Path) -> dict[str, list[int]]:
    """`{«file»::«chi legge»: [righe]}` per ogni `test_*.py` della cartella,
    tranne questo file (che i percorsi li nomina per vietarli)."""
    readers: dict[str, list[int]] = {}
    for path in sorted(folder.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        for who, line in readings(path.read_text(encoding="utf-8")):
            readers.setdefault(f"{path.name}::{who}", []).append(line)
    return {key: sorted(lines) for key, lines in readers.items()}


def test_no_test_reads_server_source_outside_the_admission_list():
    """Il cancello. Una lettura nuova del testo di `server.py` ferma la suite.

    Si scrive la prova sull'app avviata (`tests/_avvio.py::started_app`, o
    `router_routes` per le rotte): l'esempio finito e'
    `tests/test_lavori_periodici.py`.

    Mutazione ESEGUITA il 03/10/2026: un file nuovo
    `tests/test_mutazione_cancello.py` con
    `assert "x" in inspect.getsource(server._on_startup)` -- rossa, e il
    messaggio nomina `test_mutazione_cancello.py::test_x`."""
    new = {key: lines for key, lines in scan(TESTS).items() if key not in ADMITTED}

    assert new == {}, (
        "queste prove leggono il testo di hiris/app/server.py: chiedi all'app "
        f"avviata cio' che cerchi nel sorgente -- {new}")


def test_every_admission_is_still_needed():
    """La lista si accorcia: un'ammissione che non legge piu' niente esce.

    E' anche la prova che la scansione non si e' svuotata: se smettesse di
    vedere una forma, le ammesse di quella forma comparirebbero qui.

    Mutazione ESEGUITA il 03/10/2026: tolto `getsource` da `SOURCE_READERS`
    -- rossa, con l'elenco delle ammesse che leggevano con `getsource`."""
    stale = sorted(set(ADMITTED) - set(scan(TESTS)))

    assert stale == [], (
        f"queste prove non leggono piu' server.py: togli la loro ammissione -- {stale}")


@pytest.mark.parametrize("source", [
    (
        "from hiris.app import server\n"
        "import inspect\n"
        "def test_x():\n"
        "    assert 'x' in inspect.getsource(server._on_startup)\n"
    ),
    (
        "import inspect\n"
        "from hiris.app.server import _on_startup\n"
        "def test_x():\n"
        "    assert 'x' in inspect.getsource(_on_startup)\n"
    ),
    (
        "import inspect\n"
        "import hiris.app.server as srv\n"
        "def test_x():\n"
        "    assert 'x' in inspect.getsource(srv)\n"
    ),
    (
        "import pathlib\n"
        "from hiris.app import server\n"
        "def test_x():\n"
        "    assert 'x' in pathlib.Path(server.__file__).read_text()\n"
    ),
    (
        "import pathlib\n"
        "def test_x():\n"
        "    assert 'x' in pathlib.Path('hiris/app/server.py').read_text()\n"
    ),
    (
        "import pathlib\n"
        "_SERVER = pathlib.Path(__file__).parents[1] / 'hiris' / 'app' / 'server.py'\n"
        "def test_x():\n"
        "    assert 'x' in _SERVER.read_text()\n"
    ),
    (
        "import inspect\n"
        "from hiris.app import server\n"
        "def _calls(obj):\n"
        "    return inspect.getsource(obj)\n"
        "def test_x():\n"
        "    assert 'x' in _calls(server._on_startup)\n"
    ),
])
def test_the_scan_sees_every_form_it_declares(source):
    """Le quattro forme del docstring, una per una: se la scansione ne
    perdesse una, il cancello resterebbe verde guardando meno di quanto
    dichiara."""
    assert {who for who, _ in readings(source)} == {"test_x"}


@pytest.mark.parametrize("source", [
    # La cartella del prodotto, non il file: chi cammina su tutto `hiris/app`.
    (
        "import pathlib\n"
        "from hiris.app import server\n"
        "def test_x():\n"
        "    folder = pathlib.Path(server.__file__).resolve().parent\n"
    ),
    # Un `server.py` finto scritto dalla prova nella sua cartella temporanea.
    (
        "def test_x(tmp_path):\n"
        "    (tmp_path / 'server.py').write_text('')\n"
    ),
    # Un indirizzo HTTP, non un file.
    (
        "async def test_x(client):\n"
        "    await client.get('/static/../server.py')\n"
    ),
    # Il nome in un docstring.
    (
        "def test_x():\n"
        "    '''Prima si leggeva hiris/app/server.py.'''\n"
    ),
    # Il sorgente di un ALTRO modulo: fuori da questo cancello (docstring).
    (
        "import inspect\n"
        "from hiris.app.api import handlers_chat\n"
        "def test_x():\n"
        "    assert 'x' in inspect.getsource(handlers_chat)\n"
    ),
])
def test_the_scan_does_not_see_what_is_not_a_reading(source):
    """Il verso opposto: un cancello che chiama sbagliato il codice giusto
    spinge a cambiare prove che funzionano per farlo tacere."""
    assert readings(source) == set()
