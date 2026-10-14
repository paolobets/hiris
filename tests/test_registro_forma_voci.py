"""Un registro degli errori in forma inattesa e' un guasto, non un registro
vuoto, fino in fondo ai due lettori (N161-2, revisore giro 161).

Home Assistant manda `system_log/list` come una LISTA nuda
(`HAClient.system_log`). Se mandasse altro, il client rende la busta di
`forma`, e la lettura della storia (`house_history.read_log`, la casa sola
della lettura dal 14/10/2026, A-41) la gira com'e'. Qui si prova cosa ne fanno
i due lettori, col client vero sopra la casa finta: il giro delle condizioni
si salta (un registro letto come vuoto, due giri di fila, chiuderebbe ogni
voce aperta), e gli errori della storia rendono la busta.

Mutazione ESEGUITA (14/10/2026): tolto da `HAClient.system_log` il controllo
`isinstance(result, list)` -- rosse tutte e sei: il giro chiama l'osservatore
con le voci sbagliate e `read_errors` solleva invece di rendere la busta.
Ripristino verificato con `git status`.
"""
import asyncio
import logging
import sys
from pathlib import Path

import pytest

from hiris.app.home_space.house_history import read_errors
from hiris.app.home_space.rounds import HA_PROBLEMS_KEY
from hiris.app.mind.conditions_round import watch_system_conditions
from hiris.app.mind.watcher import WATCHER_KEY
from hiris.app.proxy.ha_client import SHAPE
from tests._casa_sintetica import synthetic_inputs
from tests.test_mind_wiring import _announced, _OsservatoreFinto

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app.live_value import LiveValue
from hiris.app.startup import live_values

#: Cio' che Home Assistant potrebbe mandare al posto della lista: un
#: dizionario, niente, una stringa.
ANSWERS = {"dizionario": {}, "niente": None, "stringa": "x"}


def _house(name: str) -> CasaFinta:
    return CasaFinta(synthetic_inputs(),
                     answers={"system_log/list": lambda extra: ANSWERS[name]})


@pytest.mark.parametrize("name", sorted(ANSWERS))
def test_il_giro_delle_condizioni_si_salta(name, caplog):
    osservatore = _OsservatoreFinto()
    app = _announced({**live_values(),
                      WATCHER_KEY: osservatore, HA_PROBLEMS_KEY: LiveValue({"problemi": []})}, [])
    with caplog.at_level(logging.WARNING):
        esito = asyncio.run(watch_system_conditions(app, _house(name)))
    assert esito is None
    assert osservatore.chiamate == []
    assert "giro saltato" in caplog.text


@pytest.mark.parametrize("name", sorted(ANSWERS))
def test_gli_errori_della_storia_rendono_la_busta_forma(name):
    answer = asyncio.run(read_errors(_house(name), None, seal=None, manifest=None))
    assert answer["causa"] == SHAPE, answer
