"""Il dato fermo entra nel resoconto (piano degli attori, strato 1, Task 1.3;
D3 «la sua storia» e D4 «rifiutata» del proprietario, 03/10/2026).

Il caso: il 30/09/2026 l'inverter ha smesso di aggiornare i contatori, e il
resoconto ha scritto **produzione 0 con copertura 1.0** (BACKLOG, «Un
contatore CONGELATO non si distingue da un giorno a zero»). La copertura conta
le ore che hanno un valore, non se quel valore dice qualcosa.

Qui la strada e' quella vera: `server._report_ingredients` sul client vero di
Home Assistant (`scripts/casa_finta.py`), che chiede le statistiche orarie in
UNA richiesta -- il giorno e la sua storia -- e poi `report.build_report`,
cioe' cio' che fanno l'aggregazione notturna, il recupero dei resoconti e la
riparazione d'avvio. **Le serie sono sintetiche**, senza nomi della casa: un
contatore di produzione che di giorno cresce e di notte no, e il 30/09 non
cresce mai.

Mutazioni ESEGUITE (06/10/2026), ognuna ripristinata e verificata con
`git status`, tutte rosse per la ragione giusta:
- `_report_ingredients` che non passa i rifiuti «ferma» al resoconto (torna
  `silent` senza `ferme`) -- rosse le due prove del 30/09: la misura esce
  `valore 0.0`, `copertura 1.0`, cioe' lo zero falso;
- la lettura senza la storia (`storia_da_ts = da_ts`) -- rossa la prova del
  30/09: senza storia la regola dice «non lo so», e non rifiuta;
- il guasto dell'elenco delle statistiche che torna `None` invece dei
  rifiuti «ferma» -- rossa la prova del guasto.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from hiris.app import server
from hiris.app.home_space.historian import day_boundaries
from hiris.app.mind.flatline import HISTORY_DAYS
from hiris.app.mind.operations import FROZEN
from hiris.app.mind.report import build_report
from tests._casa_sintetica import synthetic_inputs
from tests.test_attori_davanti_alla_fonte import _mirror_cache, _registries
from tests.test_fonte_della_casa import _Store

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

TIMEZONE = "Europe/Rome"
FROZEN_DAY = "2026-09-30"
#: Un'entita' della casa sintetica: qui conta solo la sua serie.
COUNTER = "light.viva"
DEVICE = "d_inverter"
RECIPE = {"why": "la produzione del giorno", "steps": [
    {"name": "produzione", "operation": "somma_periodo", "inputs": [f"@{COUNTER}"],
     "params": {"unit": "kWh"}}]}
SUN_HOURS_UTC = range(5, 17)


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _rows(from_iso, to_iso, *, frozen_from: float | None):
    """Le righe orarie di Home Assistant (`recorder/statistics_during_period`,
    un contatore: `change`) fra due istanti. Da `frozen_from` in poi il
    contatore non cresce piu'."""
    moment = datetime.fromisoformat(from_iso)
    end = datetime.fromisoformat(to_iso)
    rows = []
    while moment < end:
        frozen = frozen_from is not None and moment.timestamp() >= frozen_from
        change = 0.0 if frozen or moment.hour not in SUN_HOURS_UTC else 0.4
        rows.append({"start": _ms(moment), "end": _ms(moment + timedelta(hours=1)),
                     "sum": None, "state": None, "change": change})
        moment += timedelta(hours=1)
    return rows


async def _report(day, *, frozen_from, statistic_ids=None):
    app = {"knowledge": object(),
           "home_space_store": _Store(_registries([{"id": DEVICE, "name": "Inverter"}])),
           "entity_cache": _mirror_cache()}
    asked: list[dict] = []

    def _statistics(extra):
        asked.append(extra)
        return {COUNTER: _rows(extra["start_time"], extra["end_time"],
                               frozen_from=frozen_from)}

    async def _stat_ids(_app, _ha, **_kw):
        return {COUNTER} if statistic_ids is None else statistic_ids

    house = CasaFinta(synthetic_inputs(), answers={
        "recorder/statistics_during_period": _statistics})
    with mock.patch.object(server.recipe_turn, "recipes", lambda _k: {DEVICE: RECIPE}), \
            mock.patch.object(server, "statistic_ids_for_round", _stat_ids):
        ricette, serie, nomi, silent, mute = await server._report_ingredients(
            app, house, giorno=day, timezone=TIMEZONE)
    report = build_report(day=day, episodes=[], series=serie, recipes=ricette,
                          names=nomi, silent=silent, muted=mute)
    [row] = [r for r in report["misure"] if r["misura"] == "produzione"]
    return row, asked


def _start(day) -> float:
    return day_boundaries(day, TIMEZONE)[0]


@pytest.mark.asyncio
async def test_il_30_09_la_produzione_ferma_non_e_uno_zero_con_copertura_piena():
    row, _asked = await _report(FROZEN_DAY, frozen_from=_start(FROZEN_DAY))
    assert "valore" not in row and "copertura" not in row, row
    assert row["causa"] == FROZEN
    assert row["non_calcolabile"].startswith(f"{COUNTER} e' ferma: non varia dalle ")
    assert f"in ciascuno dei {HISTORY_DAYS} giorni di storia" in row["non_calcolabile"]


@pytest.mark.asyncio
async def test_un_giorno_che_si_muove_resta_una_misura():
    """Il controllo: la stessa casa, un giorno prima del blocco, da' il suo
    numero con la copertura piena. Una regola che rifiutasse tutto sarebbe
    verde sulla prova qui sopra."""
    row, _asked = await _report("2026-09-29", frozen_from=_start(FROZEN_DAY))
    assert row["valore"] == round(0.4 * len(SUN_HOURS_UTC), 2)
    assert row["copertura"] == 1.0
    assert "causa" not in row


@pytest.mark.asyncio
async def test_giorno_e_storia_si_chiedono_in_una_richiesta_sola():
    """Il costo dichiarato (R16): una richiesta per giro di resoconto, con la
    finestra allungata di `HISTORY_DAYS` giorni -- non una seconda lettura."""
    _row, asked = await _report(FROZEN_DAY, frozen_from=_start(FROZEN_DAY))
    assert len(asked) == 1
    start, end = day_boundaries(FROZEN_DAY, TIMEZONE)
    assert datetime.fromisoformat(asked[0]["start_time"]) == datetime.fromtimestamp(
        start - HISTORY_DAYS * 86400, tz=UTC)
    assert datetime.fromisoformat(asked[0]["end_time"]) == datetime.fromtimestamp(end, tz=UTC)


@pytest.mark.asyncio
async def test_con_l_elenco_delle_statistiche_guasto_la_fonte_ferma_resta_ferma():
    """Se `recorder/list_statistic_ids` non si legge, di quali entita' non
    abbiano statistiche non si afferma niente. Ma la serie si e' letta, e il
    blocco si e' visto su di lei: quello resta."""
    row, _asked = await _report(FROZEN_DAY, frozen_from=_start(FROZEN_DAY),
                                statistic_ids={"errore": "giu'", "causa": "rete"})
    assert row["causa"] == FROZEN
