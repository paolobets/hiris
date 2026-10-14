"""R3: un'entita' si compone in un posto solo, la resa (Tappa 4).

Lo scheletro del cancello R3 dello sprint «Una fonte sola di verita'» (spec
`docs/design/2026-10-01-una-fonte-sola-di-verita.md`, R3; piano della Tappa 4,
Task 1, passo 4). Nato ROSSO, con `xfail(strict=True)`, quando le funzioni
che componevano «un'entita' col suo stato» ciascuna per conto suo erano circa
quattordici (registro, C-01). Verde e senza marcatore dalla Tappa 9 (F2,
12/10/2026): i renditori chiamano `render.render_entity`, e chi compone un
altro oggetto sta in `ADMITTED` con la sua ragione.

**La proprieta', non la forma** (CLAUDE.md, I-0). Una funzione COMPONE
un'entita' quando costruisce un dizionario -- letterale, o una variabile
riempita con `x["campo"] = ...` -- che porta insieme due campi dell'entita'
del vocabolario. Una porta che INOLTRA il dizionario della resa non scrive
nessuna chiave, e non e' toccata.

**Ogni elenco si chiede.**

- I campi dell'entita' al vocabolario, `home_space/field_vocabulary.py`
  (dalla Tappa 9, F2, 08/10/2026; fino ad allora la tabella del glossario,
  che il modulo ricopia e `tests/test_vocabolario_dei_campi.py` tiene uguale).
  Sono campi dell'entita' i nomi delle righe
  che hanno `entita` fra i loro proprietari, con i nomi che escono; meno quelli
  che ogni oggetto porta (`id`, `nome`, `genere`, i riferimenti `area`,
  `piano`, `dispositivo`): una riga che vale anche per area e dispositivo non
  dice che l'oggetto e' un'entita'.
- I moduli che rispondono a chi li chiama: le rotte del router dell'app, il
  catalogo degli strumenti col suo dispatcher, e tutto cio' che importano
  dentro `hiris/app/` (la chiusura degli import). I compositori dei prompt
  degli attori ci stanno: li importa chi gira i giri, `server.py`, che e' il
  modulo delle rotte.
- `ADMITTED` e' una lista di AMMISSIONE: le funzioni che compongono cio' che
  la casa E' -- il record dell'anagrafe, lo specchio, il fatto di `House` --
  non cio' che si rende -- e la riga di un oggetto che non e' un'entita' ma
  porta due parole del vocabolario. Ognuna col suo perche'.

**I limiti, dichiarati.** Il cancello non vede le chiavi che arrivano da `dict(zip(...))`
ne' da una collezione costruita a pezzi (giro 114). Le righe in TESTO per i
modelli non sono dizionari: dalla Tappa 9, F4 (12/10/2026) quelle degli
attori sono `render.entity_line`, la resa in testo dello stesso dizionario
(D8), e il cancello del testo (`text_composers`, piu' sotto) ferma chi
torna a comporle chiedendo i campi alla casa. `keeper/exchange._domanda`
scrive l'istantanea di una promessa, gia' resa da `render_entity` quando la
promessa e' nata: legge un dizionario, non la casa. `house_history._value_row`
porta un solo campo dell'entita' (`unita`) oltre a id e nome: e' una serie,
e la vede il Task 8 coi generi.
"""
from __future__ import annotations

import ast
from pathlib import Path

from hiris.app.home_space.field_vocabulary import FIELDS

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
ENTITY = "entita"
#: I generi che, se una riga del vocabolario li porta insieme, dicono che il
#: campo e' di ogni oggetto e non dell'entita'.
SHARED_BY = {"dispositivo", "area"}
#: I moduli della resa: li' un'entita' si compone, ed e' il loro mestiere.
RENDER_MODULES = {"home_space/render.py", "home_space/field_vocabulary.py"}

#: Lista di AMMISSIONE: `modulo::funzione` -> perche' non e' una resa.
ADMITTED: dict[str, str] = {
    "home_space/reader.py::_entity": (
        "il record dell'anagrafe: la riga dell'entita' cosi' come l'anagrafe "
        "la tiene, letta dai registri di Home Assistant. E' cio' che la resa "
        "LEGGE, non cio' che rende"),
    "home_space/reader.py::_integration": (
        "il record dell'anagrafe per un'integrazione: `dominio` e `stato` "
        "sono quelli della voce di configurazione di Home Assistant"),
    "proxy/entity_cache.py::_to_minimal": (
        "lo specchio degli stati: la voce minimale con le chiavi di Home "
        "Assistant (`state`, `unit`), al confine. E' la fonte, non una resa"),
    "home_space/house.py::kind_of": (
        "il fatto «che tipo e'» dell'oggetto casa della Tappa 3 (B-17): "
        "una domanda della casa, che la resa chiamera'"),
    "action/actuator.py::_fingerprint": (
        "l'impronta del confronto prima/dopo di un comando, non la resa: lo "
        "stato, l'unita' e TUTTI gli attributi appiattiti, chiave per chiave, "
        "costruita allo stesso modo da tre fonti -- lo specchio, il ritorno di "
        "`call_service` e l'annuncio del websocket -- due delle quali non "
        "passano dalla casa (`House`) che la resa legge. Rendere qui vorrebbe "
        "dire confrontare lo specchio di prima con lo specchio di prima "
        "(Tappa 9, F2, 11/10/2026)"),
    "action/construction/revisions.py::_row": (
        "la riga di una costruzione, non un'entita': `stato` e' quello della "
        "costruzione (in attesa, confermata...) e `dominio` quello della voce "
        "di configurazione che costruisce. Due parole del vocabolario, un "
        "altro oggetto"),
    # Tappa 9, F2 (12/10/2026): gli undici che restavano, giudicati uno per
    # uno. Nessuno rende l'entita' viva della casa: sono altri oggetti che
    # portano due parole del vocabolario, o un fatto passato.
    "api/handlers_mind.py::_fact_row": (
        "la riga di un fatto del sapere: `valore` e' cio' che il fatto afferma "
        "(un significato, un attributo utile), `fonte` da dove l'ha imparato. "
        "Un altro oggetto, `specie` + `soggetto` lo dicono"),
    "home_space/energy.py::describe": (
        "un ruolo della dashboard Energia (C-61): `id` e `unita` della "
        "statistica li chiede a `House.kind_of`, la fonte unica; "
        "`statistiche` e' se il giro ne tiene le serie. Il ruolo dell'entita' "
        "nella resa e' `ruolo_energia` (D13)"),
    "home_space/house.py::source": (
        "il fatto «la fonte» di `House` (D6), che la resa LEGGE e mette in "
        "`fonte`: `stato` e' lo stato della fonte (viva, sparita, ferma...), "
        "non quello dell'entita'"),
    "home_space/topology.py::hierarchy": (
        "le chiavi `disabilitata`/`nascosta` sono le classi di "
        "`topology.visibility` in una tabella di smistamento verso le liste "
        "parallele: nessuna riga esce con quei nomi. Le righe smistate sono "
        "i record dell'anagrafe (`reader._entity`)"),
    "keeper/promise.py::serializza": (
        "l'unica forma di una promessa: `stato` e `stato_leggibile` sono "
        "quelli della promessa (in attesa, mantenuta, disdetta...)"),
    "mind/analyst_turn.py::_enrich": (
        "un'osservazione dell'analista: `valore` e `unita` sono quelli della "
        "MISURA della ricetta (l'ultimo valore della serie calcolata), non lo "
        "stato dell'entita'"),
    "mind/facts.py::_absences": (
        "un episodio del resoconto (un'assenza): `stato`, `classe` e `dominio` "
        "sono quelli scritti nel grezzo quando l'entita' e' sparita -- un "
        "fatto PASSATO, che vive piu' dei cambi. La resa dice la casa di adesso"),
    "mind/facts.py::build_episodes": (
        "un episodio aperto del resoconto: lo `stato` e la `classe` del cambio "
        "che l'ha aperto, dal grezzo -- un fatto passato, non la casa di adesso"),
    "mind/facts.py::close": (
        "il corpo di un episodio chiuso del resoconto: `stato`, `classe`, "
        "`dominio` e gli `attributi` cambiati come li scriveva il grezzo in "
        "quell'istante -- un fatto passato, non la casa di adesso"),
    "mind/report.py::_measurements": (
        "una misura della ricetta: `valore` e `unita` sono quelli calcolati "
        "dall'operazione (`outcome.value`, `outcome.unit`), non lo stato "
        "dell'entita'"),
    # N113-1 (giro 113, 12/10/2026): le comprensioni che prendono le chiavi
    # da una collezione di stringhe scritte, che il cancello prima non vedeva.
    # Tappa 9, F5 (12/10/2026): `alias` entra nel vocabolario dei campi
    # dell'entita', e due righe che non sono entita' lo portavano gia'.
    "home_space/tools.py::_propose": (
        "l'intento di una costruzione: `alias` e' il campo di Home Assistant "
        "per il nome di un'automazione o di uno script, `dominio` quello di "
        "cio' che si costruisce. Non e' un'entita' resa, e' cio' che si "
        "chiedera' a Home Assistant di creare"),
    "model_resolution.py::compose_panel": (
        "la riga di un modello nella pagina Modelli: `alias` dice se il nome "
        "e' un alias del fornitore, `fonte` da dove viene la scelta. Nessuna "
        "cosa della casa"),
    "home_space/house_history.py::parse_query": (
        "i FILTRI di chi si chiede (`dominio`, `classe`, `integrazione` come "
        "parametri di `search`), copiati dagli argomenti per `parse_filters`: "
        "una domanda, non un'entita'"),
    "mind/report.py::_entry": (
        "una riga della cronaca del resoconto: l'ancora di un episodio "
        "passato (`classe`, `dominio`, `attributi` dal corpo dell'episodio, "
        "`mind/facts.close`) -- un fatto passato, non la casa di adesso. "
        "Visto dal giro 114 (N114-1), coi cicli su costanti"),
    "mind/store.py::proposals": (
        "la riga di una proposta: `stato` e `stato_leggibile` sono quelli "
        "della proposta, con la stessa frase delle costruzioni (C-10)"),
}


def entity_fields() -> set[str]:
    """I nomi dei campi dell'entita', chiesti al vocabolario
    (`home_space/field_vocabulary.FIELDS`, dalla Tappa 9): i campi che hanno
    `entita` fra i proprietari, con i nomi che hanno tolto; meno quelli che
    valgono anche per area e dispositivo."""
    shared = set().union(*({name, *field.replaces} for name, field in FIELDS.items()
                           if SHARED_BY <= field.owners))
    return set().union(*({name, *field.replaces} for name, field in FIELDS.items()
                         if ENTITY in field.owners)) - shared


def _module_path(name: str) -> Path | None:
    parts = name.split(".")
    if parts[:2] != ["hiris", "app"]:
        return None
    base = APP.joinpath(*parts[2:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


def _imports(path: Path) -> set[Path]:
    """I moduli di `hiris/app/` che `path` importa (assoluti e relativi)."""
    package = ["hiris", "app", *path.relative_to(APP).parent.parts]
    found: set[Path] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = (package[:len(package) - node.level + 1] if node.level else [])
            module = [*base, *(node.module.split(".") if node.module else [])]
            names = [".".join(module)] + [".".join([*module, alias.name])
                                          for alias in node.names]
        else:
            continue
        for name in names:
            target = _module_path(name)
            if target is not None:
                found.add(target)
    return found


def responding_modules() -> set[Path]:
    """I moduli che rispondono: quelli dei gestori delle rotte (chiesti al
    router), quello del dispatcher degli strumenti (chiesto al catalogo),
    quello che compone l'app (`create_app`), e la chiusura dei loro import
    dentro `hiris/app/`.

    Il modulo di `create_app` e' una radice dichiarata dal 14/10/2026 (F8
    passo 5): i collaboratori che le rotte ricevono dall'app e non importano
    (l'attuatore, l'officina, le revisioni) li importa solo chi li monta.
    Fino a quel giorno ci si arrivava per caso, perche' un gestore -- il guscio
    HTML -- viveva ancora in `server.py`; uscito il guscio, l'attuatore era
    uscito dal cancello senza che nessuno lo decidesse."""
    import sys

    from hiris.app import server
    from hiris.app.home_space import tools

    app = server.create_app()
    roots = {route.handler.__module__ for route in app.router.routes()}
    roots.add(server.create_app.__module__)
    assert tools.KNOWLEDGE_TOOLS, "il catalogo degli strumenti e' vuoto"
    roots.add(tools.ToolDispatcher.__module__)
    todo = [Path(sys.modules[name].__file__) for name in roots
            if name.startswith("hiris.app")]
    seen: set[Path] = set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        todo.extend(_imports(path) - seen)
    return seen


def _string_keys(node: ast.Dict) -> set[str]:
    return {key.value for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)}


def _string_constants(node) -> set[str] | None:
    """Le stringhe di una tupla, lista o insieme di sole costanti; `None` se
    il nodo non e' una collezione di stringhe scritte."""
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)) or not node.elts:
        return None
    values = {element.value for element in node.elts
              if isinstance(element, ast.Constant) and isinstance(element.value, str)}
    return values if len(values) == len(node.elts) else None


def module_constants(tree) -> dict[str, set[str]]:
    """I nomi legati a una collezione di stringhe scritte
    (`_LIVE_KIND = ("classe", "unita")`), al primo livello del modulo o
    della funzione che si passa: le chiavi che una comprensione o un ciclo
    possono prendere da li'."""
    found: dict[str, set[str]] = {}
    for node in tree.body:
        targets, value = ((node.targets, node.value) if isinstance(node, ast.Assign)
                          else ([node.target], node.value) if isinstance(node, ast.AnnAssign)
                          else ([], None))
        strings = _string_constants(value) if value is not None else None
        for target in targets:
            if strings is not None and isinstance(target, ast.Name):
                found[target.id] = strings
    return found


def _comprehension_keys(node: ast.DictComp, constants: dict[str, set[str]]) -> set[str]:
    """Le chiavi di `{k: ... for k in COSTANTI}`: la chiave e' la variabile
    del ciclo, e il ciclo scorre una collezione di stringhe scritte, nel
    modulo o in linea (N113-1, giro 113: `_with_live_kind` sfuggiva cosi').

    Mutazione ESEGUITA: in `queries.py` una `_CAMPI = ("stato", "unita")` e
    una funzione `{k: ... for k in _CAMPI}` -- il cancello rosso col nome.
    Mutazione ESEGUITA: comprensioni non lette -- rossa
    `test_ogni_ammessa_compone_ancora`, con le due ammesse di N113-1."""
    if len(node.generators) != 1 or not isinstance(node.key, ast.Name):
        return set()
    loop = node.generators[0]
    if not isinstance(loop.target, ast.Name) or loop.target.id != node.key.id:
        return set()
    if isinstance(loop.iter, ast.Name):
        return set(constants.get(loop.iter.id, set()))
    return _string_constants(loop.iter) or set()


def _built_dicts(function, constants: dict[str, set[str]] | None = None
                 ) -> list[tuple[int, set[str]]]:
    """Ogni dizionario che la funzione costruisce, con le sue chiavi: i
    letterali, le comprensioni che prendono le chiavi da una collezione di
    stringhe scritte, e per ogni variabile le chiavi del letterale che le si
    assegna piu' quelle scritte con `x["chiave"] = ...`."""
    # Le costanti del modulo, piu' quelle legate a un nome dentro la funzione
    # (N114-1, giro 114).
    constants = {**(constants or {}), **module_constants(function)}
    built = [(node.lineno, _string_keys(node)) for node in ast.walk(function)
             if isinstance(node, ast.Dict)]
    built += [(node.lineno, _comprehension_keys(node, constants))
              for node in ast.walk(function) if isinstance(node, ast.DictComp)]
    by_name: dict[str, tuple[int, set[str]]] = {}
    # `for k in COSTANTI: x[k] = ...` (N114-1): la variabile del ciclo usata
    # come chiave porta le stringhe della collezione. Mutazioni ESEGUITE in
    # `queries.py`: una tupla locale con una comprensione, e un ciclo su una
    # tupla in linea con `riga[k] = ...` -- rosso il cancello, col nome.
    for loop in ast.walk(function):
        if not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Name):
            continue
        keys = (constants.get(loop.iter.id) if isinstance(loop.iter, ast.Name)
                else _string_constants(loop.iter))
        if not keys:
            continue
        for node in ast.walk(loop):
            for target in getattr(node, "targets", ()):
                if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and isinstance(target.slice, ast.Name)
                        and target.slice.id == loop.target.id):
                    by_name.setdefault(target.value.id, (node.lineno, set()))[1].update(keys)
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                by_name.setdefault(target.id, (node.lineno, set()))[1].update(
                    _string_keys(node.value))
            elif (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                  and isinstance(target.slice, ast.Constant)
                  and isinstance(target.slice.value, str)):
                by_name.setdefault(target.value.id, (node.lineno, set()))[1].add(
                    target.slice.value)
    return built + list(by_name.values())


def composers(modules: set[Path], fields: set[str]) -> dict[str, tuple[int, list[str]]]:
    """`modulo::funzione` -> (riga, campi dell'entita') per ogni funzione che
    costruisce un dizionario con almeno due campi dell'entita'."""
    found: dict[str, tuple[int, list[str]]] = {}
    for path in sorted(modules):
        relative = path.relative_to(APP).as_posix()
        if relative in RENDER_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = module_constants(tree)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for line, keys in _built_dicts(function, constants):
                common = sorted(keys & fields)
                name = f"{relative}::{function.name}"
                if len(common) >= 2 and name not in found:
                    found[name] = (line, common)
    return found


def entity_questions() -> set[str]:
    """Le domande che `House` sa fare su un'entita': i metodi il cui primo
    parametro e' `entity_id`, chiesti alla firma."""
    import inspect

    from hiris.app.home_space.house import House

    return {name for name, method in inspect.getmembers(House, inspect.isfunction)
            if list(inspect.signature(method).parameters)[1:2] == ["entity_id"]}


def separator_names(tree, separator: str) -> set[str]:
    """I nomi legati al separatore delle righe (`sep = " · "`), al primo
    livello del modulo o della funzione che si passa."""
    return {target.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(node.value, ast.Constant) and node.value.value == separator
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)}


def _text_composer(function, questions: set[str], separator: str,
                   names: frozenset[str] = frozenset()) -> bool:
    """Una funzione che chiede alla casa i campi di un'entita' e li unisce in
    una riga col separatore delle righe degli attori.

    L'unione ha tre forme (N123-2, giro 123): `" · ".join(...)`, un `.join`
    su un nome legato al separatore (`names`, del modulo o importato, piu'
    quelli della funzione), e una f-string che porta il separatore fra le sue
    parti scritte."""
    names = names | separator_names(function, separator)
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)]
    asks = any(call.func.attr in questions for call in calls)
    joins = any(call.func.attr == "join" and (
        (isinstance(call.func.value, ast.Constant) and call.func.value.value == separator)
        or (isinstance(call.func.value, ast.Name) and call.func.value.id in names))
        for call in calls)
    formats = any(isinstance(node, ast.JoinedStr) and any(
        isinstance(part, ast.Constant) and separator in str(part.value) for part in node.values)
        for node in ast.walk(function))
    return asks and (joins or formats)


#: Lista di AMMISSIONE del cancello del testo: `modulo::funzione` -> perche'
#: non e' la riga di un'entita'.
TEXT_ADMITTED: dict[str, str] = {
    "mind/recipes.py::muted_recipes": (
        "unisce i MOTIVI dei rifiuti di una ricetta (`silence`, uno per "
        "entita' che tace), non i campi di un'entita'"),
}


def text_composers(sources: dict[str, str], questions: set[str], separator: str) -> list[str]:
    """`modulo::funzione` per ogni funzione fuori dalla resa che compone la
    riga di testo di un'entita' (D8 della Tappa 4). `sources` e' `{modulo:
    sorgente}`."""
    from hiris.app.home_space import render

    exported = separator_names(ast.parse(Path(render.__file__).read_text(encoding="utf-8")),
                               separator)
    found = []
    for relative, source in sorted(sources.items()):
        if relative in RENDER_MODULES:
            continue
        tree = ast.parse(source)
        imported = {alias.asname or alias.name for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) for alias in node.names
                    if alias.name in exported}
        names = frozenset(separator_names(tree, separator) | imported)
        for function in ast.walk(tree):
            if (isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and _text_composer(function, questions, separator, names)):
                found.append(f"{relative}::{function.name}")
    return found


def app_sources() -> dict[str, str]:
    return {path.relative_to(APP).as_posix(): path.read_text(encoding="utf-8")
            for path in APP.rglob("*.py")}


# ── le derivazioni non si sono svuotate ────────────────────────────────────

def test_i_campi_dell_entita_si_chiedono_al_vocabolario():
    """Mutazione ESEGUITA: tolto `entita` dai proprietari della riga
    `stato_leggibile` del glossario -- rossa qui (`stato_leggibile` esce
    dall'insieme). Mutazione ESEGUITA: aggiunto `dispositivo` `area` ai
    proprietari della riga `unita` -- rossa (`unita` diventa di ogni oggetto)."""
    fields = entity_fields()
    assert {"stato", "stato_leggibile", "ultimo_cambio", "unita", "classe",
            "integrazione", "valore", "da_quando", "piattaforma"} <= fields, fields
    assert not fields & {"id", "nome", "genere", "area", "dispositivo"}, fields
    assert len(fields) >= 15, fields


def test_i_moduli_che_rispondono_si_chiedono_al_router_e_al_catalogo():
    """Mutazione ESEGUITA: un modulo nuovo `home_space/_prova_mutazione.py`
    con una funzione che restituisce `{"stato": ..., "da_quando": ...}`,
    importato da `queries.py` -- entra fra i moduli e fra i compositori senza
    toccare questa prova; tolto, esce."""
    modules = {path.relative_to(APP).as_posix() for path in responding_modules()}
    assert {"server.py", "home_space/tools.py", "home_space/queries.py",
            "home_space/house_query.py", "home_space/house_history.py",
            "home_space/energy.py", "api/handlers_home_space.py",
            "action/actuator.py", "mind/observer.py", "mind/recipe_turn.py",
            "keeper/exchange.py"} <= modules, sorted(modules)
    assert len(modules) >= 60, len(modules)


def test_il_cancello_legge_costanti_cicli_e_comprensioni():
    """N115-1 (giro 115): nessuna funzione del prodotto usa oggi una tupla
    locale, quindi la sola prova del cancello non direbbe se la lettura si
    e' rotta. Qui le tre forme, scritte apposta, e le chiavi pretese.

    Mutazione ESEGUITA: `_built_dicts` senza le costanti locali -- rossa
    (`locale` senza chiavi). Mutazione ESEGUITA: senza i cicli `x[k] = ...`
    -- rossa (`ciclo`). Mutazione ESEGUITA: senza le comprensioni -- rossa
    (`modulo`)."""
    tree = ast.parse(
        'CAMPI = ("stato", "unita")\n'
        'def modulo(e):\n'
        '    return {k: e for k in CAMPI}\n'
        'def locale(e):\n'
        '    nomi = ("classe", "integrazione")\n'
        '    return {k: e for k in nomi}\n'
        'def ciclo(e):\n'
        '    riga = {}\n'
        '    for k in ("stato_leggibile", "ultimo_cambio"):\n'
        '        riga[k] = e\n'
        '    return riga\n')
    constants = module_constants(tree)
    keys = {function.name: set().union(*(found for _line, found
                                         in _built_dicts(function, constants)))
            for function in tree.body if isinstance(function, ast.FunctionDef)}
    assert keys == {"modulo": {"stato", "unita"},
                    "locale": {"classe", "integrazione"},
                    "ciclo": {"stato_leggibile", "ultimo_cambio"}}, keys


def test_ogni_ammessa_compone_ancora():
    """Un'ammissione che non compone piu' niente e' un elenco invecchiato:
    esce con la funzione."""
    found = composers(responding_modules(), entity_fields())
    stale = sorted(set(ADMITTED) - set(found))
    assert not stale, f"ammesse che non compongono piu' un'entita': {stale}"


# ── il cancello ────────────────────────────────────────────────────────────

def test_nessuna_porta_compone_un_entita_fuori_dalla_resa():
    """Verde dalla Tappa 9 (F2, 12/10/2026): i renditori di C-01 chiamano
    `render_entity`, e chi resta compone un altro oggetto (`ADMITTED`).

    Mutazione ESEGUITA: una funzione di `home_space/queries.py` che torna a
    scrivere `da_quando` accanto a `stato` in una riga sua -- rossa, col nome
    della funzione e le due chiavi."""
    found = composers(responding_modules(), entity_fields())
    loose = {name: place for name, place in found.items() if name not in ADMITTED}
    assert not loose, (
        f"{len(loose)} funzioni compongono un'entita' fuori dalla resa:\n"
        + "\n".join(f"  {name} (riga {line}): {', '.join(keys)}"
                    for name, (line, keys) in sorted(loose.items())))


def test_il_cancello_del_testo_riconosce_una_riga_composta_a_mano():
    """La derivazione del cancello del testo non si e' svuotata: le domande
    della casa si chiedono alla firma di `House`, e la riga com'era fino al
    12/10/2026 (`recipe_turn.device_lines`) si riconosce."""
    from hiris.app.home_space.render import _LINE_SEPARATOR

    questions = entity_questions()
    assert {"kind_of", "where", "source"} <= questions, sorted(questions)
    sample = (
        "def device_lines(house, device_id):\n"
        "    lines = []\n"
        "    for entity_id in house.entities_of(device_id):\n"
        "        kind = house.kind_of(entity_id) or {}\n"
        "        lines.append(' · '.join([entity_id, kind.get('classe')]))\n"
        "    return lines\n")
    found = text_composers({"mind/prova.py": sample}, questions, _LINE_SEPARATOR)
    assert found == ["mind/prova.py::device_lines"]


def test_il_cancello_del_testo_riconosce_f_string_e_separatore_in_un_nome():
    """N123-2 (giro 123): la riga composta con una f-string, o con `.join` su
    un nome legato al separatore (locale, del modulo, o `_LINE_SEPARATOR`
    importato dalla resa), e' la stessa riga, e il cancello la vede.

    Mutazione ESEGUITA: `_text_composer` senza le f-string e senza i nomi --
    rossa su tutti e quattro i campioni. Mutazione ESEGUITA: senza i nomi
    importati -- rossa su `mind/importato.py`."""
    from hiris.app.home_space.render import _LINE_SEPARATOR

    questions = entity_questions()
    asks = "    kind = house.kind_of(entity_id) or {}\n"
    samples = {
        "mind/fstring.py": ("def riga(house, entity_id):\n" + asks
                            + "    return f\"{entity_id} · {kind.get('classe')}\"\n"),
        "mind/locale.py": ("def riga(house, entity_id):\n" + asks + "    sep = ' · '\n"
                           "    return sep.join([entity_id, kind.get('classe')])\n"),
        "mind/modulo.py": ("SEP = ' · '\n\ndef riga(house, entity_id):\n" + asks
                           + "    return SEP.join([entity_id, kind.get('classe')])\n"),
        "mind/importato.py": ("from ..home_space.render import _LINE_SEPARATOR\n\n"
                              "def riga(house, entity_id):\n" + asks
                              + "    return _LINE_SEPARATOR.join([entity_id, "
                                "kind.get('classe')])\n"),
    }
    found = text_composers(samples, questions, _LINE_SEPARATOR)
    assert found == sorted(f"{module}::riga" for module in samples), found
    other = {"mind/altro.py": ("def riga(house, entity_id):\n" + asks
                               + "    return f\"{entity_id}: {kind.get('classe')}\"\n")}
    assert text_composers(other, questions, _LINE_SEPARATOR) == []


def test_ogni_ammessa_del_testo_compone_ancora():
    from hiris.app.home_space.render import _LINE_SEPARATOR

    found = text_composers(app_sources(), entity_questions(), _LINE_SEPARATOR)
    assert not set(TEXT_ADMITTED) - set(found), sorted(set(TEXT_ADMITTED) - set(found))


def test_nessuno_compone_la_riga_di_un_entita_fuori_dalla_resa():
    """Le righe degli attori sono `render.entity_line` (Tappa 9, F4; D8 della
    Tappa 4): chi chiede alla casa i campi di un'entita' e li unisce in una
    riga la compone fuori dalla resa.

    Mutazione ESEGUITA: `recipe_turn.device_lines` com'era (i campi chiesti a
    `House.kind_of` e uniti con « · ») -- rossa col nome della funzione."""
    from hiris.app.home_space.render import _LINE_SEPARATOR

    found = text_composers(app_sources(), entity_questions(), _LINE_SEPARATOR)
    loose = [name for name in found if name not in TEXT_ADMITTED]
    assert loose == [], loose
