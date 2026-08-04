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


from hiris.app.brain.portrait import render_portrait


def test_render_empty_portrait_is_empty_string():
    assert render_portrait({"aree": {}, "cambiato": [],
                            "conteggi": {"entita": 0, "aree": 0}}) == ""


def test_render_has_both_sections():
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce cucina"], "aperto": ["Finestra"]}},
        "cambiato": [{"nome": "Luce cucina", "entity_id": "light.cucina",
                      "was": "off", "now": "on", "since": "2026-08-04T09:00:00Z"}],
        "conteggi": {"entita": 42, "aree": 5},
    })
    assert "Com'e' la casa" in txt
    assert "Cucina" in txt and "Luce cucina" in txt and "Finestra" in txt
    assert "Cos'e' cambiato" in txt
    assert "off" in txt and "on" in txt


def test_render_omits_the_change_section_when_nothing_changed():
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce"], "aperto": []}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    })
    assert "Com'e' la casa" in txt
    assert "Cos'e' cambiato" not in txt


def test_render_is_bounded():
    aree = {f"Area{i}": {"acceso": [f"Luce {i}-{j}" for j in range(50)],
                         "aperto": []} for i in range(30)}
    txt = render_portrait({"aree": aree, "cambiato": [],
                           "conteggi": {"entita": 1500, "aree": 30}},
                          max_chars=500)
    assert len(txt) <= 500


def test_render_never_raises_on_garbage():
    assert render_portrait(None) == ""
    assert render_portrait({"aree": "non un dict"}) == ""


def test_render_puts_alarms_first():
    """Un rilevatore scattato e' la cosa piu' importante che la casa dica:
    non deve finire in fondo a una riga fra le luci accese."""
    txt = render_portrait({
        "aree": {
            "Cucina": {"acceso": ["Luce"], "aperto": ["Finestra"],
                       "allerta": ["Fumo"]},
            "Salotto": {"acceso": ["Lampada"], "aperto": [], "allerta": []},
        },
        "cambiato": [],
        "conteggi": {"entita": 4, "aree": 2},
    })
    assert txt.startswith("ALLERTA:")
    assert "- Cucina: Fumo" in txt
    assert txt.index("ALLERTA:") < txt.index("Com'e' la casa:")
    # l'allerta non viene ripetuta fra le aperture
    assert "aperto: Finestra" in txt and "aperto: Finestra, Fumo" not in txt


def test_render_omits_the_alarm_section_when_there_are_none():
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce"], "aperto": [], "allerta": []}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    })
    assert "ALLERTA" not in txt
    assert txt.startswith("Com'e' la casa:")


def test_render_with_only_an_alarm_has_no_empty_house_header():
    txt = render_portrait({
        "aree": {"Sottotetto": {"acceso": [], "aperto": [],
                                "allerta": ["Allagamento"]}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    })
    assert "ALLERTA:" in txt and "Allagamento" in txt
    assert "Com'e' la casa:" not in txt


def test_render_starts_with_the_change_section_when_it_is_the_only_one():
    txt = render_portrait({
        "aree": {},
        "cambiato": [{"nome": "Luce", "entity_id": "light.a",
                      "was": "on", "now": "off",
                      "since": "2026-08-04T09:00:00Z"}],
        "conteggi": {"entita": 1, "aree": 0},
    })
    assert txt.startswith("Cos'e' cambiato dall'ultima volta:")


def test_render_empty_when_cambiato_has_only_non_dict_items():
    """A header without content breaks the contract: the caller depends on ""
    to mean 'do not add any block to the prompt'. A bare header leaks
    implementation details (ritratto tried but found nothing to say) and
    violates byte-identity when the portrait is unavailable."""
    txt = render_portrait({"aree": {}, "cambiato": [1, 2, 3],
                          "conteggi": {"entita": 0, "aree": 0}})
    assert txt == ""


def test_render_single_blank_line_between_alarms_and_changes_when_casa_empty():
    """When there are alarms and changes but no lit/open entities, the house
    section is omitted. The rendering must have exactly one blank line
    between alarms and changes: no double newlines."""
    txt = render_portrait({
        "aree": {
            "Sottotetto": {"acceso": [], "aperto": [],
                          "allerta": ["Allagamento"]},
        },
        "cambiato": [{"nome": "Sensore", "entity_id": "sensor.a",
                     "was": "ok", "now": "allarme", "since": "2026-08-04T09:00:00Z"}],
        "conteggi": {"entita": 2, "aree": 1},
    })
    assert txt.startswith("ALLERTA:")
    assert txt.index("ALLERTA:") < txt.index("Cos'e' cambiato")
    assert "\n\n\n" not in txt


def test_render_max_chars_zero_returns_empty_string():
    """When max_chars is 0, the result must respect the bound: length <= 0,
    which means empty string. Truncation never returns a single "…" for
    max_chars=0."""
    txt = render_portrait({
        "aree": {"Cucina": {"acceso": ["Luce"], "aperto": []}},
        "cambiato": [], "conteggi": {"entita": 1, "aree": 1},
    }, max_chars=0)
    assert txt == ""
    assert len(txt) <= 0
