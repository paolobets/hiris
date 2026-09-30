"""Il filtro di riservatezza della porta della casa (spec §3).

Decisione del proprietario, 29/09/2026: credenziali mai; la posizione della
casa si'; di persone e dispositivi che si spostano solo «in casa / fuori
casa». In TUTTE le profondita'.
"""
import json

import pytest

from hiris.app.home_space import privacy
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.memory.store import MemoryStore
from hiris.app.proxy import entity_cache
from tests.test_knowledge_tools import _semina_casa


def test_una_persona_in_una_zona_nominata_esce_solo_fuori_casa():
    """Il nome di una zona («Lavoro») direbbe gia' dove e'.

    Mutazione ESEGUITA: restituire lo stato cosi' com'e' -- rossa."""
    assert privacy.redact_state("person.marta", "Lavoro") == "not_home"
    assert privacy.redact_state("device_tracker.iphone", "Palestra") == "not_home"
    assert privacy.redact_state("person.marta", "home") == "home"
    assert privacy.redact_state("person.marta", "unavailable") == "unavailable"


def test_lo_stato_delle_altre_entita_non_si_tocca():
    """Il filtro di redazione dello stato vale solo per moving_domains.

    Mutazione ESEGUITA: togliere il controllo su MOVING_DOMAINS, ridurre
    redact_state a `return state if state in _NEUTRAL_STATES else "not_home"`
    -- rossa su light.sala e sensor.t."""
    assert privacy.redact_state("light.sala", "on") == "on"
    assert privacy.redact_state("sensor.t", "Lavoro") == "Lavoro"


def test_le_coordinate_di_chi_si_sposta_non_escono_quelle_della_casa_si():
    """Mutazione ESEGUITA: togliere `latitude` anche a `zone.home` -- rossa
    sulla seconda asserzione; non toglierla a `person` -- rossa sulla prima."""
    persona = {"values": {"latitude": 45.1, "longitude": 10.2,
                          "gps_accuracy": 5, "in_zones": ["zone.lavoro"],
                          "source": "device_tracker.iphone"}}
    fuori = privacy.redact_attributes("person.marta", persona)
    assert fuori == {"values": {"source": "device_tracker.iphone"}}
    casa = {"values": {"latitude": 45.1, "longitude": 10.2, "radius": 100}}
    assert privacy.redact_attributes("zone.home", casa) == casa


def test_le_credenziali_non_escono_mai():
    """Mutazione ESEGUITA: lasciare la cesta `credentials` -- rossa."""
    attributi = {"values": {"volume_level": 0.3},
                 entity_cache.CREDENTIALS: {"access_token": "abc"}}
    assert privacy.redact_attributes("media_player.tv", attributi) == {
        "values": {"volume_level": 0.3}}


def test_ip_mac_e_host_name_sono_gia_credenziali_nello_specchio():
    """Decisione del proprietario: identificativi di rete fuori. Lo specchio
    li mette gia' nella cesta delle credenziali: si verifica, non si ripete.

    Mutazione ESEGUITA: durante lo sviluppo, rimuovere `ip` da
    `_CREDENTIAL_ATTRIBUTES` in entity_cache.py e osservare il fallimento --
    rossa su `"ip" not in ceste.get("values", {})`."""
    ceste = entity_cache.inherited_attributes(
        {"ip": "192.168.1.10", "mac": "AA:BB:CC:DD:EE:FF", "host_name": "nvr",
         "source_type": "router"}, "device_tracker")
    assert "ip" not in ceste.get("values", {})
    assert "mac" not in ceste.get("values", {})
    assert "host_name" not in ceste.get("values", {})
    fuori = privacy.redact_attributes("device_tracker.nvr", ceste)
    assert entity_cache.CREDENTIALS not in fuori


def test_anche_il_dettaglio_completo_passa_dal_filtro():
    """Il dettaglio di `queries.view` usa chiavi italiane (`valori`,
    `trattenuti`), non le ceste dello specchio: il filtro vale per tutte e due.

    Mutazione ESEGUITA: riconoscere solo `CREDENTIALS` -- rossa su `trattenuti`;
    togliere le coordinate solo dalla cesta `values` -- rossa su `valori`."""
    dettaglio = {"id": "person.marta", "stato": "Lavoro", "attributi": {
        "valori": {"latitude": 1.0, "gps_accuracy": 3, "source": "x"},
        "trattenuti": {"token": "credenziale"}}}
    fuori = privacy.redact_row(dettaglio)
    assert fuori["stato"] == "not_home"
    assert fuori["attributi"] == {"valori": {"source": "x"}}


def test_una_riga_intera_passa_dal_filtro_senza_toccare_l_originale():
    """La funzione redact_row restituisce una copia, non muta l'originale.

    Mutazione ESEGUITA: modificare redact_row per mutare `row` in place,
    assegnando risultati direttamente: `out = row` invece di `out = dict(row)`
    -- rossa su `riga["stato"] == "Lavoro"`."""
    riga = {"id": "person.marta", "stato": "Lavoro",
            "attributi": {"values": {"latitude": 1.0, "source": "x"}}}
    fuori = privacy.redact_row(riga)
    assert fuori == {"id": "person.marta", "stato": "not_home",
                     "attributi": {"values": {"source": "x"}}}
    assert riga["stato"] == "Lavoro"


def test_zone_diverse_da_home_perdono_coordinate_zone_home_le_tiene():
    """Le zone che non sono zone.home perdono coordinate (rivelerebbero dove
    vanno le persone); zone.home le tiene (serve a sole, meteo, orari).

    Mutazione ESEGUITA: invertire il controllo, togliere coordinate da
    zone.home e non da zone.lavoro -- rossa su entrambe le asserzioni."""
    lavoro = {"values": {"latitude": 45.5, "longitude": 10.0, "radius": 200}}
    assert privacy.redact_attributes("zone.lavoro", lavoro) == {"values": {"radius": 200}}
    casa = {"values": {"latitude": 45.1, "longitude": 10.2, "radius": 100}}
    assert privacy.redact_attributes("zone.home", casa) == casa


# -- In TUTTE le profondita': le righe annidate del dettaglio completo --------
#
# Review finale della fetta (C1, 30/09/2026): il dettaglio di un dispositivo o
# di un'area porta le sue entita' come righe annidate, ognuna col suo `stato`
# grezzo. Le prove qui sotto passano dalla `search` VERA -- dispatcher,
# `_full_detail_sync`, `queries.view`, `query_house` -- perche' il difetto
# stava nella forma del dettaglio vero, che nessuna finta riproduceva.

_MOVING_HOME = {
    "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
    "aree": [{"id": "ingresso", "nome": "Ingresso", "piano_id": "terra",
              "alias": [], "etichette": []}],
    "dispositivi": [{"id": "dev_iphone", "nome": "iPhone di Marta",
                     "nome_utente": None, "produttore": "Apple", "modello": None,
                     "area_id": None, "disabilitato": 0, "etichette": []}],
    "entita": [
        {"id": "device_tracker.iphone_marta", "nome": "", "area_id": None,
         "dispositivo_id": "dev_iphone", "piattaforma": "mobile_app",
         "classe": None, "unita": None, "disabilitata": 0},
        {"id": "sensor.iphone_marta_batteria", "nome": "", "area_id": None,
         "dispositivo_id": "dev_iphone", "piattaforma": "mobile_app",
         "classe": "battery", "unita": "%", "disabilitata": 0},
        {"id": "person.marta", "nome": "Marta", "area_id": "ingresso",
         "dispositivo_id": None, "piattaforma": "person",
         "classe": None, "unita": None, "disabilitata": 0},
        {"id": "light.ingresso", "nome": "Luce ingresso", "area_id": "ingresso",
         "dispositivo_id": None, "piattaforma": "hue",
         "classe": None, "unita": None, "disabilitata": 0},
    ],
    "etichette": [], "categorie": [], "integrazioni": [],
}

_MOVING_STATES = [
    {"entity_id": "device_tracker.iphone_marta", "state": "Lavoro",
     "attributes": {"friendly_name": "iPhone Marta", "latitude": 45.4642,
                    "longitude": 9.19, "gps_accuracy": 12}},
    {"entity_id": "sensor.iphone_marta_batteria", "state": "80",
     "attributes": {"friendly_name": "iPhone Marta batteria",
                    "unit_of_measurement": "%", "device_class": "battery"}},
    {"entity_id": "person.marta", "state": "Palestra",
     "attributes": {"friendly_name": "Marta", "latitude": 45.4642,
                    "longitude": 9.19, "in_zones": ["zone.palestra"]}},
    {"entity_id": "light.ingresso", "state": "on",
     "attributes": {"friendly_name": "Luce ingresso"}},
]


class _MovingMirror:
    """Lo specchio nella forma vera: le righe escono da `_to_minimal`."""
    loaded = True

    def all_states(self):
        return [entity_cache._to_minimal(raw) for raw in _MOVING_STATES]


@pytest.fixture
def moving_door(tmp_path):
    casa = _semina_casa(tmp_path, casa=_MOVING_HOME, comportamento=[])
    memoria = MemoryStore(str(tmp_path / "memoria.db"))
    yield ToolDispatcher(casa, memoria, cache=_MovingMirror())
    memoria.close()
    casa.close()


def _dove_sono(risposta: dict) -> list[str]:
    """Cio' che direbbe dove sono Marta e il suo telefono, in tutto il testo
    della risposta -- a qualunque livello di annidamento."""
    testo = json.dumps(risposta, ensure_ascii=False)
    return [indizio for indizio in ("Lavoro", "Palestra", "45.4642", "9.19",
                                    "zone.palestra", "gps_accuracy")
            if indizio in testo]


@pytest.mark.asyncio
async def test_il_dettaglio_di_un_telefono_non_dice_dove_si_trova(moving_door):
    """Il telefono con l'app di Home Assistant ha SEMPRE un `device_tracker`:
    il dettaglio del dispositivo lo porta annidato in `entita`.

    Mutazione ESEGUITA: in `privacy.redact_row` togliere la discesa negli
    elenchi (`elif isinstance(value, list)`) -- rossa («Lavoro» esce)."""
    r = await moving_door.dispatch(
        "search", {"genere": "dispositivo", "riferimento": "dev_iphone"})
    voce, = r["voci"]
    assert voce["esiste"] is True
    righe = {e["id"]: e for e in voce["entita"]}
    assert righe["device_tracker.iphone_marta"]["stato"] == "not_home"
    # Il resto della riga resta: e' il grezzo di chi si sposta che esce ridotto.
    assert righe["sensor.iphone_marta_batteria"]["stato"] == "80"
    assert _dove_sono(r) == []


@pytest.mark.asyncio
async def test_il_dettaglio_di_un_area_non_dice_dove_e_una_persona(moving_door):
    """Mutazione ESEGUITA: la stessa di sopra -- rossa («Palestra» esce
    dentro l'area)."""
    r = await moving_door.dispatch(
        "search", {"genere": "area", "riferimento": "ingresso"})
    voce, = r["voci"]
    righe = {e["id"]: e for e in voce["entita"]}
    assert righe["person.marta"]["stato"] == "not_home"
    assert righe["light.ingresso"]["stato"] == "on"
    assert _dove_sono(r) == []


@pytest.mark.asyncio
async def test_cercare_il_telefono_per_nome_non_dice_dove_si_trova(moving_door):
    """La sonda della review: `search(nome="iphone")`, a qualunque profondita'
    la porta decida.

    Mutazione ESEGUITA: la stessa di sopra -- rossa."""
    r = await moving_door.dispatch("search", {"nome": "iphone"})
    assert r["trovate"] >= 1
    assert _dove_sono(r) == []
    r = await moving_door.dispatch("search", {"genere": "dispositivo",
                                                      "nome": "iphone"})
    assert r["profondita"] == "completa"
    assert _dove_sono(r) == []


def test_una_resa_dello_stato_grezzo_esce_col_grezzo():
    """Quando lo stato si riduce a `not_home`, la sua resa in parole e il
    motivo del suo silenzio parlavano del GREZZO: escono con lui.

    Mutazione ESEGUITA: non togliere `_RENDERED_STATE_KEYS` -- rossa."""
    riga = {"id": "person.marta", "stato": "Lavoro", "stato_leggibile": "Lavoro",
            "stato_non_reso": {"motivo": "«Lavoro» non ha resa"}}
    assert privacy.redact_row(riga) == {"id": "person.marta", "stato": "not_home"}
    casa = {"id": "person.marta", "stato": "home", "stato_leggibile": "A casa"}
    assert privacy.redact_row(casa) == casa


def test_gli_stati_annidati_di_chi_si_sposta_perdono_zona_e_coordinate():
    """La traccia di un'esecuzione porta `trigger.to_state` intero, e lo
    ripete nei passi (spec «la storia» §5, Review Focus 1): «Lavoro» ->
    «Palestra», con le coordinate, a ogni profondita'.

    Mutazione ESEGUITA: `redact_nested` che non scende nelle liste -- rossa
    (`passi`); che non riduce gli `attributes` -- rossa (`latitude`)."""
    traccia = {"variables": {"trigger": {
        "from_state": {"entity_id": "person.marta", "state": "Lavoro",
                       "attributes": {"latitude": 45.1, "longitude": 9.2,
                                      "friendly_name": "Marta"}},
        "to_state": {"entity_id": "person.marta", "state": "Palestra",
                     "attributes": {"latitude": 45.3, "longitude": 9.4,
                                    "gps_accuracy": 5, "friendly_name": "Marta"}}}},
        "passi": [{"changed_variables": [{"entity_id": "device_tracker.iphone",
                                          "state": "Palestra"}]}],
        "altro": {"entity_id": "light.sala", "state": "on",
                  "attributes": {"latitude": 1.0}}}
    fuori = privacy.redact_nested(traccia)
    testo = json.dumps({chiave: v for chiave, v in fuori.items() if chiave != "altro"})
    for dove in ("Lavoro", "Palestra", "latitude", "longitude", "gps_accuracy"):
        assert dove not in testo, dove
    stato = fuori["variables"]["trigger"]["to_state"]
    assert stato["state"] == "not_home"
    assert stato["attributes"] == {"friendly_name": "Marta"}
    assert fuori["passi"][0]["changed_variables"][0]["state"] == "not_home"
    assert fuori["altro"] == traccia["altro"]
    assert traccia["variables"]["trigger"]["to_state"]["state"] == "Palestra"


def test_la_zona_di_un_innesco_perde_le_coordinate_ma_la_casa_no():
    """Un innesco `zone` porta lo stato della zona, con le sue coordinate: la
    stessa regola di `redact_attributes` (le zone che non sono `zone.home`),
    dalla stessa fonte.

    Mutazione ESEGUITA: in `redact_nested` `_domain(entity_id) in
    MOVING_DOMAINS` al posto di `_hides_position` -- rossa."""
    innesco = {"zone": {"entity_id": "zone.lavoro", "state": "1",
                        "attributes": {"latitude": 45.1, "longitude": 9.2,
                                       "radius": 100}},
               "casa": {"entity_id": "zone.home", "state": "2",
                        "attributes": {"latitude": 45.0, "longitude": 9.0}}}
    fuori = privacy.redact_nested(innesco)
    assert fuori["zone"] == {"entity_id": "zone.lavoro", "state": "1",
                             "attributes": {"radius": 100}}
    assert fuori["casa"] == innesco["casa"]
