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

from hiris.app.migrazione_opzioni import semina, semina_catena

VUOTO = {
    "chain_order": [],
    "provider_models": {"claude": "", "openai": "", "openrouter": ""},
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
    "ollama": {"modello": "", "timeout_s": 120},
    "nascondi_gratuiti": False,
    "strategia_ultima": "balanced",
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
    assert copiate == [], (
        "debito F del Task 6: `strategia_ultima` aveva predefinito \"\" mentre "
        "config.yaml e run.sh dicono \"balanced\", quindi OGNI installazione "
        "-- anche nuova -- risultava avere un valore da copiare e il ramo "
        "«erano tutti ai predefiniti» era morto in produzione"
    )
    assert fuori["strategia_ultima"] == "balanced"


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
    from hiris.app.migrazione_opzioni import semina, semina_catena

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


# ---------------------------------------------------------------------------
# La semina della CATENA (fetta «la catena e' l'unica verita'»). E' la seconda
# meta' della versione A: senza, togliere la derivazione dai cinque
# interruttori farebbe passare l'installazione del proprietario -- interruttori
# a false, credenziali presenti -- da «due provider lavorano» a «zero
# provider», e la chat morirebbe al riavvio.
# ---------------------------------------------------------------------------


def test_la_catena_si_semina_con_quella_di_oggi_non_con_l_ordine_di_strategia():
    """La catena di oggi arriva dalla vecchia regola ancora viva. Qui si COPIA,
    non si ricalcola: la lista di prova e' deliberatamente diversa dall'ordine
    di `balanced` (claude, openrouter), cosi' una semina che rigenerasse invece
    di copiare si vedrebbe."""
    a = _vuoto()
    a["seminato"] = True                      # il Task 6 e' gia' passato
    fuori, seminata = semina_catena(a, ["openrouter", "claude"], log=logging.getLogger("t"))
    assert fuori["chain_order"] == ["openrouter", "claude"]
    assert seminata is True


def test_una_catena_gia_scelta_non_si_tocca():
    a = _vuoto()
    a["chain_order"] = ["ollama"]
    fuori, seminata = semina_catena(a, ["claude", "openrouter"], log=logging.getLogger("t"))
    assert fuori["chain_order"] == ["ollama"]
    assert seminata is False


def test_seminare_una_catena_vuota_con_niente_da_copiare_non_mente_nel_log():
    reg = logging.getLogger("catena-test")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        _, seminata = semina_catena(_vuoto(), [], log=reg)
    finally:
        reg.removeHandler(h)
    assert seminata is False
    assert "copiata" not in buf.getvalue()


def test_la_semina_della_catena_si_dichiara_nel_log_con_l_ordine_vero():
    reg = logging.getLogger("catena-test-2")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        semina_catena(_vuoto(), ["openrouter", "claude"], log=reg)
    finally:
        reg.removeHandler(h)
    testo = buf.getvalue()
    assert "openrouter -> claude" in testo, (
        "una catena copiata senza essere nominata non e' dichiarata: "
        "l'operatore non puo' verificare che sia quella che stava usando"
    )


def test_la_catena_non_si_semina_guardando_seminato():
    """`seminato` e' il segno della semina delle OPZIONI (Task 6). L'archivio
    che questo rilascio trova sull'impianto del proprietario e' seminato E ha
    la catena vuota: legare le due cose lascerebbe quella catena vuota per
    sempre, cioe' zero provider."""
    a = _vuoto()
    a["seminato"] = True
    _, seminata = semina_catena(a, ["claude"], log=logging.getLogger("t"))
    assert seminata is True


# ---------------------------------------------------------------------------
# La semina della CATENA, cablata nell'avvio. Stessa tecnica del blocco qui
# sopra, e per la stessa ragione: `_on_startup` non e' eseguibile nei test
# (ogni fixture fa `app.on_startup.clear()`), quindi si ESTRAE il blocco dal
# sorgente vero e lo si esegue isolato.
#
# Il brief del Task 7 proponeva di verificare questo cablaggio con
# `pytest tests/test_api.py`, «che costruisce l'app vera». Non lo verifica:
# quella fixture azzera `on_startup`, quindi il blocco non gira mai e il test
# passerebbe anche se il blocco non esistesse. Sesto test-che-non-puo-fallire
# di questa fetta, e il piu' pericoloso, perche' cio' che protegge e' la sola
# cosa che impedisce alla chat del proprietario di morire al riavvio.
#
# La finta e' scomoda: il disco e' vero (tmp_path), l'ambiente NON eredita
# quello del processo, e le funzioni di archivio sono quelle di produzione.
# ---------------------------------------------------------------------------


def _blocco_semina_catena_dallo_startup(ambiente_finto):
    import inspect
    import textwrap

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index("    from .migrazione_opzioni import semina_catena")
    marker = 'app["models_config"] = load_models_config(data_dir)'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    # `_nome_modello_com_era` e non `local_model_name` dal Task 9: e' l'UNICO
    # uso rimasto di `LOCAL_MODEL_NAME` in server.py, e il nome dice a cosa
    # serve -- ricostruire la CREDENZIALE COM'ERA, dove il modello contava
    # insieme all'indirizzo. Il modello che il runner usa arriva dall'archivio.
    firma = ("def _avvio(app, os, logger, data_dir, _credenziali, "
             "local_model_url, _nome_modello_com_era):\n")
    func_src = firma + textwrap.indent(corpo, "    ")
    # `env_bool` legge `os.environ` DENTRO env_util.py, quindi l'`os` finto
    # passato al blocco non la raggiunge: se si lasciasse quella vera, i cinque
    # interruttori arriverebbero dall'ambiente del processo di test e il caso
    # «un interruttore acceso» non sarebbe esprimibile. Si sostituisce con una
    # che legge lo STESSO dizionario finto e con le STESSE regole di verita'
    # (`_TRUTHY` di env_util, non un `== "true"` scritto qui: una finta piu'
    # permissiva o piu' severa della realta' proverebbe un'altra cosa).
    from hiris.app.env_util import _TRUTHY

    def _env_bool_finta(nome, default=False):
        raw = ambiente_finto.environ.get(nome)
        if raw is None or raw.strip() == "":
            return default
        return raw.strip().lower() in _TRUTHY

    namespace: dict = {
        "__package__": "hiris.app",
        "__name__": "hiris.app.server",
        "_catena_com_era": server._catena_com_era,
        "env_bool": _env_bool_finta,
    }
    from hiris.app.api.handlers_models import load_models_config, save_models_config
    namespace["load_models_config"] = load_models_config
    namespace["save_models_config"] = save_models_config
    exec(compile(func_src, "<_on_startup semina_catena>", "exec"), namespace)
    return namespace["_avvio"]


def _avvia_la_semina_della_catena(tmp_path, ambiente, credenziali,
                                  local_model_url="", local_model_name=""):
    import logging

    from hiris.app.api.handlers_models import load_models_config

    ambiente_finto = _AmbienteFinto(ambiente)
    avvio = _blocco_semina_catena_dallo_startup(ambiente_finto)
    app = {"models_config": load_models_config(str(tmp_path))}
    avvio(app, ambiente_finto, logging.getLogger("t"), str(tmp_path),
          credenziali, local_model_url, local_model_name)
    return app


CREDENZIALI_DEL_PROPRIETARIO = {
    "subscription": True,    # token del piano presente
    "claude": True,          # chiave API presente (a credito zero, ma presente)
    "openai": False,
    "openrouter": True,
    "ollama": False,
}


def test_l_impianto_del_proprietario_non_passa_da_due_provider_a_zero(tmp_path):
    """Il caso vero, e l'unico che esista al mondo: cinque interruttori a
    false, credenziali presenti. Con la vecchia regola `legacy` lavoravano
    Claude API e OpenRouter mentre la pagina li mostrava spenti. Se la catena
    non venisse seminata PRIMA che quella regola sparisca, al riavvio HIRIS
    resterebbe con zero provider e la chat morirebbe."""
    app = _avvia_la_semina_della_catena(
        tmp_path,
        {"LLM_STRATEGY": "balanced"},          # nessun PROVIDER_* acceso
        CREDENZIALI_DEL_PROPRIETARIO,
    )
    assert app["models_config"]["chain_order"] == ["claude", "openrouter"]


def test_la_catena_seminata_finisce_sul_disco_non_solo_in_memoria(tmp_path):
    import json

    _avvia_la_semina_della_catena(
        tmp_path, {"LLM_STRATEGY": "balanced"}, CREDENZIALI_DEL_PROPRIETARIO)
    disco = json.loads((tmp_path / "models_config.json").read_text(encoding="utf-8"))
    assert disco["chain_order"] == ["claude", "openrouter"], (
        "senza il save, il prossimo avvio ricomincerebbe da capo -- e dopo la "
        "versione B l'ambiente sara' muto, quindi non ricomincerebbe affatto"
    )


def test_la_strategia_scelta_decide_l_ordine_copiato(tmp_path):
    """La catena copiata e' quella che HIRIS STAVA usando, non un ordine
    canonico: chi aveva `cost_first` deve ritrovarsi il suo ordine."""
    app = _avvia_la_semina_della_catena(
        tmp_path, {"LLM_STRATEGY": "cost_first"}, CREDENZIALI_DEL_PROPRIETARIO)
    assert app["models_config"]["chain_order"] == ["openrouter", "claude"]


def test_con_gli_interruttori_accesi_vale_quello_che_dicono_loro(tmp_path):
    """L'altro ramo della vecchia regola: acceso almeno un interruttore, la
    compatibilita' cadeva e contavano solo gli accesi. Chi era in quello stato
    deve ritrovare la SUA catena, non quella di chi non aveva toccato niente."""
    app = _avvia_la_semina_della_catena(
        tmp_path,
        {"LLM_STRATEGY": "balanced", "PROVIDER_OPENROUTER": "true"},
        CREDENZIALI_DEL_PROPRIETARIO,
    )
    assert app["models_config"]["chain_order"] == ["openrouter"]


def test_il_piano_non_entra_mai_in_chain_order(tmp_path):
    """Il piano non e' un membro della catena: sta in testa quando il ponte e'
    acceso, e questo lo dice `ponte.attivo`, non l'appartenenza."""
    app = _avvia_la_semina_della_catena(
        tmp_path,
        {"LLM_STRATEGY": "balanced", "BRIDGE_ENABLED": "true"},
        CREDENZIALI_DEL_PROPRIETARIO,
    )
    assert "subscription" not in app["models_config"]["chain_order"]


def test_ollama_senza_modello_non_entra_in_catena_per_migrazione(tmp_path):
    """La credenziale di Ollama e' cambiata in questa fetta (era `url AND
    model`, adesso e' il solo `url`). La MIGRAZIONE deve usare quella vecchia:
    con la nuova, un'installazione con l'indirizzo e senza modello si
    ritroverebbe Ollama in catena senza esserci mai stato -- cioe' la
    migrazione inventerebbe invece di copiare, e in catena finirebbe un
    provider per cui il runner non viene nemmeno costruito."""
    app = _avvia_la_semina_della_catena(
        tmp_path,
        {"LLM_STRATEGY": "cost_first"},
        {**CREDENZIALI_DEL_PROPRIETARIO, "ollama": True},
        local_model_url="http://ollama.local:11434",
        local_model_name="",
    )
    assert "ollama" not in app["models_config"]["chain_order"]


def test_una_catena_gia_scelta_sopravvive_all_avvio(tmp_path):
    from hiris.app.api.handlers_models import save_models_config

    save_models_config(str(tmp_path), {"chain_order": ["ollama"]})
    app = _avvia_la_semina_della_catena(
        tmp_path, {"LLM_STRATEGY": "balanced"}, CREDENZIALI_DEL_PROPRIETARIO)
    assert app["models_config"]["chain_order"] == ["ollama"]
