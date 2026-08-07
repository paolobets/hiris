import pytest

from hiris.app.memoria.interpretazione import VOCABOLARIO, valida
from hiris.app.memoria.riconoscitore import costruisci_indice

_CASA = {
    "aree": [{"id": "sala_pranzo", "nome": "Sala da pranzo", "alias": [], "piano_id": None}],
    "entita": [{"id": "climate.sala", "nome": "Termostato", "alias": [],
                "area_id": "sala_pranzo", "classe": "temperature", "unita": "°C"}],
    "dispositivi": [], "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
}


@pytest.fixture
def indice():
    return costruisci_indice(_CASA)


def test_una_interpretazione_buona_passa_intera(indice):
    proposta = {
        "forza": "preferenza", "grandezza": "temperature",
        "minimo": 19, "massimo": 20,
        "ancore": [{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala da pranzo"}],
        "condizioni": [{"tipo": "stagione", "valore": "inverno"}],
    }
    pulita, problemi, _correzioni = valida(proposta, indice)
    assert problemi == []
    assert pulita["forza"] == "preferenza"
    assert pulita["unita"] == "°C"          # dedotta dall'entita' dell'area, non inventata


def test_una_forza_inventata_si_scarta_e_si_dichiara(indice):
    pulita, problemi, _correzioni = valida({"forza": "suggerimento"}, indice)
    assert pulita["forza"] is None
    assert any("suggerimento" in p for p in problemi)


def test_una_condizione_fuori_vocabolario_si_scarta(indice):
    pulita, problemi, _correzioni = valida(
        {"condizioni": [{"tipo": "umore", "valore": "buono"},
                        {"tipo": "presenza", "valore": "casa"}]}, indice)
    assert [c["tipo"] for c in pulita["condizioni"]] == ["presenza"]
    assert any("umore" in p for p in problemi)


def test_un_ancora_che_non_esiste_non_si_scrive(indice):
    """Regola non negoziabile: se «taverna» non esiste nell'anagrafe, l'ancora
    non si scrive. Meglio un ricordo che resta testo di uno che punta al nulla."""
    pulita, problemi, _correzioni = valida(
        {"ancore": [{"tipo": "area", "riferimento": "taverna", "nome_visto": "taverna"}]}, indice)
    assert pulita["ancore"] == []
    assert any("taverna" in p for p in problemi)


def test_una_interpretazione_vuota_e_legittima(indice):
    """Regola 3: parziale e opzionale. «Mi piace il caffe'» non ha ne' ancore
    ne' condizioni, e non e' un errore."""
    pulita, problemi, _correzioni = valida({}, indice)
    assert problemi == []
    assert pulita["ancore"] == [] and pulita["condizioni"] == []


def test_un_intervallo_rovesciato_si_raddrizza(indice):
    """Un intervallo raddrizzato e' una CORREZIONE, non un problema: il dato
    c'e' ed e' stato riparato. Metterlo fra i problemi faceva rifiutare
    l'intera richiesta -- e per giunta solo quando se ne correggeva meta',
    mentre lo stesso intervallo mandato intero veniva accettato."""
    pulita, problemi, correzioni = valida({"minimo": 20, "massimo": 19}, indice)
    assert (pulita["minimo"], pulita["massimo"]) == (19.0, 20.0)
    assert problemi == []
    assert correzioni


def test_una_condizione_senza_valore_si_scarta_e_si_dichiara(indice):
    """`condizioni.valore` e' `NOT NULL` in archivio (memoria/archivio.py):
    una condizione senza valore che superasse il cancello spaccherebbe la
    scrittura con un IntegrityError invece di essere scartata qui, dove il
    problema si puo' ancora dichiarare a chi legge."""
    pulita, problemi, _correzioni = valida({"condizioni": [{"tipo": "ora"}]}, indice)
    assert pulita["condizioni"] == []
    assert any("ora" in p and "valore" in p for p in problemi)


def test_un_ancora_non_verificabile_si_scarta_con_la_ragione_vera(indice):
    """Quando il tipo dell'ancora e' fra quelli che non si possono
    controllare (anagrafe non letta, o quel registro non ha risposto), il
    problema deve dire "non si puo' verificare", non "non esiste" -- sono
    due fatti diversi, e il secondo e' falso quando non si e' potuto
    nemmeno guardare."""
    pulita, problemi, _correzioni = valida(
        {"ancore": [{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}]},
        indice, frozenset({"area"}))
    assert pulita["ancore"] == []
    assert any("non si puo' verificare" in p for p in problemi)
    assert not any("non esiste nell'anagrafe" in p for p in problemi)


def test_il_vocabolario_e_chiuso():
    """Se domani qualcuno aggiunge una casella, questo test lo fa sapere:
    un vocabolario che cresce in silenzio smette di essere compilabile bene."""
    assert set(VOCABOLARIO) == {"forza", "condizioni", "ancore"}
    assert set(VOCABOLARIO["forza"]) == {"preferenza", "divieto", "fatto", "regola"}
    assert set(VOCABOLARIO["condizioni"]) == {"ora", "giorno", "presenza",
                                              "sole", "meteo", "stagione"}
    assert set(VOCABOLARIO["ancore"]) == {"area", "entita", "dispositivo"}
