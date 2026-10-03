"""La casa si costruisce UNA volta per turno (R18; Tappa 3, Task 2).

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
"""
import sys
from collections import Counter
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.handlers_home_space import compose_briefing
from hiris.app.home_space import topology
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
    conta niente."""
    compose_briefing(app)
    dispatcher = create_tool_dispatcher(app)
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
        assert len(wrapped[label]) >= 2, (
            f"{label}: avvolto solo dove nasce -- chi l'importa per nome sfugge al conto")
    answers = await _chat_turn(started_app)
    failed = [answer for answer in answers if "errore" in answer]
    assert not failed, failed
    assert calls["hierarchy"] > 0 and calls["live_mirror"] > 0, calls


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="R18: la casa si rifa' a ogni porta; "
                                       "la chiude l'istantanea House, Tappa 3 Task 4")
async def test_un_turno_costruisce_la_casa_una_volta(started_app, counted):
    calls, _wrapped = counted
    await _chat_turn(started_app)
    assert calls == Counter(hierarchy=1, live_mirror=1), calls
