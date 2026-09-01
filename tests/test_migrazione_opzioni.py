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

from hiris.app.migrazione_opzioni import seed, seed_chain

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
    fuori, copiate = seed(_vuoto(), AMBIENTE, log=logging.getLogger("t"))
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
        seed(_vuoto(), AMBIENTE, log=reg)
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
    primo, _ = seed(_vuoto(), AMBIENTE, log=logging.getLogger("t"))
    primo["ponte"]["scadenza_min"] = 3          # l'utente ha scelto 3 dalla pagina
    secondo, copiate = seed(primo, AMBIENTE, log=logging.getLogger("t"))
    assert secondo["ponte"]["scadenza_min"] == 3
    assert copiate == []


def test_un_ambiente_vuoto_lascia_i_predefiniti_e_semina_lo_stesso():
    """Chi installa HIRIS oggi non ha niente da salvare: la semina segna
    comunque `seminato`, cosi' il primo avvio dopo la versione B non ricomincia
    a cercare opzioni che non esistono piu'."""
    fuori, copiate = seed(_vuoto(), {}, log=logging.getLogger("t"))
    assert fuori["seminato"] is True
    assert fuori["ponte"]["scadenza_min"] == 5
    assert copiate == [], (
        "debito F del Task 6: `strategia_ultima` aveva predefinito \"\" mentre "
        "config.yaml e run.sh dicono \"balanced\", quindi OGNI installazione "
        "-- anche nuova -- risultava avere un valore da copiare e il ramo "
        "«erano tutti ai predefiniti» era morto in produzione"
    )
    assert fuori["strategia_ultima"] == "balanced"


def test_un_ambiente_muto_non_afferma_che_i_valori_erano_ai_predefiniti():
    """**C2 della revisione del commit 3.0.0.** «Erano tutti ai predefiniti» e'
    un'affermazione sui valori dell'utente, e con l'ambiente muto nessun valore
    dell'utente e' stato letto. Dalla versione B e' la condizione NORMALE (via
    Supervisor l'unica possibile), non l'eccezione.

    E la stessa riga compariva nel caso peggiore: archivio troncato, `seminato`
    tornato a falso, dodici decisioni riscritte dai predefiniti -- e questa
    riga, insieme a quella della catena, era l'unica cosa che l'utente
    leggeva."""
    reg = logging.getLogger("muto")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        seed(_vuoto(), {}, log=reg)
    finally:
        reg.removeHandler(h)
    testo = buf.getvalue()
    assert "erano tutti ai predefiniti" not in testo, (
        "afferma di aver guardato dei valori che non ha potuto leggere"
    )
    assert "nessuna opzione dell'add-on da copiare" in testo, (
        "e il silenzio totale non va bene neanche lui: chi legge il registro "
        "deve sapere PERCHE' non e' stato copiato niente"
    )


def test_un_ambiente_popolato_ai_predefiniti_lo_dice_ancora():
    """Il ramo gemello, che resta vero e quindi resta: qui le variabili ci
    sono davvero e valgono il predefinito. La distinzione fra i due casi e'
    tutto il punto della chiusura."""
    reg = logging.getLogger("ai-predefiniti")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        _, copiate = seed(_vuoto(), {"BRIDGE_ENABLED": "false",
                                     "CHAT_DAILY_CAP": "50"}, log=reg)
    finally:
        reg.removeHandler(h)
    assert copiate == []
    assert "erano tutti ai predefiniti" in buf.getvalue()


def test_un_valore_non_numerico_non_fa_saltare_l_avvio():
    """`run.sh` esporta stringhe, e `bashio::config` su un campo vuoto torna "".
    Un ValueError qui fermerebbe l'add-on all'avvio per un'opzione che l'utente
    non ha nemmeno toccato."""
    fuori, _ = seed(_vuoto(), {"BRIDGE_DEADLINE_MIN": "", "CHAT_DAILY_CAP": "boh"},
                    log=logging.getLogger("t"))
    assert fuori["ponte"]["scadenza_min"] == 5
    assert fuori["ponte"]["tetto_giornaliero"] == 50


def test_la_semina_finisce_sul_disco_non_solo_in_memoria(tmp_path):
    import json
    import logging

    from hiris.app.api.handlers_models import load_models_config, save_models_config
    from hiris.app.migrazione_opzioni import seed

    archivio, _ = seed(load_models_config(str(tmp_path)),
                       {"BRIDGE_DEADLINE_MIN": "20"}, log=logging.getLogger("t"))
    # `flags=True`: `seminato` e' un SEGNO DI MIGRAZIONE e solo l'avvio lo
    # scrive -- vedi `test_una_put_non_puo_riscrivere_il_segno_della_semina`.
    save_models_config(str(tmp_path), archivio, flags=True)
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
    fuori, seminata = seed_chain(a, ["openrouter", "claude"], log=logging.getLogger("t"))
    assert fuori["chain_order"] == ["openrouter", "claude"]
    assert seminata is True


def test_una_catena_gia_scelta_non_si_tocca():
    """L'ordine manuale di un'installazione pre-2.5.0 sopravvive. Il segno si
    scrive lo stesso -- ed e' per questo che il secondo valore di ritorno
    significa «c'e' qualcosa da persistere», non «ho copiato una catena»."""
    a = _vuoto()
    a["chain_order"] = ["ollama"]
    fuori, da_salvare = seed_chain(a, ["claude", "openrouter"], log=logging.getLogger("t"))
    assert fuori["chain_order"] == ["ollama"]
    assert fuori["catena_seminata"] is True
    assert da_salvare is True


def test_seminare_una_catena_vuota_con_niente_da_copiare_non_mente_nel_log():
    reg = logging.getLogger("catena-test")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        fuori, da_salvare = seed_chain(_vuoto(), [], log=reg)
    finally:
        reg.removeHandler(h)
    assert "copiata" not in buf.getvalue()
    # Niente da copiare, ma la migrazione E' avvenuta: il segno si scrive e si
    # persiste, altrimenti il prossimo avvio ricalcolerebbe `_chain_as_it_was`.
    assert fuori["catena_seminata"] is True
    assert da_salvare is True


def test_la_semina_della_catena_si_dichiara_nel_log_con_l_ordine_vero():
    reg = logging.getLogger("catena-test-2")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        seed_chain(_vuoto(), ["openrouter", "claude"], log=reg)
    finally:
        reg.removeHandler(h)
    testo = buf.getvalue()
    assert "openrouter -> claude" in testo, (
        "una catena scritta senza essere nominata non e' dichiarata: "
        "l'operatore non puo' verificare che sia quella giusta"
    )
    # **C2 della revisione del commit 3.0.0, porta 1.** Qui ci arriva anche
    # un'installazione nata ieri, che non stava usando NIENTE e la cui catena
    # e' stata composta adesso dalle credenziali presenti. Da questa versione
    # quel ramo si esegue a OGNI installazione nuova, per sempre: raccontare
    # una storia che non c'e' stata e' l'invariante 3 («nessuna parola che
    # affermi piu' di cio' che il sistema sa») violato dove si esegue di piu'.
    assert "stava usando" not in testo, (
        "il log afferma che HIRIS stava usando questa catena: su "
        "un'installazione nuova non e' vero, e quel ramo e' il caso normale"
    )


def test_la_catena_non_si_semina_guardando_seminato():
    """`seminato` e' il segno della semina delle OPZIONI (Task 6), e non e' il
    segno di questa: sono due migrazioni diverse e un archivio puo' trovarsi a
    meta'. L'archivio che questo rilascio trova sull'impianto del proprietario
    e' seminato E ha la catena vuota: legare le due cose lascerebbe quella
    catena vuota per sempre, cioe' zero provider.

    La versione precedente di questo test si fermava qui, e nella sua premessa
    c'era il buco: dedurre da «`seminato` non e' il segno giusto» che il segno
    fosse la FORMA della catena. Il segno vero e' `catena_seminata`, e a
    difenderlo c'e' il test qui sotto."""
    a = _vuoto()
    a["seminato"] = True
    fuori, da_salvare = seed_chain(a, ["claude"], log=logging.getLogger("t"))
    assert fuori["chain_order"] == ["claude"]
    assert da_salvare is True


def test_una_catena_svuotata_di_proposito_non_si_ripopola_al_riavvio():
    """**C3 della revisione finale, e la QUARTA porta della regola `legacy`.**

    Fino a questa chiusura la semina della catena guardava solo se
    `chain_order` fosse vuota. Ma una `chain_order` vuota non e' piu' «non ho
    ancora deciso»: da questa fetta e' una DECISIONE, e la pagina Modelli la
    rende esprimibile in due click (la ✕ su ogni riga, `riordinabile` vero per
    tutte). Il proprietario legge in cima alla pagina che sta pagando due
    volte, toglie la chiave a credito zero e OpenRouter per restare sul piano
    che ha gia' pagato -- poi l'add-on si riavvia, e `_chain_as_it_was` (cioe'
    `legacy = not any(interruttori)`, la regola che questa fetta ha tolto dal
    prodotto) glieli rimette tutti e due in catena: la spesa a consumo
    riparte, e a dirlo c'e' una riga di log che afferma il falso («la catena
    che HIRIS stava usando»: HIRIS stava usando una catena vuota).

    Rimettere il difetto -- la guardia su `chain_order` al posto di quella su
    `catena_seminata` -- fa cadere questo test."""
    reg = logging.getLogger("catena-svuotata")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        # Primo avvio: la catena si semina dalla vecchia regola.
        a, _ = seed_chain(_vuoto(), ["claude", "openrouter"], log=reg)
        assert a["chain_order"] == ["claude", "openrouter"]
        # Il gesto dell'utente: via tutti e due.
        a["chain_order"] = []
        buf.truncate(0)
        buf.seek(0)
        # Riavvio, con la stessa vecchia regola che direbbe ancora le stesse
        # due cose.
        b, da_salvare = seed_chain(a, ["claude", "openrouter"], log=reg)
    finally:
        reg.removeHandler(h)
    assert b["chain_order"] == [], (
        "una catena svuotata di proposito e' stata ripopolata al riavvio: la "
        "regola di compatibilita' e' rientrata dalla porta della migrazione"
    )
    assert da_salvare is False
    assert buf.getvalue() == "", (
        "la migrazione della catena ha parlato di nuovo: non era piu' il suo "
        "momento"
    )


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
    start = src.index("    from .migrazione_opzioni import seed_chain")
    marker = 'app["models_config"] = load_models_config(data_dir)'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    # `_model_name_as_it_was` e non `local_model_name` dal Task 9: e' l'UNICO
    # uso rimasto di `LOCAL_MODEL_NAME` in server.py, e il nome dice a cosa
    # serve -- ricostruire la CREDENZIALE COM'ERA, dove il modello contava
    # insieme all'indirizzo. Il modello che il runner usa arriva dall'archivio.
    firma = ("def _avvio(app, os, logger, data_dir, _credentials, "
             "local_model_url, _model_name_as_it_was):\n")
    func_src = firma + textwrap.indent(corpo, "    ")
    # `env_bool` legge `os.environ` DENTRO env_util.py, quindi l'`os` finto
    # passato al blocco non la raggiunge: se si lasciasse quella vera,
    # `BRIDGE_ENABLED` -- l'unica variabile che questo blocco legge ancora,
    # dopo l'uscita dei cinque `PROVIDER_*` col ramo morto -- arriverebbe
    # dall'ambiente del processo di test, e il ponte non sarebbe esprimibile
    # dal caso. Si sostituisce con una che legge lo STESSO dizionario finto e
    # con le STESSE regole di verita' (`_TRUTHY` di env_util, non un `==
    # "true"` scritto qui: una finta piu' permissiva o piu' severa della
    # realta' proverebbe un'altra cosa).
    from hiris.app.env_util import _TRUTHY

    def _env_bool_finta(nome, default=False):
        raw = ambiente_finto.environ.get(nome)
        if raw is None or raw.strip() == "":
            return default
        return raw.strip().lower() in _TRUTHY

    namespace: dict = {
        "__package__": "hiris.app",
        "__name__": "hiris.app.server",
        "_chain_as_it_was": server._chain_as_it_was,
        "env_bool": _env_bool_finta,
    }
    from hiris.app.api.handlers_models import load_models_config, save_models_config
    namespace["load_models_config"] = load_models_config
    namespace["save_models_config"] = save_models_config
    exec(compile(func_src, "<_on_startup seed_chain>", "exec"), namespace)
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


# Qui viveva `test_con_gli_interruttori_accesi_vale_quello_che_dicono_loro`:
# provava il SECONDO ramo della vecchia regola (`legacy = not
# any(interruttori)` falso, e allora contavano solo gli interruttori accesi).
# E' uscito con quel ramo (G4 della revisione): i cinque `provider_*` non sono
# piu' nello schema e `run.sh` non esporta piu' nessuno dei cinque
# `PROVIDER_*`, quindi via Supervisor gli interruttori erano strutturalmente
# tutti falsi e quel ramo era irraggiungibile. Non era un test che non poteva
# fallire -- falliva benissimo -- era un test che difendeva un comportamento
# che nessun utente puo' piu' produrre, e che teneva in vita una firma con un
# parametro morto.


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


def test_due_avvii_veri_non_ripopolano_la_catena_che_il_proprietario_ha_svuotato(tmp_path):
    """**C3 cablato nell'avvio vero**, col disco vero in mezzo: il test di
    `seed_chain` da solo sopravviverebbe a un `server.py` che si dimentica
    di guardare il segno, ed e' esattamente la guardia che questa chiusura
    sposta.

    Il caso e' quello del proprietario, riprodotto dalla revisione finale:
    cinque interruttori a false, chiave Claude presente ma a credito zero,
    OpenRouter presente. Primo avvio: la vecchia regola copia
    `claude -> openrouter`. Poi lui li toglie tutti e due dalla pagina per
    restare sul piano che ha gia' pagato. Riavvio -- e prima di questa
    chiusura se li ritrovava in catena, con la spesa a consumo che ripartiva.

    Rimettere il difetto (`if not app["models_config"].get("chain_order")` al
    posto di `catena_seminata`) fa cadere questo test."""
    from hiris.app.api.handlers_models import save_models_config

    ambiente = {"LLM_STRATEGY": "balanced"}
    primo = _avvia_la_semina_della_catena(
        tmp_path, ambiente, CREDENZIALI_DEL_PROPRIETARIO)
    assert primo["models_config"]["chain_order"] == ["claude", "openrouter"]

    # Il gesto dell'utente: la ✕ su tutte e due le righe. E' una PUT, quindi
    # `flags` resta falso -- come dalla pagina.
    save_models_config(str(tmp_path), {"chain_order": []})

    secondo = _avvia_la_semina_della_catena(
        tmp_path, ambiente, CREDENZIALI_DEL_PROPRIETARIO)
    assert secondo["models_config"]["chain_order"] == [], (
        "al riavvio la catena svuotata di proposito si e' ripopolata da "
        "`_chain_as_it_was`: la regola di compatibilita' e' rientrata dalla "
        "quarta porta, e la spesa a consumo riparte da sola"
    )
