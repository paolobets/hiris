"""«Quali entita' hanno statistiche?» si chiede una volta per giro, e solo se
serve (Tappa 2, Task 8: A-05, A-20).

`recorder/list_statistic_ids` serve a due giri: le ricette (`recipe_round`,
ogni dieci minuti: potare le ricette senza serie e dire al modello quali
entita' ne hanno) e gli ingredienti del resoconto (`_report_ingredients`: il
recupero ogni cinque minuti, l'aggregazione notturna, la riparazione
d'avvio). Contato sul codice del 04/10/2026, prima di queste prove: ognuno la
leggeva per conto suo (due letture dello stesso elenco in `server.py`), e il
giro delle ricette la leggeva a ogni passaggio anche senza niente da potare
ne' da chiedere -- prima di guardare se ci fosse qualcosa da fare.

Ora la lettura vive in `server.statistic_ids_for_round`: una memoria piu'
breve del giro piu' frequente che la usa (cosi' un giro non riusa mai la
propria lettura precedente, ma due giri vicini ne fanno una sola), e mai su
un guasto.
"""
import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app import server
from hiris.app.home_space.house import House
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import recipe_turn
from hiris.app.mind.knowledge import KnowledgeStore
from hiris.app.mind.store import ObservationsStore
from tests._avvio import started_app  # noqa: F401
from tests._casa_sintetica import synthetic_inputs

pytestmark = pytest.mark.asyncio(loop_scope="module")

_LIST = "recorder/list_statistic_ids"
_STATISTICS = "recorder/statistics_during_period"

CASA = {
    "dispositivi": [{"id": "dev1", "nome": "Inverter"}],
    "entita": [
        {"id": "sensor.prodotta", "nome": "Energia prodotta oggi",
         "dispositivo_id": "dev1", "classe": "energy", "unita": "kWh"},
    ],
    "aree": [],
}

RICETTA = {
    "why": "l'inverter pesa sul risparmio",
    "steps": [{"name": "prodotta", "operation": "somma_periodo",
               "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh"}}],
}


class _Anagrafe(HomeSpace):
    """L'anagrafe vera con la casa di queste prove: serve intera, perche' il
    giro le chiede anche la dashboard Energia (Task 2.2 degli attori)."""

    def __init__(self):
        super().__init__("/percorso/che/non/esiste")

    def read(self):
        return CASA

    def unavailable(self):
        return []


@pytest.fixture
def stores(tmp_path):
    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    yield sapere, archivio
    sapere.close()
    archivio.close()


def _house() -> CasaFinta:
    """La casa sintetica col client vero; l'elenco delle statistiche porta
    l'entita' della ricetta (altrimenti il giro la poterebbe), e le
    statistiche orarie rispondono vuote."""
    return CasaFinta(synthetic_inputs(), answers={
        _LIST: lambda extra: [{"statistic_id": "sensor.prodotta"}],
        _STATISTICS: lambda extra: {}})


def _app(stores, house):
    sapere, archivio = stores
    return {"observations": archivio, "knowledge": sapere,
            "home_space_store": _Anagrafe(), "ha_client": house}


def _asked(house: CasaFinta) -> int:
    return sum(1 for command, _extra in house.calls if command == _LIST)


def _with_recipe(sapere):
    recipe_turn.apply_recipe(sapere, House(CASA, Mirror()), "dev1", json.dumps(RICETTA),
                             who="prova", when_ts=1789000000.0)
    assert recipe_turn.recipes(sapere).get("dev1") is not None


async def test_niente_da_potare_ne_da_chiedere_nessuna_lettura(stores):
    """A-20: nessuna ricetta scritta e nessun dispositivo da chiedere (lo
    scope e' vuoto): il giro non ha niente da fare, e non chiede niente.

    Rosso letto prima del codice: `assert 1 == 0` -- la lettura partiva
    prima della domanda «c'e' qualcosa da fare?».

    Mutazione (verificata eseguendola): togliere la guardia -- rossa."""
    house = _house()

    assert await server.recipe_round(_app(stores, house)) is None
    assert _asked(house) == 0


async def test_con_una_ricetta_da_controllare_si_legge(stores):
    """L'altra meta': una ricetta scritta si controlla (puo' essere senza
    serie), e per controllarla serve l'elenco.

    Mutazione (verificata eseguendola): `has_named_recipes` (allora
    `has_prunable_recipes`) che risponde
    sempre `False` -- rossa (`assert 0 == 1`)."""
    _with_recipe(stores[0])
    house = _house()

    await server.recipe_round(_app(stores, house))

    assert _asked(house) == 1


async def test_due_giri_vicini_una_lettura_sola(stores):
    """A-05: il giro delle ricette e gli ingredienti del resoconto, uno
    dietro l'altro: l'elenco si legge una volta.

    Rosso letto prima del codice: `assert 2 == 1`.

    Mutazione (verificata eseguendola): nessuna memoria -- rossa."""
    _with_recipe(stores[0])
    house = _house()
    app = _app(stores, house)

    await server.recipe_round(app)
    _ricette, _serie, _nomi, silent = await server._report_ingredients(
        app, house, giorno="2026-10-03", timezone="Europe/Rome")

    assert _asked(house) == 1
    assert silent == {}


async def test_un_guasto_non_si_ricorda(stores):
    """Un elenco non letto non vale per il giro dopo: si richiede.

    Mutazione (verificata eseguendola): ricordare anche la busta del guasto
    -- rossa: la seconda lettura rende la busta ricordata invece
    dell'elenco (`assert isinstance(second, set)`)."""
    house = CasaFinta(synthetic_inputs(), silence={_LIST})
    app = {}

    first = await server.statistic_ids_for_round(app, house)
    house.unmute(_LIST)
    second = await server.statistic_ids_for_round(app, house)

    assert "errore" in first
    assert isinstance(second, set)
    assert _asked(house) == 2


async def test_la_memoria_scade(stores):
    """Passata la memoria, si richiede: e' piu' breve di ogni giro, quindi un
    giro non riusa mai la propria lettura precedente.

    Mutazione (verificata eseguendola): `<=` al posto di `<` nel confronto
    dell'eta' -- rossa sul bordo."""
    house = _house()
    app = {}
    memory = server.STATISTIC_IDS_MEMORY_S

    await server.statistic_ids_for_round(app, house, now=1000.0)
    await server.statistic_ids_for_round(app, house, now=1000.0 + memory - 1)
    assert _asked(house) == 1
    await server.statistic_ids_for_round(app, house, now=1000.0 + memory)
    assert _asked(house) == 2


APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


def _call_graph() -> dict[str, set[str]]:
    """Per ogni funzione del prodotto (anche quelle annidate, come i lavori
    di `_on_startup`), i nomi che chiama -- su tutto `hiris/app`, non su un
    file: un giro spostato in un altro modulo resta nel grafo. Due funzioni
    con lo stesso nome si fondono: il grafo vede un chiamante di troppo, mai
    uno di meno, e la prova diventa piu' severa, non piu' cieca."""
    graph: dict[str, set[str]] = {}
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                graph.setdefault(node.name, set()).update(
                    call.func.id if isinstance(call.func, ast.Name) else call.func.attr
                    for call in ast.walk(node)
                    if isinstance(call, ast.Call)
                    and isinstance(call.func, (ast.Name, ast.Attribute)))
    return graph


def _reaches(graph, start: str, target: str) -> bool:
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name == target:
            return True
        if name not in seen:
            seen.add(name)
            todo.extend(graph.get(name, ()))
    return False


async def test_la_memoria_e_piu_breve_di_ogni_giro_che_la_usa(started_app):
    """La memoria si confronta con i lavori periodici che arrivano davvero a
    `statistic_ids_for_round`, chiesti allo schedulatore dell'app avviata e
    al grafo delle chiamate del prodotto -- non scritti qui.

    Le due prove della derivazione: i giri trovati non sono zero (oggi il
    giro delle ricette e il recupero dei resoconti a intervallo, piu'
    l'aggregazione notturna a orario); e la mutazione eseguita -- la memoria
    portata a 300 secondi, la cadenza del recupero -- rossa."""
    graph = _call_graph()
    users = [job for job in started_app["scheduler"].get_jobs()
             if _reaches(graph, job.func.__name__, "statistic_ids_for_round")]
    intervals = [job.trigger.interval.total_seconds() for job in users
                 if hasattr(job.trigger, "interval")]
    assert len(intervals) >= 2, [job.id for job in users]
    assert server.STATISTIC_IDS_MEMORY_S < min(intervals)


class _Modello:
    """Il modello della catena: conta le domande, risponde senza ricetta."""

    def __init__(self):
        self.domande = []

    async def chat(self, user_message, **kw):
        self.domande.append(user_message)
        return "{}"


async def test_una_ricetta_rotta_si_richiede_nello_stesso_giro(stores):
    """Il dispositivo la cui ricetta non puo' calcolare (nessuna sua entita'
    ha statistiche) torna una domanda, e si chiede GIA' in questo giro, con
    la domanda che dice perche' (attori, Task 1.6: prima la ricetta si
    potava, ora si ripara nel suo giro). La risposta del modello qui e'
    storta, e la ricetta vecchia non calcolava niente: si sostituisce col
    «non capito», come faceva la potatura.

    Mutazione (verificata eseguendola il 05/10/2026): non aggiungere i
    dispositivi da riparare a quelli da chiedere -- rossa (`assert 0 ==
    1`: nessuna domanda)."""
    sapere, archivio = stores
    _with_recipe(sapere)
    archivio.decide_scope("sensor.prodotta", inside=True, reason="pesa",
                          author="proprietario")
    # Una casa senza dashboard Energia: la domanda resta quella di prima.
    house = CasaFinta(synthetic_inputs(), answers={_LIST: lambda extra: []},
                      refuse={"energy/get_prefs": {"code": "not_found",
                                                   "message": "No prefs"}})
    modello = _Modello()
    app = {**_app(stores, house), "llm_router": modello}

    await server.recipe_round(app)

    assert recipe_turn.recipes(sapere).get("dev1") is None
    assert len(modello.domande) == 1
    assert "Inverter" in modello.domande[0]
    assert "non funziona piu'" in modello.domande[0]
    assert _asked(house) == 1
