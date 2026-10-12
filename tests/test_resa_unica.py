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

**I limiti, dichiarati.** Le righe in TESTO per i modelli non sono
dizionari: `observer.house_lines`, `recipe_turn.device_lines` e
`keeper/exchange._domanda` compongono l'entita' in una stringa e il
cancello non le vede. Al Task 9 diventano la resa in testo dello stesso
dizionario (D8), e il cancello del testo nasce li'. `house_history._value_row`
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
    "mind/facts.py::_episodes": (
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
    router), quello del dispatcher degli strumenti (chiesto al catalogo), e
    la chiusura dei loro import dentro `hiris/app/`."""
    import sys

    from hiris.app import server
    from hiris.app.home_space import tools

    app = server.create_app()
    roots = {route.handler.__module__ for route in app.router.routes()}
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


def _built_dicts(function) -> list[tuple[int, set[str]]]:
    """Ogni dizionario che la funzione costruisce, con le sue chiavi: i
    letterali, e per ogni variabile le chiavi del letterale che le si assegna
    piu' quelle scritte con `x["chiave"] = ...`."""
    built = [(node.lineno, _string_keys(node)) for node in ast.walk(function)
             if isinstance(node, ast.Dict)]
    by_name: dict[str, tuple[int, set[str]]] = {}
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
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for line, keys in _built_dicts(function):
                common = sorted(keys & fields)
                name = f"{relative}::{function.name}"
                if len(common) >= 2 and name not in found:
                    found[name] = (line, common)
    return found


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
