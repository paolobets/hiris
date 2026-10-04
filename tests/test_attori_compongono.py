"""Gli attori compongono la casa (R13, criterio di accettazione 6; Tappa 3,
Task 12).

**Cosa difende.** Fino al 04/10/2026 osservatore e ricette si rifacevano la
casa da se': l'osservatore scorreva `home_space["entita"]`, nominava col nome
del registro, collocava con l'`area_id` proprio e una mappa delle aree sua
(`observer.house_lines`); le ricette prendevano ogni entita' del dispositivo,
comprese disabilitate, nascoste e di servizio (`recipe_turn._device_entities`),
e scorrevano i dispositivi per sapere a chi chiedere. Il resoconto
(`server._report_ingredients`) nominava i dispositivi scorrendo l'anagrafe.
Ogni volta che la casa imparava una regola -- il nome vivo (D1), l'area
ereditata (D3), la regola del fuori (D2) -- gli attori restavano indietro.

**La proprieta', non la forma** (CLAUDE.md, «Un cancello CHIEDE il suo
elenco»). Un attore che chiede `house.name(...)`, `house.where(...)`,
`house.entities_of(...)` e' giusto; uno che scorre le tabelle dell'anagrafe no.
Il cancello guarda le funzioni di `mind/` e quelle dei giri in `server.py`, e
trova:

- le letture di una **tabella** dell'anagrafe (`x["entita"]`,
  `x.get("dispositivi")`...): le tabelle si chiedono a `reader.TABLES`;
- le letture di un **campo** dell'anagrafe su cio' che ne e' uscito (`for e in
  ...["entita"]: e.get("area_id")`): i campi si chiedono alle chiavi che
  `reader._entity`, `_device` e `_area` restituiscono davvero.

Le funzioni dei giri si chiedono allo schedulatore dell'app avviata (i
lavori, e i moduli in cui vivono) e al grafo delle chiamate di quei moduli,
non si elencano qui: il nome del file non e' scritto in questa prova (il
cancello di `tests/test_prove_non_leggono_il_testo.py`).

Rosso letto il 04/10/2026 sul codice di prima (`06fcd59`), con le funzioni
dei giri chieste allo schedulatore: `observer._area_names`,
`observer.house_lines`, `recipe_turn._device_entities`, `_device_name`,
`devices_to_ask`, `_named_recipes`, `server.reconsideration_round` (l'anagrafe
intera per `measure_memory_window`) e `server._report_ingredients`.

Mutazioni ESEGUITE il 04/10/2026, ognuna ripristinata e verificata
(impronta del file uguale prima e dopo):
- rimessa in `house_lines` la mappa delle aree con `areas.get(entity.get(
  "area_id"))` -- rossa (il cancello: `tabella aree`);
- rimesso in `_report_ingredients` lo scorrimento di `dispositivi` -- rossa
  (il cancello);
- aggiunto a `reader._entity` un campo nuovo e in `mind/observer.py` una
  funzione che lo legge scorrendo `entita` -- rossa (`campo campo_nuovo`),
  senza toccare la prova: la derivazione dei campi e' viva;
- `House.entities_of` che torna tutte le entita' del dispositivo (la vecchia
  `_device_entities`) -- rossa
  (`test_le_ricette_vedono_solo_le_entita_che_la_casa_guarda`);
- `house_lines` col nome del registro, e con l'area propria -- rosse
  (`test_l_osservatore_riceve_il_nome_vivo_e_l_area_ereditata`);
- `apply_answer` che accetta ogni entita' dell'anagrafe -- rossa
  (`test_la_risposta_dell_osservatore_vale_per_cio_che_la_casa_ha_scelto`).
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

from hiris.app.home_space import reader
from hiris.app.home_space.house import House
from hiris.app.home_space.reader import build_home_space
from hiris.app.home_space.topology import live_mirror
from hiris.app.mind import observer, recipe_turn
from hiris.app.mind.store import ObservationsStore
from hiris.app.proxy.entity_cache import _to_minimal
from tests._avvio import started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs

APP = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"


def anagrafe_fields() -> frozenset[str]:
    """I campi dell'anagrafe, chiesti al lettore: le chiavi che `_entity`,
    `_device` e `_area` restituiscono su una riga minima di Home Assistant."""
    return frozenset(reader._entity({"entity_id": "x.y"})) | frozenset(
        reader._device({"id": "d"})) | frozenset(reader._area({"area_id": "a"}))


def _constant_key(node: ast.AST) -> str | None:
    """La chiave costante letta da `x[K]` o `x.get(K, ...)`, o `None`."""
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return node.slice.value if isinstance(node.slice.value, str) else None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return node.args[0].value
    return None


def _base(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.Subscript):
        return node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.value
    return None


def _reads_table(node: ast.AST, tables: frozenset[str]) -> bool:
    return any(_constant_key(sub) in tables for sub in ast.walk(node))


def _bound_names(target: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def scan_function(func: ast.AST, tables: frozenset[str],
                  fields: frozenset[str]) -> list[str]:
    """Le letture dell'anagrafe dentro UNA funzione: «tabella X» per ogni
    tabella letta, «campo Y» per ogni campo letto su un nome che viene da
    una tabella (un ciclo, una comprensione, un assegnamento)."""
    found: list[str] = []
    tainted: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, (ast.For, ast.comprehension)) and _reads_table(node.iter, tables):
            tainted |= _bound_names(node.target)
        elif isinstance(node, ast.Assign) and _reads_table(node.value, tables):
            for target in node.targets:
                tainted |= _bound_names(target)
    for node in ast.walk(func):
        key = _constant_key(node)
        if key is None:
            continue
        if key in tables:
            found.append(f"tabella {key}")
            continue
        base = _base(node)
        if key in fields and isinstance(base, ast.Name) and base.id in tainted:
            found.append(f"campo {key}")
    return found


def _functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _calls(func: ast.AST) -> set[str]:
    return {call.func.id if isinstance(call.func, ast.Name) else call.func.attr
            for call in ast.walk(func)
            if isinstance(call, ast.Call) and isinstance(call.func, (ast.Name, ast.Attribute))}


def _job_sources(app) -> tuple[set[str], set[pathlib.Path]]:
    """I lavori periodici dell'app avviata, e i moduli in cui vivono: tutti e
    due si chiedono allo schedulatore (`job.func`), non si scrivono qui. Se
    domani i giri escono dal modulo di oggi, il cancello li segue."""
    jobs = app["scheduler"].get_jobs()
    names = {job.func.__name__ for job in jobs}
    files = {pathlib.Path(sys.modules[job.func.__module__].__file__) for job in jobs}
    return names, files


def round_functions(app) -> dict[str, ast.AST]:
    """Le funzioni che un lavoro periodico raggiunge, nei moduli dei lavori,
    per nome: i lavori dallo schedulatore, il resto dal grafo delle chiamate
    (anche le funzioni annidate di `_on_startup`, che sono i lavori stessi)."""
    names, files = _job_sources(app)
    by_name: dict[str, tuple[str, ast.AST]] = {}
    for path in sorted(files):
        for func in _functions(ast.parse(path.read_text(encoding="utf-8"))):
            by_name.setdefault(func.name, (path.name, func))
    seen, todo = set(), [n for n in names if n in by_name]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(c for c in _calls(by_name[name][1]) if c in by_name)
    return {f"{by_name[name][0]}::{name}": by_name[name][1] for name in seen}


def actor_functions(app) -> dict[str, ast.AST]:
    out = {}
    for path in sorted((APP / "mind").glob("*.py")):
        for func in _functions(ast.parse(path.read_text(encoding="utf-8"))):
            out[f"mind/{path.name}::{func.name}"] = func
    out.update(round_functions(app))
    return out


def violations(functions: dict[str, ast.AST]) -> dict[str, list[str]]:
    tables, fields = frozenset(reader.TABLES), anagrafe_fields()
    out = {}
    for name, func in functions.items():
        found = scan_function(func, tables, fields)
        if found:
            out[name] = sorted(set(found))
    return out


@pytest.mark.asyncio
async def test_nessun_attore_scorre_l_anagrafe(started_app):
    """Il criterio di accettazione 6. Rosso il 04/10/2026 sul codice di prima
    su osservatore (`house_lines`, `_area_names`), ricette (`_device_entities`,
    `_device_name`, `devices_to_ask`, `_named_recipes`) e server
    (`_report_ingredients`, il giro dello scope)."""
    found = violations(actor_functions(started_app))
    assert not found, found


@pytest.mark.asyncio
async def test_la_derivazione_non_si_e_svuotata(started_app):
    """Le due prove della derivazione. I campi chiesti al lettore ci sono
    tutti quelli che le copie leggevano; i giri del server trovati comprendono
    quelli che compongono la casa; e una funzione piantata che scorre
    l'anagrafe e ne legge un campo si vede, senza toccare la prova."""
    fields = anagrafe_fields()
    assert {"area_id", "dispositivo_id", "translation_key", "nome", "classe",
            "unita", "piano_id"} <= fields
    rounds = {key.split("::")[1] for key in round_functions(started_app)}
    assert {"_report_ingredients", "recipe_round",
            "reconsideration_round"} <= rounds, sorted(rounds)
    planted = ast.parse(
        "def f(home_space):\n"
        "    for e in home_space.get('entita') or []:\n"
        "        yield e.get('area_id')\n"
        "def g(rows):\n"
        "    return [r.get('area_id') for r in rows]\n")
    found = violations({f.name: f for f in _functions(planted)})
    assert found == {"f": ["campo area_id", "tabella entita"]}


# -- cio' che gli attori ricevono, sulla casa sintetica (D1, D2, D3) ---------

def _house():
    inputs = synthetic_inputs()
    return House(build_home_space(inputs["registries"]),
                 live_mirror([_to_minimal(row) for row in inputs["states"]]))


def test_l_osservatore_riceve_il_nome_vivo_e_l_area_ereditata():
    """D1 «vivo» e D3 «si'»: `sensor.sensore_a_temperatura` non ha un'area
    propria (la eredita da `dev_a`, Stanza uno) e il registro la chiama
    «Temperatura» mentre Home Assistant la mostra «Sensore A Temperatura»."""
    line = next(line for line in observer.house_lines(_house())
                if line.startswith("sensor.sensore_a_temperatura "))
    assert line == ("sensor.sensore_a_temperatura · Sensore A Temperatura · "
                    "temperature · °C · Stanza uno")


def test_le_ricette_vedono_solo_le_entita_che_la_casa_guarda():
    """D2 «si'»: di `dev_b` la ricetta vedeva anche il segnale (`diagnostic`)
    e la soglia (`config`); di `dev_d`, disabilitato, l'entita' spenta."""
    house = _house()
    assert [line.split(" · ")[0] for line in recipe_turn.device_lines(house, "dev_b")] == [
        "sensor.sensore_b_potenza", "switch.presa_uno"]
    assert recipe_turn.device_lines(house, "dev_d") == []
    assert house.entities_of("dev_b") == ["sensor.sensore_b_potenza", "switch.presa_uno"]
    assert [e["id"] for e in house.device_entities("dev_b")] == [
        "sensor.sensore_b_potenza", "switch.presa_uno", "sensor.sensore_b_segnale",
        "number.sensore_b_soglia"]


def test_la_risposta_dell_osservatore_vale_per_cio_che_la_casa_ha_scelto(tmp_path):
    """L'insieme valido di `apply_answer` e' la scelta della casa, non le
    righe rilette: un'entita' di servizio nominata dal modello si ignora."""
    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        outcome = observer.apply_answer(
            store, _house(),
            '[{"id": "sensor.sensore_b_segnale", "dentro": true, "motivo": "x"},'
            ' {"id": "light.luce_uno", "dentro": true, "motivo": "illumina"}]',
            record=False, now=1_790_000_000.0)
    finally:
        store.close()
    assert (outcome["decise"], outcome["ignorate"]) == (1, 1)
