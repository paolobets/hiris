"""La ricetta al volo (`mind/compute.py`; D6 del proprietario, 06/10/2026;
piano degli attori, strato 3, Task 3.1 e 3.2).

Le serie sono SINTETICHE. Home Assistant e' la casa finta della storia
(`tests/test_history_tool._house`, cioe' `scripts/casa_finta.py`: il client
VERO col trasporto sostituito), che risponde coi messaggi grezzi delle
statistiche orarie e dello storico; l'elenco delle statistiche arriva con la
casa (`House.with_statistics`), come nel giro delle ricette.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.reader import build_home_space
from hiris.app.mind import compute, operations
from hiris.app.mind.recipes import Recipe, hourly_points
from hiris.app.proxy.entity_cache import _to_minimal
from tests.test_attori_davanti_alla_fonte import _Cache
from tests.test_fonte_della_casa import _Store
from tests.test_history_tool import _HISTORY_PATH, _asked
from tests.test_history_tool import _house as _ha_house

#: Il 10/09/2026 a mezzanotte UTC, e dieci giorni dopo.
START = datetime(2026, 9, 10, tzinfo=UTC).timestamp()
DAY = 86400.0
END = START + 10 * DAY
NOW = END + 3600.0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _hours(values_per_hour, start=START):
    """Le fasce orarie nella forma GREZZA di `recorder/statistics_during_period`:
    `start`/`end` in millisecondi, `change` di un contatore."""
    return [{"start": int((start + h * 3600) * 1000),
             "end": int((start + (h + 1) * 3600) * 1000), "change": v}
            for h, v in enumerate(values_per_hour)]


def _Ha(statistics=None, states=None):
    """Home Assistant: le statistiche orarie e gli stati, dalla casa finta."""
    return _ha_house(serie=states, fasce=statistics)


def _client_points(raw):
    """Le fasce come il client le consegna (`HAClient.hourly_statistics`)."""
    return [{"inizio": r["start"] / 1000, "fine": r["end"] / 1000, "cambio": r["change"]}
            for r in raw]


def _house(entities, listed=None):
    rows = [{"entity_id": e, "platform": "x", "config_entry_id": None,
             "device_id": None, "disabled_by": None, "hidden_by": None}
            for e in entities]
    home_space = build_home_space({"entita": rows, "integrazioni": [], "dispositivi": []})
    mirror = _Cache([_to_minimal({"entity_id": e, "state": "1", "attributes": {}})
                     for e in entities])
    return House.read(_Store(home_space), mirror).with_statistics(
        set(entities) if listed is None else listed)


QUOTA = {"perche": "quanto dell'energia prodotta e' stata consumata in casa",
         "passi": [
             {"name": "prodotta", "operation": "somma_periodo",
              "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh"}},
             {"name": "consumata", "operation": "somma_periodo",
              "inputs": ["@sensor.consumata"], "params": {"unit": "kWh"}},
             {"name": "quota", "operation": "quota",
              "inputs": ["$consumata", "$prodotta"]}],
         "da": _iso(START), "a": _iso(END)}


async def _run(arguments, ha, entities, listed=None):
    return await compute.compute(arguments, ha=ha, house=_house(entities, listed), now=NOW,
                                 timezone="Europe/Rome")


@pytest.mark.asyncio
async def test_una_quota_su_dieci_giorni_e_LA_STESSA_della_ricetta():
    """Lo stesso motore: la quota che lo strumento calcola su dieci giorni e'
    quella che la stessa ricetta da' sulle stesse serie con `Recipe.run`.

    Mutazione ESEGUITA (06/10/2026): in `compute`, passare a `Recipe.run` le
    righe del client senza `hourly_points` -- rossa (`KeyError: 'valore'`:
    il passo esce rifiutato invece che col numero della ricetta).
    """
    prodotta = _hours([2.0] * 240)
    consumata = _hours([1.0] * 240)
    ha = _Ha({"sensor.prodotta": prodotta, "sensor.consumata": consumata})

    risposta = await _run(QUOTA, ha, ["sensor.prodotta", "sensor.consumata"])

    attesa = Recipe({"why": QUOTA["perche"], "steps": QUOTA["passi"]}).run(
        series={"sensor.prodotta": hourly_points(_client_points(prodotta)),
                "sensor.consumata": hourly_points(_client_points(consumata))})
    passi = {p["nome"]: p for p in risposta["passi"]}
    assert passi["quota"]["valore"] == attesa["quota"].value == 0.5
    assert passi["prodotta"]["valore"] == 480.0
    assert passi["prodotta"]["copertura"] == 1.0
    assert passi["quota"]["unita"] == "frazione"


@pytest.mark.asyncio
async def test_le_ore_attese_vengono_dal_PERIODO_e_un_buco_abbassa_la_copertura():
    """Dieci giorni sono 240 ore: se Home Assistant ne manda 180, la copertura
    e' 0,75 -- non 1,0, che sarebbe la copertura del campione.

    Mutazione ESEGUITA (06/10/2026): togliere `expected_parts` da
    `PERIOD_PARAMS` -- rossa (`assert 1.0 == 0.75`)."""
    ha = _Ha({"sensor.prodotta": _hours([2.0] * 180),
              "sensor.consumata": _hours([1.0] * 240)})

    risposta = await _run(QUOTA, ha, ["sensor.prodotta", "sensor.consumata"])

    passi = {p["nome"]: p for p in risposta["passi"]}
    assert passi["prodotta"]["copertura"] == 0.75
    assert passi["quota"]["copertura"] == 0.75


@pytest.mark.asyncio
async def test_un_entita_SENZA_statistiche_si_rifiuta_con_la_causa_della_fonte():
    ha = _Ha({"sensor.prodotta": _hours([2.0] * 240)})

    risposta = await _run(QUOTA, ha, ["sensor.prodotta", "sensor.consumata"],
                          listed={"sensor.prodotta"})

    passi = {p["nome"]: p for p in risposta["passi"]}
    assert passi["consumata"]["causa"] == operations.NO_STATISTICS
    assert "sensor.consumata" in passi["consumata"]["non_calcolabile"]
    # Il «non lo so» arriva fino in fondo, con la sua causa.
    assert passi["quota"]["causa"] == operations.NO_STATISTICS


@pytest.mark.asyncio
async def test_una_richiesta_STORTA_dice_TUTTI_i_problemi_e_non_legge_niente():
    """Tutti insieme, come `Recipe.validate`: e prima di qualunque lettura."""
    storta = {"perche": "", "passi": [
        {"name": "a", "operation": "inventata", "inputs": ["@sensor.a"]},
        {"name": "b", "operation": "somma_periodo", "inputs": ["@sensor.a"],
         "params": {"expected_parts": 24}},
        {"name": "c", "operation": "quota", "inputs": ["$zeta", "$b"]}],
        "da": _iso(START), "a": _iso(END)}
    ha = _Ha()

    risposta = await _run(storta, ha, ["sensor.a"])

    problemi = risposta["problemi"]
    assert any("PERCHE'" in p for p in problemi), problemi
    assert any("inventata" in p for p in problemi), problemi
    assert any("expected_parts" in p and "mette il codice" in p for p in problemi)
    assert any("unit" in p for p in problemi), problemi
    assert any("zeta" in p for p in problemi), problemi
    assert ha.calls == []


@pytest.mark.asyncio
async def test_il_periodo_si_legge_come_in_HISTORY():
    """Le stesse parole e gli stessi limiti della storia: oltre 90 giorni no."""
    lunga = {**QUOTA, "da": _iso(START - 100 * DAY)}

    risposta = await _run(lunga, _Ha(), ["sensor.prodotta", "sensor.consumata"])

    assert "90 giorni" in risposta["errore"]


@pytest.mark.asyncio
async def test_LA_PRESENZA_dagli_stati_di_una_persona():
    """D7: il tempo in casa, dagli stati -- `episodio` e `tempo_in_stato`,
    offribili solo allo strumento. Gli stati si chiedono alla storia, non alle
    statistiche, e la risposta dice da quando cominciano."""
    presenza = {"perche": "quanto tempo e' stata in casa", "passi": [
        {"name": "in_casa", "operation": "episodio", "inputs": ["@person.giulia"],
         "params": {"state": "home"}},
        {"name": "quanto", "operation": "tempo_in_stato", "inputs": ["$in_casa"]}],
        "da": _iso(START), "a": _iso(START + DAY)}
    stati = [{"quando": _iso(START), "valore": "not_home"},
             {"quando": _iso(START + 8 * 3600), "valore": "home"},
             {"quando": _iso(START + 18 * 3600), "valore": "not_home"}]
    ha = _Ha(states={"person.giulia": stati})

    risposta = await _run(presenza, ha, ["person.giulia"])

    passi = {p["nome"]: p for p in risposta["passi"]}
    assert passi["quanto"]["valore"] == 10 * 3600.0
    assert passi["quanto"]["unita"] == "s"
    assert passi["in_casa"]["valore"]["finestre"]
    assert risposta["stati_dal"]["person.giulia"].startswith("2026-09-10T02:00")
    assert {name for name, _ in _asked(ha)} == {_HISTORY_PATH}


@pytest.mark.asyncio
async def test_la_presenza_su_un_MESE_con_otto_giorni_di_stati_si_rifiuta():
    """Gli stati coprono circa otto giorni (R0, 03/10/2026): un mese chiesto
    non diventa il tempo di otto giorni con la faccia di un mese.

    Mutazioni ESEGUITE (06/10/2026): copertura 1.0 fissa in `_episode`, e
    `tempo_in_stato` senza il controllo `computable` -- rossa tutte e due."""
    presenza = {"perche": "in casa nel mese", "passi": [
        {"name": "in_casa", "operation": "episodio", "inputs": ["@person.giulia"],
         "params": {"state": "home"}},
        {"name": "quanto", "operation": "tempo_in_stato", "inputs": ["$in_casa"]}],
        "da": _iso(START - 20 * DAY), "a": _iso(END)}
    stati = [{"quando": _iso(END - 8 * DAY), "valore": "home"}]

    risposta = await _run(presenza, _Ha(states={"person.giulia": stati}),
                          ["person.giulia"])

    passi = {p["nome"]: p for p in risposta["passi"]}
    assert passi["quanto"]["causa"] == operations.COVERAGE_LOW


def test_lo_schema_si_CHIEDE_al_registro():
    """Le operazioni dello strumento sono quelle che il registro dice
    offribili: c'e' `episodio`, che una ricetta non puo' scrivere, e ci sono
    tutte quelle del catalogo delle ricette.

    Mutazione ESEGUITA: registrare un'operazione nuova offribile (in una
    copia del registro) -- entra nello schema senza toccare questa prova.
    """
    nomi = compute.tool_def()["input_schema"]["properties"]["passi"]["items"][
        "properties"]["operation"]["enum"]
    attese = sorted(n for n, op in operations.REGISTRY.items() if op.offered_to_tool)
    assert nomi == attese
    assert len(nomi) >= len([op for op in operations.REGISTRY.values() if op.offerable])
    assert "episodio" in nomi and "somma_fra" in nomi
    descrizione = compute.tool_def()["description"]
    assert "period_end" not in descrizione and "expected_parts" not in descrizione


def test_un_operazione_nuova_entra_nello_schema_da_sola(monkeypatch):
    nuova = operations.Operation(
        name="prova_nuova", inputs=("una misura",), returns="la stessa",
        refuses_when=("mai",), run=lambda m: m, takes=(operations.SHAPE_RESULT,),
        gives=operations.SHAPE_RESULT)
    monkeypatch.setitem(operations._REGISTRY, "prova_nuova", nuova)

    assert "prova_nuova" in compute.tool_def()["input_schema"]["properties"][
        "passi"]["items"]["properties"]["operation"]["enum"]


def test_le_ore_attese_sono_le_righe_che_HOME_ASSISTANT_selezionerebbe():
    """`start_ts >= inizio` e `start_ts < fine`, righe allo scoccare dell'ora."""
    ora = 3600.0
    assert compute.expected_hours(START, START + 24 * ora) == 24
    assert compute.expected_hours(START + 1800, START + 24 * ora) == 23
    assert compute.expected_hours(START + 1800, START + 24 * ora + 1) == 24
