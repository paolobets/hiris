"""Il pavimento: cosa l'osservatore guarda comunque.

Non e' una lista scritta a mano: si deriva da cio' che Home Assistant dichiara
gia' su ogni entita'. I casi qui sotto sono MISURATI sulla casa vera il 26
agosto 2026 (spec §9), non inventati -- ed e' la misura che ha corretto due
volte la prima stesura della spec.
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
])
def test_le_cinque_gambe_dell_obiettivo(eid, attributi, atteso):
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


def test_nel_pavimento_e_la_stessa_domanda_di_gamba():
    """Due funzioni che rispondono alla stessa domanda devono non poter
    divergere: la seconda si deriva dalla prima."""
    assert nel_pavimento("person.marta", {}) is True
    assert nel_pavimento("light.lampadario", {}) is False


def test_attributi_malformati_non_sollevano():
    """Gli attributi arrivano da Home Assistant: possono mancare o avere tipi
    inattesi. Un'eccezione qui fermerebbe l'osservatore su un evento solo."""
    for attributi in [{}, {"device_class": None}, {"device_class": 3},
                      {"state_class": []}, {"source_type": None}]:
        assert gamba("sensor.x", attributi) in (None, "consumo", "comfort", "buono stato")
