"""Il filtro di riservatezza della porta della casa (spec §3).

Decisione del proprietario, 29/09/2026: credenziali mai; la posizione della
casa si'; di persone e dispositivi che si spostano solo «in casa / fuori
casa». In TUTTE le profondita'.
"""
from hiris.app.home_space import privacy
from hiris.app.proxy import entity_cache


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
