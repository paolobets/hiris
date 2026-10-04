"""R19: fuori dal modulo della casa nessuno rifa' le sue domande.

Lo sprint «Una fonte sola di verita'» e' la quinta volta che questo lavoro
viene chiesto. Le prime quattro si e' curato un doppione alla volta, e niente
ha fermato il successivo. Questo e' cio' che lo ferma: un cancello che legge
l'albero del codice e conta, fuori dai moduli che ne sono proprietari,

- le chiamate alle LETTURE del client di Home Assistant (`letture-del-client`;
  le scritture hanno gia' il loro cancello, `test_mind_actuator_guards.py`);
- i letterali degli stati «non valore» (`letterali-di-stato`);
- le letture dei campi con cui si decide «e' fuori?» (`regola-del-fuori`).

**Le eccezioni sono le copie che il registro conosce** (`fonte_unica_eccezioni
.json`): per ogni file, QUALE nome e quante volte, con le voci del registro che
lo spiegano -- oppure, dove il letterale vuol dire un'altra cosa, il motivo
scritto. Un conto che SALE e' un doppione nuovo. Un conto che SCENDE e' una
copia guarita, e va tolta dall'elenco nello stesso commit. Si conta per (file,
nome) e non per file: una copia guarita e una nuova nello stesso file si
compenserebbero, e il cancello resterebbe verde.

**«Puo' solo accorciarsi» e' un tetto, non una serratura.** Il tetto
(`CEILING`) e' la somma dei conti e la prova lo vuole ESATTO: scende a ogni
copia che esce. Niente impedisce meccanicamente di alzarlo insieme all'elenco
-- servirebbe la storia di git, che in CI non c'e' -- ma farlo e' una riga di
diff in due file, e una revisione la vede.

**Ogni elenco si chiede, non si ricopia.** I metodi del client al sorgente di
`HAClient`; gli stati al vocabolario; i campi alla funzione che E' la regola.

**I limiti, dichiarati.**

- Il cancello conta per NOME. Un metodo del client che si chiama come una
  funzione di un altro modulo non si puo' attribuire e resta fuori dal conto:
  quali siano e' un elenco di ammissione (`AMBIGUOUS`), e se cresce la prova
  si ferma.
- Vede la chiamata, il riferimento (`leggi = ha.get_states`) e
  `getattr(ha, "get_states")` con il nome scritto. Non vede un nome composto
  a runtime, ne' un client passato sotto un'altra interfaccia, ne' il
  riferimento nudo a un nome che altrove e' un campo (`problems`).
- Non vede chi parla con Home Assistant o col Supervisor con una sessione
  propria, senza il client: e' la voce E-06 del registro, e si chiude alla
  Tappa 2.
- Non vede due funzioni che rispondono alla stessa domanda con codice diverso
  senza toccare questi tre segnali: quello resta alla sonda di parita' e agli
  occhi.

Mutazione ESEGUITA: aggiunta in `hiris/app/mind/report.py` la riga
`_mutation = {}.get("disabilitata")` -- rossa (`regola-del-fuori:
hiris/app/mind/report.py conta 1 in piu' dell'eccezione nota`).
Mutazione ESEGUITA: tolte da `digest_visible_entity_ids` le tre negazioni
(`and not e.get(...)`) -- rossa (`la regola del fuori non ha piu' campi`).
Una prima versione di questa mutazione metteva un `return frozenset()` in
testa lasciando sotto il corpo vecchio: era INERTE, perche' il cancello legge
l'albero e l'albero aveva ancora i campi. Dedotta sarebbe passata per buona.
Mutazione ESEGUITA: tolta una riga dall'elenco delle eccezioni -- rossa (quel
file «conta N in piu'»); abbassato un conto di uno -- rossa allo stesso modo.
"""
import ast
import functools
import inspect
import json
import pathlib
import sys
import textwrap

from tests.test_casa_script import WRITING_VERBS
from tests.test_mind_actuator_guards import porte_home_assistant

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
sys.path.insert(0, str(ROOT / "scripts"))

from hiris.app.home_space import briefing, type_vocabulary

EXCEPTIONS_FILE = ROOT / "tests" / "fonte_unica_eccezioni.json"
REGISTER = ROOT / "docs" / "design" / "2026-10-01-registro-dei-doppioni.md"
KNOWN_DUPLICATES = ROOT / "scripts" / "doppioni_noti.json"

#: I metodi del client che non sono domande alla casa: lo accendono e lo
#: spengono. Lista di AMMISSIONE, con la ragione: chi avvia l'add-on deve
#: poterli chiamare, e contarli sarebbe contare `scheduler.start()`.
#: `reread_after_first_connection` (Tappa 2, Task 7) dice al websocket di
#: lunga vita che anche la prima connessione deve far rileggere: lo chiama
#: l'avvio quando Home Assistant non risponde, e non manda niente alla casa.
LIFECYCLE = frozenset({"start", "stop", "start_websocket",
                       "reread_after_first_connection"})


def _module_of(function) -> str:
    return pathlib.Path(inspect.getsourcefile(function)).resolve().relative_to(
        APP).as_posix()


#: Chi possiede ogni domanda OGGI. Per le due regole della casa il
#: proprietario e' il MODULO in cui la regola e' definita -- chiesto alla
#: funzione, non scritto qui: se la regola trasloca, il confine la segue.
OWNERS = {
    "letture-del-client": ("proxy/",),
    "letterali-di-stato": (_module_of(type_vocabulary.unknown_states),),
    "regola-del-fuori": (_module_of(briefing.digest_visible_entity_ids),),
}

#: Il tetto delle eccezioni: la somma dei conti. Si ABBASSA quando una copia
#: esce, nello stesso commit. Alzarlo e' una riga di diff che una revisione
#: vede -- ed e' il punto.
CEILING = 65

#: Le letture del client che il cancello NON puo' attribuire, perche' il nome
#: e' anche di un'altra funzione del prodotto. Lista di AMMISSIONE: una voce
#: nuova vuol dire che un metodo e' appena uscito dal cancello, e qualcuno
#: deve deciderlo per iscritto.
AMBIGUOUS = frozenset({"related"})


@functools.cache
def _sources() -> dict[str, ast.AST]:
    return {path.relative_to(APP).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
            for path in sorted(APP.rglob("*.py"))}


@functools.cache
def _defined_elsewhere() -> frozenset[str]:
    """I nomi di funzione e di metodo definiti fuori dal client."""
    names: set[str] = set()
    for relative, tree in _sources().items():
        if relative == "proxy/ha_client.py":
            continue
        names |= {node.name for node in ast.walk(tree)
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return frozenset(names)


def _client_reads() -> frozenset[str]:
    """I metodi pubblici di `HAClient` che LEGGONO: tutti, meno quelli che
    scrivono (per verbo: lo stesso vocabolario della porta degli script) e
    meno il ciclo di vita."""
    return frozenset(name for name in porte_home_assistant()
                     if not name.startswith(WRITING_VERBS) and name not in LIFECYCLE)


@functools.cache
def _fields_elsewhere() -> frozenset[str]:
    """I nomi che fuori dal client sono CAMPI: annotati in una classe, o
    assegnati su `self`. `validation.problems` e' un campo di `Validation`, non
    la lettura `HAClient.problems`: un riferimento nudo a un nome cosi' non si
    puo' attribuire. La CHIAMATA `.problems()` invece si conta lo stesso."""
    names: set[str] = set()
    for relative, tree in _sources().items():
        if relative == "proxy/ha_client.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names |= {item.target.id for item in node.body
                          if isinstance(item, ast.AnnAssign)
                          and isinstance(item.target, ast.Name)}
            if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
                    and isinstance(node.value, ast.Name) and node.value.id == "self"):
                names.add(node.attr)
    return frozenset(names)


def client_methods() -> frozenset[str]:
    """Le letture del client che nessun altro nel prodotto definisce con lo
    stesso nome: una chiamata `.nome(...)` e' una chiamata al client."""
    return frozenset(_client_reads() - _defined_elsewhere())


def ambiguous_client_methods() -> frozenset[str]:
    """Quelle che il cancello NON vede, perche' il nome e' anche di altri."""
    return frozenset(_client_reads() & _defined_elsewhere())


def state_literals() -> frozenset[str]:
    return frozenset(type_vocabulary.unknown_states())


def visibility_fields() -> frozenset[str]:
    """I campi che la regola «e' fuori?» nega: letti dal corpo della funzione
    che E' la regola, `briefing.digest_visible_entity_ids`."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(briefing.digest_visible_entity_ids)))
    fields = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
            continue
        for call in ast.walk(node.operand):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "get" and call.args
                    and isinstance(call.args[0], ast.Constant)):
                fields.add(call.args[0].value)
    return frozenset(fields)


def _outside(relative: str, rule: str) -> bool:
    return not relative.startswith(OWNERS[rule])


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)):
                found.add(id(body[0].value))
    return found


def _named_by_getattr(node: ast.AST) -> str | None:
    """`getattr(x, "nome")` col nome scritto: e' un riferimento come un altro."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "getattr" and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)):
        return node.args[1].value
    return None


def _key_read(node: ast.AST) -> str | None:
    """Il campo letto da `x.get("campo")` o da `x["campo"]`."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return node.args[0].value
    if (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)):
        return node.slice.value
    return None


def count_in(trees: dict[str, ast.AST]) -> dict[str, dict[str, dict[str, int]]]:
    """Per regola, per file fuori dai proprietari, per NOME: quante occorrenze.

    Prende gli alberi da fuori perche' le prove gli diano un prodotto finto e
    vedano cosa conta -- senza scrivere nel prodotto vero.
    """
    methods, literals, fields = client_methods(), state_literals(), visibility_fields()
    also_fields = _fields_elsewhere()
    found: dict[str, dict[str, dict[str, int]]] = {rule: {} for rule in OWNERS}

    def count(rule: str, relative: str, name: str) -> None:
        per_name = found[rule].setdefault(f"hiris/app/{relative}", {})
        per_name[name] = per_name.get(name, 0) + 1

    for relative, tree in trees.items():
        documentation = _docstrings(tree)
        called = {id(node.func) for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        for node in ast.walk(tree):
            if _outside(relative, "letture-del-client"):
                # Ogni riferimento a `x.metodo`: la chiamata sempre; il
                # riferimento nudo (`leggi = ha.get_states`, un alias) solo se
                # quel nome non e' anche un campo di qualcun altro.
                if (isinstance(node, ast.Attribute) and node.attr in methods
                        and (id(node) in called or node.attr not in also_fields)):
                    count("letture-del-client", relative, node.attr)
                if _named_by_getattr(node) in methods:
                    count("letture-del-client", relative, _named_by_getattr(node))
            if (_outside(relative, "letterali-di-stato") and isinstance(node, ast.Constant)
                    and isinstance(node.value, str) and node.value in literals
                    and id(node) not in documentation):
                count("letterali-di-stato", relative, node.value)
            if _outside(relative, "regola-del-fuori") and _key_read(node) in fields:
                count("regola-del-fuori", relative, _key_read(node))
    return found


@functools.cache
def violations() -> dict[str, dict[str, dict[str, int]]]:
    return count_in(_sources())


def _exceptions() -> dict[str, dict[str, dict]]:
    return json.loads(EXCEPTIONS_FILE.read_text(encoding="utf-8"))


def _flat(table: dict, leaf=lambda entry: entry) -> dict[tuple[str, str, str], int]:
    """{(regola, file, nome): conto}, dalla forma annidata."""
    return {(rule, path, name): count
            for rule, per_file in table.items()
            for path, entry in per_file.items()
            for name, count in leaf(entry).items()}


def test_ogni_regola_ha_ancora_il_suo_elenco():
    methods = client_methods()
    assert len(methods) >= 20, f"i metodi del client derivati sono troppo pochi: {sorted(methods)}"
    assert state_literals(), "nessuno stato non-valore: il cancello non guarda niente"
    assert len(visibility_fields()) >= 3, (
        "la regola del fuori non ha piu' campi: il cancello non guarda niente "
        f"({sorted(visibility_fields())})")
    assert len(_sources()) > 100, "l'albero del prodotto si e' svuotato"
    assert ambiguous_client_methods() == AMBIGUOUS, (
        "le letture del client che il cancello non vede sono cambiate: "
        f"{sorted(ambiguous_client_methods())}. Una funzione omonima altrove ha tolto "
        "un metodo dal cancello: o si rinomina, o si ammette per iscritto.")


def _known() -> dict[tuple[str, str, str], int]:
    return _flat(_exceptions(), leaf=lambda entry: entry["conti"])


def test_nessun_doppione_nuovo():
    known = _known()
    grown = [f"{rule}: {path} conta {count - known.get((rule, path, name), 0)} in piu' "
             f"dell'eccezione nota (`{name}`)"
             for (rule, path, name), count in sorted(_flat(violations()).items())
             if count > known.get((rule, path, name), 0)]
    assert not grown, "\n".join(grown)


def test_un_eccezione_guarita_esce_dall_elenco():
    found = _flat(violations())
    stale = [f"{rule}: {path} ha `{name}` {found.get((rule, path, name), 0)} volte, "
             f"l'elenco dice {count}"
             for (rule, path, name), count in sorted(_known().items())
             if found.get((rule, path, name), 0) < count]
    assert not stale, "eccezioni da abbassare o togliere:\n" + "\n".join(stale)


def _fake_product(source: str) -> dict[str, ast.AST]:
    return {"mind/prova.py": ast.parse(source)}


def test_il_cancello_vede_la_chiamata_l_alias_e_il_getattr():
    """Mutazione ESEGUITA: in `count_in` contate solo le `ast.Call` -- rossa
    (l'alias e il `getattr` non si contano: 1 invece di 3)."""
    counted = count_in(_fake_product(
        "async def f(ha):\n"
        "    await ha.get_states([])\n"
        "    leggi = ha.get_states\n"
        "    return await getattr(ha, 'get_states')([])\n"))
    assert counted["letture-del-client"] == {"hiris/app/mind/prova.py": {"get_states": 3}}


def test_uno_scambio_nello_stesso_file_non_passa():
    """Una copia guarita e una nuova nello stesso file: per file il conto e'
    lo stesso, per nome no (rilievo I3 della revisione del 01/10/2026)."""
    before = count_in(_fake_product("async def f(ha):\n    await ha.problems()\n"))
    after = count_in(_fake_product("async def f(ha):\n    await ha.statistic_ids()\n"))
    assert _flat(before) != _flat(after)
    assert sum(_flat(before).values()) == sum(_flat(after).values()) == 1


def test_il_cancello_vede_la_regola_del_fuori_e_i_letterali():
    counted = count_in(_fake_product(
        "def f(e, s):\n"
        "    if e.get('disabilitata') or e['nascosta']:\n"
        "        return None\n"
        "    return s != 'unavailable'\n"))
    path = "hiris/app/mind/prova.py"
    assert counted["regola-del-fuori"] == {path: {"disabilitata": 1, "nascosta": 1}}
    assert counted["letterali-di-stato"] == {path: {"unavailable": 1}}


def test_l_elenco_puo_solo_accorciarsi():
    total = sum(_known().values())
    assert total == CEILING, (
        f"le eccezioni sommano {total}, il tetto e' {CEILING}: quando una copia esce "
        "si abbassa il tetto, mai il contrario")


def test_ogni_eccezione_cita_una_voce_aperta_del_registro():
    import registro
    open_ids = {entry.id for entry in registro.read_entries(REGISTER) if not entry.closed}
    assert len(open_ids) > 50, "il registro letto e' quasi vuoto: il lettore si e' rotto"
    entries = [(rule, path, entry) for rule, per_file in _exceptions().items()
               for path, entry in per_file.items()]
    # Un'eccezione e' una copia nota (e cita le sue voci) oppure non e' un
    # doppione (e dice perche'): una delle due, mai nessuna e mai entrambe.
    unexplained = [f"{rule}: {path}" for rule, path, entry in entries
                   if bool(entry.get("voci")) == bool(entry.get("non_e_un_doppione"))]
    assert all(entry["conti"] for _rule, _path, entry in entries), "eccezioni senza conti"
    assert not unexplained, f"eccezioni senza voce del registro ne' motivo: {unexplained}"
    cited = {voice for _rule, _path, entry in entries for voice in entry.get("voci", ())}
    # Anche l'elenco dei doppioni noti di `doppioni.py` cita il registro: e'
    # lo stesso patto, e si verifica nello stesso punto.
    cited |= set(json.loads(KNOWN_DUPLICATES.read_text(encoding="utf-8")).values())
    orphans = sorted(cited - open_ids)
    assert not orphans, f"eccezioni che citano voci chiuse o inesistenti: {orphans}"
