"""L'appartenenza alla catena, e nient'altro.

I test della vecchia derivazione (`derive_active_providers`, `reconcile_chain`)
sono usciti col loro soggetto: provavano i cinque interruttori dell'add-on
incrociati con le credenziali e la regola di compatibilita'
`legacy = not any(toggles.values())`, cioe' la SECONDA rappresentazione dello
stato di un provider -- quella per cui, sull'unica installazione esistente, due
provider lavoravano mentre la pagina li mostrava spenti.

Della vecchia regola resta nel repo la sola META' di compatibilita', in
`server._chain_as_it_was`, ed e' provata li'
(`tests/test_migrazione_opzioni.py`). Il ramo che leggeva gli interruttori e'
uscito con loro: senza nessuno che esporti i cinque `PROVIDER_*`, era
irraggiungibile, e il test che lo esercitava difendeva uno stato che nessun
utente puo' produrre.
"""
from hiris.app.model_activation import providers_in_chain


def test_in_catena_ci_sta_chi_l_utente_ci_ha_messo_e_ha_una_credenziale():
    assert providers_in_chain(
        ["openrouter", "claude", "ollama"],
        {"openrouter": True, "claude": True, "ollama": False},
    ) == ["openrouter", "claude"]


def test_l_ordine_e_quello_dell_utente_non_quello_di_una_strategia():
    """`reconcile_chain` sapeva ricostruire un ordine da `_STRATEGY_ORDER`.
    Qui non c'e' nessun ordine di riserva: l'unico ordine e' quello scritto
    nell'archivio, altrimenti riordinare dalla pagina non vorrebbe dire
    niente."""
    assert providers_in_chain(
        ["ollama", "openai", "claude"],
        {"claude": True, "openai": True, "ollama": True},
    ) == ["ollama", "openai", "claude"]


def test_un_provider_credenziato_e_fuori_catena_NON_entra_da_solo():
    """La proprieta' buona di `reconcile_chain` (non nascondere un provider
    diventato attivo dopo) cambia forma, non sparisce: chi diventa credenziato
    compare in «Fuori dalla catena», visibile, a un gesto di distanza. Cio' che
    si guadagna e' che NIENTE entra in catena senza che qualcuno ce l'abbia
    messo -- l'altro difetto, quello che `reconcile_chain` creava mentre ne
    risolveva uno."""
    assert providers_in_chain(["claude"], {"claude": True, "openai": True}) == ["claude"]


def test_una_catena_vuota_resta_vuota_e_non_si_riempie_di_nascosto():
    """`legacy = not any(toggles.values())` accendeva OGNI provider con
    credenziale quando erano spenti tutti. Catena vuota adesso significa una
    cosa sola, «HIRIS non puo' rispondere», e la pagina lo dice."""
    assert providers_in_chain([], {"claude": True, "openrouter": True}) == []


def test_i_nomi_sconosciuti_e_i_doppioni_cadono():
    assert providers_in_chain(
        ["claude", "claude", "gemini"], {"claude": True}) == ["claude"]


def test_la_vecchia_derivazione_non_esiste_piu():
    import hiris.app.model_activation as m
    assert not hasattr(m, "derive_active_providers")
    assert not hasattr(m, "reconcile_chain")


# ---------------------------------------------------------------------------
# Il CABLAGGIO: `app["catena_modelli"]` viene da `providers_in_chain` sulla
# chain_order dell'archivio e sulle credenziali, e da nient'altro.
#
# Non e' provabile con la fixture dell'app (`app.on_startup.clear()` in
# tests/test_api.py: `_on_startup` non gira mai), quindi si ESTRAE il blocco
# dal sorgente vero e lo si esegue isolato -- stessa tecnica di
# tests/test_avvio_websocket.py e tests/test_migrazione_opzioni.py.
#
# E' anche cio' che chiude il DEBITO E dichiarato al Task 1: fino alla 2.4.1
# `app["catena_modelli"]` aveva DUE scritture, `list(_chain)` dentro il ramo
# dei runner e `[]` nel suo `else`, e la seconda non era coperta da niente.
# Adesso ne ha una sola, fuori da entrambi i rami: non c'e' piu' un secondo
# posto da tenere allineato.
# ---------------------------------------------------------------------------


def _blocco_catena_dallo_startup():
    import inspect
    import textwrap

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index("    from .model_activation import providers_in_chain")
    marker = 'app["catena_modelli"] = list(_chain)'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    # Il parametro si chiama `_risponde` e non `_credentials` dal Task 9: in
    # catena ci sta chi puo' RISPONDERE, che per quattro provider su cinque
    # coincide con la credenziale e per Ollama no (la credenziale e' il solo
    # indirizzo, ma senza un modello scelto il runner non viene costruito e il
    # router salterebbe quell'anello in silenzio). Il nome e' il contratto:
    # questo blocco e' il sorgente VERO di `_on_startup`.
    func_src = "def _avvio(app, _risponde, logger):\n" + textwrap.indent(corpo, "    ")
    namespace: dict = {"__package__": "hiris.app", "__name__": "hiris.app.server"}
    exec(compile(func_src, "<_on_startup catena>", "exec"), namespace)
    return namespace["_avvio"]


def _registro():
    import logging
    return logging.getLogger("catena-avvio")


def test_l_avvio_costruisce_la_catena_dall_archivio_e_dalle_credenziali():
    avvio = _blocco_catena_dallo_startup()
    app = {"models_config": {"chain_order": ["openrouter", "claude", "ollama"]}}
    avvio(app, {"openrouter": True, "claude": True, "ollama": False}, _registro())
    assert app["catena_modelli"] == ["openrouter", "claude"]


def test_l_avvio_non_accoda_un_credenziato_che_nessuno_ha_messo_in_catena():
    avvio = _blocco_catena_dallo_startup()
    app = {"models_config": {"chain_order": ["claude"]}}
    avvio(app, {"claude": True, "openrouter": True, "openai": True}, _registro())
    assert app["catena_modelli"] == ["claude"]


def test_l_avvio_lascia_vuota_una_catena_vuota():
    """Il debito E, chiuso: l'unica scrittura di `app["catena_modelli"]` e'
    questa, e vale anche quando non c'e' nessun runner. Prima ce n'era una
    seconda, `[]` nel ramo `else`, che nessun test poteva raggiungere."""
    avvio = _blocco_catena_dallo_startup()
    app = {"models_config": {"chain_order": []}}
    avvio(app, {"claude": True, "openrouter": True}, _registro())
    assert app["catena_modelli"] == []


def test_l_avvio_scrive_una_copia_non_la_lista_del_router():
    """`app["catena_modelli"]` e' pubblicata alla pagina; `_chain` entra nel
    router. Se fossero lo STESSO oggetto, una modifica dell'una toccherebbe
    l'altro -- e la pagina e il router divergerebbero senza che nessuno abbia
    scritto una seconda regola."""
    avvio = _blocco_catena_dallo_startup()
    app = {"models_config": {"chain_order": ["claude"]}}
    avvio(app, {"claude": True}, _registro())
    app["catena_modelli"].append("openrouter")
    assert app["models_config"]["chain_order"] == ["claude"]


def test_l_avvio_dichiara_nel_registro_chi_resta_fuori_dalla_catena():
    """Nessuna perdita in silenzio. Prima `reconcile_chain` accodava da solo un
    provider credenziato; adesso resta fuori, e il cambio di comportamento si
    dichiara dove un operatore lo cerca -- altrimenti e' un provider
    configurato che non risponde mai, senza una riga che spieghi perche'."""
    import io
    import logging

    reg = logging.getLogger("catena-avvio-log")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        avvio = _blocco_catena_dallo_startup()
        app = {"models_config": {"chain_order": ["claude"]}}
        avvio(app, {"claude": True, "openrouter": True, "openai": False}, reg)
    finally:
        reg.removeHandler(h)
    testo = buf.getvalue()
    assert "openrouter" in testo
    assert "claude" not in testo.split("FUORI dalla catena:")[1], \
        "chi e' IN catena non deve comparire nell'elenco di chi ne sta fuori"


def test_l_avvio_non_scrive_niente_quando_non_c_e_niente_da_dichiarare():
    import io
    import logging

    reg = logging.getLogger("catena-avvio-log-2")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        avvio = _blocco_catena_dallo_startup()
        avvio({"models_config": {"chain_order": ["claude"]}}, {"claude": True}, reg)
    finally:
        reg.removeHandler(h)
    assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# Chi puo' RISPONDERE non e' chi ha una credenziale (Task 9)
#
# Il buco dichiarato dal Task 7: la credenziale di Ollama e' il SOLO indirizzo
# -- l'indirizzo si custodisce, il modello si decide -- ma senza un modello
# scelto `server.py` non costruisce il runner. Con la sola credenziale a
# filtrare la catena, Ollama poteva finire in `app["catena_modelli"]` senza un
# backend dietro: la pagina lo avrebbe disegnato come anello numerato, col suo
# connettore, e `LLMRouter._ordered_backends` lo avrebbe saltato in silenzio.
# Un anello a schermo che non risponde mai e' la bugia che questa fetta ritira.
#
# La derivazione vive dentro `_on_startup`, che ogni fixture azzera: si estrae
# dal sorgente vero, stessa tecnica del blocco qui sopra.
# ---------------------------------------------------------------------------


def _blocco_risponde_dallo_startup():
    import inspect
    import textwrap

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index('    _ollama_model = (app["models_config"]')
    marker = '"ollama": bool(local_model_url and _ollama_model)}'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    func_src = ("def _avvio(app, _credentials, local_model_url):\n"
                + textwrap.indent(corpo, "    ")
                + "\n    return _risponde")
    namespace: dict = {"__package__": "hiris.app", "__name__": "hiris.app.server"}
    exec(compile(func_src, "<_on_startup risponde>", "exec"), namespace)
    return namespace["_avvio"]


def _archivio(modello_ollama):
    return {"models_config": {"provider_models": {},
                              "ollama": {"modello": modello_ollama}}}


def test_ollama_con_l_indirizzo_e_senza_modello_non_puo_rispondere():
    risponde = _blocco_risponde_dallo_startup()(
        _archivio(""), {"claude": True, "ollama": True}, "http://ollama.local:11434")
    assert risponde["ollama"] is False, (
        "senza modello il runner non viene costruito: in catena sarebbe un "
        "anello che il router salta"
    )
    assert risponde["claude"] is True, "gli altri quattro non cambiano"


def test_ollama_col_modello_scelto_risponde():
    risponde = _blocco_risponde_dallo_startup()(
        _archivio("llama3.1:8b"), {"ollama": True}, "http://ollama.local:11434")
    assert risponde["ollama"] is True


def test_senza_indirizzo_non_risponde_nemmeno_con_un_modello_scelto():
    """La credenziale resta necessaria: il modello non la sostituisce."""
    risponde = _blocco_risponde_dallo_startup()(
        _archivio("llama3.1:8b"), {"ollama": False}, "")
    assert risponde["ollama"] is False


def test_il_modello_di_ollama_si_legge_DALL_ARCHIVIO_non_dall_ambiente(monkeypatch):
    """`LOCAL_MODEL_NAME` non decide piu' niente qui: se decidesse ancora,
    questa prova passerebbe con l'archivio vuoto."""
    monkeypatch.setenv("LOCAL_MODEL_NAME", "llama3.1:8b")
    risponde = _blocco_risponde_dallo_startup()(
        _archivio(""), {"ollama": True}, "http://ollama.local:11434")
    assert risponde["ollama"] is False


# ---------------------------------------------------------------------------
# LA SCRITTURA A CALDO (Task 10): `_recompute_chain`
#
# Fino alla 2.4.1 `handle_save_models_config` aggiornava `app["models_config"]`
# e basta: la catena del router si costruiva all'avvio, quindi un riordino
# salvato non cambiava il turno successivo e -- peggio -- la pagina, che
# descrive il RUNTIME perche' e' la sola misura che ha, alla ricarica
# rimostrava l'ordine vecchio. Il salvataggio sembrava perso, e c'era una riga
# in pagina che lo confessava.
#
# `_recompute_chain` e' a livello di modulo apposta: e' l'UNICO calcolo che
# rimette in vigore, lo chiama sia la PUT sia l'avvio, e si puo' provare senza
# far girare `_on_startup`.
# ---------------------------------------------------------------------------


class _Runner:
    """Un backend qualsiasi: al ricalcolo interessa solo se ESISTE."""


class _RunnerLocale(_Runner):
    def __init__(self):
        self.timeout_applicati = []

    def apply_timeout(self, secondi):
        self.timeout_applicati.append(secondi)


def _router(**backends):
    from hiris.app.llm_router import LLMRouter
    return LLMRouter(claude=backends.get("claude"), openai=backends.get("openai"),
                     openrouter=backends.get("openrouter"), ollama=backends.get("ollama"),
                     model_chain=list(backends.get("catena", [])))


def _app(chain_order, *, ollama_modello="", timeout_s=120, router=None):
    return {"models_config": {"chain_order": list(chain_order),
                              "ollama": {"modello": ollama_modello,
                                         "timeout_s": timeout_s}},
            "llm_router": router}


def test_il_riordino_cambia_la_PAGINA_e_il_RUNTIME_insieme():
    """Il difetto che questo task chiude. Senza il ricalcolo, `catena_modelli`
    resta quella dell'avvio e `_chat_policy` pure: la pagina inviterebbe a un
    gesto e poi lo dimenticherebbe."""
    from hiris.app.server import _recompute_chain

    r = _router(claude=_Runner(), openrouter=_Runner(),
                catena=["openrouter", "claude"])
    app = _app(["claude", "openrouter"], router=r)
    _recompute_chain(app)
    assert app["catena_modelli"] == ["claude", "openrouter"]
    assert r._chat_policy == ["claude", "openrouter"], (
        "senza questo, il riordino cambia la PAGINA e non il RUNTIME -- "
        "cioe' la pagina torna a mentire"
    )


def test_la_pagina_e_il_router_ricevono_lo_stesso_ordine_in_due_oggetti():
    """Lo stesso valore, due copie. Se fossero lo stesso oggetto, una modifica
    dell'uno toccherebbe l'altro e i due potrebbero divergere senza che nessuno
    abbia scritto una seconda regola (stessa ragione del `list(_chain)`
    dell'avvio)."""
    from hiris.app.server import _recompute_chain

    r = _router(claude=_Runner(), openai=_Runner(), catena=[])
    app = _app(["openai", "claude"], router=r)
    _recompute_chain(app)
    assert app["catena_modelli"] == r._chat_policy
    assert app["catena_modelli"] is not r._chat_policy


def test_una_catena_svuotata_svuota_ANCHE_il_router():
    """NIENTE ripiego sull'ordine di prima. Un `or router._chat_policy`
    rimetterebbe in piedi la regola legacy tolta al Task 7: pagina che dice
    «la catena e' vuota, HIRIS non ha a chi chiedere» e chat che risponde lo
    stesso, usando l'ordine di prima."""
    from hiris.app.server import _recompute_chain

    r = _router(claude=_Runner(), openrouter=_Runner(), catena=["claude", "openrouter"])
    app = _app([], router=r)
    _recompute_chain(app)
    assert app["catena_modelli"] == []
    assert r._chat_policy == []
    assert r._ordered_backends() == []


def test_un_nome_senza_backend_costruito_non_entra_in_catena():
    """Un anello che il router salta in silenzio, disegnato numerato dalla
    pagina, e' la bugia che questa fetta ritira. La credenziale non basta: il
    ricalcolo guarda i backend che il router ha in mano."""
    from hiris.app.server import _recompute_chain

    r = _router(claude=_Runner(), catena=["claude"])
    app = _app(["openai", "claude", "openrouter"], router=r)
    _recompute_chain(app)
    assert app["catena_modelli"] == ["claude"]
    assert r._chat_policy == ["claude"]


def test_ollama_senza_modello_non_entra_nemmeno_col_runner_costruito():
    """Il runner locale nasce con l'indirizzo (e' la credenziale), ma senza un
    modello scelto non puo' rispondere: `_resolve_model` manderebbe "". E' la
    stessa regola dell'avvio (`_risponde`), riletta invece che ricordata."""
    from hiris.app.server import _recompute_chain

    r = _router(ollama=_RunnerLocale(), catena=[])
    app = _app(["ollama"], ollama_modello="", router=r)
    _recompute_chain(app)
    assert app["catena_modelli"] == []


def test_scegliere_il_modello_di_ollama_lo_fa_entrare_SENZA_riavviare():
    """Il gesto che il Task 9 ha reso possibile e che questo task deve far
    valere: si sceglie il modello nel pannello, si mette in catena, e il
    prossimo messaggio ci passa. Il runner locale esiste gia' perche' nasce con
    l'indirizzo -- se nascesse con `address AND modello`, questo gesto
    tornerebbe 200 e non farebbe niente fino al riavvio."""
    from hiris.app.server import _recompute_chain

    locale = _RunnerLocale()
    r = _router(claude=_Runner(), ollama=locale, catena=["claude"])
    app = _app(["claude", "ollama"], ollama_modello="llama3.1:8b", router=r)
    _recompute_chain(app)
    assert app["catena_modelli"] == ["claude", "ollama"]
    assert r._ordered_backends()[-1] is locale


def test_il_timeout_del_locale_viene_dall_archivio_a_ogni_ricalcolo():
    """L'unico valore della fetta che non si puo' leggere al momento dell'uso:
    `AsyncOpenAI` cuoce il timeout nel client alla costruzione. Il ricalcolo lo
    riapplica, cosi' anche quel numero vale dal prossimo messaggio."""
    from hiris.app.server import _recompute_chain

    locale = _RunnerLocale()
    app = _app(["ollama"], ollama_modello="llama3.1:8b", timeout_s=300,
               router=_router(ollama=locale, catena=["ollama"]))
    _recompute_chain(app)
    assert locale.timeout_applicati == [300]


def test_senza_router_il_ricalcolo_non_solleva_e_svuota_la_catena():
    """Il ramo `else` di `_on_startup` (nessun provider configurato) e' il PRIMO
    gesto di chi installa HIRIS: senza una funzione anche li', la prima PUT
    solleverebbe `TypeError: 'NoneType' object is not callable`. E la catena
    dev'essere vuota, non l'ordine scritto: senza backend non risponde
    nessuno."""
    from hiris.app.server import _recompute_chain

    app = _app(["claude", "openrouter"], router=None)
    _recompute_chain(app)
    assert app["catena_modelli"] == []


def test_il_ricalcolo_regge_un_archivio_assente():
    from hiris.app.server import _recompute_chain

    app: dict = {}
    _recompute_chain(app)
    assert app["catena_modelli"] == []


def test_l_avvio_pubblica_il_ricalcolo_FUORI_dai_due_rami():
    """Il ramo `else` (nessun runner) deve pubblicarlo quanto l'altro, e con UNA
    implementazione sola: due funzioni sarebbero due regole da tenere allineate,
    cioe' il difetto di questa fetta un piano piu' sotto. La riga vive dentro
    `_on_startup`, che ogni fixture azzera: si legge dal sorgente vero, stessa
    tecnica dei pin gemelli in questo file."""
    import inspect

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    righe = [r for r in src.splitlines()
             if 'app["ricalcola_catena"]' in r and not r.lstrip().startswith("#")]
    assert len(righe) == 1, righe
    assert righe[0].startswith('    app["ricalcola_catena"]'), (
        "pubblicata con un rientro maggiore = dentro un ramo: l'altro resta "
        "senza, e la prima PUT di chi installa HIRIS solleva TypeError"
    )
    assert "    _rimetti_in_vigore()" in src, (
        "l'avvio deve passare dalla STESSA strada che rimette in vigore: se le "
        "due derivazioni della catena potessero divergere, devono divergere "
        "all'avvio, dove ogni prova le guarda"
    )


def test_l_avvio_costruisce_il_runner_locale_con_l_INDIRIZZO_non_col_modello():
    """Il runner locale nasce con la credenziale (l'indirizzo) e non con
    `address AND modello`. Se nascesse col modello, scegliere un modello
    dalla pagina su un'installazione partita senza sarebbe un gesto che torna
    200 e non fa niente fino al riavvio -- cioe' la didascalia che il Task 10
    toglie, rimessa da un'altra porta. Chi puo' RISPONDERE resta `_risponde`
    (indirizzo E modello) e governa la catena: il runner c'e', ma senza modello
    nessuno lo mette in catena.

    Il pin e' sul sorgente perche' la costruzione vive dentro `_on_startup`,
    che ogni fixture azzera (stessa tecnica dei blocchi qui sopra)."""
    import inspect

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    i = src.index("    ollama_runner = None")
    blocco = src[i:src.index("    openrouter_runner = None", i)]
    guardia = [r for r in blocco.splitlines()
               if r.startswith("    if ") and "ollama_runner = OpenAICompatRunner"
               not in r]
    assert guardia[0] == "    if local_model_url:", guardia
    assert guardia[1] == '    if _risponde["ollama"]:', (
        "la verifica di raggiungibilita' parla del MODELLO scaricato: senza un "
        "modello scelto non c'e' niente da verificare"
    )
    assert "read_model=_local_model," in blocco
    assert "local=True," in blocco


def test_ogni_runner_riceve_la_lettura_del_SUO_provider():
    """Tre chiamate alla stessa fabbrica, tre nomi diversi: uno scambio qui
    sarebbe invisibile a ogni prova sui runner (la lettura funziona lo stesso,
    legge solo la casella sbagliata) e produrrebbe una pagina che mostra un
    modello e un turno che ne usa un altro -- la divergenza di questa fetta,
    dentro un solo dizionario."""
    import inspect

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    for provider, costruttore in (("claude", "claude_runner = ClaudeRunner("),
                                  ("openai", "openai_runner = OpenAICompatRunner("),
                                  ("openrouter", "openrouter_runner = OpenRouterRunner(")):
        i = src.index(costruttore)
        blocco = src[i:src.index("        )", i)]
        assert f'read_model=_model_of("{provider}")' in blocco, blocco
