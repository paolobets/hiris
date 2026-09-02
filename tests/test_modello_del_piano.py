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
    assert handlers_models._STORE_DEFAULTS["ponte"]["modello"] == "sonnet"


@pytest.mark.parametrize("alias", ALIAS)
def test_i_tre_alias_passano_intatti(alias):
    assert handlers_models._clean_bridge({"modello": alias})["modello"] == alias


def test_un_archivio_senza_il_campo_riceve_il_predefinito():
    assert handlers_models._clean_bridge({})["modello"] == "sonnet"


@pytest.mark.parametrize("scritto,atteso", [
    ("claude-opus-4-7", "opus"),
    ("claude-haiku-4-5-20251001", "haiku"),
    ("OPUS", "opus"),
])
def test_un_identificatore_si_riporta_dentro_invece_di_far_fallire(scritto, atteso):
    """Come i due `_clamp_int` accanto: un valore fuori range non e' un corpo
    malformato, si riporta dentro. Il riduttore e' `modello_cli`, che qui trova
    la sua unica casa."""
    assert handlers_models._clean_bridge({"modello": scritto})["modello"] == atteso


@pytest.mark.parametrize("spazzatura", ["gpt-4o", "", None, 42, [], {"a": 1}])
def test_cio_che_non_e_un_alias_diventa_sonnet_e_non_esplode(spazzatura):
    esito = handlers_models._clean_bridge({"modello": spazzatura})["modello"]
    assert esito in ALIAS
    assert esito == "sonnet"


def test_il_campo_nuovo_non_cancella_gli_altri_tre_del_ponte():
    """`_clean_bridge` scrive l'oggetto intero: un campo aggiunto senza
    riportare gli altri li azzererebbe a ogni PUT."""
    pulito = handlers_models._clean_bridge(
        {"attivo": True, "scadenza_min": 10, "tetto_giornaliero": 150,
         "modello": "opus"})
    assert pulito == {"attivo": True, "scadenza_min": 10,
                      "tetto_giornaliero": 150, "modello": "opus"}


# ── La semina: una volta sola, con un segno proprio ────────────────────────

import inspect
import logging
import textwrap

from hiris.app import options_migration

log = logging.getLogger("prova")


def test_la_semina_copia_il_valore_derivato_oggi():
    """Il giorno dell'aggiornamento niente cambia sotto l'utente: il campo
    nuovo nasce col valore che l'installazione stava GIA' usando. Sull'impianto
    del proprietario, misurato il 15 agosto 2026: `haiku`."""
    archivio, da_salvare = options_migration.seed_subscription_model(
        {"ponte": {"attivo": True, "scadenza_min": 10,
                   "tetto_giornaliero": 150, "modello": "sonnet"}},
        "haiku", log=log)
    assert archivio["ponte"]["modello"] == "haiku"
    assert archivio["piano_seminato"] is True
    assert da_salvare is True


def test_la_semina_non_rigira_e_non_ricopre_una_scelta():
    """La guardia e' il SEGNO, non la forma del valore. Regolarsi sul valore --
    «se e' ancora il predefinito allora semina» -- farebbe ricoprire al riavvio
    la scelta di chi ha scelto proprio `sonnet`."""
    archivio, da_salvare = options_migration.seed_subscription_model(
        {"piano_seminato": True,
         "ponte": {"attivo": True, "scadenza_min": 10,
                   "tetto_giornaliero": 150, "modello": "sonnet"}},
        "opus", log=log)
    assert archivio["ponte"]["modello"] == "sonnet"
    assert da_salvare is False


def test_il_segno_si_scrive_anche_quando_il_valore_coincideva():
    """Altrimenti la semina resta una condizione che si rivaluta a ogni avvio
    invece di un evento che accade una volta."""
    archivio, da_salvare = options_migration.seed_subscription_model(
        {"ponte": {"attivo": False, "scadenza_min": 5,
                   "tetto_giornaliero": 50, "modello": "sonnet"}},
        "sonnet", log=log)
    assert archivio["piano_seminato"] is True
    assert da_salvare is True


def test_il_segno_non_viaggia_in_una_put(tmp_path):
    """Un client che rimandasse `piano_seminato: false` -- un gateway MCP con
    uno snapshot vecchio -- farebbe RIGIRARE la semina al riavvio successivo,
    ricoprendo la scelta dell'utente col valore derivato. Il segno vive fuori
    da `_OUR_KEYS`, come gli altri due."""
    d = str(tmp_path)
    handlers_models.save_models_config(
        d, {"ponte": {"attivo": True, "scadenza_min": 5,
                      "tetto_giornaliero": 50, "modello": "opus"},
            "piano_seminato": True},
        flags=True)
    handlers_models.save_models_config(
        d, {"ponte": {"attivo": True, "scadenza_min": 5,
                      "tetto_giornaliero": 50, "modello": "opus"},
            "piano_seminato": False})
    assert handlers_models.load_models_config(d)["piano_seminato"] is True


def test_il_segno_sopravvive_al_giro_load_save(tmp_path):
    d = str(tmp_path)
    handlers_models.save_models_config(d, {"piano_seminato": True}, flags=True)
    assert handlers_models.load_models_config(d)["piano_seminato"] is True


# ── Il CABLAGGIO: il blocco dell'avvio, eseguito davvero ───────────────────
#
# La suite non avvia l'app intera per provare `_on_startup` (servirebbero
# Supervisor, WebSocket di HA, MQTT). L'idioma del repo e' estrarre il blocco
# dal sorgente vero ed eseguirlo isolato: `tests/test_avvio_websocket.py`.
# Provare la FUNZIONE non dimostra che qualcuno la chiami, e un cablaggio che
# non c'e' e' esattamente il modo in cui una migrazione non avviene.


def _carica_blocco_semina():
    from hiris.app import server
    src = inspect.getsource(server._on_startup)
    start = src.index("    from .options_migration import seed_subscription_model")
    fine = 'app["models_config"] = load_models_config(data_dir)'
    end = src.index(fine, start) + len(fine)
    corpo = textwrap.dedent(src[start:end])
    func_src = ("def _check(app, data_dir, save_models_config, "
                "load_models_config, logger):\n"
                + textwrap.indent(corpo, "    "))
    # `__name__`/`__package__` del modulo vero: il blocco fa import RELATIVI
    # (`from .options_migration import ...`), e senza il pacchetto d'origine
    # non si risolvono. Prenderli da `server` invece di scriverli a mano
    # significa che il test segue il modulo se un giorno cambiasse casa.
    namespace: dict = {"__name__": server.__name__,
                       "__package__": server.__package__}
    exec(compile(func_src, "<_on_startup semina del piano>", "exec"), namespace)
    return namespace["_check"]


def _archivio_pre_fetta(tmp_path, modello_claude, modello_piano="sonnet"):
    d = str(tmp_path)
    handlers_models.save_models_config(d, {
        "provider_models": {"claude": modello_claude, "openai": "", "openrouter": ""},
        "ponte": {"attivo": True, "scadenza_min": 10,
                  "tetto_giornaliero": 150, "modello": modello_piano},
        "seminato": True, "catena_seminata": True, "chain_order": ["claude"],
    }, flags=True)
    return d


def test_l_avvio_semina_il_modello_che_l_installazione_stava_usando(tmp_path):
    """Il metro dell'aggiornamento: sull'impianto del proprietario
    `provider_models.claude` e' haiku, quindi il campo nuovo nasce `haiku` e
    NIENTE cambia sotto di lui."""
    d = _archivio_pre_fetta(tmp_path, "claude-haiku-4-5-20251001")
    app = {"models_config": handlers_models.load_models_config(d)}
    _carica_blocco_semina()(app, d, handlers_models.save_models_config,
                            handlers_models.load_models_config, log)
    assert app["models_config"]["ponte"]["modello"] == "haiku"
    assert app["models_config"]["piano_seminato"] is True
    assert handlers_models.load_models_config(d)["ponte"]["modello"] == "haiku", (
        "e finisce sul DISCO: una semina che resta in memoria rigira al riavvio")


def test_un_secondo_avvio_non_ricopre_la_scelta(tmp_path):
    """L'utente sceglie opus e cambia anche il modello di Claude API. Al
    riavvio il piano resta opus: e' l'indipendenza, provata dove serve."""
    d = _archivio_pre_fetta(tmp_path, "claude-haiku-4-5-20251001")
    blocco = _carica_blocco_semina()
    app = {"models_config": handlers_models.load_models_config(d)}
    blocco(app, d, handlers_models.save_models_config,
           handlers_models.load_models_config, log)

    archivio = handlers_models.load_models_config(d)
    archivio["ponte"]["modello"] = "opus"
    archivio["provider_models"]["claude"] = "claude-sonnet-4-6"
    handlers_models.save_models_config(d, archivio)

    app2 = {"models_config": handlers_models.load_models_config(d)}
    blocco(app2, d, handlers_models.save_models_config,
           handlers_models.load_models_config, log)
    assert app2["models_config"]["ponte"]["modello"] == "opus"
