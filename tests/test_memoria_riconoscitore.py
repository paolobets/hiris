import pytest

from hiris.app.memoria.riconoscitore import costruisci_indice

_CASA = {
    "aree": [
        {"id": "sala_pranzo", "nome": "Sala da pranzo", "alias": ["tinello"], "piano_id": "terra"},
        {"id": "cucina", "nome": "Cucina", "alias": [], "piano_id": "terra"},
    ],
    "entita": [
        {"id": "climate.sala", "nome": "Termostato sala da pranzo", "alias": ["caldaia"],
         "area_id": "sala_pranzo", "classe": "temperature", "unita": "°C"},
        {"id": "light.cucina", "nome": "Luce cucina", "alias": [], "area_id": "cucina",
         "classe": None, "unita": None},
    ],
    "dispositivi": [{"id": "d1", "nome": "Frigorifero", "area_id": "cucina"}],
    "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
}


@pytest.fixture
def indice():
    return costruisci_indice(_CASA)


def test_trova_un_area_per_nome(indice):
    trovate = indice.trova("d'inverno la sala da pranzo sta bene a 19 gradi")
    assert [(t["tipo"], t["riferimento"]) for t in trovate] == [("area", "sala_pranzo")]
    assert trovate[0]["nome_visto"] == "sala da pranzo"


def test_trova_un_area_per_alias(indice):
    """Gli alias sono sinonimi DICHIARATI dall'utente in Home Assistant per
    l'assistente vocale: significato dato, non dedotto."""
    trovate = indice.trova("nel tinello fa freddo")
    assert [t["riferimento"] for t in trovate] == ["sala_pranzo"]
    assert trovate[0]["nome_visto"] == "tinello"


def test_le_maiuscole_e_gli_accenti_non_contano(indice):
    assert [t["riferimento"] for t in indice.trova("LA SALA DA PRANZO")] == ["sala_pranzo"]


def test_trova_piu_cose_in_una_frase(indice):
    trovate = indice.trova("in cucina la luce cucina resta accesa")
    assert {t["riferimento"] for t in trovate} == {"cucina", "light.cucina"}


def test_preferisce_il_nome_piu_lungo(indice):
    """«Sala da pranzo» contiene «sala»: se vincesse il piu' corto, l'ancora
    punterebbe alla cosa sbagliata."""
    casa = dict(_CASA, aree=_CASA["aree"] + [{"id": "sala", "nome": "Sala",
                                              "alias": [], "piano_id": "terra"}])
    trovate = costruisci_indice(casa).trova("la sala da pranzo")
    assert [t["riferimento"] for t in trovate] == ["sala_pranzo"]


def test_una_parola_dentro_un_altra_non_conta(indice):
    """«cucinare» non nomina la cucina."""
    assert indice.trova("mi piace cucinare la sera") == []


def test_niente_di_riconosciuto_non_e_un_errore(indice):
    assert indice.trova("domani piove") == []


def test_una_casa_vuota_non_esplode():
    vuota = {chiave: [] for chiave in _CASA}
    assert costruisci_indice(vuota).trova("la sala da pranzo") == []


def test_verifica_un_ancora_proposta_dal_modello(indice):
    """La semantica la fa il modello: «salotto» -> area soggiorno lo risolve
    lui, che ha la casa in contesto. Qui si verifica solo che esista."""
    trovata = indice.verifica("area", "sala_pranzo")
    assert trovata["nome"] == "Sala da pranzo"


def test_un_ancora_inventata_dal_modello_non_passa(indice):
    """Il modello propone, il codice restringe: se non esiste, non si scrive."""
    assert indice.verifica("area", "taverna") is None
    assert indice.verifica("entita", "light.inesistente") is None


def test_verifica_non_confonde_i_tipi(indice):
    """Un identificatore di entita' passato come area non deve passare per
    somiglianza: sono spazi di nomi diversi."""
    assert indice.verifica("area", "climate.sala") is None
