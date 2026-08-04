"""Il ritratto: funzioni pure di selezione, composizione e resa.

Il criterio che regge tutto: il notevole e' DISCRETO. Una porta e' aperta o
chiusa; una temperatura cambia sempre. Se i sensori numerici entrassero nel
notevole, il delta direbbe "tutto e' cambiato" a ogni giro -- cioe' niente.
"""
from hiris.app.brain.portrait import notable_state


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
