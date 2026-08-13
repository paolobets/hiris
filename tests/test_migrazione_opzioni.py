"""Versione A della migrazione: HIRIS legge dal proprio archivio e, se e' vuoto,
copia il valore dall'opzione dell'add-on -- dichiarandolo nel log.

Perche' serve: togliere un'opzione dallo schema significa che il Supervisor la
scarta. `AddonOptions.__call__` elimina ogni chiave fuori schema PRIMA che
/data/options.json esista, quindi nessuna migrazione lato add-on e' possibile e
nessun ripiego in `run.sh` puo' funzionare -- `bashio::config 'vecchia_chiave'`
tornerebbe vuoto comunque. `llm_strategy`, il ponte e il modello di Ollama
hanno valori dell'utente che sparirebbero IN SILENZIO.

Un avvio con questa versione, e i valori sono al sicuro. Solo dopo, la B.
"""
import io
import logging

from hiris.app.migrazione_opzioni import semina

VUOTO = {
    "chain_order": [],
    "provider_models": {"claude": "", "openai": "", "openrouter": ""},
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
    "ollama": {"modello": "", "timeout_s": 120},
    "nascondi_gratuiti": False,
    "strategia_ultima": "",
    "seminato": False,
}

AMBIENTE = {
    "BRIDGE_ENABLED": "true",
    "BRIDGE_DEADLINE_MIN": "20",
    "CHAT_DAILY_CAP": "200",
    "LOCAL_MODEL_NAME": "llama3.1:8b",
    "OLLAMA_REQUEST_TIMEOUT": "300",
    "HIRIS_HIDE_FREE_MODELS": "true",
    "LLM_STRATEGY": "cost_first",
}


def _vuoto() -> dict:
    import copy
    return copy.deepcopy(VUOTO)


def test_al_primo_avvio_i_valori_dell_utente_entrano_nell_archivio():
    fuori, copiate = semina(_vuoto(), AMBIENTE, log=logging.getLogger("t"))
    assert fuori["ponte"] == {"attivo": True, "scadenza_min": 20, "tetto_giornaliero": 200}
    assert fuori["ollama"] == {"modello": "llama3.1:8b", "timeout_s": 300}
    assert fuori["nascondi_gratuiti"] is True
    assert fuori["strategia_ultima"] == "cost_first"
    assert fuori["seminato"] is True
    assert set(copiate) == {"ponte", "ollama", "nascondi_gratuiti", "strategia_ultima"}


def test_la_copia_si_dichiara_nel_log_e_nomina_i_valori():
    reg = logging.getLogger("semina-test")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        semina(_vuoto(), AMBIENTE, log=reg)
    finally:
        reg.removeHandler(h)
    testo = buf.getvalue()
    assert "opzioni dell'add-on" in testo
    assert "llama3.1:8b" in testo, "un valore copiato senza essere nominato non e' dichiarato"


def test_la_semina_avviene_UNA_volta_sola():
    """La seconda volta l'archivio e' la verita', anche se l'ambiente dice altro.
    Senza questo, ogni riavvio riscriverebbe sopra la scelta fatta dalla pagina
    Modelli -- cioe' l'opzione dell'add-on continuerebbe a vincere, e la
    migrazione non finirebbe mai."""
    primo, _ = semina(_vuoto(), AMBIENTE, log=logging.getLogger("t"))
    primo["ponte"]["scadenza_min"] = 3          # l'utente ha scelto 3 dalla pagina
    secondo, copiate = semina(primo, AMBIENTE, log=logging.getLogger("t"))
    assert secondo["ponte"]["scadenza_min"] == 3
    assert copiate == []


def test_un_ambiente_vuoto_lascia_i_predefiniti_e_semina_lo_stesso():
    """Chi installa HIRIS oggi non ha niente da salvare: la semina segna
    comunque `seminato`, cosi' il primo avvio dopo la versione B non ricomincia
    a cercare opzioni che non esistono piu'."""
    fuori, copiate = semina(_vuoto(), {}, log=logging.getLogger("t"))
    assert fuori["seminato"] is True
    assert fuori["ponte"]["scadenza_min"] == 5
    assert copiate == []


def test_un_valore_non_numerico_non_fa_saltare_l_avvio():
    """`run.sh` esporta stringhe, e `bashio::config` su un campo vuoto torna "".
    Un ValueError qui fermerebbe l'add-on all'avvio per un'opzione che l'utente
    non ha nemmeno toccato."""
    fuori, _ = semina(_vuoto(), {"BRIDGE_DEADLINE_MIN": "", "CHAT_DAILY_CAP": "boh"},
                      log=logging.getLogger("t"))
    assert fuori["ponte"]["scadenza_min"] == 5
    assert fuori["ponte"]["tetto_giornaliero"] == 50


def test_la_semina_finisce_sul_disco_non_solo_in_memoria(tmp_path):
    import json
    import logging
    from hiris.app.api.handlers_models import load_models_config, save_models_config
    from hiris.app.migrazione_opzioni import semina

    archivio, _ = semina(load_models_config(str(tmp_path)),
                         {"BRIDGE_DEADLINE_MIN": "20"}, log=logging.getLogger("t"))
    save_models_config(str(tmp_path), archivio)
    disco = json.loads((tmp_path / "models_config.json").read_text(encoding="utf-8"))
    assert disco["seminato"] is True
    assert disco["ponte"]["scadenza_min"] == 20


# ---------------------------------------------------------------------------
# Il test qui sopra prova la COMPOSIZIONE (semina + save + load), non il
# cablaggio dell'avvio: eseguito da solo, sopravvive a un `server.py` che si
# dimentica di persistere. `_on_startup` non e' pinnabile per intero (ogni
# fixture fa `app.on_startup.clear()` -- e' il debito E dichiarato al Task 1),
# quindi si usa la tecnica gia' in casa: si ESTRAE il blocco dal sorgente vero
# e lo si esegue isolato (`tests/test_avvio_websocket.py`,
# `tests/test_chat_subscription_path.py`).
#
# La finta e' scomoda apposta: il disco e' vero (tmp_path) e le funzioni di
# archivio sono quelle di produzione, cosi' lo stato SOPRAVVIVE fra due avvii.
# Una finta che tenesse l'archivio in memoria non potrebbe dimostrare ne' il
# primo popolamento ne' il fatto che la copia avvenga una volta sola -- che e'
# tutto cio' che questo task deve dimostrare.
# ---------------------------------------------------------------------------


def _blocco_semina_dallo_startup():
    import inspect
    import textwrap

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index("    from .api.handlers_models import load_models_config")
    fine_marker = 'app["models_config"] = load_models_config(data_dir)'
    end = src.index(fine_marker, start) + len(fine_marker)
    corpo = textwrap.dedent(src[start:end])
    func_src = "def _avvio(data_dir, app, os, logger):\n" + textwrap.indent(corpo, "    ")
    namespace: dict = {"__package__": "hiris.app", "__name__": "hiris.app.server"}
    exec(compile(func_src, "<_on_startup semina>", "exec"), namespace)
    return namespace["_avvio"]


class _AmbienteFinto:
    """`os` finto con il SOLO `environ` che serve. Scomodo apposta: non eredita
    l'ambiente del processo di test, cosi' un'opzione che il blocco non legge
    non puo' arrivare all'archivio per caso."""

    def __init__(self, environ: dict):
        self.environ = environ


def test_l_avvio_persiste_la_semina_sul_disco(tmp_path):
    import json
    import logging

    avvio = _blocco_semina_dallo_startup()
    app: dict = {}
    avvio(str(tmp_path), app, _AmbienteFinto({"BRIDGE_DEADLINE_MIN": "20"}),
          logging.getLogger("t"))

    disco = json.loads((tmp_path / "models_config.json").read_text(encoding="utf-8"))
    assert disco["seminato"] is True, \
        "senza il save dopo la semina, il prossimo avvio ricomincerebbe da capo"
    assert disco["ponte"]["scadenza_min"] == 20
    assert app["models_config"]["ponte"]["scadenza_min"] == 20


def test_il_secondo_avvio_non_riscrive_sopra_la_scelta_della_pagina(tmp_path):
    """Due avvii veri, con lo stesso ambiente e lo stesso disco in mezzo. Fra i
    due, l'utente cambia il valore dalla pagina Modelli: il secondo avvio deve
    trovarlo intatto, altrimenti l'opzione dell'add-on continua a vincere e la
    migrazione non finisce mai."""
    import logging

    from hiris.app.api.handlers_models import save_models_config

    avvio = _blocco_semina_dallo_startup()
    ambiente = _AmbienteFinto({"BRIDGE_DEADLINE_MIN": "20", "LOCAL_MODEL_NAME": "llama3.1:8b"})

    primo: dict = {}
    avvio(str(tmp_path), primo, ambiente, logging.getLogger("t"))
    assert primo["models_config"]["ponte"]["scadenza_min"] == 20

    save_models_config(str(tmp_path), {"ponte": {"attivo": False, "scadenza_min": 3,
                                                 "tetto_giornaliero": 50}})

    secondo: dict = {}
    avvio(str(tmp_path), secondo, ambiente, logging.getLogger("t"))
    assert secondo["models_config"]["ponte"]["scadenza_min"] == 3
    assert secondo["models_config"]["ollama"]["modello"] == "llama3.1:8b"
