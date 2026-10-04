"""La dashboard Energia come oggetto della casa (piano degli attori, strato 2,
Task 2.2, D6 «oggetto a parte»).

**Cosa difende.** Chi e' rete, sole, batteria lo dichiara l'utente nella
dashboard Energia di Home Assistant, e HIRIS lo legge da li': mai dai nomi
delle entita' (CLAUDE.md, «su Home Assistant non si ipotizza mai»: l'energia
prodotta letta come «consumo» e' nata cosi'). L'oggetto porta per ogni ruolo
cio' che serve a leggerlo da solo (fondamenta 1): il ruolo, l'entita', l'unita',
se ha statistiche, la provenienza. Si legge UNA volta per giro dell'anagrafe
(`HomeSpace.hold_registries`), non a ogni domanda, e il giro delle ricette lo
cita a parte, in un blocco (`recipe_turn._energy_block`), senza cambiare la
riga dell'entita'.

**La forma di `energy/get_prefs`** viene dal sorgente di Home Assistant, tag
`2026.9.4`, letto il 04/10/2026 (`components/energy/data.py`): vedi
`home_space/energy.py`. Non e' ancora misurata su questa casa (Task 2.0).

Mutazioni ESEGUITE il 04/10/2026, elencate sulle prove che le prendono.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

from hiris.app.home_space import energy
from hiris.app.home_space.house import House
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.topology import live_mirror
from hiris.app.mind import recipe_turn


def _run(coroutine):
    return asyncio.run(coroutine)


def _grid(**fields) -> dict:
    """Una rete nella forma di oggi (`GridSourceType`), coi campi del prezzo
    che lo schema di Home Assistant scrive sempre."""
    return {"type": "grid", "stat_energy_from": None, "stat_energy_to": None,
            "stat_cost": None, "entity_energy_price": None, "number_energy_price": None,
            "stat_compensation": None, "entity_energy_price_export": None,
            "number_energy_price_export": None, "cost_adjustment_day": 0.0, **fields}


BATTERY = {"type": "battery", "stat_energy_from": "sensor.inverter_scarica",
           "stat_energy_to": "sensor.inverter_carica", "stat_soc": "sensor.inverter_soc",
           "stat_rate": "sensor.inverter_potenza_batteria", "capacity": 10.0}

#: Una dashboard intera: rete, sole con la potenza (che NON e' un ruolo
#: d'energia), batteria con lo stato di carica, un consumo di dispositivo
#: compreso in un altro, e una statistica esterna (non un'entita').
PREFS = {
    "energy_sources": [
        _grid(stat_energy_from="sensor.inverter_prelievo",
              stat_energy_to="sensor.inverter_immissione", stat_cost="sensor.costo_rete"),
        {"type": "solar", "stat_energy_from": "sensor.inverter_produzione",
         "stat_rate": "sensor.inverter_potenza", "config_entry_solar_forecast": None,
         "name": "Tetto"},
        BATTERY,
        {"type": "gas", "stat_energy_from": "contatore:gas", "stat_cost": None,
         "entity_energy_price": None, "number_energy_price": None},
    ],
    "device_consumption": [
        {"stat_consumption": "sensor.lavatrice_energia",
         "included_in_stat": "sensor.quadro_energia"},
    ],
    "device_consumption_water": [],
}

#: I registri grezzi: un inverter con sei entita' (i nomi dicono «batteria»
#: anche quando la dashboard la batteria non la dichiara), una lavatrice.
REGISTRIES = {
    "dispositivi": [{"id": "inv", "name": "Inverter"}, {"id": "lav", "name": "Lavatrice"}],
    "entita": [
        {"entity_id": eid, "device_id": "inv", "original_name": name}
        for eid, name in (("sensor.inverter_prelievo", "Energia prelevata"),
                          ("sensor.inverter_immissione", "Energia immessa"),
                          ("sensor.inverter_produzione", "Energia prodotta"),
                          ("sensor.inverter_scarica", "Batteria scarica"),
                          ("sensor.inverter_carica", "Batteria carica"),
                          ("sensor.inverter_soc", "Batteria stato di carica"))
    ] + [{"entity_id": "sensor.lavatrice_energia", "device_id": "lav",
          "original_name": "Energia"}],
}

#: Le unita' VIVE: stanno nello specchio dello stato (`unit_of_measurement`
#: fra gli attributi), non nel registro -- che non le porta quasi mai
#: (`topology.live_first`). Dal Task 7 (B-17) l'anagrafe non le copia piu'.
UNITS = {"sensor.inverter_prelievo": "kWh", "sensor.inverter_immissione": "kWh",
         "sensor.inverter_produzione": "kWh", "sensor.inverter_scarica": "kWh",
         "sensor.inverter_carica": "kWh", "sensor.inverter_soc": "%",
         "sensor.lavatrice_energia": "kWh"}


class _Cache:
    """La cache dello stato, nella forma di `entity_cache.all_states`."""

    def all_states(self) -> list[dict]:
        return [{"id": eid, "state": "1", "unit": unit} for eid, unit in UNITS.items()]


def _store(tmp_path) -> HomeSpace:
    store = HomeSpace(str(tmp_path))
    store.hold_registries(REGISTRIES)
    return store


def _house(store: HomeSpace) -> House:
    """La casa del giro: l'anagrafe del negozio e lo specchio vivo."""
    return House(store.read(), live_mirror(_Cache().all_states()))


def _roles(answer) -> dict[str, str]:
    return {r["statistica"]: r["ruolo"] for r in answer["ruoli"]}


def _asked(house: CasaFinta) -> int:
    return sum(1 for command, _extra in house.calls if command == "energy/get_prefs")


# -- i ruoli, dal sorgente di Home Assistant ---------------------------------

def test_roles_are_what_the_dashboard_declares():
    """Mutazione ESEGUITA: `stat_energy_from` e `stat_energy_to` della
    batteria scambiati nella tabella -- rossa (carica e scarica rovesciate)."""
    roles = {(r["tipo"], r["campo"]): (r["statistica"], r["ruolo"])
             for r in energy.declared_roles(PREFS)}
    assert roles == {
        ("grid", "stat_energy_from"): ("sensor.inverter_prelievo", "prelievo"),
        ("grid", "stat_energy_to"): ("sensor.inverter_immissione", "immissione"),
        ("solar", "stat_energy_from"): ("sensor.inverter_produzione", "produzione"),
        ("battery", "stat_energy_from"): ("sensor.inverter_scarica", "scarica"),
        ("battery", "stat_energy_to"): ("sensor.inverter_carica", "carica"),
        ("battery", "stat_soc"): ("sensor.inverter_soc", "stato di carica"),
        ("gas", "stat_energy_from"): ("contatore:gas", "consumo di gas"),
        ("device_consumption", "stat_consumption"):
            ("sensor.lavatrice_energia", "consumo di un dispositivo"),
    }


def test_power_and_costs_are_not_energy_roles():
    """`stat_rate` e `stat_cost` sono dichiarati, ma non sono l'energia di un
    flusso: non entrano come ruoli (scelta dichiarata in `energy.ROLES`)."""
    ids = {r["statistica"] for r in energy.declared_roles(PREFS)}
    assert not ids & {"sensor.inverter_potenza", "sensor.inverter_potenza_batteria",
                      "sensor.costo_rete"}


def test_name_and_included_in_come_from_home_assistant():
    by_id = {r["statistica"]: r for r in energy.declared_roles(PREFS)}
    assert by_id["sensor.inverter_produzione"]["nome"] == "Tetto"
    assert by_id["sensor.lavatrice_energia"]["compreso_in"] == "sensor.quadro_energia"
    assert "nome" not in by_id["sensor.inverter_prelievo"]


def test_grid_without_export_has_no_export_role():
    prefs = {"energy_sources": [_grid(stat_energy_from="sensor.inverter_prelievo")],
             "device_consumption": []}
    assert [r["ruolo"] for r in energy.declared_roles(prefs)] == ["prelievo"]


def test_legacy_grid_lists_bring_the_same_roles():
    """La forma di prima della migrazione (`LegacyGridSourceType`): al tag
    letto Home Assistant non la manda piu', ma il client la passa com'e'.

    Mutazione ESEGUITA: tolto il ramo delle liste -- rossa (nessun ruolo)."""
    prefs = {"energy_sources": [{
        "type": "grid",
        "flow_from": [{"stat_energy_from": "sensor.inverter_prelievo", "stat_cost": None}],
        "flow_to": [{"stat_energy_to": "sensor.inverter_immissione",
                     "stat_compensation": None}],
        "cost_adjustment_day": 0.0}], "device_consumption": []}
    assert {(r["statistica"], r["ruolo"]) for r in energy.declared_roles(prefs)} == {
        ("sensor.inverter_prelievo", "prelievo"), ("sensor.inverter_immissione", "immissione")}


# -- l'oggetto della casa ----------------------------------------------------

def test_object_carries_what_it_needs_to_be_read_alone(tmp_path):
    """Fondamenta 1: ruolo, entita', unita', statistiche, provenienza."""
    store = _store(tmp_path)
    house = CasaFinta({"energy_prefs": PREFS})
    answer = _run(energy.energy_dashboard(house, store, _house(store),
                                          with_series={"sensor.inverter_prelievo"}))

    assert answer["provenienza"] == "dashboard Energia di Home Assistant"
    assert answer["dichiarata"] is True and answer["letta_alle"]
    by_id = {r["statistica"]: r for r in answer["ruoli"]}
    assert by_id["sensor.inverter_prelievo"] | {} == {
        "ruolo": "prelievo", "statistica": "sensor.inverter_prelievo",
        "entita": "sensor.inverter_prelievo", "unita": "kWh", "ha_statistiche": True,
        "tipo": "grid", "campo": "stat_energy_from"}
    assert by_id["sensor.inverter_soc"]["unita"] == "%"
    # L'unita' e' quella viva: il registro di questa casa non ne porta.
    assert all(e.get("unita") is None for e in store.read()["entita"])
    assert by_id["sensor.inverter_immissione"]["ha_statistiche"] is False
    # Una statistica esterna non e' un'entita' dell'anagrafe: non si finge.
    assert by_id["contatore:gas"]["entita"] is None
    assert by_id["contatore:gas"]["unita"] is None


def test_unknown_statistics_stay_unknown():
    """`with_series` a `None` e' «non l'ho potuto chiedere»: `ha_statistiche`
    resta `None`, non diventa un «no»."""
    roles = energy.describe({"ruoli": energy.declared_roles(PREFS), "dichiarata": True,
                             "letta_alle": "x"}, House({}, live_mirror([])), None)["ruoli"]
    assert {r["ha_statistiche"] for r in roles} == {None}


def test_no_battery_no_role_guessed_from_names(tmp_path):
    """Passo 4 del piano: la dashboard non dichiara la batteria, e le entita'
    dell'inverter che nel NOME dicono «batteria» restano senza ruolo.

    Mutazione ESEGUITA: `describe` che aggiunge un ruolo «carica»/«scarica» a
    ogni entita' dell'anagrafe col nome che contiene «carica»/«scarica» --
    rossa, coi due ruoli inventati."""
    prefs = {**PREFS, "energy_sources": [s for s in PREFS["energy_sources"]
                                         if s["type"] != "battery"]}
    store = _store(tmp_path)
    answer = _run(energy.energy_dashboard(CasaFinta({"energy_prefs": prefs}),
                                          store, _house(store), with_series=None))
    assert not {"sensor.inverter_scarica", "sensor.inverter_carica",
                "sensor.inverter_soc"} & set(_roles(answer))
    assert not {"carica", "scarica", "stato di carica"} & set(_roles(answer).values())


# -- letto una volta per giro dell'anagrafe ----------------------------------

def test_read_once_per_registry_rebuild(tmp_path):
    """Due domande nello stesso giro: una lettura. L'anagrafe ricostruita:
    un'altra.

    Mutazione ESEGUITA: `hold()` che non segna la dashboard da rileggere --
    rossa sulla seconda meta' (`assert 1 == 2`). Mutazione ESEGUITA:
    `energy_dashboard` che rilegge sempre -- rossa sulla prima (`2 == 1`)."""
    store = _store(tmp_path)
    house = CasaFinta({"energy_prefs": PREFS})

    first = _run(energy.energy_dashboard(house, store, _house(store)))
    second = _run(energy.energy_dashboard(house, store, _house(store)))
    assert _asked(house) == 1
    assert first == second

    store.hold_registries(REGISTRIES)
    _run(energy.energy_dashboard(house, store, _house(store)))
    assert _asked(house) == 2


def test_house_without_dashboard_says_so_and_does_not_ask_again(tmp_path):
    """`not_found` / «No prefs» e' un fatto della casa: «nessuna dashboard
    dichiarata», tenuto per il giro come una lettura buona."""
    store = _store(tmp_path)
    house = CasaFinta({}, refuse={"energy/get_prefs": {"code": "not_found",
                                                       "message": "No prefs"}})
    answer = _run(energy.energy_dashboard(house, store, _house(store)))
    assert answer["dichiarata"] is False and answer["ruoli"] == []
    _run(energy.energy_dashboard(house, store, _house(store)))
    assert _asked(house) == 1


def test_failure_keeps_previous_and_asks_again(tmp_path):
    """Il silenzio non e' «nessuna dashboard»: si tiene quella di prima, e il
    giro dopo richiede.

    Mutazione ESEGUITA: il silenzio tenuto come `not_found` -- rossa
    (`dichiarata` diventa falsa)."""
    store = _store(tmp_path)
    house = CasaFinta({"energy_prefs": PREFS})
    assert _run(energy.energy_dashboard(house, store, _house(store)))["dichiarata"] is True

    store.hold_registries(REGISTRIES)
    house.mute("energy/get_prefs")
    kept = _run(energy.energy_dashboard(house, store, _house(store)))
    assert kept["dichiarata"] is True and kept["ruoli"]
    _run(energy.energy_dashboard(house, store, _house(store)))
    assert _asked(house) == 3


def test_never_read_and_failing_is_no_object(tmp_path):
    house = CasaFinta({}, silence={"energy/get_prefs"})
    store = _store(tmp_path)
    assert _run(energy.energy_dashboard(house, store, _house(store))) is None


# -- il lettore: il giro delle ricette (Task 2.3, Passo 1a e 2) --------------

def _home(tmp_path):
    store = _store(tmp_path)
    house = _house(store)
    return house, _run(energy.energy_dashboard(CasaFinta({"energy_prefs": PREFS}), store,
                                               house, with_series=None))


def test_recipe_question_carries_roles_apart(tmp_path):
    """Il blocco sta a parte dalle righe delle entita', che non cambiano.

    Mutazione ESEGUITA: `_energy_block` che torna sempre "" -- rossa."""
    casa, dashboard = _home(tmp_path)
    question = recipe_turn.build_device_question("risparmiare", casa, "inv",
                                                 energy=dashboard)
    assert "La dashboard Energia di Home Assistant dichiara:" in question
    assert "- sensor.inverter_prelievo: prelievo [kWh]" in question
    assert "- sensor.inverter_produzione: produzione (Tetto) [kWh]" in question
    assert "valgono piu' del nome" in question
    # Le righe delle entita' sono quelle di sempre.
    for line in recipe_turn.device_lines(casa, "inv"):
        assert line in question
    # Solo le entita' DI QUESTO dispositivo: la lavatrice non c'e'.
    assert "sensor.lavatrice_energia" not in question


def test_device_outside_dashboard_keeps_old_question(tmp_path):
    """Cambia solo la domanda dei dispositivi con entita' della dashboard."""
    casa, dashboard = _home(tmp_path)
    prefs_without_device = {**dashboard, "ruoli": [
        r for r in dashboard["ruoli"] if r["statistica"] != "sensor.lavatrice_energia"]}
    assert (recipe_turn.build_device_question("x", casa, "lav",
                                              energy=prefs_without_device)
            == recipe_turn.build_device_question("x", casa, "lav"))


def test_consumption_device_says_what_includes_it(tmp_path):
    casa, dashboard = _home(tmp_path)
    question = recipe_turn.build_device_question("x", casa, "lav", energy=dashboard)
    assert ("- sensor.lavatrice_energia: consumo di un dispositivo [kWh], "
            "compreso in sensor.quadro_energia") in question


def test_bridge_turn_carries_the_same_block(tmp_path):
    casa, dashboard = _home(tmp_path)
    job = recipe_turn.bridge_turn("x", casa, "inv", energy=dashboard)
    assert "La dashboard Energia di Home Assistant dichiara:" in job["history"][0]["content"]


# -- il giro vero: `server.recipe_round` --------------------------------------

class _Runner:
    """Il modello finto: ricorda la domanda e risponde «niente da misurare»."""

    def __init__(self):
        self.questions: list[str] = []

    async def chat(self, *, user_message, **_kwargs):
        self.questions.append(user_message)
        return '{"why": "prova", "steps": []}'


def test_recipe_round_asks_with_dashboard(tmp_path):
    """Il lettore vivo: il giro delle ricette legge la dashboard (una volta) e
    la cita nella domanda dell'inverter.

    Mutazione ESEGUITA: `recipe_round` che non passa `energy=` ad `ask` --
    rossa (la domanda senza il blocco)."""
    from hiris.app import server
    from hiris.app.mind.knowledge import KnowledgeStore
    from hiris.app.mind.store import ObservationsStore

    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        archivio.decide_scope("sensor.inverter_prelievo", inside=True,
                              reason="prova", author="prova")
        house = CasaFinta({"energy_prefs": PREFS}, answers={
            "recorder/list_statistic_ids": lambda extra: [
                {"statistic_id": "sensor.inverter_prelievo"}]})
        runner = _Runner()
        app = {"observations": archivio, "knowledge": sapere,
               "home_space_store": _store(tmp_path), "ha_client": house,
               "entity_cache": _Cache(), "llm_router": runner}

        _run(server.recipe_round(app))

        assert len(runner.questions) == 1
        assert "- sensor.inverter_prelievo: prelievo [kWh]" in runner.questions[0]
        assert _asked(house) == 1
    finally:
        sapere.close()
        archivio.close()
