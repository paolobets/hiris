"""Il modello del Piano Claude Max e' un valore SUO.

Fino alla 3.1.0 era un effetto collaterale del modello di Claude API:
`handlers_chat._enqueue_chat_job` componeva
`modello_cli(resolve_model("auto", "chat", provider_models["claude"]))`, e la
riga del piano nella pagina Modelli mostrava tre radio spenti. Un campo solo
serviva due economie opposte -- a consumo si sceglie il modello frugale, nel
piano il modello non costa di piu' -- e l'impianto del proprietario, misurato
il 15 agosto 2026, girava sul piano con `haiku`.
"""
import pytest

from hiris.app.api import handlers_models

ALIAS = ("haiku", "sonnet", "opus")


def test_il_predefinito_del_campo_non_e_mai_vuoto():
    """Vuoto significherebbe «non so», e «non so» e' la porta da cui la regola
    «se non so niente allora fai come prima» e' gia' rientrata quattro volte."""
    assert handlers_models._PREDEFINITI_ARCHIVIO["ponte"]["modello"] == "sonnet"


@pytest.mark.parametrize("alias", ALIAS)
def test_i_tre_alias_passano_intatti(alias):
    assert handlers_models._pulisci_ponte({"modello": alias})["modello"] == alias


def test_un_archivio_senza_il_campo_riceve_il_predefinito():
    assert handlers_models._pulisci_ponte({})["modello"] == "sonnet"


@pytest.mark.parametrize("scritto,atteso", [
    ("claude-opus-4-7", "opus"),
    ("claude-haiku-4-5-20251001", "haiku"),
    ("OPUS", "opus"),
])
def test_un_identificatore_si_riporta_dentro_invece_di_far_fallire(scritto, atteso):
    """Come i due `_clamp_int` accanto: un valore fuori range non e' un corpo
    malformato, si riporta dentro. Il riduttore e' `modello_cli`, che qui trova
    la sua unica casa."""
    assert handlers_models._pulisci_ponte({"modello": scritto})["modello"] == atteso


@pytest.mark.parametrize("spazzatura", ["gpt-4o", "", None, 42, [], {"a": 1}])
def test_cio_che_non_e_un_alias_diventa_sonnet_e_non_esplode(spazzatura):
    esito = handlers_models._pulisci_ponte({"modello": spazzatura})["modello"]
    assert esito in ALIAS
    assert esito == "sonnet"


def test_il_campo_nuovo_non_cancella_gli_altri_tre_del_ponte():
    """`_pulisci_ponte` scrive l'oggetto intero: un campo aggiunto senza
    riportare gli altri li azzererebbe a ogni PUT."""
    pulito = handlers_models._pulisci_ponte(
        {"attivo": True, "scadenza_min": 10, "tetto_giornaliero": 150,
         "modello": "opus"})
    assert pulito == {"attivo": True, "scadenza_min": 10,
                      "tetto_giornaliero": 150, "modello": "opus"}
