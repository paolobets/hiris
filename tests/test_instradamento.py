"""Chi risponde a questo turno: una domanda, una casa.

Fino al 22 agosto 2026 la regola viveva dentro `handle_chat`, intrecciata con
la persistenza del turno e con la coda -- e il turno di una promessa, che
quella funzione non la attraversa, ne aveva per forza una seconda: andava
dritto a `llm_router`, dove il ponte non e' nemmeno un anello.

Non era una svista, era la struttura a imporlo. Visto dal vivo il 21/08 su una
casa che gira INTERAMENTE sul Piano Claude Max: chat perfetta, promesse tutte
fallite su due chiavi API esaurite, e l'abbonamento sano li' accanto che le
promesse non potevano usare.

La distinzione che questi test tengono ferma e' fra le due ragioni per cui si
scende alla catena:

  - il ponte NON E' IN GIOCO (spento, o non cablato) -- non c'e' nessun
    ripiego da dichiarare, e' la configurazione. Motivo vuoto.
  - il ponte c'e' ma NON PUO' rispondere -- quello e' un ripiego vero, dal
    forfait al consumo, e si dichiara. Il motivo e' una CHIAVE di
    `decisione_modelli._MOTIVI_RIPIEGO`, non una frase: la frase la compone
    `nota_ripiego`, e un motivo fuori vocabolario non produce un errore,
    produce SILENZIO -- cioe' un prelievo non annunciato.
"""
import pytest

from hiris.app.decisione_modelli import _MOTIVI_RIPIEGO, VARIABILE_TOKEN_DEL_PIANO
from hiris.app.instradamento import chi_risponde


class _CodaFinta:
    """La coda vera vista da `chi_risponde`: sa contare i turni di oggi."""

    def __init__(self, oggi: int = 0) -> None:
        self._oggi = oggi

    def count_turni_oggi(self, now=None) -> int:
        return self._oggi


def _app(*, ponte=True, coda=None, tetto=150):
    return {
        "ponte_attivo": ponte,
        "reasoning_queue": coda if coda is not None else _CodaFinta(),
        "models_config": {"ponte": {"tetto_giornaliero": tetto}},
    }


@pytest.fixture
def col_token(monkeypatch):
    # La costante, non il nome scritto a mano: se qualcuno rinomina la
    # variabile del token questi test devono seguirlo, non passare a vuoto.
    monkeypatch.setenv(VARIABILE_TOKEN_DEL_PIANO, "un-token-qualunque")


@pytest.fixture
def senza_token(monkeypatch):
    monkeypatch.delenv(VARIABILE_TOKEN_DEL_PIANO, raising=False)


def test_col_ponte_acceso_e_il_piano_capace_risponde_il_ponte(col_token):
    assert chi_risponde(_app()) == ("ponte", "")


def test_col_ponte_spento_si_scende_alla_catena_SENZA_dichiarare_un_ripiego(col_token):
    """Non e' un ripiego: e' la configurazione. Annunciarlo a ogni turno
    direbbe all'utente che sta perdendo qualcosa che non ha mai avuto."""
    via, motivo = chi_risponde(_app(ponte=False))
    assert via == "catena"
    assert motivo == ""


def test_senza_la_coda_cablata_si_scende_alla_catena_senza_ripiego(col_token):
    app = _app()
    del app["reasoning_queue"]
    assert chi_risponde(app) == ("catena", "")


def test_senza_il_token_del_piano_e_un_ripiego_e_si_dichiara(senza_token):
    via, motivo = chi_risponde(_app())
    assert via == "catena"
    assert motivo == "manca il token"
    assert motivo in _MOTIVI_RIPIEGO, (
        "un motivo fuori vocabolario non produce un errore: produce silenzio, "
        "cioe' un passaggio dal forfait al consumo che nessuno annuncia")


def test_a_tetto_pieno_e_un_ripiego_e_si_dichiara(col_token):
    via, motivo = chi_risponde(_app(coda=_CodaFinta(oggi=150)))
    assert via == "catena"
    assert motivo == "tetto giornaliero"
    assert motivo in _MOTIVI_RIPIEGO


def test_sotto_il_tetto_di_uno_il_ponte_risponde_ancora(col_token):
    assert chi_risponde(_app(coda=_CodaFinta(oggi=149))) == ("ponte", "")
