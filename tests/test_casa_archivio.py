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


_COMPORTAMENTO = [
    {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
     "corpo": {"trigger": [{"platform": "time", "at": "07:00"}]}, "origine": "file"},
    {"id": "automation.a_mano", "tipo": "automazione", "nome": "Scritta a mano",
     "corpo": None, "origine": "solo_stato"},
    {"id": "script.saluta", "tipo": "script", "nome": "Saluta",
     "corpo": {"sequence": []}, "origine": "file"},
]


def test_il_comportamento_si_sostituisce_e_si_rilegge(archivio):
    archivio.sostituisci_comportamento(_COMPORTAMENTO)
    voci = {v["id"]: v for v in archivio.comportamento()}
    assert voci["automation.sveglia"]["corpo"]["trigger"][0]["at"] == "07:00"
    assert voci["automation.sveglia"]["tipo"] == "automazione"


def test_un_corpo_che_non_si_puo_leggere_resta_None_non_vuoto(archivio):
    """«Non ho il corpo» e «il corpo e' vuoto» dicono due cose diverse:
    la prima e' un limite di HIRIS, la seconda un fatto sulla casa."""
    archivio.sostituisci_comportamento(_COMPORTAMENTO)
    voci = {v["id"]: v for v in archivio.comportamento()}
    assert voci["automation.a_mano"]["corpo"] is None
    assert voci["automation.a_mano"]["origine"] == "solo_stato"


def test_sostituire_il_comportamento_non_tocca_l_anagrafe(archivio):
    """Cadenze diverse, fonti diverse: un'automazione modificata non deve
    costringere a rileggere i registri, e viceversa un registro riletto non
    deve far sparire il comportamento gia' noto."""
    archivio.sostituisci(_REGISTRI)
    archivio.sostituisci_comportamento(_COMPORTAMENTO)
    assert [a["nome"] for a in archivio.leggi()["aree"]] == ["Cucina"]
    archivio.sostituisci_comportamento([])
    assert [a["nome"] for a in archivio.leggi()["aree"]] == ["Cucina"]

    # Direzione inversa: ricostruire l'anagrafe (sostituisci) non deve
    # cancellare il comportamento gia' letto dai file.
    archivio.sostituisci_comportamento(_COMPORTAMENTO)
    archivio.sostituisci(_REGISTRI)
    assert len(archivio.comportamento()) == len(_COMPORTAMENTO)


def test_il_comportamento_non_accumula(archivio):
    archivio.sostituisci_comportamento(_COMPORTAMENTO)
    archivio.sostituisci_comportamento(_COMPORTAMENTO[:1])
    assert len(archivio.comportamento()) == 1


def test_un_corpo_illeggibile_su_disco_diventa_None_non_vuoto(archivio):
    """Il ramo difensivo della rilettura, che nessun test esercitava.

    `test_un_corpo_che_non_si_puo_leggere_resta_None_non_vuoto` scrive gia'
    `corpo=None` a monte, quindi salta il json.dumps E il try/except in
    lettura: quel ramo restava scoperto, e chi domani lo cambiasse in `{}`
    passerebbe la suite verde. Qui il JSON si corrompe DOPO la scrittura, come
    farebbe un troncamento o una scrittura interrotta.
    """
    archivio.sostituisci_comportamento([
        {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
         "corpo": {"trigger": []}, "origine": "file"},
    ])
    archivio._conn.execute(
        "UPDATE comportamento SET corpo = ? WHERE id = ?",
        ("{questo non e' json", "automation.sveglia"))
    archivio._conn.commit()

    voce = archivio.comportamento()[0]
    assert voce["corpo"] is None          # non {} e non un'eccezione
    assert voce["origine"] == "file"      # il resto della voce sopravvive
