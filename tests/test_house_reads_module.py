"""Le letture della casa escono dall'oggetto per turno (Tappa 3, Task 13; R13,
seconda meta').

`ToolDispatcher` nasce a ogni turno di chat e porta la persona: il soffitto,
il soggetto, la frase. Le letture della casa non dipendono da nessuna di
queste -- lo specchio, la scelta di «di chi», il fuso, la chiave di
un'esecuzione, lo storico -- e fino al 04/10/2026 vivevano come metodi privati
del dispatcher: un attore (l'osservatore, una ricetta, una promessa che si
sveglia) che voleva leggere la storia doveva costruirsi un turno di chat
finto, o rifarsela.

Qui un attore finto le chiama con `House` e `CasaFinta`, e basta: nessun
`ToolDispatcher`. E la risposta e' la STESSA del dispatcher sugli stessi
ingressi e allo stesso istante: lo spostamento e' una pura sostituzione.

Il permesso resta SOPRA, nel dispatcher: il cancello di `ADMIN_KINDS` per
`errori`/`esecuzioni` e il corpo coperto (`cover_automation_body`). Le prove
di quel permesso sono quelle di sempre (`tests/test_admission.py`,
`tests/test_history_tool.py`, `tests/test_knowledge_tools.py`), rilanciate con
le mutazioni dopo lo spostamento (rapporto del Task 13).

Mutazioni ESEGUITE il 04/10/2026, dopo lo spostamento, ripristini verificati:
- tolto il cancello `ADMIN_KINDS` da `ToolDispatcher._history` -- rosse le
  prove di chi non amministra (`test_admission.py`, `test_history_tool.py`);
- tolta la chiamata a `cover_automation_body` -- rosse
  `test_il_CORPO_di_un_automazione_e_degli_amministratori` e
  `test_chi_non_amministra_non_vede_il_corpo_di_un_automazione`;
- la lettura degli errori ricopiata dentro `_history` -- rossa qui la spia, e
  R1 in `test_fonte_unica.py` (`system_log` chiamata da `tools.py`);
- la casa del turno costruita anche per gli errori -- rossa
  `test_errors_do_not_read_the_house`.
"""
import copy
import time
from datetime import timedelta

import pytest

from hiris.app.home_space import historian, tools
from hiris.app.home_space import house_history as hh
from hiris.app.home_space.house import House
from hiris.app.home_space.redaction import home_assistant_seal
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.home_space.topology import Mirror
from tests.test_history_tool import (
    _ADESSO,
    _COMPORTAMENTO,
    _history_house,
    _history_mirror,
    _house,
    _traccia,
)
from tests.test_knowledge_tools import _semina_casa

#: Un istante fisso: la finestra di `parse_query` e quella del dispatcher
#: (che legge `time.time()`) devono essere la stessa per confrontare.
NOW = _ADESSO.timestamp()

#: Le domande, una per genere, con gli ingressi che le fanno rispondere.
_SERIE = {"light.cucina_1": [{"quando": (_ADESSO - timedelta(hours=2)).isoformat(),
                              "valore": "on"}]}
_FASCE = {"sensor.energia_oggi": [
    {"start": int((NOW - 7200) * 1000), "end": int((NOW - 3600) * 1000),
     "change": 1.5, "mean": None, "min": None, "max": None}]}
_TRACCE = {"automation.177130": [_traccia("r1")], "script.bn_1": [_traccia("r2", ore=3)]}
_REGISTRO = [{"name": "homeassistant.components.hydrawise", "level": "ERROR",
              "message": ["Errore di prova"], "exception": "Traceback\nValueError: x",
              "timestamp": NOW - 600, "count": 1, "first_occurred": NOW - 600,
              "source": ["hydrawise.py", 10]}]
_DOMANDE = {
    "stati": {"genere": "stati", "riferimento": "light.cucina_1"},
    "valori": {"genere": "valori", "riferimento": "sensor.energia_oggi"},
    "esecuzioni": {"genere": "esecuzioni", "nome": "rifiuto carta"},
    "esecuzioni-script": {"genere": "esecuzioni", "riferimento": "script.buonanotte"},
    "errori": {"genere": "errori"},
}


def _ha():
    return _house(serie=_SERIE, fasce=_FASCE, tracce=_TRACCE,
                  registro=copy.deepcopy(_REGISTRO))


async def _actor_reads(tmp_path, arguments: dict):
    """Un attore che non e' un turno di chat: archivio, specchio e canale, e
    le funzioni di modulo. Nessun `ToolDispatcher`."""
    store = _semina_casa(tmp_path / "attore", casa=_history_house(),
                         comportamento=_COMPORTAMENTO)
    cache, ha = _history_mirror(), _ha()
    # Il fuso, lo specchio e la selezione: gia' fuori dal dispatcher.
    timezone = historian.house_timezone(store)
    house = House.read(store, cache)
    assert timezone == "Europe/Rome" and isinstance(house.mirror, Mirror)
    query = hh.parse_query(arguments, now=NOW, timezone=timezone)
    answer = await hh.read_history(ha, query, house, store.behavior(), cache=cache,
                                   seal=home_assistant_seal(), journal=None, now=NOW)
    return answer, ha


async def _dispatcher_reads(tmp_path, arguments: dict, monkeypatch):
    store = _semina_casa(tmp_path / "turno", casa=_history_house(),
                         comportamento=_COMPORTAMENTO)
    ha = _ha()
    monkeypatch.setattr(time, "time", lambda: NOW)
    try:
        answer = await ToolDispatcher(store, None, cache=_history_mirror(),
                                      ha=ha).dispatch("history", arguments)
    finally:
        monkeypatch.undo()
    return answer, ha


@pytest.mark.asyncio
@pytest.mark.parametrize("label", sorted(_DOMANDE))
async def test_an_actor_reads_the_history_without_a_dispatcher(tmp_path, monkeypatch,
                                                                label):
    """La stessa risposta, e le stesse domande a Home Assistant, del
    dispatcher: per ogni genere. Un turno senza persona (soffitto `None`)
    legge come l'amministratore, quindi il cancello non c'entra qui.

    Rossa prima del 04/10/2026: `house_history.read_history` non esisteva --
    la storia era `ToolDispatcher._history` e i suoi metodi privati."""
    arguments = _DOMANDE[label]
    by_actor, actor_ha = await _actor_reads(tmp_path, arguments)
    by_turn, turn_ha = await _dispatcher_reads(tmp_path, arguments, monkeypatch)
    assert "errore" not in by_actor, by_actor
    assert by_actor["trovate"] >= 1, by_actor
    assert by_actor == by_turn
    assert actor_ha.calls == turn_ha.calls


def test_the_run_key_is_a_module_function():
    """La chiave con cui Home Assistant conserva le esecuzioni, senza un
    dispatcher: l'id di configurazione dallo specchio per un'automazione,
    l'`unique_id` del registro per uno script rinominato, l'`object_id` per
    uno script che il registro non conosce."""
    cache = _history_mirror()
    registry = {"script.buonanotte": {"id": "script.buonanotte", "unique_id": "bn_1"}}
    assert hh.run_key(cache, "automation.rifiuto_carta", registry) == ("automation", "177130")
    assert hh.run_key(cache, "script.buonanotte", registry) == ("script", "bn_1")
    assert hh.run_key(cache, "script.risveglio", registry) == ("script", "risveglio")
    assert hh.run_key(cache, "automation.non_esiste", registry) is None


@pytest.mark.asyncio
async def test_the_dispatcher_composes_the_module_read_and_keeps_no_copy(tmp_path,
                                                                         monkeypatch):
    """L'accordo fra attore e dispatcher non vede una COPIA: resterebbe verde
    con la lettura ricopiata dentro `_history`. Qui si prova la chiamata, per
    i generi che leggono la casa e per gli errori."""
    calls = []
    real_history, real_errors = hh.read_history, hh.read_errors

    async def history_spy(*args, **kwargs):
        calls.append("read_history")
        return await real_history(*args, **kwargs)

    async def errors_spy(*args, **kwargs):
        calls.append("read_errors")
        return await real_errors(*args, **kwargs)

    monkeypatch.setattr(tools, "read_history", history_spy)
    monkeypatch.setattr(tools, "read_errors", errors_spy)
    store = _semina_casa(tmp_path, casa=_history_house(), comportamento=_COMPORTAMENTO)
    dispatcher = ToolDispatcher(store, None, cache=_history_mirror(), ha=_ha())
    for arguments in (_DOMANDE["stati"], _DOMANDE["errori"]):
        await dispatcher.dispatch("history", arguments)
    assert calls == ["read_history", "read_errors"]


@pytest.mark.asyncio
async def test_errors_do_not_read_the_house(tmp_path):
    """Gli errori non guardano la casa: `read_errors` non chiede ne' anagrafe
    ne' specchio, e il dispatcher non costruisce la casa del turno per loro
    (come prima dello spostamento: gli errori si chiedono anche con la casa
    non ancora caricata)."""
    store = _semina_casa(tmp_path, casa=_history_house(), comportamento=_COMPORTAMENTO)
    cache = _history_mirror()
    dispatcher = ToolDispatcher(store, None, cache=cache, ha=_ha())
    answer = await dispatcher.dispatch("history", _DOMANDE["errori"])
    assert answer["trovate"] == 1
    assert cache.letture == 0 and dispatcher._house is None
