"""Le due semine che girano ancora: la catena e il modello del piano.

Qui stavano anche le prove della semina delle OPZIONI dell'add-on (`seed`):
copiava nell'archivio sette valori letti da variabili d'ambiente che `run.sh`
non esporta dalla 3.0.0. E' uscita il 02/10/2026 con quelle letture, e le sue
prove con lei.
"""
import io
import logging

from hiris.app.options_migration import seed_chain

VUOTO = {
    "chain_order": [],
    "provider_models": {"claude": "", "openai": "", "openrouter": ""},
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
    "ollama": {"modello": "", "timeout_s": 120},
    "nascondi_gratuiti": False,
    "strategia_ultima": "balanced",
    "seminato": False,
}

def _vuoto() -> dict:
    import copy
    return copy.deepcopy(VUOTO)


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
# Il disco e' vero (tmp_path) e le funzioni di archivio sono quelle di
# produzione. Il blocco non legge piu' l'ambiente (dal 02/10/2026): preset,
# Ollama e ponte valgono il silenzio che avevano su ogni installazione.
# ---------------------------------------------------------------------------


def _blocco_semina_catena_dallo_startup():
    import inspect
    import textwrap

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index("    from .options_migration import seed_chain")
    marker = 'app["models_config"] = load_models_config(data_dir)'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    firma = "def _avvio(app, logger, data_dir, _credentials):\n"
    func_src = firma + textwrap.indent(corpo, "    ")
    namespace: dict = {
        "__package__": "hiris.app",
        "__name__": "hiris.app.server",
        "_chain_as_it_was": server._chain_as_it_was,
    }
    from hiris.app.api.handlers_models import load_models_config, save_models_config
    namespace["load_models_config"] = load_models_config
    namespace["save_models_config"] = save_models_config
    exec(compile(func_src, "<_on_startup seed_chain>", "exec"), namespace)
    return namespace["_avvio"]


def _avvia_la_semina_della_catena(tmp_path, credenziali):
    from hiris.app.api.handlers_models import load_models_config

    avvio = _blocco_semina_catena_dallo_startup()
    app = {"models_config": load_models_config(str(tmp_path))}
    avvio(app, logging.getLogger("t"), str(tmp_path), credenziali)
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
        tmp_path, CREDENZIALI_DEL_PROPRIETARIO,
    )
    assert app["models_config"]["chain_order"] == ["claude", "openrouter"]


def test_la_catena_seminata_finisce_sul_disco_non_solo_in_memoria(tmp_path):
    import json

    _avvia_la_semina_della_catena(
        tmp_path, CREDENZIALI_DEL_PROPRIETARIO)
    disco = json.loads((tmp_path / "models_config.json").read_text(encoding="utf-8"))
    assert disco["chain_order"] == ["claude", "openrouter"], (
        "senza il save, il prossimo avvio ricomincerebbe da capo -- e dopo la "
        "versione B l'ambiente sara' muto, quindi non ricomincerebbe affatto"
    )


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
        tmp_path, CREDENZIALI_DEL_PROPRIETARIO,
    )
    assert "subscription" not in app["models_config"]["chain_order"]


def test_ollama_senza_modello_non_entra_in_catena_per_migrazione(tmp_path):
    """La semina della catena non mette MAI Ollama, anche quando la sua
    credenziale di oggi (il solo indirizzo) c'e'. La vecchia regola lo voleva
    con indirizzo E modello, e il modello arrivava da una variabile d'ambiente
    che nessuna installazione riceve piu': un'installazione con l'indirizzo si
    ritroverebbe in catena un provider senza modello.

    Mutazione ESEGUITA: `{**_credentials}` al posto di
    `{**_credentials, "ollama": False}` in `server._on_startup` -- rossa."""
    app = _avvia_la_semina_della_catena(
        tmp_path, {**CREDENZIALI_DEL_PROPRIETARIO, "ollama": True})
    assert "ollama" not in app["models_config"]["chain_order"]


def test_una_catena_gia_scelta_sopravvive_all_avvio(tmp_path):
    from hiris.app.api.handlers_models import save_models_config

    save_models_config(str(tmp_path), {"chain_order": ["ollama"]})
    app = _avvia_la_semina_della_catena(
        tmp_path, CREDENZIALI_DEL_PROPRIETARIO)
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

    primo = _avvia_la_semina_della_catena(
        tmp_path, CREDENZIALI_DEL_PROPRIETARIO)
    assert primo["models_config"]["chain_order"] == ["claude", "openrouter"]

    # Il gesto dell'utente: la ✕ su tutte e due le righe. E' una PUT, quindi
    # `flags` resta falso -- come dalla pagina.
    save_models_config(str(tmp_path), {"chain_order": []})

    secondo = _avvia_la_semina_della_catena(
        tmp_path, CREDENZIALI_DEL_PROPRIETARIO)
    assert secondo["models_config"]["chain_order"] == [], (
        "al riavvio la catena svuotata di proposito si e' ripopolata da "
        "`_chain_as_it_was`: la regola di compatibilita' e' rientrata dalla "
        "quarta porta, e la spesa a consumo riparte da sola"
    )
