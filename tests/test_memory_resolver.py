
import pytest

from hiris.app.memory.resolver import costruisci_indice

_HOME_SPACE = {
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
def lookup():
    return costruisci_indice(_HOME_SPACE)


def test_verifica_un_ancora_proposta_dal_modello(lookup):
    """La semantica la fa il modello: «salotto» -> area soggiorno lo risolve
    lui, che ha la casa in contesto. Qui si verifica solo che esista."""
    trovata = lookup.verify("area", "sala_pranzo")
    assert trovata["nome"] == "Sala da pranzo"


def test_un_ancora_inventata_dal_modello_non_passa(lookup):
    """Il modello propone, il codice restringe: se non esiste, non si scrive."""
    assert lookup.verify("area", "taverna") is None
    assert lookup.verify("entita", "light.inesistente") is None


def test_verifica_non_confonde_i_tipi(lookup):
    """Un identificatore di entita' passato come area non deve passare per
    somiglianza: sono spazi di nomi diversi."""
    assert lookup.verify("area", "climate.sala") is None


# -- il nome di ripiego: sull'impianto vero e' la strada normale ------------
#
# La finta deve mentire come mente la realta'. Sull'impianto misurato il 14
# agosto il `nome` del REGISTRO e' nullo quasi ovunque (le quattro valvole
# dell'irrigazione, le abat-jour) mentre il `friendly_name` dello specchio
# dello stato vivo c'e' su tutte e 849 le entita' vive. Una finta con i nomi
# del registro popolati proverebbe il caso che su quella casa NON ESISTE:
# ogni test qui sotto parte da un'entita' col nome vuoto o None.


def _casa_senza_nomi() -> dict:
    """Le abat-jour: registro con `name` e `original_name` entrambi vuoti --
    la forma esatta che home_space/store.py:133 produce su questa casa."""
    return {
        "aree": [{"id": "salotto", "nome": "Salotto", "alias": []}],
        "dispositivi": [],
        "entita": [
            {"id": "light.abat_jour_1", "nome": None, "alias": [],
             "area_id": "salotto", "piattaforma": "shelly"},
            {"id": "light.abat_jour_2", "nome": "", "alias": [],
             "area_id": "salotto", "piattaforma": "shelly"},
        ],
        "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
    }


# -- Piani ed etichette non sono candidati (review finale, M3, 30/09/2026) --
#
# Dal T7/T8 (R2, docs/design/2026-08-20-i-riferimenti.md) al 30/09/2026 l'indice
# offriva anche piani ed etichette come candidati, per la vecchia ricerca per
# nome. L'unico lettore rimasto e' `remember`, che ancora solo aree, entita' e
# dispositivi: quei candidati erano codice morto, e sono usciti.

