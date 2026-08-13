"""L'appartenenza alla catena, e nient'altro.

I test della vecchia derivazione (`derive_active_providers`, `reconcile_chain`)
sono usciti col loro soggetto: provavano i cinque interruttori dell'add-on
incrociati con le credenziali e la regola di compatibilita'
`legacy = not any(toggles.values())`, cioe' la SECONDA rappresentazione dello
stato di un provider -- quella per cui, sull'unica installazione esistente, due
provider lavoravano mentre la pagina li mostrava spenti.

La vecchia regola non e' scomparsa dal repo: vive in `server._catena_com_era`,
eseguita una volta alla migrazione, ed e' provata li'
(`tests/test_migrazione_opzioni.py`).
"""
from hiris.app.model_activation import provider_in_catena


def test_in_catena_ci_sta_chi_l_utente_ci_ha_messo_e_ha_una_credenziale():
    assert provider_in_catena(
        ["openrouter", "claude", "ollama"],
        {"openrouter": True, "claude": True, "ollama": False},
    ) == ["openrouter", "claude"]


def test_l_ordine_e_quello_dell_utente_non_quello_di_una_strategia():
    """`reconcile_chain` sapeva ricostruire un ordine da `_STRATEGY_ORDER`.
    Qui non c'e' nessun ordine di riserva: l'unico ordine e' quello scritto
    nell'archivio, altrimenti riordinare dalla pagina non vorrebbe dire
    niente."""
    assert provider_in_catena(
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
    assert provider_in_catena(["claude"], {"claude": True, "openai": True}) == ["claude"]


def test_una_catena_vuota_resta_vuota_e_non_si_riempie_di_nascosto():
    """`legacy = not any(toggles.values())` accendeva OGNI provider con
    credenziale quando erano spenti tutti. Catena vuota adesso significa una
    cosa sola, «HIRIS non puo' rispondere», e la pagina lo dice."""
    assert provider_in_catena([], {"claude": True, "openrouter": True}) == []


def test_i_nomi_sconosciuti_e_i_doppioni_cadono():
    assert provider_in_catena(
        ["claude", "claude", "gemini"], {"claude": True}) == ["claude"]


def test_la_vecchia_derivazione_non_esiste_piu():
    import hiris.app.model_activation as m
    assert not hasattr(m, "derive_active_providers")
    assert not hasattr(m, "reconcile_chain")


# ---------------------------------------------------------------------------
# Il CABLAGGIO: `app["catena_modelli"]` viene da `provider_in_catena` sulla
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
    start = src.index("    from .model_activation import provider_in_catena")
    marker = 'app["catena_modelli"] = list(_chain)'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    # Il parametro si chiama `_risponde` e non `_credenziali` dal Task 9: in
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
    start = src.index('    _modello_ollama = (app["models_config"]')
    marker = '"ollama": bool(local_model_url and _modello_ollama)}'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    func_src = ("def _avvio(app, _credenziali, local_model_url):\n"
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
