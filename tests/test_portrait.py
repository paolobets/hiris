"""Il ritratto: funzioni pure di selezione, composizione e resa.

Il criterio che regge tutto: il notevole e' DISCRETO. Una porta e' aperta o
chiusa; una temperatura cambia sempre. Se i sensori numerici entrassero nel
notevole, il delta direbbe "tutto e' cambiato" a ogni giro -- cioe' niente.
"""
from hiris.app.brain.portrait import notable_state, build_portrait


def _s(eid, state, *, domain=None, device_class=None, name=None):
    return {
        "id": eid,
        "state": state,
        "name": name or eid,
        "unit": "",
        "domain": domain or eid.split(".")[0],
        "device_class": device_class,
    }


def test_discrete_domains_are_notable():
    out = notable_state([
        _s("light.cucina", "on"),
        _s("lock.ingresso", "locked"),
        _s("climate.salotto", "heat"),
        _s("alarm_control_panel.casa", "armed_away"),
    ])
    assert out == {
        "light.cucina": "on",
        "lock.ingresso": "locked",
        "climate.salotto": "heat",
        "alarm_control_panel.casa": "armed_away",
    }


def test_numeric_sensors_are_never_notable():
    out = notable_state([
        _s("sensor.temperatura", "21.4", device_class="temperature"),
        _s("sensor.potenza", "1230", device_class="power"),
        _s("sensor.umidita", "55", device_class="humidity"),
    ])
    assert out == {}


def test_binary_sensor_only_for_meaningful_classes():
    out = notable_state([
        _s("binary_sensor.porta", "on", device_class="door"),
        _s("binary_sensor.finestra", "off", device_class="window"),
        _s("binary_sensor.fumo", "off", device_class="smoke"),
        _s("binary_sensor.movimento", "on", device_class="motion"),
        _s("binary_sensor.presenza", "on", device_class="occupancy"),
    ])
    assert out == {
        "binary_sensor.porta": "on",
        "binary_sensor.finestra": "off",
        "binary_sensor.fumo": "off",
    }


def test_unreadable_states_are_skipped():
    out = notable_state([
        _s("light.a", "unavailable"),
        _s("light.b", "unknown"),
        _s("light.c", ""),
        _s("light.d", None),
        _s("light.e", "on"),
    ])
    assert out == {"light.e": "on"}


def test_malformed_rows_do_not_raise():
    out = notable_state([
        {"state": "on"},
        {"id": "light.a"},
        None,
        "non un dict",
        _s("light.ok", "on"),
    ])
    assert out == {"light.ok": "on"}


def test_state_is_clamped_and_sanitized():
    out = notable_state([_s("light.a", "on" + "x" * 500)])
    assert len(out["light.a"]) <= 120


def test_build_groups_open_and_on_by_area():
    p = build_portrait(
        area_map={
            "Cucina": ["light.cucina", "binary_sensor.finestra_cucina"],
            "Ingresso": ["lock.ingresso"],
        },
        states=[
            _s("light.cucina", "on", name="Luce cucina"),
            _s("binary_sensor.finestra_cucina", "on",
               device_class="window", name="Finestra cucina"),
            _s("lock.ingresso", "locked", name="Serratura"),
        ],
        baseline={},
        changes=[],
    )
    assert p["aree"]["Cucina"]["acceso"] == ["Luce cucina"]
    assert p["aree"]["Cucina"]["aperto"] == ["Finestra cucina"]
    assert "Ingresso" not in p["aree"]
    assert p["conteggi"] == {"entita": 3, "aree": 2}


def test_build_reports_changes_with_friendly_names():
    p = build_portrait(
        area_map={"Cucina": ["light.cucina"]},
        states=[_s("light.cucina", "off", name="Luce cucina")],
        baseline={},
        changes=[{"entity_id": "light.cucina", "was": "on",
                  "now": "off", "since": "2026-08-04T09:00:00Z"}],
    )
    assert p["cambiato"] == [
        {"nome": "Luce cucina", "entity_id": "light.cucina",
         "was": "on", "now": "off", "since": "2026-08-04T09:00:00Z"}
    ]


def test_build_uses_since_from_baseline_for_open_things():
    p = build_portrait(
        area_map={"Cucina": ["binary_sensor.finestra"]},
        states=[_s("binary_sensor.finestra", "on",
                   device_class="window", name="Finestra")],
        baseline={"binary_sensor.finestra":
                  {"state": "on", "since": "2026-08-04T07:00:00Z"}},
        changes=[],
    )
    assert p["aree"]["Cucina"]["aperto"] == ["Finestra (da 2026-08-04T07:00:00Z)"]


def test_build_tolerates_missing_area_map():
    p = build_portrait(
        area_map=None,
        states=[_s("light.a", "on", name="Luce")],
        baseline={}, changes=[],
    )
    assert p["aree"] == {}
    assert p["conteggi"]["aree"] == 0


def test_build_never_raises_on_garbage():
    p = build_portrait(area_map={"X": None}, states=None,
                       baseline=None, changes=None)
    assert p["aree"] == {} and p["cambiato"] == []


def test_alarm_sensors_go_to_their_own_bucket_not_to_open():
    """Un rilevatore di fumo che scatta non e' una finestra socchiusa."""
    p = build_portrait(
        area_map={"Cucina": ["binary_sensor.fumo", "binary_sensor.finestra"]},
        states=[
            _s("binary_sensor.fumo", "on", device_class="smoke", name="Fumo"),
            _s("binary_sensor.finestra", "on",
               device_class="window", name="Finestra"),
        ],
        baseline={}, changes=[],
    )
    assert p["aree"]["Cucina"]["allerta"] == ["Fumo"]
    assert p["aree"]["Cucina"]["aperto"] == ["Finestra"]
    assert p["aree"]["Cucina"]["acceso"] == []


def test_an_area_with_only_an_alarm_is_still_reported():
    p = build_portrait(
        area_map={"Sottotetto": ["binary_sensor.allagamento"]},
        states=[_s("binary_sensor.allagamento", "on",
                   device_class="moisture", name="Allagamento")],
        baseline={}, changes=[],
    )
    assert p["aree"]["Sottotetto"]["allerta"] == ["Allagamento"]


def test_change_states_are_sanitized():
    """was/now sono stati di entita' HA: il vincolo globale vale anche qui."""
    p = build_portrait(
        area_map={}, states=[_s("light.a", "off", name="Luce")],
        baseline={},
        changes=[{"entity_id": "light.a", "was": "x" * 500,
                  "now": "y" * 500, "since": "2026-08-04T09:00:00Z"}],
    )
    assert len(p["cambiato"][0]["was"]) <= 120
    assert len(p["cambiato"][0]["now"]) <= 120


def test_change_with_no_previous_state_keeps_none():
    p = build_portrait(
        area_map={}, states=[_s("light.a", "on", name="Luce")],
        baseline={},
        changes=[{"entity_id": "light.a", "was": None,
                  "now": "on", "since": "2026-08-04T09:00:00Z"}],
    )
    assert p["cambiato"][0]["was"] is None
