import pytest

from hiris.app.casa.archivio import ArchivioCasa

_REGISTRI = {
    "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0, "icon": "mdi:home"}],
    "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra",
              "aliases": ["angolo cottura"], "labels": ["giorno"], "icon": None}],
    "dispositivi": [{"id": "d1", "name": "Frigo", "name_by_user": "Frigorifero",
                     "manufacturer": "Bosch", "model": "KGN", "area_id": "cucina",
                     "disabled_by": None, "labels": []}],
    "entita": [{"entity_id": "sensor.frigo_temp", "device_id": "d1", "area_id": None,
                "platform": "mqtt", "entity_category": None,
                "original_device_class": "temperature", "unit_of_measurement": "°C",
                "disabled_by": None, "hidden_by": None, "name": None,
                "original_name": "Temperatura frigo", "aliases": [], "labels": []}],
    "etichette": [{"label_id": "giorno", "name": "Zona giorno", "color": "blue", "icon": None}],
    "categorie": [{"category_id": "c1", "name": "Clima", "ambito": "automation"}],
    "integrazioni": [{"domain": "mqtt", "title": "MQTT", "state": "loaded"}],
}


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


def test_una_casa_vuota_si_legge_senza_esplodere(archivio):
    casa = archivio.leggi()
    assert casa["aree"] == []
    assert archivio.aggiornata_il() is None


def test_sostituisci_e_rileggi(archivio):
    archivio.sostituisci(_REGISTRI)
    casa = archivio.leggi()
    assert [a["nome"] for a in casa["aree"]] == ["Cucina"]
    assert casa["aree"][0]["piano_id"] == "terra"
    assert casa["aree"][0]["alias"] == ["angolo cottura"]
    assert casa["dispositivi"][0]["nome"] == "Frigorifero"   # name_by_user vince
    assert casa["entita"][0]["nome"] == "Temperatura frigo"  # original_name se name manca
    assert casa["entita"][0]["classe"] == "temperature"
    assert archivio.aggiornata_il() is not None


def test_i_registri_caduti_si_conservano_accanto_ai_dati(archivio):
    archivio.sostituisci(_REGISTRI, ["piani"])
    assert archivio.non_disponibili() == ["piani"]
    archivio.sostituisci(_REGISTRI)
    assert archivio.non_disponibili() == []   # una lettura sana li azzera


def test_la_categoria_conserva_il_proprio_ambito(archivio):
    """HA partiziona le categorie per ambito e non lo riporta nelle righe:
    lo mette leggi_registri, e l'archivio non deve perderlo."""
    archivio.sostituisci(_REGISTRI)
    assert archivio.leggi()["categorie"][0]["ambito"] == "automation"


def test_sostituisci_non_accumula(archivio):
    """E' una replica: la seconda lettura di HA rimpiazza la prima, non ci si somma."""
    archivio.sostituisci(_REGISTRI)
    ridotti = dict(_REGISTRI, aree=[{"area_id": "bagno", "name": "Bagno",
                                     "floor_id": None, "aliases": [], "labels": []}])
    archivio.sostituisci(ridotti)
    casa = archivio.leggi()
    assert [a["nome"] for a in casa["aree"]] == ["Bagno"]


def test_una_sostituzione_fallita_non_lascia_la_casa_a_meta(archivio):
    archivio.sostituisci(_REGISTRI)
    with pytest.raises(Exception):
        archivio.sostituisci(dict(_REGISTRI, entita=[{"nessun_entity_id": True}]))
    casa = archivio.leggi()
    assert [a["nome"] for a in casa["aree"]] == ["Cucina"]   # la vecchia e' intatta
    # "aree" viene riscritta prima di "entita" nell'ordine di sostituisci(): la
    # riga sopra da sola resterebbe verde anche senza rollback, perche' la
    # rottura avviene dopo che "aree" e' gia' stata ripopolata. "entita" e'
    # invece la tabella su cui la sostituzione si rompe: solo il rollback la
    # riporta al contenuto precedente, quindi e' lei a difendere davvero il test.
    assert [e["nome"] for e in casa["entita"]] == ["Temperatura frigo"]


def test_il_nome_dell_utente_vince_su_quello_dell_integrazione(archivio):
    registri = dict(_REGISTRI, entita=[dict(_REGISTRI["entita"][0], name="Il mio frigo")])
    archivio.sostituisci(registri)
    assert archivio.leggi()["entita"][0]["nome"] == "Il mio frigo"
