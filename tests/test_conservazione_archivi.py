"""Ogni archivio dichiara per quanto tiene, e uno solo li pota (Tappa 8, Task 6).

Il reperto C-6 (23/09/2026) aveva dato a `osservazioni.db` una decisione
scritta accanto a ogni tabella. Gli altri archivi no: ognuno potava a modo
suo -- a ogni turno, a ogni promessa, a ogni proposta, a ogni comando, a ogni
spazzata (e solo a ponte acceso) -- e nessuno sapeva rispondere a «per
quanto tempo HIRIS ricorda questa cosa».

**Il cancello CHIEDE il suo elenco** (CLAUDE.md, I-0): quali siano gli
archivi lo dice il codice, cioe' le classi che chiamano `storage.init_schema`,
lette dall'albero sintattico del prodotto. Non c'e' un elenco da tenere
allineato: un archivio nuovo entra nella prova da solo, e senza dichiarazione
la ferma.
"""
import ast
import json
import pathlib
import time
from importlib import import_module
from types import SimpleNamespace

import pytest

from hiris.app import conservazione, server, storage
from tests._avvio import started_app  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
#: La casa di `init_schema`, chiesta al modulo: la definizione non e' un chiamante.
STORAGE = pathlib.Path(storage.__file__).resolve()


def _calls_init_schema(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "init_schema":
                return True
    return False


def archive_classes() -> set[tuple[str, str]]:
    """`(modulo, classe)` di ogni classe del prodotto che chiama
    `init_schema`: gli archivi, chiesti al codice."""
    found = set()
    for path in sorted(APP.rglob("*.py")):
        if path.resolve() == STORAGE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _calls_init_schema(node):
                found.add((module, node.name))
    return found


def _files_naming_init_schema() -> set[str]:
    """Un secondo modo di guardare, piu' grezzo: i file che chiamano
    `init_schema(` nel testo. Serve a vedere che la derivazione non si sia
    rotta, non a sostituirla."""
    found = set()
    for path in APP.rglob("*.py"):
        if path.resolve() == STORAGE:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            if "init_schema(" in code and "def init_schema" not in code:
                found.add(".".join(path.relative_to(ROOT).with_suffix("").parts))
    return found


def test_la_derivazione_non_si_e_rotta():
    """Un insieme improvvisamente piccolo e' un cancello che sembra vivo e
    non guarda piu' niente. Due prove: l'archivio del cervello, il primo che
    ha dichiarato (C-6), c'e'; e ogni file che chiama `init_schema(` nel
    testo ha una classe fra quelle derivate dall'albero sintattico."""
    classes = archive_classes()
    assert ("hiris.app.mind.store", "ObservationsStore") in classes
    assert _files_naming_init_schema() == {module for module, _ in classes}


def _declaration(module: str) -> dict:
    declared = getattr(import_module(module), "CONSERVAZIONE", None)
    assert isinstance(declared, dict), (
        f"{module}: un archivio senza la dichiarazione `CONSERVAZIONE` accanto "
        "allo schema -- per quanto tiene ogni tabella, e perche'")
    return declared


@pytest.mark.parametrize("module,name", sorted(archive_classes()))
def test_ogni_archivio_dichiara_e_sa_potarsi(module, name):
    """La forma di `mind/store.CONSERVAZIONE` (`storage.Retention`): per
    tabella i giorni (`None` = per sempre), la ragione, e la cancellazione
    -- una frase SQL letterale che nomina la tabella in chiaro, perche' il
    censimento la veda, con al piu' un `?` (il confine, che `prune_declared`
    calcola dai giorni). E una classe che la porta e sa applicarla."""
    declared = _declaration(module)
    assert declared, f"{module}: una dichiarazione vuota non dichiara niente"
    for table, (days, reason, deletion) in declared.items():
        assert isinstance(reason, str) and reason.strip(), (
            f"{module}.{table}: tiene per un tempo che nessuno spiega")
        if days is None:
            assert deletion is None, f"{module}.{table}: per sempre, e si cancella"
            continue
        assert isinstance(days, int) and days > 0, f"{module}.{table}: {days!r}"
        assert deletion and f"DELETE FROM {table} " in deletion, (
            f"la cancellazione di «{table}» non la nomina in chiaro")
        assert deletion.count("?") <= 1, f"{module}.{table}: {deletion}"
    kind = getattr(import_module(module), name)
    assert hasattr(kind, "CONSERVAZIONE"), f"{name} non porta la sua dichiarazione"
    assert callable(getattr(kind, "prune", None)), f"{name} non sa potarsi"


def _tables(store) -> set[str]:
    return {row[0] for row in store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")}


@pytest.mark.asyncio(loop_scope="module")
async def test_l_app_avviata_pota_tutti_e_soli_gli_archivi(started_app):
    """Gli archivi che il lavoro notturno trova sull'app (`archives`) sono
    esattamente le classi che chiamano `init_schema`: uno aperto e non
    potato crescerebbe per sempre, uno potato e non derivato sfuggirebbe a
    questa prova. E di ognuno la dichiarazione copre tutte e sole le tabelle
    che l'archivio ha davvero su disco."""
    found = conservazione.archives(started_app)
    kinds = {(type(store).__module__, type(store).__name__) for _, store in found}
    assert kinds == archive_classes()
    for name, store in found:
        declared = set(_declaration(type(store).__module__))
        assert set(store.CONSERVAZIONE) == declared, name
        assert _tables(store) == declared, (
            f"{name}: tabelle senza decisione {sorted(_tables(store) - declared)}, "
            f"decisioni senza tabella {sorted(declared - _tables(store))}")
        assert isinstance(store.prune(time.time()), int), name


@pytest.mark.asyncio(loop_scope="module")
async def test_la_salute_dice_per_quanto_HIRIS_ricorda(started_app):
    """D7: un campo di sola lettura in `/api/health`, chiesto alle
    dichiarazioni -- una riga per tabella di ogni archivio, coi giorni e la
    ragione. Il valore e' quello della dichiarazione, non una copia.

    Mutazione ESEGUITA (08/10/2026): tolta la chiave `conservazione` da
    `handle_health` -- rossa (`KeyError`)."""
    response = await server.handle_health(SimpleNamespace(app=started_app, get={}.get))
    rows = json.loads(response.body)["conservazione"]
    assert rows == conservazione.declarations(started_app)
    by_place = {(row["archivio"], row["tabella"]): row for row in rows}
    for name, store in conservazione.archives(started_app):
        for table, (days, reason, _deletion) in store.CONSERVAZIONE.items():
            assert by_place[(name, table)]["giorni"] == days
            assert by_place[(name, table)]["ragione"] == reason
    assert {name for name, _ in conservazione.archives(started_app)} >= {
        "osservazioni.db", "reasoning.db", "chat_history.db"}


@pytest.mark.asyncio(loop_scope="module")
async def test_la_coda_del_ponte_si_pota_a_ponte_spento(started_app):
    """Fino all'08/10/2026 la coda si potava dentro la spazzata, e la
    spazzata a ponte spento non girava: chi spegneva il ponte si teneva la
    coda per sempre. Adesso la pota il lavoro notturno, come ogni archivio,
    e il ponte non c'entra.

    Mutazione ESEGUITA (08/10/2026): in `conservazione.nightly` l'archivio
    della coda saltato quando `app["bridge_active"]` e' falso -- rossa."""
    from unittest import mock

    queue = started_app["reasoning_queue"]
    window_s = queue.CONSERVAZIONE["reasoning_jobs"][0] * storage.DAY_S
    born = time.time() - window_s - 3600
    queue.enqueue("chat", {}, {}, born + 60, job_id="vecchio", now=born)
    queue.sweep_expired(now=born + 120)
    assert queue.get("vecchio")["status"] == "expired"

    with mock.patch.dict(started_app, {"bridge_active": False}):
        await started_app["scheduler"].get_job("hiris_retention").func()

    assert queue.get("vecchio") is None
