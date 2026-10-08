"""Il dato fermo entra nel resoconto (piano degli attori, strato 1, Task 1.3;
D4 «rifiutata»; la regola delle sorelle, proposta del 06/10/2026).

Il caso: il 30/09/2026 l'inverter ha smesso di mandare dati, e il resoconto ha
scritto **produzione 0 con copertura 1.0** (BACKLOG, «Un contatore CONGELATO
non si distingue da un giorno a zero»).

Qui la strada e' quella vera: `server._report_ingredients` sul client vero di
Home Assistant (`scripts/casa_finta.py`) con un'anagrafe vera
(`build_home_space`), poi `report.build_report` -- cio' che fanno
l'aggregazione notturna, il recupero dei resoconti e la riparazione d'avvio.
L'inverter ha due entita' con statistiche sullo stesso dispositivo: la
produzione, che la ricetta nomina, e lo stato di carica, che la ricetta NON
nomina e che deve arrivare lo stesso, come sorella, nella stessa richiesta.
Un contatore della casa, su un altro dispositivo e con la sua ricetta, si
muove sempre: e' «il resto della casa», che la regola vede fra le serie lette. **Le serie
sono sintetiche**, senza nomi della casa.

Mutazioni ESEGUITE (06/10/2026), ognuna ripristinata (`git status`), tutte
rosse per la ragione giusta:
- `_report_ingredients` che non passa i rifiuti «ferma» al resoconto -- rossa
  la prova del 30/09: la misura esce `valore 0.0`, `copertura 1.0`;
- le sorelle non chieste (si leggono solo le entita' delle ricette) -- rosse
  la prova del 30/09 (un gruppo di una sola serie non si giudica) e quella
  della richiesta unica;
- la lettura senza la storia -- rossa la prova del 30/09;
- `House.sibling_group` che chiede l'elenco del giro invece di
  `has_statistics` (la forma prima del giro 7) -- rosse la prova dell'elenco
  guasto e quella dello `state_class` (G7-1);
- con l'elenco guasto, la casa del ripiego sullo `state_class` invece
  dell'elenco detto dalla risposta delle serie -- rossa la prova dei
  termometri (`KeyError`: nessun rifiuto); `House.possible_siblings` senza
  l'istanza -- rossa la stessa prova (G7-1, rimisura).
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
from hiris.app.mind.flatline import HISTORY_DAYS
from hiris.app.mind.operations import FROZEN
from hiris.app.mind.report import build_report
from hiris.app.proxy.entity_cache import _to_minimal
from tests._casa_sintetica import synthetic_inputs
from tests.test_attori_davanti_alla_fonte import _Cache
from tests.test_fonte_della_casa import _Store

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

TIMEZONE = "Europe/Rome"
FROZEN_DAY = "2026-09-30"
PRODUCTION = "sensor.inverter_prodotta"
CHARGE = "sensor.inverter_carica"
HOUSE_METER = "sensor.casa_energia"
DEVICE = "d_inverter"
RECIPE = {"why": "la produzione del giorno", "steps": [
    {"name": "produzione", "operation": "somma_periodo", "inputs": [f"@{PRODUCTION}"],
     "params": {"unit": "kWh"}}]}
SUN_HOURS_UTC = range(5, 17)
HOUSE_RECIPE = {"why": "il consumo della casa", "steps": [
    {"name": "consumo", "operation": "somma_periodo", "inputs": [f"@{HOUSE_METER}"],
     "params": {"unit": "kWh"}}]}
STATISTIC_IDS = {PRODUCTION, CHARGE, HOUSE_METER}


def _entity(entity_id, device_id):
    return {"entity_id": entity_id, "platform": "zcs", "config_entry_id": "e_" + device_id,
            "device_id": device_id, "disabled_by": None, "hidden_by": None}


def _app():
    home_space = build_home_space({
        "entita": [_entity(PRODUCTION, DEVICE), _entity(CHARGE, DEVICE),
                   _entity(HOUSE_METER, "d_contatore")],
        "integrazioni": [],
        "dispositivi": [{"id": DEVICE, "name": "Inverter", "disabled_by": None},
                        {"id": "d_contatore", "name": "Contatore", "disabled_by": None}]})
    return {"knowledge": object(), "home_space_store": _Store(home_space),
            # Le tre fonti sono vive: senza stato sarebbero «sparite», e le
            # loro ricette mute (`recipes.muted_recipes`).
            "entity_cache": _Cache([_to_minimal(
                {"entity_id": e, "state": "1", "attributes": {"state_class": "measurement"}})
                for e in STATISTIC_IDS])}


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _rows(entity_id, from_iso, to_iso, frozen_from):
    """Le righe orarie di Home Assistant (`recorder/statistics_during_period`)
    fra due istanti. Da `frozen_from` in poi l'inverter non manda piu' niente:
    la produzione non cresce, lo stato di carica resta al 74%."""
    moment, end = datetime.fromisoformat(from_iso), datetime.fromisoformat(to_iso)
    rows = []
    while moment < end:
        frozen = moment.timestamp() >= frozen_from
        row = {"start": _ms(moment), "end": _ms(moment + timedelta(hours=1)),
               "sum": None, "state": None, "change": None,
               "mean": None, "min": None, "max": None}
        if entity_id == PRODUCTION:
            row["change"] = 0.0 if frozen or moment.hour not in SUN_HOURS_UTC else 0.4
        elif entity_id == CHARGE:
            low, high = (74, 74) if frozen else (40 + moment.hour, 41 + moment.hour)
            row.update(min=low, max=high, mean=(low + high) / 2)
        else:
            row["change"] = 0.1 + moment.hour / 1000
        rows.append(row)
        moment += timedelta(hours=1)
    return rows


async def _report(day, *, frozen_from, statistic_ids=STATISTIC_IDS):
    asked: list[dict] = []

    def _statistics(extra):
        asked.append(extra)
        return {e: _rows(e, extra["start_time"], extra["end_time"], frozen_from)
                for e in extra["statistic_ids"]}

    async def _stat_ids(_app, _ha, **_kw):
        return statistic_ids if isinstance(statistic_ids, dict) else set(statistic_ids)

    house = CasaFinta(synthetic_inputs(), answers={
        "recorder/statistics_during_period": _statistics})
    recipes = {DEVICE: RECIPE, "d_contatore": HOUSE_RECIPE}
    with mock.patch.object(server.recipe_turn, "recipes", lambda _k: recipes), \
            mock.patch.object(server, "statistic_ids_for_round", _stat_ids):
        ricette, serie, nomi, silent, mute = await server._report_ingredients(
            _app(), house, giorno=day, timezone=TIMEZONE)
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
    # Nell'ora della casa (G4-4): il giorno di Roma comincia alle 22:00Z.
    assert row["non_calcolabile"].startswith(
        f"{PRODUCTION} e' ferma: dalle 2026-09-30T00:00:00+02:00 ")
    assert CHARGE in row["non_calcolabile"]


@pytest.mark.asyncio
async def test_un_giorno_che_si_muove_resta_una_misura():
    """Il controllo: la stessa casa, un giorno prima del blocco, da' il suo
    numero con la copertura piena."""
    row, _asked = await _report("2026-09-29", frozen_from=_start(FROZEN_DAY))
    assert row["valore"] == round(0.4 * len(SUN_HOURS_UTC), 2)
    assert row["copertura"] == 1.0
    assert "causa" not in row


@pytest.mark.asyncio
async def test_giorno_storia_e_sorelle_in_una_richiesta_sola():
    """Il costo dichiarato (R16): una richiesta per giro, con la finestra
    allungata di `HISTORY_DAYS` giorni e la sorella che nessuna ricetta nomina
    dentro -- non una lettura in piu'."""
    _row, asked = await _report(FROZEN_DAY, frozen_from=_start(FROZEN_DAY))
    assert len(asked) == 1
    assert sorted(asked[0]["statistic_ids"]) == [HOUSE_METER, CHARGE, PRODUCTION]
    start, end = day_boundaries(FROZEN_DAY, TIMEZONE)
    assert datetime.fromisoformat(asked[0]["start_time"]) == datetime.fromtimestamp(
        start - HISTORY_DAYS * 86400, tz=UTC)
    assert datetime.fromisoformat(asked[0]["end_time"]) == datetime.fromtimestamp(end, tz=UTC)


@pytest.mark.asyncio
async def test_con_l_elenco_delle_statistiche_guasto_la_fonte_ferma_resta_ferma():
    """G7-1 (revisione del giro 7): se `recorder/list_statistic_ids` non si
    legge, le sorelle le dice la risposta delle serie di Home Assistant (chi
    ha righe nella finestra), e il blocco del 30/09 si vede lo stesso. Con le
    sorelle chieste solo all'elenco, il 30/09 tornava zero con copertura
    1.0."""
    row, asked = await _report(FROZEN_DAY, frozen_from=_start(FROZEN_DAY),
                               statistic_ids={"errore": "giu'", "causa": "rete"})
    assert row["causa"] == FROZEN
    assert sorted(asked[0]["statistic_ids"]) == [HOUSE_METER, CHARGE, PRODUCTION]


# -- le sorelle, chieste alla casa (`House.sibling_group`) --------------------


def _house(entities, statistic_ids, state_classes=None):
    from hiris.app.home_space.house import House
    home_space = build_home_space({"entita": entities, "integrazioni": [],
                                   "dispositivi": []})
    mirror = _Cache([_to_minimal({"entity_id": e, "state": "1",
                                  "attributes": {"state_class": c}})
                     for e, c in (state_classes or {}).items()])
    return House.read(_Store(home_space), mirror, statistic_ids=statistic_ids)


def test_le_sorelle_sono_il_dispositivo_quando_ha_due_entita_con_statistiche():
    house = _house([_entity("sensor.a", "d1"), _entity("sensor.b", "d1"),
                    _entity("sensor.c", "d2")], {"sensor.a", "sensor.b", "sensor.c"})
    assert house.sibling_group("sensor.a") == ("dispositivo", "d1")
    assert house.siblings("sensor.a") == ["sensor.a", "sensor.b"]


def test_un_entita_sola_sul_dispositivo_ha_per_sorelle_la_sua_istanza():
    """Gli 8 termometri del 29/09: otto dispositivi con un'entita' ciascuno,
    sulla stessa istanza dell'integrazione (misurato dallo sprint, 06/10/2026).
    Non la piattaforma: un'altra istanza della stessa integrazione non c'entra."""
    rows = [{**_entity(f"sensor.t{i}", f"d{i}"), "config_entry_id": "e_hub"}
            for i in range(3)]
    rows.append({**_entity("sensor.altro_hub", "d9"), "config_entry_id": "e_altro"})
    house = _house(rows, {r["entity_id"] for r in rows})
    assert house.sibling_group("sensor.t0") == ("istanza", "e_hub")
    assert house.siblings("sensor.t0") == ["sensor.t0", "sensor.t1", "sensor.t2"]


def test_senza_l_elenco_le_sorelle_le_dice_lo_state_class():
    """G7-1: senza l'elenco del giro vale la regola del sorgente
    (`House.has_statistics`): una sorella senza `state_class` non ha
    statistiche, e non entra nel gruppo."""
    rows = [_entity("sensor.a", "d1"), _entity("sensor.b", "d1"), _entity("sensor.c", "d1")]
    house = _house(rows, None, {"sensor.a": "measurement", "sensor.b": "total_increasing"})
    assert house.sibling_group("sensor.a") == ("dispositivo", "d1")
    assert house.siblings("sensor.a") == ["sensor.a", "sensor.b"]
    assert house.sibling_group("sensor.c") is None


# -- i termometri del 29/09 con l'elenco guasto (G7-1, la rimisura) ----------
#
# La rimisura dello sprint su 413ce7a7 (06/10/2026, catture 03/09-03/10): con
# l'elenco delle statistiche illeggibile, gli 8 termometri -- un'entita' per
# dispositivo, la stessa istanza -- perdevano il gruppo, perche' nello
# specchio non portavano lo `state_class` e il ripiego di `has_statistics`
# diceva «niente statistiche». Il blocco del 29/09 spariva. Qui la forma e'
# la stessa, sintetica: tre termometri senza `state_class` nello specchio.

THERMOMETERS = [f"sensor.termometro_{i}" for i in range(3)]
HUB = "e_hub_termometri"


def _thermometer_app():
    rows = [{**_entity(t, f"d_termometro_{i}"), "config_entry_id": HUB}
            for i, t in enumerate(THERMOMETERS)]
    home_space = build_home_space({
        "entita": [*rows, _entity(HOUSE_METER, "d_contatore")],
        "integrazioni": [],
        "dispositivi": [*({"id": f"d_termometro_{i}", "name": f"Termometro {i}",
                           "disabled_by": None} for i in range(len(THERMOMETERS))),
                        {"id": "d_contatore", "name": "Contatore", "disabled_by": None}]})
    cache = [_to_minimal({"entity_id": t, "state": "21.3", "attributes": {}})
             for t in THERMOMETERS]
    cache.append(_to_minimal({"entity_id": HOUSE_METER, "state": "1",
                              "attributes": {"state_class": "total_increasing"}}))
    return {"knowledge": object(), "home_space_store": _Store(home_space),
            "entity_cache": _Cache(cache)}


def _thermometer_rows(entity_id, from_iso, to_iso, frozen_from):
    moment, end = datetime.fromisoformat(from_iso), datetime.fromisoformat(to_iso)
    rows = []
    while moment < end:
        row = {"start": _ms(moment), "end": _ms(moment + timedelta(hours=1)),
               "sum": None, "state": None, "change": None,
               "mean": None, "min": None, "max": None}
        if entity_id == HOUSE_METER:
            row["change"] = 0.1 + moment.hour / 1000
        elif moment.timestamp() >= frozen_from:
            row.update(min=21.3, max=21.3, mean=21.3)
        else:
            low = 19 + moment.hour / 10
            row.update(min=low, max=low + 0.2, mean=low + 0.1)
        rows.append(row)
        moment += timedelta(hours=1)
    return rows


async def _thermometer_ingredients(day, *, frozen_from, statistic_ids):
    asked: list[dict] = []

    def _statistics(extra):
        asked.append(extra)
        return {e: _thermometer_rows(e, extra["start_time"], extra["end_time"], frozen_from)
                for e in extra["statistic_ids"]
                if e in THERMOMETERS or e == HOUSE_METER}

    async def _stat_ids(_app, _ha, **_kw):
        return statistic_ids

    house = CasaFinta(synthetic_inputs(), answers={
        "recorder/statistics_during_period": _statistics})
    recipes = {"d_termometro_0": {"why": "la temperatura", "steps": [
                   {"name": "temperatura", "operation": "media_min_max",
                    "inputs": [f"@{THERMOMETERS[0]}"], "params": {"unit": "°C"}}]},
               "d_contatore": HOUSE_RECIPE}
    with mock.patch.object(server.recipe_turn, "recipes", lambda _k: recipes), \
            mock.patch.object(server, "statistic_ids_for_round", _stat_ids):
        ricette, serie, nomi, silent, mute = await server._report_ingredients(
            _thermometer_app(), house, giorno=day, timezone=TIMEZONE)
    # Un termometro e' una misura istantanea: dall'08/10/2026 il dato fermo
    # gli toglie le ore ferme -- qui il giorno intero -- e la misura che
    # resta senza un numero si rifiuta `ferma` (`Recipe.run`).
    report = build_report(day=day, episodes=[], series=serie, recipes=ricette,
                          names=nomi, silent=silent, muted=mute)
    [row] = [r for r in report["misure"] if r["misura"] == "temperatura"]
    return row, asked


@pytest.mark.asyncio
async def test_con_l_elenco_i_termometri_del_29_09_sono_fermi():
    """Il controllo: con l'elenco letto i tre termometri stanno nella loro
    istanza, e il blocco si vede."""
    row, _asked = await _thermometer_ingredients(
        "2026-09-29", frozen_from=_start("2026-09-29"),
        statistic_ids={*THERMOMETERS, HOUSE_METER})
    assert row["causa"] == FROZEN, row


@pytest.mark.asyncio
async def test_con_l_elenco_guasto_i_termometri_restano_nella_loro_istanza():
    """G7-1, la rimisura: l'elenco non si legge e lo specchio non porta lo
    `state_class` dei termometri. Le sorelle le dice la risposta delle serie
    di Home Assistant -- chi ha statistiche nella finestra -- e il blocco del
    29/09 resta preso."""
    row, asked = await _thermometer_ingredients(
        "2026-09-29", frozen_from=_start("2026-09-29"),
        statistic_ids={"errore": "giu'", "causa": "rete"})
    assert row["causa"] == FROZEN, row
    assert THERMOMETERS[2] in row["non_calcolabile"]
    assert len(asked) == 1
