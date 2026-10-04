"""La casa si costruisce UNA volta per turno (R18; Tappa 3, Task 2 e 4).

Un turno di chat sull'app avviata davvero (la montatura di `tests/_avvio.py`,
`fotografia_porte.mounted`, con una casa che serve anche lo storico: la casa
condivisa dell'avvio non lo porta, e la `history` cadrebbe prima di contare
niente): il nucleo, tre
`search` (per nome, per riferimento d'area, per genere) e una `history`, sullo
STESSO dispatcher. Si contano le chiamate a `topology.hierarchy` (la
gerarchia) e a `topology.live_mirror` (lo specchio in sei mappe): il tetto e'
una e una. Oggi ogni porta se le rifa' da se' -- misurato sulla casa sintetica
nel piano: una `search` per nome tre gerarchie, quattro se trova un'area --
quindi la prova e' rossa, marcata `xfail(strict=True)` fino al Task 4, che
porta l'istantanea `House` e toglie il marcatore. Strict: il giorno in cui
passa senza che nessuno l'abbia tolto, fallisce e lo dice.

**I moduli da avvolgere si CHIEDONO** a `sys.modules`, cercando l'oggetto
funzione e non il suo nome: un modulo che importa `hierarchy` per nome (o
sotto un altro nome) ha una sua copia del riferimento, e avvolgere solo
`topology` lascerebbe le sue chiamate fuori dal conto. Un elenco scritto a
mano invecchierebbe in silenzio (CLAUDE.md, «un cancello chiede il suo
elenco»).

Le due prove della derivazione: (a) qui sotto, i moduli avvolti non sono zero
e il turno passa davvero da loro (il conto e' maggiore di zero: un conto a
zero sarebbe un tetto rispettato senza guardare niente); (b) la mutazione si
esegue al Task 4, quando la prova diventa verde: si riporta una porta a
ricostruirsi la casa e la prova torna rossa.

Misurato il 03/10/2026 sulla casa sintetica: il turno fa 10 gerarchie e 5
specchi (la prova a tetto, letta con `--runxfail`: «Counter({'hierarchy': 10,
'live_mirror': 5})»).

Mutazione ESEGUITA il 03/10/2026 sulla derivazione: avvolto il solo modulo
`topology`, senza cercare gli altri in `sys.modules` -- rossa la prova della
derivazione («avvolto solo dove nasce»), e il conto scende a 8 gerarchie e 0
specchi: le chiamate di chi importa per nome non si vedevano piu'.
Ripristinata, `git status` pulito.

**Verde dal 04/10/2026 (Task 4):** l'istantanea `home_space.house.House`,
letta una volta da chi apre il turno (`handlers_home_space.house_of`) e
passata a nucleo e dispatcher. Il marcatore `xfail` e' uscito. Le prove in
fondo difendono l'altra meta' di R18: la casa vale UN turno -- il turno dopo
vede lo specchio cambiato, l'anagrafe ricostruita a meta' turno si rilegge,
un comando eseguito la butta, e nessuna `House` resta in `app[...]`.

Mutazioni ESEGUITE il 04/10/2026, ognuna ripristinata (`git status`):
- in `house_query._area_rows`, la gerarchia ricostruita con
  `topology.hierarchy(...)` invece di `house.hierarchy()` -- rossa la prova a
  tetto, «Counter({'hierarchy': 3, 'live_mirror': 1})» (le due `search` che
  passano dalle aree se ne rifanno una ciascuna);
- `house_of` che tiene la casa in `app["casa_tenuta"]` e la riusa -- rosse
  tre prove: il tetto (Counter() -- la casa del turno prima, gia' contata),
  «nessuna House nell'app» e il turno nuovo («'off' == 'on'»);
- `_execute` senza `self._house = None` -- rossa la prova del comando;
- `_turn_house` senza il confronto d'identita' sull'anagrafe -- rossa la
  prova dell'anagrafe ricostruita.
"""
import sys
from collections import Counter
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.handlers_home_space import compose_briefing, house_of
from hiris.app.home_space import topology
from hiris.app.home_space.house import House
from hiris.app.home_space.tools import ToolDispatcher
from tests._casa_sintetica import INSTANT, synthetic_inputs

pytestmark = pytest.mark.asyncio(loop_scope="module")

#: L'entita' di cui il turno chiede la storia.
ASKED = "sensor.sensore_a_temperatura"


class HouseWithHistory(fotografia_porte.FrozenHouse):
    """La casa sintetica che risponde anche a `GET /api/history/period`, nella
    forma grezza di `minimal_response` (un gruppo per entita', l'`entity_id`
    sul primo punto). Firma di `HAClient`, come la vuole `mounted`."""

    def __init__(self, base_url=None, token=None) -> None:
        super().__init__(synthetic_inputs(), answers={"/api/history/period": lambda path: [
            [{"entity_id": ASKED, "state": "21.5", "last_changed": INSTANT}]]})


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def started_app(tmp_path_factory):
    data_dir = str(tmp_path_factory.mktemp("casa_per_turno"))
    async with fotografia_porte.mounted(synthetic_inputs(), data_dir, HouseWithHistory) as app:
        yield app

#: Le due costruzioni della casa che un turno dovrebbe fare una volta sola.
COUNTED = {"hierarchy": topology.hierarchy, "live_mirror": topology.live_mirror}


def _holders(target) -> list[tuple[object, str]]:
    """Ogni (modulo, nome) del prodotto che tiene QUESTO oggetto: il modulo
    che lo definisce e chi l'ha importato per nome."""
    found = []
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith("hiris.app"):
            continue
        for attribute, value in list(vars(module).items()):
            if value is target:
                found.append((module, attribute))
    return found


@pytest.fixture
def counted(monkeypatch):
    """Avvolge ogni riferimento alle due funzioni e conta le chiamate."""
    calls: Counter = Counter()
    wrapped: dict[str, list[str]] = {}
    for label, target in COUNTED.items():
        def counting(*args, _label=label, _target=target, **kwargs):
            calls[_label] += 1
            return _target(*args, **kwargs)
        holders = _holders(target)
        wrapped[label] = sorted(module.__name__ for module, _attribute in holders)
        for module, attribute in holders:
            monkeypatch.setattr(module, attribute, counting)
    return calls, wrapped


async def _chat_turn(app) -> list[dict]:
    """Il nucleo, tre `search` e una `history` su un dispatcher solo, come in
    un turno di chat. Le risposte tornano, perche' un turno che fallisce non
    conta niente.

    La casa del turno la legge chi apre il turno e la passa a nucleo e
    strumenti, come `handlers_chat.handle_chat`."""
    house = house_of(app)
    compose_briefing(app, house)
    dispatcher = create_tool_dispatcher(app, house=house)
    return [
        await dispatcher.dispatch("search", {"nome": "Sensore"}),
        await dispatcher.dispatch("search", {"genere": "area", "riferimento": "stanza_uno"}),
        await dispatcher.dispatch("search", {"genere": "dispositivo"}),
        await dispatcher.dispatch("history", {"riferimento": ASKED, "genere": "stati",
                                              "ore": 24}),
    ]


async def test_la_derivazione_avvolge_chi_tiene_le_funzioni_e_vede_il_turno(
        started_app, counted):
    calls, wrapped = counted
    for label in COUNTED:
        assert "hiris.app.home_space.topology" in wrapped[label], wrapped
    # La gerarchia la importano per nome altri moduli: senza cercarli, le
    # loro chiamate sfuggirebbero. Lo specchio no, dal 04/10/2026 (B-41):
    # i lettori passano da `topology.read_mirror`, che lo costruisce dentro
    # `topology`, e il conto lo vede da li'.
    assert len(wrapped["hierarchy"]) >= 2, (
        "hierarchy: avvolto solo dove nasce -- chi l'importa per nome sfugge al conto")
    answers = await _chat_turn(started_app)
    failed = [answer for answer in answers if "errore" in answer]
    assert not failed, failed
    assert calls["hierarchy"] > 0 and calls["live_mirror"] > 0, calls


async def test_un_turno_costruisce_la_casa_una_volta(started_app, counted):
    calls, _wrapped = counted
    await _chat_turn(started_app)
    assert calls == Counter(hierarchy=1, live_mirror=1), calls


async def test_la_casa_del_turno_non_resta_nell_app(started_app):
    """R12: l'istantanea vale un turno. Tenuta in `app[...]`, il turno dopo
    guarderebbe la casa di prima -- la copia che invecchia in silenzio."""
    await _chat_turn(started_app)
    kept = [key for key, value in started_app.items() if isinstance(value, House)]
    assert kept == []


# -- quando la casa cambia sotto il turno ------------------------------------

class _Store:
    """L'anagrafe: `read()` restituisce un oggetto nuovo a ogni ricostruzione,
    come `HomeSpace` (e' cio' su cui il dispatcher confronta)."""

    def __init__(self) -> None:
        self.home_space = {"entita": [], "aree": [], "dispositivi": []}

    def read(self) -> dict:
        return self.home_space

    def unavailable(self) -> list[str]:
        return []


class _Cache:
    loaded = True

    def __init__(self, state: str) -> None:
        self.state = state

    def all_states(self) -> list[dict]:
        return [{"id": "light.cucina", "state": self.state}]


class _Actuator:
    def __init__(self, cache: _Cache) -> None:
        self._cache = cache

    async def execute(self, arguments, *, actor, subject):
        self._cache.state = "on"
        return {"ok": True}


async def test_un_turno_nuovo_vede_la_casa_di_adesso():
    """Lo specchio cambia fra due turni: il secondo lo vede, sia dalla casa
    che apre il turno (`house_of`, come `handle_chat`) sia dal dispatcher
    che se la legge da se'."""
    store, cache = _Store(), _Cache("off")
    app = {"home_space_store": store, "entity_cache": cache}
    assert house_of(app).mirror.state["light.cucina"] == "off"
    assert ToolDispatcher(store, None, cache=cache)._mirror().state["light.cucina"] == "off"
    cache.state = "on"
    assert house_of(app).mirror.state["light.cucina"] == "on"
    assert ToolDispatcher(store, None, cache=cache)._mirror().state["light.cucina"] == "on"


async def test_l_anagrafe_ricostruita_a_meta_turno_si_rilegge():
    store, cache = _Store(), _Cache("off")
    dispatcher = ToolDispatcher(store, None, cache=cache)
    first = dispatcher._turn_house()
    assert dispatcher._turn_house() is first
    store.home_space = {"entita": [], "aree": [], "dispositivi": []}
    assert dispatcher._turn_house().home_space is store.home_space


async def test_dopo_un_comando_lo_stesso_turno_rilegge_lo_specchio():
    """La domanda dopo un `execute`, nello stesso turno, deve vedere lo stato
    che il comando ha cambiato, non quello di prima."""
    store, cache = _Store(), _Cache("off")
    dispatcher = ToolDispatcher(store, None, cache=cache, actuator=_Actuator(cache))
    assert dispatcher._mirror().state["light.cucina"] == "off"
    await dispatcher._execute({"servizio": "light.turn_on"})
    assert dispatcher._mirror().state["light.cucina"] == "on"


# -- la casa si legge in un modo solo ------------------------------------------

PRODUCT = Path(__file__).resolve().parents[1] / "hiris" / "app"
HOUSE_MODULE = PRODUCT / "home_space" / "house.py"


def _house_constructions() -> dict[str, list[str]]:
    """Ogni `House(...)` e ogni `House.read(...)` del prodotto, per file. I
    file si chiedono alla cartella, non a un elenco."""
    import ast

    found: dict[str, list[str]] = {"costruita": [], "letta": []}
    for path in sorted(PRODUCT.rglob("*.py")):
        if path == HOUSE_MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            where = f"{path.relative_to(PRODUCT)}:{node.lineno}"
            if isinstance(node.func, ast.Name) and node.func.id == "House":
                found["costruita"].append(where)
            elif (isinstance(node.func, ast.Attribute) and node.func.attr == "read"
                  and isinstance(node.func.value, ast.Name) and node.func.value.id == "House"):
                found["letta"].append(where)
    return found


def test_la_casa_si_legge_solo_con_house_read():
    """La casa si compone in un posto: `House.read` mette insieme l'anagrafe,
    lo specchio (`topology.read_mirror`) e i registri caduti. Una porta che
    scrive `House(home_space, read_mirror(cache), unavailable)` a mano ripete
    quella composizione, e la prima volta che `House.read` impara un pezzo
    nuovo (l'elenco delle statistiche del giro, la fonte) quella porta guarda
    un'altra casa (fondamenta 2). Trovato dalla revisione della Tappa 3
    (Task 14, 04/10/2026): `handle_get_home_space` era l'ultima.

    Le prove possono costruirla a mano: la regola vale per il prodotto.

    Derivazione viva: la scansione trova le letture vere (`House.read` sta in
    `server.py` e nei gestori), quindi non e' un cancello che non guarda
    niente.

    Rossa sul codice di prima (`ee4c7ab`), letta il 04/10/2026:
    «['api/handlers_home_space.py:146']». Mutazione ESEGUITA dopo la
    correzione, senza toccare la prova: `House(casa.read(), read_mirror(...))`
    al posto di `House.read` in `handlers_mind._device_names` -- rossa,
    «['api/handlers_mind.py:423']». Ripristinata, `git status` pulito.
    """
    found = _house_constructions()
    assert len(found["letta"]) >= 3, found
    assert found["costruita"] == [], found["costruita"]
