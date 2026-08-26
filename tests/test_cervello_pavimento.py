"""Il pavimento: cosa l'osservatore guarda comunque.

Non e' una lista scritta a mano: si deriva da cio' che Home Assistant dichiara
gia' su ogni entita'. I casi qui sotto sono MISURATI sulla casa vera il 26
agosto 2026 (spec §9), non inventati -- ed e' la misura che ha corretto due
volte la prima stesura della spec, e una terza (la sesta gamba, "sicurezza")
la review del primo task.
"""
import pytest

from hiris.app.cervello.pavimento import GAMBE, gamba, nel_pavimento


@pytest.mark.parametrize("eid, attributi, atteso", [
    ("person.paolo_bettinelli", {}, "chi c'e'"),
    ("binary_sensor.movimento", {"device_class": "occupancy"}, "chi c'e'"),
    ("sensor.camera_temperatura", {"device_class": "temperature"}, "comfort"),
    ("climate.camera_t", {}, "comfort"),
    ("binary_sensor.porta_ingresso", {"device_class": "door"}, "dispersione"),
    ("cover.tapparella_studio", {}, "dispersione"),
    ("sensor.presa_energia", {"device_class": "energy"}, "consumo"),
    ("sensor.contatore", {"state_class": "total_increasing"}, "consumo"),
    ("sensor.iphone_batteria", {"device_class": "battery"}, "buono stato"),
    ("lock.porta_ingresso", {}, "sicurezza"),
    ("alarm_control_panel.centrale", {}, "sicurezza"),
    ("binary_sensor.rilevatore_fumo", {"device_class": "smoke"}, "sicurezza"),
    ("sensor.rilevatore_co", {"device_class": "carbon_monoxide"}, "sicurezza"),
])
def test_le_sei_gambe_dell_obiettivo(eid, attributi, atteso):
    assert gamba(eid, attributi) == atteso
    assert atteso in GAMBE


def test_i_device_tracker_del_router_restano_FUORI():
    """La misura che ha corretto la spec: 65 dei 73 `device_tracker` di questa
    casa hanno `source_type: router` -- l'NVR, Alexa, un Echo, una TV, una
    lampada. Dicono «questo apparecchio e' connesso al wifi», non «c'e'
    qualcuno in casa».

    Non e' una questione di volume: quei 65 fanno 114 cambi al giorno, lo zero
    per cento. E' che non significano niente per l'obiettivo.
    """
    assert gamba("device_tracker.nvr", {"source_type": "router"}) is None
    assert gamba("device_tracker.alexa", {"source_type": "router"}) is None


def test_i_device_tracker_gps_sono_le_persone():
    """I 4 `gps` sono i telefoni, e sono le fonti che stanno dietro alle due
    `person`. Senza di loro «chi c'e'» si riduce a due entita' sole."""
    assert gamba("device_tracker.iphone_di_marta", {"source_type": "gps"}) == "chi c'e'"


def test_un_tracker_senza_source_type_resta_fuori():
    """Nella casa vera quattro tracker non dichiarano `source_type`. Nel dubbio
    si sta fuori: un rumore in piu' costa disco, un dato mancante costa un
    passato che non si ricompra -- ma un tracker senza tipo non e' una persona
    finche' non lo dice, e le `person` non passano di qui."""
    assert gamba("device_tracker.ipad_mini", {}) is None


def test_la_batteria_entra_anche_se_e_di_servizio():
    """`config` e `diagnostic` sono 604 su 1226 in questa casa e per lo piu'
    sono rumore -- ma i sensori di batteria sono `diagnostic` e sono
    precisamente «buono stato». Il filtro e' per CLASSE del dispositivo, non
    per categoria: escluderli in blocco toglierebbe una gamba dell'obiettivo.
    """
    assert gamba("sensor.sensore_batteria",
                 {"device_class": "battery", "entity_category": "diagnostic"}) == "buono stato"


def test_cio_che_non_serve_all_obiettivo_resta_fuori():
    for eid, attributi in [
        ("light.lampadario", {}),
        ("media_player.tv", {}),
        ("sensor.uptime", {}),
        ("button.identifica", {}),
        ("update.firmware", {}),
    ]:
        assert gamba(eid, attributi) is None, eid


@pytest.mark.parametrize("eid, attributi, atteso", [
    ("lock.porta_ingresso", {}, "sicurezza"),
    ("lock.cancello", {}, "sicurezza"),
    ("alarm_control_panel.centrale", {}, "sicurezza"),
    ("binary_sensor.fumo_cucina", {"device_class": "smoke"}, "sicurezza"),
    ("binary_sensor.fuga_gas_cucina", {"device_class": "gas"}, "sicurezza"),
    ("binary_sensor.co_garage", {"device_class": "carbon_monoxide"}, "sicurezza"),
    ("sensor.rilevatore_co_soggiorno", {"device_class": "carbon_monoxide"}, "sicurezza"),
    ("binary_sensor.allagamento_bagno", {"device_class": "moisture"}, "sicurezza"),
    ("binary_sensor.porta_forzata", {"device_class": "safety"}, "sicurezza"),
    ("binary_sensor.manomissione_sirena", {"device_class": "tamper"}, "sicurezza"),
    ("binary_sensor.guasto_caldaia", {"device_class": "problem"}, "sicurezza"),
    ("binary_sensor.caldo_eccessivo", {"device_class": "heat"}, "sicurezza"),
    ("binary_sensor.gelo_tubi", {"device_class": "cold"}, "sicurezza"),
    ("siren.sirena_esterna", {}, "sicurezza"),
])
def test_la_sesta_gamba_sicurezza(eid, attributi, atteso):
    """La sesta gamba, aggiunta il 26/08 dalla review del primo task: la prima
    stesura della spec non conteneva gli allarmi (ne' fumo, ne' gas, ne'
    monossido, ne' allagamento, ne' serrature, ne' pannello dell'allarme) --
    era una dimenticanza, non una scelta, ed e' il buco peggiore possibile:
    un allarme che scatta e rientra mentre nessuno e' in casa, se non
    osservato, dopo tre giorni non esiste piu' in Home Assistant."""
    assert gamba(eid, attributi) == atteso


def test_la_trappola_del_gas_due_gambe_per_lo_stesso_nome_di_classe():
    """`gas` vive in due gambe a seconda del DOMINIO, non della classe da
    sola: `sensor` con classe `gas` e' il contatore dei metri cubi (consumo),
    `binary_sensor` con classe `gas` e' il rilevatore di fuga (sicurezza). Il
    ramo per dominio le separa gia'; un controllo per sola classe le
    fonderebbe."""
    assert gamba("sensor.contatore_gas", {"device_class": "gas"}) == "consumo"
    assert gamba("binary_sensor.fuga_gas", {"device_class": "gas"}) == "sicurezza"


def test_carbon_monoxide_non_co():
    """Trappola gia' documentata nel prodotto: la classe si chiama
    `carbon_monoxide`, NON `co`. Un'entita' con la sigla sbagliata non deve
    finire ne' in sicurezza ne' altrove per un falso positivo di stringa."""
    assert gamba("sensor.monossido_garage", {"device_class": "carbon_monoxide"}) == "sicurezza"
    assert gamba("sensor.monossido_garage", {"device_class": "co"}) is None


@pytest.mark.parametrize("classe", [
    "carbon_dioxide", "pm1", "pm10", "pm25",
    "volatile_organic_compounds", "volatile_organic_compounds_parts",
    "nitrogen_dioxide", "nitrogen_monoxide", "nitrous_oxide", "ozone",
    "sulphur_dioxide",
])
def test_la_qualita_dell_aria_entra_in_comfort(classe):
    """Il docstring di `gamba` promette «che aria si respira»: prima di questa
    correzione il codice copriva solo temperatura e umidita', una frase
    falsa."""
    assert gamba("sensor.aria_soggiorno", {"device_class": classe}) == "comfort"


def test_nel_pavimento_e_la_stessa_domanda_di_gamba():
    """Due funzioni che rispondono alla stessa domanda devono non poter
    divergere: la seconda si deriva dalla prima. La divergenza puo' nascere
    sia sui rami decisi dal DOMINIO sia su quelli decisi dagli ATTRIBUTI
    (`device_class`, `state_class`, `source_type`): entrambi vanno provati."""
    # Rami decisi dal dominio da soli.
    assert nel_pavimento("person.marta", {}) is True
    assert nel_pavimento("light.lampadario", {}) is False
    assert nel_pavimento("lock.porta_ingresso", {}) is True
    assert nel_pavimento("alarm_control_panel.centrale", {}) is True

    # Rami decisi da `device_class` su `binary_sensor`.
    assert nel_pavimento("binary_sensor.movimento", {"device_class": "occupancy"}) is True
    assert nel_pavimento("binary_sensor.porta", {"device_class": "door"}) is True
    assert nel_pavimento("binary_sensor.fumo", {"device_class": "smoke"}) is True
    assert nel_pavimento("binary_sensor.rumore", {"device_class": "sound"}) is False

    # Rami decisi da `device_class` su `sensor`.
    assert nel_pavimento("sensor.temp", {"device_class": "temperature"}) is True
    assert nel_pavimento("sensor.aria", {"device_class": "pm25"}) is True
    assert nel_pavimento("sensor.co", {"device_class": "carbon_monoxide"}) is True
    assert nel_pavimento("sensor.batteria", {"device_class": "battery"}) is True
    assert nel_pavimento("sensor.energia", {"device_class": "energy"}) is True
    assert nel_pavimento("sensor.uptime", {"device_class": "timestamp"}) is False

    # Ramo deciso da `state_class` su `sensor` (senza `device_class`).
    assert nel_pavimento("sensor.contatore", {"state_class": "total_increasing"}) is True
    assert nel_pavimento("sensor.istantaneo", {"state_class": "measurement"}) is False

    # Rami decisi da `source_type` su `device_tracker`.
    assert nel_pavimento("device_tracker.iphone", {"source_type": "gps"}) is True
    assert nel_pavimento("device_tracker.nvr", {"source_type": "router"}) is False
    assert nel_pavimento("device_tracker.ipad", {}) is False


@pytest.mark.parametrize("attributi, atteso", [
    ({}, None),
    ({"device_class": None}, None),
    ({"device_class": 3}, None),
    ({"state_class": []}, None),
    ({"source_type": None}, None),
])
def test_attributi_malformati_non_sollevano(attributi, atteso):
    """Gli attributi arrivano da Home Assistant: possono mancare o avere tipi
    inattesi. Un'eccezione qui fermerebbe l'osservatore su un evento solo --
    ma "non solleva" non basta: nessuno di questi valori malformati descrive
    una classe o un tipo che il pavimento riconosce, quindi il risultato
    corretto e' sempre e soltanto `None`, non uno qualsiasi fra piu' esiti."""
    assert gamba("sensor.x", attributi) is atteso
