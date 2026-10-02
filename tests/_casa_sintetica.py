"""Una casa finta, piccola e senza nomi veri, per provare gli attrezzi.

La sonda di parita' e la fotografia delle porte lavorano sugli ingressi che
`scripts/casa.py` congela dalla casa vera -- che stanno FUORI dal repo, perche'
portano i nomi di una casa. Le loro prove hanno bisogno degli stessi ingressi
in piccolo, e con i casi che contano messi apposta:

- tre entita' che EREDITANO l'area dal dispositivo (non ne hanno una propria);
- una disabilitata, una nascosta, due di servizio (`config`, `diagnostic`);
- un dispositivo disabilitato;
- una entita' `unavailable`;
- nomi di registro senza il prefisso del dispositivo, e `friendly_name` vivo
  col prefisso -- che e' la forma vera di Home Assistant.

**La forma e' quella dei file catturati** (`casa.INPUTS`): `registries` ha le
chiavi che `HAClient.read_registries` restituisce e le righe grezze di Home
Assistant; `states` sono le righe di `GET /api/states`; il resto e' cio' che i
metodi omonimi del client restituiscono.
"""
from __future__ import annotations

INSTANT = "2026-10-01T10:00:00+00:00"


def _state(entity_id: str, state: str, name: str, **attributes) -> dict:
    return {"entity_id": entity_id, "state": state,
            "attributes": {"friendly_name": name, **attributes},
            "last_changed": INSTANT, "last_updated": INSTANT}


def _entity(entity_id: str, platform: str, **fields) -> dict:
    return {"entity_id": entity_id, "platform": platform, "name": None,
            "original_name": None, "area_id": None, "device_id": None,
            "entity_category": None, "disabled_by": None, "hidden_by": None,
            "aliases": [], "labels": [], "categories": {}, **fields}


def synthetic_inputs() -> dict:
    """Gli ingressi, nuovi a ogni chiamata: chi li modifica non sporca gli altri."""
    registries = {
        "piani": [{"floor_id": "piano_terra", "name": "Piano terra", "level": 0},
                  {"floor_id": "primo_piano", "name": "Primo piano", "level": 1}],
        "aree": [
            {"area_id": "stanza_uno", "name": "Stanza uno", "floor_id": "piano_terra"},
            {"area_id": "stanza_due", "name": "Stanza due", "floor_id": "piano_terra"},
            {"area_id": "stanza_tre", "name": "Stanza tre", "floor_id": "primo_piano"}],
        "dispositivi": [
            {"id": "dev_a", "name": "Sensore A", "area_id": "stanza_uno"},
            {"id": "dev_b", "name": "Sensore B", "area_id": "stanza_due"},
            {"id": "dev_c", "name": "Sensore C", "area_id": "stanza_tre"},
            {"id": "dev_d", "name": "Sensore D", "area_id": "stanza_uno",
             "disabled_by": "user"}],
        "entita": [
            # Le tre che ereditano l'area dal dispositivo.
            _entity("sensor.sensore_a_temperatura", "marca_uno", device_id="dev_a",
                    original_name="Temperatura"),
            _entity("sensor.sensore_a_umidita", "marca_uno", device_id="dev_a",
                    original_name="Umidita"),
            _entity("sensor.sensore_b_potenza", "marca_uno", device_id="dev_b",
                    original_name="Potenza"),
            # Con l'area propria.
            _entity("light.luce_uno", "marca_due", area_id="stanza_uno", name="Luce uno"),
            _entity("switch.presa_uno", "marca_uno", device_id="dev_b",
                    area_id="stanza_due", original_name="Presa"),
            _entity("binary_sensor.porta_uno", "marca_due", device_id="dev_c",
                    area_id="stanza_tre", original_name="Porta"),
            _entity("sensor.contatore_uno", "marca_due", device_id="dev_c",
                    area_id="stanza_tre", original_name="Contatore"),
            # Di servizio, nascosta, disabilitata.
            _entity("sensor.sensore_b_segnale", "marca_uno", device_id="dev_b",
                    original_name="Segnale", entity_category="diagnostic"),
            _entity("number.sensore_b_soglia", "marca_uno", device_id="dev_b",
                    original_name="Soglia", entity_category="config"),
            _entity("sensor.sensore_c_riserva", "marca_due", device_id="dev_c",
                    original_name="Riserva", hidden_by="user"),
            _entity("sensor.sensore_d_spento", "marca_uno", device_id="dev_d",
                    original_name="Spento", disabled_by="user"),
            _entity("automation.automazione_uno", "automation", name="Automazione uno"),
        ],
        "etichette": [],
        "categorie": [],
        "integrazioni": [
            {"entry_id": "voce_uno", "domain": "marca_uno", "title": "Marca Uno",
             "state": "loaded", "source": "user"},
            {"entry_id": "voce_due", "domain": "marca_due", "title": "Marca Due",
             "state": "loaded", "source": "user"}],
    }
    states = [
        _state("sensor.sensore_a_temperatura", "21.5", "Sensore A Temperatura",
               unit_of_measurement="°C", device_class="temperature",
               state_class="measurement"),
        _state("sensor.sensore_a_umidita", "48", "Sensore A Umidita",
               unit_of_measurement="%", device_class="humidity",
               state_class="measurement"),
        _state("sensor.sensore_b_potenza", "120", "Sensore B Potenza",
               unit_of_measurement="W", device_class="power", state_class="measurement"),
        _state("light.luce_uno", "on", "Luce uno"),
        _state("switch.presa_uno", "off", "Sensore B Presa"),
        _state("binary_sensor.porta_uno", "unavailable", "Sensore C Porta",
               device_class="door"),
        _state("sensor.contatore_uno", "1532.4", "Sensore C Contatore",
               unit_of_measurement="kWh", device_class="energy",
               state_class="total_increasing"),
        _state("sensor.sensore_b_segnale", "-61", "Sensore B Segnale",
               unit_of_measurement="dBm", device_class="signal_strength",
               state_class="measurement"),
        _state("number.sensore_b_soglia", "30", "Sensore B Soglia"),
        _state("sensor.sensore_c_riserva", "3", "Sensore C Riserva"),
        _state("automation.automazione_uno", "on", "Automazione uno",
               id="auto_uno", last_triggered=None),
    ]
    return {
        "registries": registries,
        "states": states,
        "statistic_ids": ["sensor.contatore_uno", "sensor.sensore_a_temperatura",
                          "sensor.sensore_a_umidita", "sensor.sensore_b_potenza",
                          "sensor.sensore_b_segnale"],
        "behavior": {"configurazioni": {"automation.automazione_uno": {
            "id": "auto_uno", "alias": "Automazione uno",
            "trigger": [{"platform": "state", "entity_id": "binary_sensor.porta_uno"}],
            "action": [{"service": "light.turn_on",
                        "target": {"entity_id": "light.luce_uno"}}]}}},
        "ha_config": {"version": "2026.9.4", "time_zone": "Europe/Rome",
                      "language": "it", "unit_system": {"temperature": "°C"}},
        "services": [{"domain": "light", "services": {
            "turn_on": {"name": "Turn on", "fields": {}, "target": {"entity": [{}]}},
            "turn_off": {"name": "Turn off", "fields": {}, "target": {"entity": [{}]}}}}],
        "translations": {"language": "it", "category": "entity_component",
                         "report": {"risorse": {
                             "component.binary_sensor.entity_component.door.state.on": "Aperta",
                             "component.binary_sensor.entity_component.door.state.off":
                                 "Chiusa"}}},
        "problems": {"problemi": []},
        "system_log": {"voci": []},
        "dashboards": {"entries": [], "unavailable": []},
    }
