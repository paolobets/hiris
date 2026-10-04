"""R19: fuori dal modulo della casa nessuno rifa' le sue domande.

Lo sprint «Una fonte sola di verita'» e' la quinta volta che questo lavoro
viene chiesto. Le prime quattro si e' curato un doppione alla volta, e niente
ha fermato il successivo. Questo e' cio' che lo ferma: un cancello che legge
l'albero del codice e conta, fuori dai moduli che ne sono proprietari,

- le chiamate alle LETTURE del client di Home Assistant (`letture-del-client`;
  le scritture hanno gia' il loro cancello, `test_mind_actuator_guards.py`);
- i letterali degli stati «non valore» (`letterali-di-stato`);
- le letture dei campi con cui si decide «e' fuori?» (`regola-del-fuori`).

**R1 stretto (Tappa 2, Task 13): ogni lettura del client ha UN modulo
chiamante.** Per le letture non si contano piu' le occorrenze fuori da
`proxy/`: ogni lettura ha il suo proprietario, scritto in `READ_OWNERS` con la
ragione, e un secondo modulo che la chiama e' un rosso -- a meno che
`SHARED_READS` non lo ammetta per iscritto, con la ragione e la voce APERTA del
registro che lo chiudera'. Le due mappe sono liste di AMMISSIONE; l'insieme
delle letture che devono comparirci si CHIEDE a `HAClient`. Si guarda tutto
`hiris/app/` tranne il client stesso: anche lo specchio e le traduzioni (che
stanno in `proxy/`) sono chiamanti, e lo specchio e' il proprietario di
`get_states`. Il cancello guarda i MODULI, non quante volte un modulo chiama:
`read_registry("entita")` e `read_registry("etichette")` nell'officina sono
due domande diverse, e il conto per nome le confondeva.

**Le eccezioni delle altre due regole sono le copie che il registro conosce**
(`fonte_unica_eccezioni.json`): per ogni file, QUALE nome e quante volte, con
le voci del registro che lo spiegano -- oppure, dove il letterale vuol dire
un'altra cosa, il motivo scritto. Un conto che SALE e' un doppione nuovo. Un
conto che SCENDE e' una copia guarita, e va tolta dall'elenco nello stesso
commit. Si conta per (file, nome) e non per file: una copia guarita e una nuova nello stesso file si
compenserebbero, e il cancello resterebbe verde.

**«Puo' solo accorciarsi» e' un tetto, non una serratura.** Il tetto
(`CEILING`) e' la somma dei conti piu' i secondi chiamanti ammessi da
`SHARED_READS`, e la prova lo vuole ESATTO: scende a ogni copia che esce.
Niente impedisce meccanicamente di alzarlo insieme all'elenco
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
  Tappa 7 (capitolo E: sono scritture o il Supervisor, non letture).
- Non vede due funzioni che rispondono alla stessa domanda con codice diverso
  senza toccare questi tre segnali: quello resta alla sonda di parita' e agli
  occhi.

Mutazione ESEGUITA: aggiunta in `hiris/app/mind/report.py` la riga
`_mutation = {}.get("disabilitata")` -- rossa (`regola-del-fuori:
hiris/app/mind/report.py conta 1 in piu' dell'eccezione nota`).
Mutazione ESEGUITA (01/10/2026, quando la regola era il digesto del nucleo):
tolte da `digest_visible_entity_ids` le tre negazioni (`and not e.get(...)`)
-- rossa (`la regola del fuori non ha piu' campi`). Una prima versione di
questa mutazione metteva un `return frozenset()` in testa lasciando sotto il
corpo vecchio: era INERTE, perche' il cancello legge l'albero e l'albero aveva
ancora i campi. Dedotta sarebbe passata per buona.
Mutazione ESEGUITA (04/10/2026, la regola in `topology.visibility_classes`):
la partizione di `hierarchy` riscritta in linea con `entity.get(...)` --
rossa (`topology.py conta 1 in piu'`). Con il MODULO come proprietario, come
prima, la stessa mutazione era INERTE: per questo il proprietario di questa
regola e' la funzione (`VISIBILITY_RULE`).
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

from hiris.app.home_space import topology, type_vocabulary

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
#: Per le letture del client qui sta solo il client stesso, che non si conta:
#: il proprietario di ogni lettura e' in `READ_OWNERS` (R1 stretto).
OWNERS = {
    "letture-del-client": ("proxy/ha_client.py",),
    "letterali-di-stato": (_module_of(type_vocabulary.unknown_states),),
    "regola-del-fuori": (_module_of(topology.visibility_classes),),
}

#: Il tetto delle eccezioni: la somma dei conti di `fonte_unica_eccezioni.json`
#: (10) piu' i secondi chiamanti ammessi da `SHARED_READS` (7). Si ABBASSA
#: quando una copia esce, nello stesso commit. Alzarlo e' una riga di diff che
#: una revisione vede -- ed e' il punto. Era 64 prima di R1 stretto: i 30 conti
#: delle letture del client sono usciti dall'elenco, e chi chiama cosa sta ora
#: in `READ_OWNERS` e `SHARED_READS`. Era 41 prima della Tappa 3, Task 5: le
#: 24 copie della regola del fuori (B-01, B-02) chiedono ora a
#: `topology.visibility`.
CEILING = 17

#: Le letture del client che il cancello NON puo' attribuire, perche' il nome
#: e' anche di un'altra funzione del prodotto. Lista di AMMISSIONE: una voce
#: nuova vuol dire che un metodo e' appena uscito dal cancello, e qualcuno
#: deve deciderlo per iscritto.
AMBIGUOUS = frozenset({"related"})

#: R1 stretto: per ogni lettura del client, il SOLO modulo (relativo a
#: `hiris/app/`) che la chiama, con la ragione. Lista di AMMISSIONE: le chiavi
#: devono essere esattamente le letture che il cancello vede (chieste a
#: `HAClient`), quindi una lettura nuova senza proprietario e' un rosso, e un
#: proprietario che smette di chiamare e' una riga da togliere.
#: Lo stato misurato il 04/10/2026 sul ramo della Tappa 2 (HEAD ca3c5217).
READ_OWNERS: dict[str, tuple[str, str]] = {
    "behavior_configs": (
        "home_space/behavior.py",
        "l'unico lettore del corpo delle automazioni: il comportamento della casa"),
    "read_dashboards": (
        "home_space/behavior.py",
        "l'unico lettore delle plance, per lo stesso comportamento"),
    "calendars": (
        "home_space/tools.py",
        ("lo strumento calendario della chat; l'elenco dallo specchio e' A-34, "
         "che il piano della Tappa 2 lascia aperta: la vista REST filtra per "
         "permesso dell'utente, e la misura sulla casa non c'e'")),
    "calendar_events": (
        "home_space/tools.py",
        "lo stesso strumento calendario: gli impegni di ogni calendario (A-34)"),
    "history": (
        "home_space/tools.py",
        ("lo storico dettagliato per lo strumento della chat, fino alla Tappa 3; "
         "l'altro modo di leggere lo storico (`recorded_changes`) e' A-36")),
    "recorded_changes": (
        "mind/cadence.py",
        ("la cadenza dell'osservatore conta i cambi per finestra; con `history` "
         "sono due comandi per la stessa domanda, A-36")),
    "trace": (
        "home_space/tools.py",
        "la traccia passo per passo di un'esecuzione, solo dallo strumento"),
    "traces": (
        "home_space/tools.py",
        ("la raffica delle tracce per lo strumento della chat (Task 8 della "
         "Tappa 2); il secondo chiamante e' in `SHARED_READS`")),
    "system_log": (
        "home_space/tools.py",
        ("il registro degli errori per lo strumento della chat; il giro delle "
         "condizioni e' in `SHARED_READS`")),
    "hourly_statistics": (
        "home_space/tools.py",
        ("le statistiche orarie per lo strumento della chat; il resoconto del "
         "giorno e' in `SHARED_READS`")),
    "problems": (
        "server.py",
        ("`reread_ha_problems`, il giro dei 5 minuti: il giro delle condizioni "
         "riusa `app[\"ha_problems\"]` (A-02, chiusa al Task 5)")),
    "statistic_ids": (
        "server.py",
        ("`statistic_ids_for_round`, la lettura condivisa dai giri (prova: "
         "`tests/test_giro_statistic_ids.py`)")),
    "extract_from_target": (
        "action/actuator.py",
        ("la porta dei servizi chiede a Home Assistant di risolvere un "
         "bersaglio prima di eseguire; il confronto dell'albero e' in "
         "`SHARED_READS`")),
    "get_services": (
        "action/registry.py",
        ("l'unico lettore di `/api/services` dal Task 8 della Tappa 2: il "
         "recapito delle promesse chiede i `notify` a questo registro")),
    "read_configuration": (
        "action/construction/workshop.py",
        ("la porta della configurazione legge il corpo scritto di un oggetto, "
         "il «prima» di una modifica o di una cancellazione")),
    "validate_config": (
        "action/construction/workshop.py",
        ("la porta della configurazione fa validare a Home Assistant prima di "
         "scrivere")),
    "read_registry": (
        "action/construction/workshop.py",
        ("l'officina rilegge le entita' dopo una scrittura e le etichette prima "
         "(D4 della Tappa 2, «restano»); il recapito e' in `SHARED_READS`")),
    "read_registries": (
        "home_space/topology.py",
        "l'anagrafe: i registri letti insieme per costruire la casa"),
    "get_config": (
        "home_space/topology.py",
        ("l'anagrafe: il sistema di riferimento della casa "
         "(`topology.reference_frame`)")),
    "get_states": (
        "proxy/entity_cache.py",
        ("lo specchio degli stati: chi vuole uno stato lo chiede a lui "
         "(`EntityCache.get`/`states_for`, Task 6 della Tappa 2)")),
    "get_translations": (
        "proxy/state_translations.py",
        "i significati degli stati, letti da chi li tiene"),
    "panels": (
        "panel_visibility.py",
        ("la voce di menu dell'add-on: legge i pannelli per sapere se scriverla "
         "(E-01, una delle due scritture dichiarate fuori dalle porte)")),
    "users": (
        "api/soffitto.py",
        "«chi sei e cosa puoi»: i ruoli dagli utenti di Home Assistant (F-01)"),
}

#: R1 stretto: i SECONDI moduli che chiamano una lettura, ammessi per iscritto.
#: Per ognuno la voce del registro che lo chiudera' (deve essere APERTA) e la
#: ragione. Lista di AMMISSIONE: una voce si toglie quando il secondo chiamante
#: smette, e la prova lo pretende.
SHARED_READS: dict[str, dict[str, tuple[str, str]]] = {
    "get_states": {
        "action/construction/workshop.py": (
            "A-15",
            ("D4 della Tappa 2 (03/10/2026, «restano»): `_reread` rilegge gli "
             "stati SUBITO dopo una scrittura, e lo specchio arriva per evento, "
             "dopo. Si riguarda alla Tappa 7 («rileggere prima di scrivere»).")),
        "keeper/recipient.py": (
            "A-03",
            ("D4 della Tappa 2 (03/10/2026, «restano», con la condizione di "
             "Paolo: nessun dato sensibile ai modelli): `recipients_for` cerca "
             "le `person` per `user_id`, che lo specchio trattiene come "
             "credenziale. Prova: `tests/test_specchio_per_id.py`.")),
    },
    "read_registry": {
        "keeper/recipient.py": (
            "A-03",
            ("la stessa ricerca di `recipients_for` (D4): entita' e dispositivi "
             "delle `person`, accanto agli stati letti per intero")),
    },
    "extract_from_target": {
        "server.py": (
            "A-08",
            ("`tree_comparison_round` verifica l'albero dell'anagrafe contro "
             "Home Assistant: e' la sorveglianza della copia che A-08 descrive "
             "(anagrafe e specchio non coordinati)")),
    },
    # Le tre qui sotto hanno la stessa radice, R13 della spec: le letture
    # degli strumenti sono metodi privati di un oggetto che nasce a ogni turno
    # coi permessi di una persona, e i giri del cervello non possono
    # chiamarle -- quindi rileggono da soli. La voce e' A-41, aperta il
    # 04/10/2026 quando questo cancello li ha trovati: fino ad allora li
    # copriva A-08, che non parla di queste letture.
    "system_log": {
        "server.py": (
            "A-41",
            ("il giro delle condizioni (ogni 10 minuti) legge il registro degli "
             "errori per `Watcher.watch_system`; lo strumento non e' "
             "richiamabile dal cervello (R13)")),
    },
    "traces": {
        "server.py": (
            "A-41",
            ("`watch_automation_outcomes` legge in raffica le tracce delle "
             "automazioni segnate; lo strumento non e' richiamabile (R13)")),
    },
    "hourly_statistics": {
        "server.py": (
            "A-41",
            ("`_report_ingredients` legge le serie orarie del resoconto del "
             "giorno; lo strumento non e' richiamabile (R13)")),
    },
}


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
    """I campi con cui si decide «e' fuori?»: letti dal corpo della funzione
    che E' la regola, `topology.visibility_classes` (Tappa 3, Task 5,
    04/10/2026: fino a quel giorno la regola era il digesto del nucleo, e il
    cancello ne leggeva i campi negati). Ci sono anche le CAUSE
    (`disabilitata_da`, `nascosta_da`): chi le legge da se' rifa' la regola."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(VISIBILITY_RULE)))
    return frozenset(
        call.args[0].value for call in ast.walk(tree)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        and call.func.attr == "get" and call.args
        and isinstance(call.args[0], ast.Constant))


#: La funzione che E' la regola del fuori: per questa regola il proprietario
#: non e' il modulo intero ma la funzione sola. Con il modulo, una copia
#: scritta in `topology.py` fuori dalla regola -- la partizione di `hierarchy`,
#: che c'era fino al 04/10/2026 -- non si sarebbe contata: e' il punto cieco
#: che il cancello aveva quando il proprietario era tutto `briefing.py`.
VISIBILITY_RULE = topology.visibility_classes


def _rule_body(relative: str, tree: ast.AST) -> set[int]:
    """Gli id dei nodi DENTRO la funzione della regola del fuori, se `tree` e'
    il suo modulo; altrimenti vuoto."""
    if relative != OWNERS["regola-del-fuori"][0]:
        return set()
    return {id(inner) for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == VISIBILITY_RULE.__name__
            for inner in ast.walk(node)}


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
    """Il campo letto da `x.get("campo")` o da `x["campo"]`.

    `x["campo"] = ...` non e' una lettura: e' una porta che scrive il campo
    nella SUA risposta (`row["nascosta"] = True`), e chiede la classe alla
    regola per decidere se scriverlo. Contarla chiamava doppione la resa
    (Tappa 3, Task 5). Mutazione ESEGUITA: tolta la condizione sul contesto
    -- rossa in `test_una_scrittura_non_e_una_lettura`."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return node.args[0].value
    if (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
            and isinstance(node.slice, ast.Constant)
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
        rule_body = _rule_body(relative, tree)
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
            if id(node) not in rule_body and _key_read(node) in fields:
                count("regola-del-fuori", relative, _key_read(node))
    return found


@functools.cache
def violations() -> dict[str, dict[str, dict[str, int]]]:
    return count_in(_sources())


#: Le regole le cui eccezioni si CONTANO in `fonte_unica_eccezioni.json`. Le
#: letture del client no: le governa R1 stretto, per modulo.
COUNTED_RULES = ("letterali-di-stato", "regola-del-fuori")


def _counted(found: dict) -> dict:
    return {rule: found[rule] for rule in COUNTED_RULES}


def callers_by_read(found: dict) -> dict[str, frozenset[str]]:
    """{lettura: i moduli che la chiamano}, relativi a `hiris/app/`."""
    callers: dict[str, set[str]] = {}
    for path, names in found["letture-del-client"].items():
        for name in names:
            callers.setdefault(name, set()).add(path.removeprefix("hiris/app/"))
    return {name: frozenset(modules) for name, modules in callers.items()}


def r1_violations(found: dict) -> list[str]:
    """Le letture chiamate da un modulo che non e' il loro proprietario ne' un
    secondo chiamante ammesso."""
    problems = []
    for name, modules in sorted(callers_by_read(found).items()):
        if name not in READ_OWNERS:
            problems.append(f"R1: `{name}` non ha un proprietario in READ_OWNERS "
                            f"(la chiamano {sorted(modules)})")
            continue
        owner = READ_OWNERS[name][0]
        admitted = {owner} | set(SHARED_READS.get(name, {}))
        problems += [f"R1: `{name}` chiamata da {module}, ma il suo proprietario e' "
                     f"{owner}: una seconda lettura della stessa cosa, non ammessa "
                     "in SHARED_READS" for module in sorted(modules - admitted)]
    return problems


def _exceptions() -> dict[str, dict[str, dict]]:
    return json.loads(EXCEPTIONS_FILE.read_text(encoding="utf-8"))


def _flat(table: dict, leaf=lambda entry: entry) -> dict[tuple[str, str, str], int]:
    """{(regola, file, nome): conto}, dalla forma annidata."""
    return {(rule, path, name): count
            for rule, per_file in table.items()
            for path, entry in per_file.items()
            for name, count in leaf(entry).items()}


def test_ogni_regola_ha_ancora_il_suo_elenco():
    # Le letture del client hanno la loro prova:
    # `test_r1_la_derivazione_contiene_le_letture_di_oggi`.
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
             for (rule, path, name), count in sorted(_flat(_counted(violations())).items())
             if count > known.get((rule, path, name), 0)]
    assert not grown, "\n".join(grown)


def test_un_eccezione_guarita_esce_dall_elenco():
    found = _flat(_counted(violations()))
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
    before = _counted(count_in(_fake_product("def f(s):\n    return s == 'unknown'\n")))
    after = _counted(count_in(_fake_product("def f(s):\n    return s == 'unavailable'\n")))
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


def test_una_scrittura_non_e_una_lettura():
    counted = count_in(_fake_product(
        "def f(e, row):\n"
        "    row['nascosta'] = True\n"
        "    return e['disabilitata']\n"))
    assert counted["regola-del-fuori"] == {"hiris/app/mind/prova.py": {"disabilitata": 1}}


def test_la_regola_del_fuori_vive_in_topology_con_le_sue_cause():
    """La derivazione non si e' svuotata, e porta le cause: chi legge
    `disabilitata_da` fuori dalla regola la rifa'."""
    assert OWNERS["regola-del-fuori"] == ("home_space/topology.py",)
    assert VISIBILITY_RULE.__name__ in {
        node.name for node in ast.walk(ast.parse((APP / OWNERS["regola-del-fuori"][0])
                                                 .read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)}
    assert {"disabilitata", "nascosta", "categoria",
            "disabilitata_da", "nascosta_da"} <= visibility_fields()


def test_l_elenco_puo_solo_accorciarsi():
    total = sum(_known().values()) + sum(len(extra) for extra in SHARED_READS.values())
    assert total == CEILING, (
        f"le eccezioni sommano {total}, il tetto e' {CEILING}: quando una copia esce "
        "si abbassa il tetto, mai il contrario")


def test_r1_la_derivazione_contiene_le_letture_di_oggi():
    """Una derivazione rotta (un insieme improvvisamente piccolo) e' un
    cancello che sembra vivo e non guarda piu' niente.

    Mutazione ESEGUITA (04/10/2026): aggiunto a `HAClient` un metodo
    `floor_names`, senza toccare la prova -- rossa (`senza proprietario
    ['floor_names']`). Mutazione ESEGUITA: la chiave `users` di READ_OWNERS
    rinominata -- rossa allo stesso modo."""
    methods = client_methods()
    assert len(methods) >= 20, f"le letture derivate sono troppo poche: {sorted(methods)}"
    known = {"get_states", "system_log", "history", "read_registry", "traces", "users"}
    assert known <= methods, f"letture note uscite dalla derivazione: {sorted(known - methods)}"
    assert set(READ_OWNERS) == methods, (
        "READ_OWNERS non copre esattamente le letture del client: senza proprietario "
        f"{sorted(methods - set(READ_OWNERS))}; non piu' letture "
        f"{sorted(set(READ_OWNERS) - methods)}")
    assert set(SHARED_READS) <= set(READ_OWNERS), sorted(set(SHARED_READS) - set(READ_OWNERS))


def test_r1_ogni_lettura_ha_un_solo_modulo_chiamante():
    """R1 della spec: ogni lettura di `HAClient` ha UN modulo che la chiama.

    Mutazione ESEGUITA (04/10/2026): aggiunta in `hiris/app/mind/report.py` la
    funzione `async def _mutation(ha): return await ha.problems()` -- rossa
    (`R1: `problems` chiamata da mind/report.py, ma il suo proprietario e'
    server.py`). La stessa con `ha.system_log()` -- rossa (`chiamata da
    mind/report.py, ma il suo proprietario e' home_space/tools.py`). Tolta da
    SHARED_READS l'ammissione di `server.py` per `system_log` -- rossa
    (`chiamata da server.py`). Ripristini verificati con `git status`."""
    problems = r1_violations(violations())
    assert not problems, "\n".join(problems)


def test_r1_la_mappa_dice_il_vero():
    """Un proprietario che non chiama piu' la sua lettura, o un secondo
    chiamante ammesso che ha smesso, sono righe da togliere: l'ammissione puo'
    solo accorciarsi.

    Mutazione ESEGUITA (04/10/2026): proprietario di `panels` scritto
    `server.py` -- rossa qui (`il proprietario server.py non la chiama`) e in
    R1 (`chiamata da panel_visibility.py`). Mutazione ESEGUITA: la voce di un
    secondo chiamante scritta `A-02` (chiusa) -- rossa nella prova delle voci
    aperte."""
    callers = callers_by_read(violations())
    stale = [f"`{name}`: il proprietario {owner} non la chiama"
             for name, (owner, _reason) in sorted(READ_OWNERS.items())
             if owner not in callers.get(name, ())]
    stale += [f"`{name}`: {module} non la chiama piu', esce da SHARED_READS"
              for name, extra in sorted(SHARED_READS.items())
              for module in sorted(extra) if module not in callers.get(name, ())]
    stale += [f"`{name}`: {READ_OWNERS[name][0]} e' proprietario e secondo chiamante"
              for name, extra in SHARED_READS.items() if READ_OWNERS[name][0] in extra]
    assert not stale, "\n".join(stale)


def test_r1_un_secondo_modulo_e_rosso():
    """Su un prodotto finto: una lettura col suo proprietario e' muta, la
    stessa lettura da un secondo modulo e' un rosso che lo nomina."""
    owner = READ_OWNERS["system_log"][0]
    call = "async def f(ha):\n    return await ha.system_log()\n"
    alone = count_in({owner: ast.parse(call)})
    assert not r1_violations(alone)
    both = count_in({owner: ast.parse(call), "mind/prova.py": ast.parse(call)})
    assert r1_violations(both) == [
        (f"R1: `system_log` chiamata da mind/prova.py, ma il suo proprietario e' {owner}: "
         "una seconda lettura della stessa cosa, non ammessa in SHARED_READS")]


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
    # E i secondi chiamanti di R1 stretto: ognuno cita la voce che lo chiudera'.
    cited |= {voice for extra in SHARED_READS.values() for voice, _reason in extra.values()}
    orphans = sorted(cited - open_ids)
    assert not orphans, f"eccezioni che citano voci chiuse o inesistenti: {orphans}"
