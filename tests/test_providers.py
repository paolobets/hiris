"""L'appartenenza alla catena, e nient'altro.

I test della vecchia derivazione (`derive_active_providers`, `reconcile_chain`)
sono usciti col loro soggetto: provavano i cinque interruttori dell'add-on
incrociati con le credenziali e la regola di compatibilita'
`legacy = not any(toggles.values())`, cioe' la SECONDA rappresentazione dello
stato di un provider -- quella per cui, sull'unica installazione esistente, due
provider lavoravano mentre la pagina li mostrava spenti.

Della vecchia regola resta nel repo la sola META' di compatibilita', in
`options_migration._initial_chain` (era `server._chain_as_it_was`), ed e' provata li'
(`tests/test_options_migration.py`). Il ramo che leggeva gli interruttori e'
uscito con loro: senza nessuno che esporti i cinque `PROVIDER_*`, era
irraggiungibile, e il test che lo esercitava difendeva uno stato che nessun
utente puo' produrre.
"""
import contextlib
import logging
from unittest import mock

import pytest

from hiris.app.providers import providers_in_chain
from tests._avvio import SERVER_LOGGER, UNREACHABLE_OLLAMA


def _runners(router):
    """I runner della catena, in ordine: la stessa lista che `chat()` cicla."""
    return [runner for _name, runner in router._ordered_backends_with_name()]



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


# Tappa 7 T9 (M-26): `test_la_vecchia_derivazione_non_esiste_piu` e' uscito
# con `model_activation.py`, fuso nella tabella dei provider: chiedeva che il
# modulo non avesse piu' `derive_active_providers` e `reconcile_chain`, e il
# modulo non c'e' piu'.


# ---------------------------------------------------------------------------
# Il CABLAGGIO: la catena dell'avvio viene da `providers_in_chain` sulla
# chain_order dell'archivio e su chi puo' RISPONDERE, e da nient'altro.
#
# Fino al 03/10/2026 queste prove ritagliavano il blocco dal testo di
# `_on_startup` e lo eseguivano isolato. Adesso l'avvio gira davvero
# (`tests/_avvio.py::started_with`) su un archivio e su credenziali che la
# prova prepara, e si guarda la catena che l'avvio CONSEGNA al router
# (`LLMRouter(model_chain=...)`, registrata da una spia che avvolge la classe
# vera) e quella che pubblica in `app["model_chain"]`.
#
# Perche' anche la consegna al router e non solo `app["model_chain"]`: poche
# righe sotto, l'avvio chiama `_rimetti_in_vigore()` -> `_recompute_chain`, che
# RISCRIVE `app["model_chain"]` e `router._chat_policy` con la stessa regola
# riletta dal router. Guardando solo `app["model_chain"]`, un difetto del
# blocco dell'avvio sarebbe coperto dal ricalcolo, e la prova resterebbe verde.
#
# E' anche cio' che chiude il DEBITO E dichiarato al Task 1: fino alla 2.4.1
# `app["model_chain"]` aveva DUE scritture, `list(_chain)` dentro il ramo
# dei runner e `[]` nel suo `else`, e la seconda non era coperta da niente.
# Dalla Tappa 7 T9 (M-30) la scrittura e' una sola, quella di `_recompute_chain`.
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def _started(tmp_path, chain_order, *, credentials=(), ollama_url="",
                   ollama_model="", provider_models=None, environment=None):
    """`(app, catene)`: l'app avviata su un archivio con `chain_order` (le
    semine gia' fatte, perche' non lo tocchino) e con le sole credenziali in
    `credentials`; `catene` sono le `model_chain` che l'avvio ha consegnato a
    ogni `LLMRouter` costruito."""
    import json

    from hiris.app import llm_router
    from tests._avvio import credential_environment, started_with

    (tmp_path / "models_config.json").write_text(json.dumps({
        "chain_order": list(chain_order),
        "provider_models": provider_models or {},
        "ollama": {"modello": ollama_model},
        "seminato": True, "catena_seminata": True, "piano_seminato": True,
    }), encoding="utf-8")
    env = {**credential_environment(credentials), "LOCAL_MODEL_URL": ollama_url,
           **(environment or {})}
    chains: list[list[str]] = []
    real = llm_router.LLMRouter

    class RecordingRouter(real):
        def __init__(self, *args, model_chain=None, **kwargs):
            chains.append(model_chain)
            super().__init__(*args, model_chain=model_chain, **kwargs)

    with mock.patch.object(llm_router, "LLMRouter", RecordingRouter):
        async with started_with(tmp_path, env) as app:
            yield app, chains


def _the_chain(chains):
    assert len(chains) == 1, f"l'avvio doveva costruire UN router: {chains}"
    return chains[0]


@pytest.mark.asyncio
async def test_l_avvio_costruisce_la_catena_dall_archivio_e_dalle_credenziali(tmp_path):
    async with _started(tmp_path, ["openrouter", "claude", "ollama"],
                        credentials=("openrouter", "claude")) as (app, chains):
        assert _the_chain(chains) == ["openrouter", "claude"]
        assert app["model_chain"] == ["openrouter", "claude"]


@pytest.mark.asyncio
async def test_l_avvio_non_accoda_un_credenziato_che_nessuno_ha_messo_in_catena(tmp_path):
    """Mutazione ESEGUITA (03/10/2026): il filtro della catena dell'avvio
    riceve anche chi ha una credenziale e nessuno ha messo in catena
    (`providers_in_chain(chain_order + credenziati, _risponde)`) -- rossa,
    `['claude', 'openai', 'openrouter'] == ['claude']`. (La prova sopra resta
    verde sotto questa mutazione: li' i credenziati sono gia' tutti in
    catena.)"""
    async with _started(tmp_path, ["claude"],
                        credentials=("claude", "openrouter", "openai")) as (app, chains):
        assert _the_chain(chains) == ["claude"]
        assert app["model_chain"] == ["claude"]


@pytest.mark.asyncio
async def test_l_avvio_lascia_vuota_una_catena_vuota(tmp_path):
    """Il debito E, chiuso: una catena vuota resta vuota anche con due
    provider credenziati."""
    async with _started(tmp_path, [],
                        credentials=("claude", "openrouter")) as (app, chains):
        assert _the_chain(chains) == []
        assert app["model_chain"] == []


@pytest.mark.asyncio
async def test_l_avvio_scrive_una_copia_non_la_lista_del_router(tmp_path):
    """`app["model_chain"]` e' pubblicata alla pagina; la catena del router e'
    un'altra lista. Se fossero lo STESSO oggetto, una modifica dell'una
    toccherebbe l'altro -- e la pagina e il router divergerebbero senza che
    nessuno abbia scritto una seconda regola.

    Si guarda la copia che SOPRAVVIVE all'avvio: quella scritta dal ricalcolo
    (`_recompute_chain`), che riscrive la pubblicazione del blocco dell'avvio.

    Mutazione ESEGUITA (03/10/2026): in `_recompute_chain`
    `router._chat_policy = list(chain)` -> `= app["model_chain"]` -- rossa.
    La scrittura di `app["model_chain"]` nel blocco dell'avvio, che il
    ricalcolo riscriveva poche righe dopo (una mutazione su di lei restava
    verde: in produzione quella copia non arrivava a nessuno), e' uscita alla
    Tappa 7 T9 (voce M-30)."""
    async with _started(tmp_path, ["claude"], credentials=("claude",)) as (app, _chains):
        published = app["model_chain"]
        assert published == ["claude"]
        assert published is not app["llm_router"]._chat_policy
        assert published is not app["models_config"]["chain_order"]
        published.append("openrouter")
        assert app["llm_router"]._chat_policy == ["claude"]
        assert app["models_config"]["chain_order"] == ["claude"]


@pytest.mark.asyncio
async def test_l_avvio_dichiara_nel_registro_chi_resta_fuori_dalla_catena(tmp_path, caplog):
    """Nessuna perdita in silenzio. Prima `reconcile_chain` accodava da solo un
    provider credenziato; adesso resta fuori, e il cambio di comportamento si
    dichiara dove un operatore lo cerca -- altrimenti e' un provider
    configurato che non risponde mai, senza una riga che spieghi perche'.

    Mutazione ESEGUITA (03/10/2026): tolto il `logger.info` di «FUORI dalla
    catena» -- rossa (`IndexError`: la frase non c'e')."""
    with caplog.at_level(logging.INFO, logger=SERVER_LOGGER):
        async with _started(tmp_path, ["claude"],
                            credentials=("claude", "openrouter")):
            pass
    testo = caplog.text
    elenco = testo.split("FUORI dalla catena:")[1].split("\n")[0]
    assert "openrouter" in elenco
    assert "claude" not in elenco, \
        "chi e' IN catena non deve comparire nell'elenco di chi ne sta fuori"


@pytest.mark.asyncio
async def test_l_avvio_non_scrive_niente_quando_non_c_e_niente_da_dichiarare(tmp_path, caplog):
    """La vecchia prova guardava che il blocco isolato non scrivesse NIENTE;
    sull'avvio intero si guarda che non scriva la frase di chi e' fuori (il
    resto dell'avvio scrive le sue)."""
    with caplog.at_level(logging.INFO, logger=SERVER_LOGGER):
        async with _started(tmp_path, ["claude"], credentials=("claude",)):
            pass
    assert "FUORI dalla catena" not in caplog.text


# ---------------------------------------------------------------------------
# Chi puo' RISPONDERE non e' chi ha una credenziale (Task 9)
#
# Il buco dichiarato dal Task 7: la credenziale di Ollama e' il SOLO indirizzo
# -- l'indirizzo si custodisce, il modello si decide -- ma senza un modello
# scelto il runner non puo' rispondere. Con la sola credenziale a filtrare la
# catena, Ollama poteva finire nella catena senza un modello dietro: la pagina
# lo avrebbe disegnato come anello numerato, col suo connettore, e
# `LLMRouter._ordered_backends` lo avrebbe saltato in silenzio.
#
# Fino al 03/10/2026 la derivazione (`_risponde`) si ritagliava dal testo di
# `_on_startup`; adesso si guarda il suo effetto sull'avvio vero: chi entra
# nella catena consegnata al router.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_con_l_indirizzo_e_senza_modello_non_puo_rispondere(tmp_path):
    """Mutazione ESEGUITA (03/10/2026):
    `"ollama": bool(local_model_url and _ollama_model)` -> `bool(local_model_url)`
    -- rossa (`['ollama', 'claude']`)."""
    async with _started(tmp_path, ["ollama", "claude"], credentials=("claude",),
                        ollama_url=UNREACHABLE_OLLAMA) as (_app, chains):
        assert _the_chain(chains) == ["claude"], (
            "senza modello Ollama non puo' rispondere: in catena sarebbe un "
            "anello che il router salta; gli altri provider non cambiano"
        )


@pytest.mark.asyncio
async def test_ollama_col_modello_scelto_risponde(tmp_path):
    async with _started(tmp_path, ["ollama"], ollama_url=UNREACHABLE_OLLAMA,
                        ollama_model="llama3.1:8b") as (_app, chains):
        assert _the_chain(chains) == ["ollama"]


@pytest.mark.asyncio
async def test_senza_indirizzo_non_risponde_nemmeno_con_un_modello_scelto(tmp_path):
    """La credenziale resta necessaria: il modello non la sostituisce. Con il
    solo Ollama in archivio e senza indirizzo non c'e' nessun runner, e
    l'avvio non costruisce nessun router."""
    async with _started(tmp_path, ["ollama", "claude"], credentials=("claude",),
                        ollama_model="llama3.1:8b") as (_app, chains):
        assert _the_chain(chains) == ["claude"]


@pytest.mark.asyncio
async def test_il_modello_di_ollama_si_legge_DALL_ARCHIVIO_non_dall_ambiente(tmp_path):
    """`LOCAL_MODEL_NAME` non decide piu' niente qui: se decidesse ancora,
    questa prova passerebbe con l'archivio vuoto."""
    async with _started(tmp_path, ["ollama", "claude"], credentials=("claude",),
                        ollama_url=UNREACHABLE_OLLAMA,
                        environment={"LOCAL_MODEL_NAME": "llama3.1:8b"}) as (_app, chains):
        assert _the_chain(chains) == ["claude"]


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
    assert app["model_chain"] == ["claude", "openrouter"]
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
    assert app["model_chain"] == r._chat_policy
    assert app["model_chain"] is not r._chat_policy


def test_una_catena_svuotata_svuota_ANCHE_il_router():
    """NIENTE ripiego sull'ordine di prima. Un `or router._chat_policy`
    rimetterebbe in piedi la regola legacy tolta al Task 7: pagina che dice
    «la catena e' vuota, HIRIS non ha a chi chiedere» e chat che risponde lo
    stesso, usando l'ordine di prima."""
    from hiris.app.server import _recompute_chain

    r = _router(claude=_Runner(), openrouter=_Runner(), catena=["claude", "openrouter"])
    app = _app([], router=r)
    _recompute_chain(app)
    assert app["model_chain"] == []
    assert r._chat_policy == []
    assert _runners(r) == []


def test_un_nome_senza_backend_costruito_non_entra_in_catena():
    """Un anello che il router salta in silenzio, disegnato numerato dalla
    pagina, e' la bugia che questa fetta ritira. La credenziale non basta: il
    ricalcolo guarda i backend che il router ha in mano."""
    from hiris.app.server import _recompute_chain

    r = _router(claude=_Runner(), catena=["claude"])
    app = _app(["openai", "claude", "openrouter"], router=r)
    _recompute_chain(app)
    assert app["model_chain"] == ["claude"]
    assert r._chat_policy == ["claude"]


def test_ollama_senza_modello_non_entra_nemmeno_col_runner_costruito():
    """Il runner locale nasce con l'indirizzo (e' la credenziale), ma senza un
    modello scelto non puo' rispondere: `_resolve_model` manderebbe "". E' la
    stessa regola dell'avvio (`_risponde`), riletta invece che ricordata."""
    from hiris.app.server import _recompute_chain

    r = _router(ollama=_RunnerLocale(), catena=[])
    app = _app(["ollama"], ollama_modello="", router=r)
    _recompute_chain(app)
    assert app["model_chain"] == []


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
    assert app["model_chain"] == ["claude", "ollama"]
    assert _runners(r)[-1] is locale


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
    assert app["model_chain"] == []


def test_il_ricalcolo_regge_un_archivio_assente():
    from hiris.app.server import _recompute_chain

    app: dict = {}
    _recompute_chain(app)
    assert app["model_chain"] == []


@pytest.mark.asyncio
async def test_l_avvio_costruisce_il_runner_locale_con_l_INDIRIZZO_non_col_modello(
        tmp_path, caplog):
    """Il runner locale nasce con la credenziale (l'indirizzo) e non con
    `address AND modello`. Se nascesse col modello, scegliere un modello
    dalla pagina su un'installazione partita senza sarebbe un gesto che torna
    200 e non fa niente fino al riavvio -- cioe' la didascalia che il Task 10
    toglie, rimessa da un'altra porta. Chi puo' RISPONDERE resta `_risponde`
    (indirizzo E modello) e governa la catena: il runner c'e', ma senza modello
    nessuno lo mette in catena -- e nessuno ne verifica la raggiungibilita',
    che parla del MODELLO scaricato.

    Fino al 03/10/2026 la prova leggeva le guardie nel testo di `_on_startup`;
    adesso si avvia l'app e si guarda il runner nel router, e il registro.

    Mutazioni ESEGUITE (03/10/2026):
    - `if local_model_url:` (la costruzione) -> `if _risponde["ollama"]:` --
      rossa (nessun runner locale);
    - `if _risponde["ollama"]:` (la verifica) -> `if local_model_url:` --
      rossa (la verifica parte senza un modello, e il registro lo dice);
    - `read_model=_local_model` -> `read_model=_model_of("openai")` -- rossa."""
    with caplog.at_level(logging.INFO, logger=SERVER_LOGGER):
        async with _started(tmp_path, ["claude"], credentials=("claude",),
                            ollama_url=UNREACHABLE_OLLAMA) as (app, _chains):
            local = app["llm_router"]._backend_map()["ollama"]
            assert local is not None, "con l'indirizzo il runner locale c'e'"
            assert local._local is True
            assert local._chosen_model() == ""
            app["models_config"] = {**app["models_config"],
                                    "ollama": {"modello": "qwen2.5:7b"}}
            assert local._chosen_model() == "qwen2.5:7b", (
                "il modello del runner locale si legge dall'archivio, a ogni uso"
            )
    assert "Ollama non raggiungibile" not in caplog.text, (
        "senza un modello scelto non c'e' niente da verificare"
    )


@pytest.mark.asyncio
async def test_con_un_modello_scelto_la_raggiungibilita_si_verifica(tmp_path, caplog):
    """L'altra meta' della guardia qui sopra: con indirizzo E modello la
    verifica parte, e un Ollama che non risponde lo dice nel registro invece
    di fermare l'avvio.

    Mutazione ESEGUITA (03/10/2026): la guardia della verifica resa
    `if False:` (la verifica non parte mai) -- rossa."""
    with caplog.at_level(logging.WARNING, logger=SERVER_LOGGER):
        async with _started(tmp_path, ["ollama"], ollama_url=UNREACHABLE_OLLAMA,
                            ollama_model="llama3.1:8b"):
            pass
    assert "Ollama non raggiungibile" in caplog.text


@pytest.mark.asyncio
async def test_ogni_runner_riceve_la_lettura_del_SUO_provider(tmp_path):
    """Tre chiamate alla stessa fabbrica, tre nomi diversi: uno scambio qui
    sarebbe invisibile a ogni prova sui runner (la lettura funziona lo stesso,
    legge solo la casella sbagliata) e produrrebbe una pagina che mostra un
    modello e un turno che ne usa un altro -- la divergenza di questa fetta,
    dentro un solo dizionario.

    Fino al 03/10/2026 si leggeva `read_model=_model_of("…")` nel testo;
    adesso ogni runner dell'avvio vero dice quale modello legge.

    Mutazione ESEGUITA (03/10/2026): il runner di OpenAI costruito con
    `read_model=_model_of("openrouter")` -- rossa."""
    scelti = {"claude": "modello-di-claude", "openai": "modello-di-openai",
              "openrouter": "modello-di-openrouter"}
    async with _started(tmp_path, ["claude", "openai", "openrouter"],
                        credentials=tuple(scelti),
                        provider_models=scelti) as (app, _chains):
        backends = app["llm_router"]._backend_map()
        letti = {provider: backends[provider]._chosen_model() for provider in scelti}
    assert letti == scelti
