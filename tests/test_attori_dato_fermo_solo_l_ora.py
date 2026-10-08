"""Il dato fermo toglie l'ora ferma, non il giorno (decisione di Paolo,
08/10/2026: «ok per le consigliate per le date ferme»).

Il caso: il 06/10/2026 una stazione di cinque entita' di un dispositivo e'
rimasta ferma dalle 01:00 alle 02:00 ora della casa. La regola l'ha giudicata
ferma -- giustamente -- e il resoconto ha rifiutato PER INTERO media, minimo e
massimo di temperatura e umidita' della stanza: un'ora ferma costava le altre
ventitre'. Ora, per una misura istantanea, dalla serie del giorno escono solo
le ore del tratto fermo; la misura si fa sul resto, la copertura scende col
conto che c'era gia', e il risultato porta dentro di se' quali ore sono
uscite e perche' (`Measurement.excluded`, `Exclusion.out`).

La strada e' quella vera, come in `test_attori_dato_fermo_nel_resoconto.py`:
`server._report_ingredients` sul client finto di Home Assistant
(`scripts/casa_finta.py`), poi `report.build_report`. **Le serie sono
sintetiche**, senza nomi della casa.

Rosso visto (08/10/2026), sul codice di prima: lo scenario del 06/10 usciva
`non_calcolabile` con `causa: ferma`, nessun `valore`.

Mutazione ESEGUITA (08/10/2026), ripristinata (`git status`): `frozen_day`
che rimette il rifiuto del giorno intero per le misure istantanee (il ramo
tolto) -- rossa la prova del 06/10, con `KeyError: 'valore'` sulla riga che
esce rifiutata `ferma`. Le altre, eseguite lo stesso giorno e ripristinate:
- `Recipe._run_step` senza la conversione in `ferma` -- rosse il giorno
  intero (`ricetta_storta`) e la copertura minima (`copertura_bassa`);
- `report._measurements` che non scrive `esclusi` -- rosse il 06/10 e
  l'analista; `analyst.index_row` senza `esclusi_oggi` -- rossa l'analista;
- in `tests/test_mind_flatline.py`: l'eredita' fra passi tolta (rossa la
  quota), i contatori trattati come misure istantanee (rossi il contatore che
  recupera e quello fermo fino a sera);
- in `tests/js/watcher-giorno.test.mjs`: la piastrella senza il ciclo su
  `esclusi` (rossa la prova delle ore lasciate fuori).
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from hiris.app import server
from hiris.app.home_space.historian import day_boundaries
from hiris.app.home_space.reader import build_home_space
from hiris.app.mind.analyst import index
from hiris.app.mind.operations import COVERAGE_LOW, FROZEN, MINIMUM_COVERAGE
from hiris.app.mind.report import build_report, series_of_measures
from hiris.app.proxy.entity_cache import _to_minimal
from tests._casa_sintetica import synthetic_inputs
from tests.test_attori_davanti_alla_fonte import _Cache
from tests.test_fonte_della_casa import _Store

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

TIMEZONE = "Europe/Rome"
DAY = "2026-10-06"
TEMPERATURE = "sensor.stazione_temperatura"
HUMIDITY = "sensor.stazione_umidita"
HOUSE_METER = "sensor.casa_energia"
STATION = "d_stazione"
STATION_RECIPE = {"why": "il clima della stanza", "steps": [
    {"name": "temperatura", "operation": "media_min_max",
     "inputs": [f"@{TEMPERATURE}"], "params": {"unit": "°C", "expected_parts": 24}},
    {"name": "umidita", "operation": "media_min_max",
     "inputs": [f"@{HUMIDITY}"], "params": {"unit": "%", "expected_parts": 24}}]}
HOUSE_RECIPE = {"why": "il consumo della casa", "steps": [
    {"name": "consumo", "operation": "somma_periodo", "inputs": [f"@{HOUSE_METER}"],
     "params": {"unit": "kWh"}}]}
STATISTIC_IDS = {TEMPERATURE, HUMIDITY, HOUSE_METER}


def _entity(entity_id, device_id):
    return {"entity_id": entity_id, "platform": "meteo", "config_entry_id": "e_" + device_id,
            "device_id": device_id, "disabled_by": None, "hidden_by": None}


def _app():
    home_space = build_home_space({
        "entita": [_entity(TEMPERATURE, STATION), _entity(HUMIDITY, STATION),
                   _entity(HOUSE_METER, "d_contatore")],
        "integrazioni": [],
        "dispositivi": [{"id": STATION, "name": "Stazione", "disabled_by": None},
                        {"id": "d_contatore", "name": "Contatore", "disabled_by": None}]})
    return {"knowledge": object(), "home_space_store": _Store(home_space),
            "entity_cache": _Cache([_to_minimal(
                {"entity_id": e, "state": "1", "attributes": {"state_class": "measurement"}})
                for e in STATISTIC_IDS])}


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _temperature(moment: datetime) -> tuple[float, float]:
    low = 19 + moment.hour / 10
    return low, low + 0.2


def _humidity(moment: datetime) -> tuple[float, float]:
    return 50 + moment.hour, 51 + moment.hour


#: I valori a cui la stazione resta ferma: diversi da zero (lo zero e' anche il
#: riposo di un apparecchio spento, e la regola non lo giudica).
HELD = {TEMPERATURE: 21.3, HUMIDITY: 55.0}


def _rows(entity_id, from_iso, to_iso, frozen):
    """Le righe orarie di Home Assistant fra due istanti; nelle ore per cui
    `frozen(istante)` e' vero la stazione non manda niente di nuovo."""
    moment, end = datetime.fromisoformat(from_iso), datetime.fromisoformat(to_iso)
    rows = []
    while moment < end:
        row = {"start": _ms(moment), "end": _ms(moment + timedelta(hours=1)),
               "sum": None, "state": None, "change": None,
               "mean": None, "min": None, "max": None}
        if entity_id == HOUSE_METER:
            row["change"] = 0.1 + moment.hour / 1000
        elif frozen(moment.timestamp()):
            held = HELD[entity_id]
            row.update(min=held, max=held, mean=held)
        else:
            low, high = (_temperature if entity_id == TEMPERATURE else _humidity)(moment)
            row.update(min=low, max=high, mean=(low + high) / 2)
        rows.append(row)
        moment += timedelta(hours=1)
    return rows


async def _report(day, *, frozen):
    def _statistics(extra):
        return {e: _rows(e, extra["start_time"], extra["end_time"], frozen)
                for e in extra["statistic_ids"]}

    async def _stat_ids(_app, _ha, **_kw):
        return set(STATISTIC_IDS)

    house = CasaFinta(synthetic_inputs(), answers={
        "recorder/statistics_during_period": _statistics})
    recipes = {STATION: STATION_RECIPE, "d_contatore": HOUSE_RECIPE}
    with mock.patch.object(server.recipe_turn, "recipes", lambda _k: recipes), \
            mock.patch.object(server, "statistic_ids_for_round", _stat_ids):
        ricette, serie, nomi, silent, mute = await server._report_ingredients(
            _app(), house, giorno=day, timezone=TIMEZONE)
    report = build_report(day=day, episodes=[], series=serie, recipes=ricette,
                          names=nomi, silent=silent, muted=mute)
    return {r["misura"]: r for r in report["misure"]}, report


def _expected(day, entity_id, *, skip=()):
    """Media, minimo e massimo del giorno, senza le ore in `skip` (epoch).
    Le righe finte nascono in UTC, come le chiede `_report_ingredients`."""
    shape = _temperature if entity_id == TEMPERATURE else _humidity
    start, end = day_boundaries(day, TIMEZONE)
    parts = [shape(datetime.fromtimestamp(ts, tz=UTC))
             for ts in range(int(start), int(end), 3600) if ts not in skip]
    means = [(low + high) / 2 for low, high in parts]
    return {"media": round(sum(means) / len(means), 2),
            "minimo": min(low for low, _ in parts),
            "massimo": max(high for _, high in parts)}


def _one_in_the_morning(day) -> float:
    return day_boundaries(day, TIMEZONE)[0] + 3600


def _the_06_10(ts: float) -> bool:
    """Ferma dall'01:00 alle 02:00 del 06/10, ora della casa: un'ora sola."""
    one = _one_in_the_morning(DAY)
    return one <= ts < one + 3600


# -- il caso del 06/10 --------------------------------------------------------


@pytest.mark.asyncio
async def test_il_06_10_un_ora_ferma_toglie_l_ora_e_non_il_giorno():
    rows, _ = await _report(DAY, frozen=_the_06_10)
    one = _one_in_the_morning(DAY)
    for step, entity_id in (("temperatura", TEMPERATURE), ("umidita", HUMIDITY)):
        row = rows[step]
        assert row["valore"] == _expected(DAY, entity_id, skip={one}), row
        assert row["copertura"] == 23 / 24
        assert "causa" not in row and "non_calcolabile" not in row
        [declared] = row["esclusi"]
        # Nell'ora della casa: a Roma il 06/10 e' UTC+2.
        assert declared["dal"] == "2026-10-06T01:00:00+02:00"
        assert declared["al"] == "2026-10-06T02:00:00+02:00"
        assert declared["causa"] == FROZEN
        # La frase e' quella del gruppo, la stessa del rifiuto di prima.
        assert declared["perche"].startswith(
            f"{entity_id} e' ferma: dalle 2026-10-06T01:00:00+02:00 alle "
            "2026-10-06T02:00:00+02:00 non varia nessuna delle 2 entita' del suo "
            f"gruppo ({TEMPERATURE}, {HUMIDITY})")
        # E la frase per la pagina, senza id: chi la legge e' il proprietario.
        assert declared["in_breve"] == (
            "Dalle 01:00 alle 02:00 tutti i sensori di questo dispositivo sono "
            "rimasti uguali mentre il resto della casa si muoveva: quelle ore non "
            "entrano nel calcolo.")
        assert declared["parola"] == "dispositivo fermo"
        assert declared["ore"] == ["01:00", "02:00"]
    # Il resto della casa non c'entra.
    assert "esclusi" not in rows["consumo"]


@pytest.mark.asyncio
async def test_la_dichiarazione_arriva_all_analista_con_la_misura():
    """La stessa forma da ogni porta: la serie che l'analista legge porta le
    ore escluse del giorno accanto ai suoi valori."""
    rows_, report = await _report(DAY, frozen=_the_06_10)
    series = series_of_measures([report])
    [media] = [s for s in series["serie"]
               if s["misura"] == "temperatura" and s["chiave"] == "media"]
    assert media["valori"] == [_expected(DAY, TEMPERATURE,
                                         skip={_one_in_the_morning(DAY)})["media"]]
    [declared] = media["esclusi"][DAY]
    assert declared == rows_["temperatura"]["esclusi"][0]
    # E l'indice che il modello legge per primo lo dice sull'ultimo giorno.
    [line] = [r for _n, r in index(series)
              if r["misura"] == "temperatura" and r["chiave"] == "media"]
    assert line["esclusi_oggi"] == [declared]


@pytest.mark.asyncio
async def test_un_giorno_senza_tratti_fermi_resta_identico():
    rows, _ = await _report("2026-10-05", frozen=_the_06_10)
    for step, entity_id in (("temperatura", TEMPERATURE), ("umidita", HUMIDITY)):
        assert rows[step]["valore"] == _expected("2026-10-05", entity_id)
        assert rows[step]["copertura"] == 1.0
        assert "esclusi" not in rows[step]


@pytest.mark.asyncio
async def test_un_giorno_intero_fermo_resta_rifiutato_ferma():
    start = day_boundaries(DAY, TIMEZONE)[0]
    rows, _ = await _report(DAY, frozen=lambda ts: ts >= start)
    for step in ("temperatura", "umidita"):
        assert "valore" not in rows[step], rows[step]
        assert rows[step]["causa"] == FROZEN
        assert rows[step]["non_calcolabile"].startswith(
            f"{TEMPERATURE if step == 'temperatura' else HUMIDITY} e' ferma: dalle "
            "2026-10-06T00:00:00+02:00 ")


@pytest.mark.asyncio
async def test_sotto_la_copertura_minima_il_rifiuto_dice_ferma_non_copertura():
    """Il default scelto: tolte le ore ferme, se la copertura scende sotto
    `MINIMUM_COVERAGE` il perche' e' il dato fermo, non una copertura bassa
    venuta da sola."""
    start = day_boundaries(DAY, TIMEZONE)[0]
    hours = int(24 * (1 - MINIMUM_COVERAGE)) + 1
    rows, _ = await _report(
        DAY, frozen=lambda ts: start + 3600 <= ts < start + 3600 * (1 + hours))
    row = rows["temperatura"]
    assert row["causa"] == FROZEN and row["causa"] != COVERAGE_LOW
    assert "senza quelle ore" in row["non_calcolabile"]
