"""R3: un'entita' si compone in un posto solo, la resa (Tappa 4).

Lo scheletro del cancello R3 dello sprint «Una fonte sola di verita'» (spec
`docs/design/2026-10-01-una-fonte-sola-di-verita.md`, R3; piano della Tappa 4,
Task 1, passo 4). Oggi e' ROSSO, e deve esserlo: le funzioni che compongono
«un'entita' col suo stato» ciascuna per conto suo sono circa quattordici
(registro, C-01). La prova principale e' marcata `xfail(strict=True)`: rossa
oggi per la ragione giusta -- il messaggio le elenca --, e il giorno in cui
diventasse verde senza che qualcuno tolga il marcatore, la suite si ferma. Il
marcatore esce al Task 11, quando la resa e' unica.

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

**Cosa trova oggi, oltre a C-01** (05/10/2026): `mind/analyst_turn._enrich`
e `mind/report._measurements` (un'entita' col suo valore e l'unita', verso
il modello), `topology.hierarchy` (le righe annidate dell'albero, che
`/api/home-space` manda). E tre che il Task 11 deve giudicare prima di
togliere il marcatore: `house_history.error_rows` (`fonte` e `integrazione`
di una riga d'errore: con D5 `fonte` diventa `codice` e la riga esce da
sola), `mind/facts.build_episodes` e `mind/facts.close` (gli episodi del
sapere, che portano classe e stato dell'entita' nell'archivio).

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

import pytest

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
    "action/construction/revisions.py::_row": (
        "la riga di una costruzione, non un'entita': `stato` e' quello della "
        "costruzione (in attesa, confermata...) e `dominio` quello della voce "
        "di configurazione che costruisce. Due parole del vocabolario, un "
        "altro oggetto"),
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

@pytest.mark.xfail(strict=True, reason=(
    "R3 non e' ancora vero: le funzioni che compongono un'entita' per conto "
    "proprio sono quelle di C-01, e la resa unica (`home_space/render.py`) "
    "nasce al Task 7 della Tappa 4. Il marcatore esce al Task 11"))
def test_nessuna_porta_compone_un_entita_fuori_dalla_resa():
    """Mutazione ESEGUITA (oggi, per vedere il verde del giorno dopo): con
    `ADMITTED` allargato a ogni compositore trovato, la prova passa e
    `strict=True` la fa fallire come XPASS. Il rosso di oggi elenca, fra le
    altre, `queries.py::_view_device` (il dizionario base in linea, la
    mutazione che il piano chiede di eseguire al Task 11)."""
    found = composers(responding_modules(), entity_fields())
    loose = {name: place for name, place in found.items() if name not in ADMITTED}
    assert not loose, (
        f"{len(loose)} funzioni compongono un'entita' fuori dalla resa:\n"
        + "\n".join(f"  {name} (riga {line}): {', '.join(keys)}"
                    for name, (line, keys) in sorted(loose.items())))
