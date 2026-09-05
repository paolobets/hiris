from hiris.app.proxy.entity_cache import _to_minimal


def test_to_minimal_adds_domain():
    raw = {"entity_id": "sensor.temp_bagno", "state": "21.5",
           "attributes": {"friendly_name": "Temperatura Bagno", "unit_of_measurement": "°C"}}
    result = _to_minimal(raw)
    assert result["domain"] == "sensor"


def test_to_minimal_adds_device_class():
    raw = {"entity_id": "sensor.temp_bagno", "state": "21.5",
           "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}}
    result = _to_minimal(raw)
    assert result["device_class"] == "temperature"


def test_to_minimal_device_class_none_when_absent():
    raw = {"entity_id": "light.sala", "state": "on", "attributes": {}}
    result = _to_minimal(raw)
    assert result["device_class"] is None


def test_to_minimal_climate_attributes():
    raw = {
        "entity_id": "climate.bagno", "state": "heat",
        "attributes": {
            "hvac_mode": "heat", "hvac_action": "heating",
            "current_temperature": 21.5, "temperature": 22.0, "preset_mode": "home",
        },
    }
    result = _to_minimal(raw)
    assert result["attributes"]["hvac_mode"] == "heat"
    assert result["attributes"]["current_temperature"] == 21.5
    assert result["attributes"]["preset_mode"] == "home"


def test_to_minimal_light_attributes():
    raw = {
        "entity_id": "light.soggiorno", "state": "on",
        "attributes": {"brightness": 200, "color_temp": 3000},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["brightness"] == 200
    assert result["attributes"]["color_temp"] == 3000


def test_to_minimal_cover_attributes():
    raw = {
        "entity_id": "cover.tapparella_salotto", "state": "open",
        "attributes": {"current_position": 75},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["current_position"] == 75


def test_to_minimal_media_player_attributes():
    raw = {
        "entity_id": "media_player.tv_salotto", "state": "playing",
        "attributes": {"media_title": "Netflix", "volume_level": 0.5, "source": "HDMI1"},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["media_title"] == "Netflix"
    assert result["attributes"]["volume_level"] == 0.5


def test_to_minimal_no_extra_attrs_for_binary_sensor():
    raw = {
        "entity_id": "binary_sensor.porta_ingresso", "state": "off",
        "attributes": {"device_class": "door"},
    }
    result = _to_minimal(raw)
    assert result.get("attributes", {}) == {}


# --------------------------------------------------------------------------
# L'id di CONFIGURAZIONE di un'automazione (Task 6 di «le tracce e il log»).
#
# Home Assistant archivia le tracce di un'automazione sotto
# `automation.<id della configurazione>`, non sotto il suo `object_id`:
# catena verificata sui tag rilasciati `2024.7.0` e `2026.9.0`, scritta
# anello per anello nel docstring di `HAClient.automation_traces()`. Lo
# specchio e' l'unico posto da cui quell'id si puo' ricavare senza aprire una
# seconda lettura verso HA, e senza queste righe la proiezione lo buttava.
# --------------------------------------------------------------------------

def test_to_minimal_keeps_the_automation_configuration_id():
    """`attributes["id"]` di un'automazione sopravvive alla proiezione, e
    sopravvive DISTINTO dall'`entity_id` -- sono due identificatori diversi
    dello stesso oggetto, e confonderli e' il difetto che questa fetta
    corregge.

    Fonte del fatto che quell'attributo esiste:
    `BaseAutomationEntity.capability_attributes` torna `{CONF_ID:
    self.unique_id}`, e `helpers/entity.py::__async_calculate_state` copia
    le capability attributes dentro gli attributi dello stato (entrambi i
    tag).

    Mutazione: togliere il blocco `if dom == "automation": ...` da
    `_to_minimal` -- il test torna rosso su
    `assert result["automation_id"] == "1771346155970"` (`KeyError`).
    """
    raw = {"entity_id": "automation.luci_sera", "state": "on",
           "attributes": {"id": "1771346155970", "friendly_name": "Luci sera",
                          "mode": "single"}}
    result = _to_minimal(raw)
    assert result["automation_id"] == "1771346155970"
    assert result["id"] == "automation.luci_sera"


def test_to_minimal_leaves_the_configuration_id_out_of_the_model_attributes():
    """L'id NON entra in `attributes`, che e' cio' che il modello legge
    (`home_space/topology.live_mirror` porta quel dizionario fino a `guarda`
    e `cerca`): e' una chiave di giunzione per il codice, non un fatto sulla
    casa da mettere davanti a chi risponde.

    Mutazione: spostare l'id dentro `_DOMAIN_ATTRS` (`"automation": ("id",)`)
    invece di scriverlo in cima -- il test torna rosso su
    `assert result.get("attributes", {}) == {}`, che troverebbe
    `{"id": "1771346155970"}`.
    """
    raw = {"entity_id": "automation.luci_sera", "state": "on",
           "attributes": {"id": "1771346155970", "friendly_name": "Luci sera"}}
    result = _to_minimal(raw)
    assert result.get("attributes", {}) == {}


def test_to_minimal_has_no_configuration_id_for_an_automation_without_one():
    """Un'automazione YAML scritta senza `id:` non ha
    `attributes["id"]`: `capability_attributes` torna `None` quando
    `unique_id is None` (entrambi i tag). La chiave non deve comparire per
    finta -- ne' vuota ne' col ripiego dell'`object_id`: chi legge deve poter
    dire «non riesco a risolverla».

    Mutazione: `result["automation_id"] = attrs.get("id") or eid.partition(
    ".")[2]` (il ripiego sull'`object_id`, cioe' proprio il difetto che
    questa fetta corregge) -- il test torna rosso su
    `assert "automation_id" not in result`, che troverebbe `"scritta_a_mano"`.
    """
    raw = {"entity_id": "automation.scritta_a_mano", "state": "on",
           "attributes": {"friendly_name": "Scritta a mano", "mode": "single"}}
    result = _to_minimal(raw)
    assert "automation_id" not in result


def test_to_minimal_has_no_configuration_id_outside_the_automation_domain():
    """`attributes["id"]` esiste anche fuori dal dominio `automation`: una
    `scene` ne porta uno (verificato alla fonte sui tag `2024.7.0` e
    `2026.9.0`, `components/homeassistant/scene.py::HomeAssistantScene.
    extra_state_attributes`, `attributes[CONF_ID] = unique_id`). Li' non e'
    pero' la chiave delle tracce -- le scene non ne hanno -- e raccoglierlo
    lo stesso metterebbe in circolo un `automation_id` che non lo e'.

    Mutazione (verificata eseguendola): `if True:` al posto di
    `if dom == "automation":` -- il test torna rosso su
    `assert "automation_id" not in result`.
    """
    raw = {"entity_id": "scene.buonanotte", "state": "unknown",
           "attributes": {"id": "1771346155971", "friendly_name": "Buonanotte"}}
    result = _to_minimal(raw)
    assert "automation_id" not in result
