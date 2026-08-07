import re

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


def _casa_con_aree(aree: list[dict]) -> dict:
    """Una casa minima con solo le aree indicate: helper per i casi di
    ambiguita' e di confine di parola, dove non serve altro dell'anagrafe."""
    return {
        "aree": aree,
        "entita": [], "dispositivi": [],
        "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
    }


def _riferimenti(trovata: dict) -> set[str]:
    """I riferimenti di una voce trovata, ambigua o no: helper di comodo per
    i test che non devono conoscere la struttura interna di `candidati`."""
    return {c["riferimento"] for c in trovata["candidati"]}


@pytest.fixture
def indice():
    return costruisci_indice(_CASA)


def test_trova_un_area_per_nome(indice):
    trovate = indice.trova("d'inverno la sala da pranzo sta bene a 19 gradi")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert [(c["tipo"], c["riferimento"]) for c in trovate[0]["candidati"]] == [("area", "sala_pranzo")]
    assert trovate[0]["nome_visto"] == "sala da pranzo"


def test_trova_un_area_per_alias(indice):
    """Gli alias sono sinonimi DICHIARATI dall'utente in Home Assistant per
    l'assistente vocale: significato dato, non dedotto."""
    trovate = indice.trova("nel tinello fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}
    assert trovate[0]["nome_visto"] == "tinello"


def test_le_maiuscole_e_gli_accenti_non_contano(indice):
    trovate = indice.trova("LA SALA DA PRANZO")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}


def test_trova_piu_cose_in_una_frase(indice):
    trovate = indice.trova("in cucina la luce cucina resta accesa")
    assert {r for t in trovate for r in _riferimenti(t)} == {"cucina", "light.cucina"}
    assert all(t["ambiguo"] is False for t in trovate)


def test_preferisce_il_nome_piu_lungo(indice):
    """«Sala da pranzo» contiene «sala»: se vincesse il piu' corto, l'ancora
    punterebbe alla cosa sbagliata."""
    casa = dict(_CASA, aree=_CASA["aree"] + [{"id": "sala", "nome": "Sala",
                                              "alias": [], "piano_id": "terra"}])
    trovate = costruisci_indice(casa).trova("la sala da pranzo")
    assert len(trovate) == 1
    assert _riferimenti(trovate[0]) == {"sala_pranzo"}


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


def test_un_nome_con_la_punteggiatura_si_trova():
    """«Bagno (piano terra)» non veniva trovato MAI, nemmeno sul nome esatto:
    il confine di parola finale pretendeva una lettera dopo la parentesi."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    indice = costruisci_indice(casa)

    trovate = indice.trova("il bagno (piano terra) e' freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is False
    assert _riferimenti(trovate[0]) == {"bagno_terra"}

    assert indice.trova("bagno (piano terra)")


def test_due_aree_omonime_sono_ambigue_non_una_sola():
    """Due «Bagno» su piani diversi: prima vinceva il primo inserito, in
    silenzio, e l'altro era irraggiungibile."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno", "alias": []},
                           {"id": "bagno_primo", "nome": "Bagno", "alias": []}])
    trovate = costruisci_indice(casa).trova("il bagno e' sporco")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"bagno_terra", "bagno_primo"}


def test_un_alias_che_collide_col_nome_di_un_altra_area_e_ambiguo():
    """«Soggiorno» ha alias «salotto», ed esiste anche un'area «Salotto»."""
    casa = _casa_con_aree([{"id": "soggiorno", "nome": "Soggiorno", "alias": ["salotto"]},
                           {"id": "salotto_vero", "nome": "Salotto", "alias": []}])
    trovate = costruisci_indice(casa).trova("in salotto fa freddo")
    assert len(trovate) == 1
    assert trovate[0]["ambiguo"] is True
    assert _riferimenti(trovate[0]) == {"soggiorno", "salotto_vero"}


def test_cucinare_non_nomina_ancora_la_cucina():
    """Il fix del confine non deve aprire la porta ai falsi positivi."""
    casa = _casa_con_aree([{"id": "cucina", "nome": "Cucina", "alias": []}])
    assert costruisci_indice(casa).trova("mi piace cucinare la sera") == []


def test_le_espressioni_si_compilano_una_volta_sola():
    """Il costo passava da 7 a 76 ms intorno alle 300 entita', perche' la cache
    implicita di CPython ha un tetto di 512 pattern condiviso col processo."""
    casa = _casa_con_aree([{"id": "bagno_terra", "nome": "Bagno (piano terra)", "alias": []}])
    indice = costruisci_indice(casa)
    # verifica strutturale: dopo costruisci_indice le espressioni esistono
    # gia' come re.Pattern, non come stringhe da compilare a ogni trova().
    assert indice._termini
    for candidati, pattern in indice._termini:
        assert candidati
        assert isinstance(pattern, re.Pattern)
