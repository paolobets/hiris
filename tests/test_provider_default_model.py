"""Il modello si LEGGE al momento dell'uso, non si riceve alla costruzione.

Era il difetto peggiore trovato dal progetto (§0.5), e la parte peggiore era
che riguardava lo STESSO valore: il modello di Claude API aveva effetto
immediato sul ponte (`api/handlers_chat._enqueue_chat_job` rilegge
`app["models_config"]` a ogni turno) e solo al riavvio sull'API (i tre runner
lo ricevevano come argomento di costruzione, `default_model=`, e poi leggevano
`self._default_model`). La pagina Modelli ne dichiarava uno solo: **sbagliata,
non imprecisa**, cioe' l'invariante 4 della spec violato in due modi insieme.

Da qui la scelta (a) del progetto §11.3: togliere il problema invece della
frase. I runner ricevono una LETTURA (`read_model`), e la pagina non ha piu'
nessuna didascalia da fare -- l'assenza di didascalie e' la cosa piu' onesta
che possa dire di se'.
"""
import contextlib
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.backends.openrouter_runner import OpenRouterRunner
from hiris.app.claude_runner import ClaudeRunner
from hiris.app.llm_router import LLMRouter
from hiris.app.providers import CLAUDE, OPENAI, OPENROUTER


async def _modello_spedito(runner, model: str = "auto") -> str:
    """Il `model=` che parte DAVVERO verso il provider, da un turno vero
    (`chat()`), con il client finto.

    Tappa 7 T10 (M-02): fino ad allora queste prove chiedevano a
    `_resolve_current_model()`, un metodo che nessun codice di produzione
    chiamava -- esisteva per loro. Adesso chiedono a cio' che il turno spedisce.
    """
    if isinstance(runner, ClaudeRunner):
        msg = MagicMock(stop_reason="end_turn",
                        content=[MagicMock(type="text", text="ok")])
        msg.usage = MagicMock(input_tokens=1, output_tokens=1,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0)
        runner._client.messages.create = AsyncMock(return_value=msg)
        await runner.chat("ciao", model=model)
        return runner._client.messages.create.call_args.kwargs["model"]
    m = MagicMock(content="ok", tool_calls=None)
    risposta = MagicMock(choices=[MagicMock(finish_reason="stop", message=m)])
    risposta.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    runner._client.chat.completions.create = AsyncMock(return_value=risposta)
    await runner.chat(user_message="ciao", model=model)
    return runner._client.chat.completions.create.call_args.kwargs["model"]


def _cloud(**kw) -> OpenAICompatRunner:
    return OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-test", **kw)


# ---------------------------------------------------------------------------
# Il mestiere non sceglie il modello (Tappa 7, T10; D11a)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("runner_class", [ClaudeRunner, OpenAICompatRunner, LLMRouter])
def test_la_chiamata_non_accetta_piu_un_mestiere(runner_class):
    """`agent_type` sceglieva il modello per mestiere: su Claude dava a tutti
    lo stesso, su OpenAI mandava osservatore e promesse su `gpt-4o-mini` e
    analista e proponente -- che non lo passavano -- su `gpt-4o`. E' uscito
    dalla firma dei due runner; il router inoltra `**kwargs`, e un mestiere
    passato oggi arriverebbe al runner e solleverebbe.

    Mutazione ESEGUITA (07/10/2026): rimesso `agent_type: str = "chat"` nella
    firma di `OpenAICompatRunner.chat` -- rossa sul parametro di OpenAI.
    Ripristinata, `git diff` senza la mutazione."""
    chat = runner_class.chat
    assert "agent_type" not in inspect.signature(chat).parameters


@pytest.mark.asyncio
@pytest.mark.parametrize("runner,atteso", [
    (lambda: ClaudeRunner(api_key="sk-test"), CLAUDE.auto_model),
    (lambda: _cloud(), OPENAI.auto_model),
], ids=["claude", "openai"])
async def test_senza_scelta_ogni_turno_va_sul_modello_automatico_del_provider(runner, atteso):
    """Senza una scelta, l'automatico della tabella dei provider -- lo stesso
    per la chat, l'osservatore, le ricette e le promesse.

    Mutazione ESEGUITA (07/10/2026): il ripiego di
    `OpenAICompatRunner._resolve_model` rimesso a `"gpt-4o-mini"` -- rossa
    (`'gpt-4o-mini' == 'gpt-4o'`). Ripristinata, `git diff` senza la
    mutazione."""
    assert await _modello_spedito(runner()) == atteso


@pytest.mark.asyncio
async def test_un_modello_esplicito_vince_sulla_scelta():
    runner = ClaudeRunner(api_key="sk-test", read_model=lambda: "claude-opus-4-7")
    assert await _modello_spedito(runner, model="claude-sonnet-4-6") == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# La lettura a caldo, runner per runner
#
# La finta e' SCOMODA nel modo in cui lo e' la produzione: `models_config` non
# viene MUTATO, viene RIASSEGNATO -- e' quello che fa
# `handle_save_models_config` (`request.app["models_config"] = clean`). Una
# finta che mutasse il dizionario in-place farebbe passare anche un runner che
# si fosse tenuto un riferimento al dizionario di partenza, cioe' regalerebbe
# una freschezza che la produzione non ha.
# ---------------------------------------------------------------------------


def _archivio(**provider_models):
    return {"models_config": {"provider_models": dict(provider_models)}}


def _lettura(app, provider):
    def leggi() -> str:
        return (app.get("models_config") or {}).get("provider_models", {}).get(provider, "")
    return leggi


@pytest.mark.asyncio
async def test_il_modello_di_claude_cambia_dal_turno_dopo_non_dal_riavvio():
    app = _archivio(claude="claude-opus-4-7")
    runner = ClaudeRunner(api_key="sk-test",
                          read_model=_lettura(app, "claude"))
    assert await _modello_spedito(runner) == "claude-opus-4-7"

    app["models_config"] = {"provider_models": {"claude": "claude-haiku-4-5-20251001"}}
    assert await _modello_spedito(runner) == "claude-haiku-4-5-20251001", (
        "il runner deve LEGGERE il modello al momento dell'uso, non averlo "
        "ricevuto alla costruzione"
    )


@pytest.mark.asyncio
async def test_il_modello_di_openai_cambia_dal_turno_dopo():
    app = _archivio(openai="gpt-4.1")
    runner = _cloud(read_model=_lettura(app, "openai"))
    assert await _modello_spedito(runner) == "gpt-4.1"
    app["models_config"] = {"provider_models": {"openai": "gpt-4o-mini"}}
    assert await _modello_spedito(runner) == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_il_modello_di_openrouter_cambia_dal_turno_dopo():
    app = _archivio(openrouter="openrouter:openai/gpt-4.1")
    runner = OpenRouterRunner(api_key="sk-or-test",
                              read_model=_lettura(app, "openrouter"))
    # Il prefisso `openrouter:` viene tolto prima della chiamata, come sempre.
    assert await _modello_spedito(runner) == "openai/gpt-4.1"
    app["models_config"] = {"provider_models": {"openrouter": ""}}
    assert await _modello_spedito(runner) == OPENROUTER.auto_model.split("openrouter:")[-1]


@pytest.mark.asyncio
async def test_il_modello_di_ollama_cambia_dal_turno_dopo():
    """Il locale e' il caso in cui il valore vince SEMPRE, anche su un modello
    passato esplicitamente (quell'istanza ne ha scaricato uno solo). Prima
    quella vittoria era di un valore cotto nel costruttore (`fixed_model`);
    adesso e' di una lettura, ed e' l'unica differenza."""
    archivio = {"models_config": {"ollama": {"modello": "llama3.1:8b"}}}
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        read_model=lambda: (
            (archivio.get("models_config") or {}).get("ollama", {}).get("modello", "")
        ),
    )
    assert await _modello_spedito(runner) == "llama3.1:8b"
    assert await _modello_spedito(runner, model="gpt-4o") == "llama3.1:8b"

    archivio["models_config"] = {"ollama": {"modello": "qwen2.5:14b"}}
    assert await _modello_spedito(runner) == "qwen2.5:14b"
    assert await _modello_spedito(runner, model="gpt-4o") == "qwen2.5:14b"


@pytest.mark.asyncio
async def test_una_lettura_che_torna_None_non_rompe_il_turno():
    """`read_model` e' fornita da chi costruisce il runner: se un giorno
    restituisse `None` (una chiave assente letta male), il runner deve ripiegare
    come se non ci fosse scelta, non mandare `None` al provider."""
    runner = ClaudeRunner(api_key="sk-test",
                          read_model=lambda: None)
    assert await _modello_spedito(runner) == CLAUDE.auto_model


# ---------------------------------------------------------------------------
# Il CABLAGGIO: la lettura che ogni runner riceve chiude su `app`, non su un
# valore. Vive dentro `_on_startup`: fino al 03/10/2026 si ritagliava dal
# testo e si eseguiva isolata; adesso l'app si avvia davvero, con le
# credenziali di Claude API e di Ollama perche' i due runner nascano, e si
# chiede la lettura AL RUNNER che l'ha ricevuta (`_read_model`).
#
# L'app e' una per file: le prove riassegnano `app["models_config"]` e lo
# rimettono com'era alla fine (`_assigned`).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def started_runners(tmp_path_factory):
    from tests._avvio import credential_environment, started_with

    data_dir = tmp_path_factory.mktemp("letture")
    async with started_with(data_dir,
                            credential_environment(["claude", "ollama"])) as app:
        yield app


def _reader(app, provider):
    runner = app["llm_router"]._backend_map()[provider]
    assert runner is not None, f"l'avvio non ha costruito il runner di {provider}"
    return runner._read_model


@contextlib.contextmanager
def _assigned(app, models_config):
    """`app["models_config"]` RIASSEGNATO (come fa la PUT), e rimesso alla
    fine: l'app e' condivisa dalle prove del file."""
    before = app.get("models_config", _MISSING)
    if models_config is _MISSING:
        app.pop("models_config", None)
    else:
        app["models_config"] = models_config
    try:
        yield
    finally:
        if before is _MISSING:
            app.pop("models_config", None)
        else:
            app["models_config"] = before


_MISSING = object()


@pytest.mark.asyncio(loop_scope="module")
async def test_la_lettura_dell_avvio_vede_l_archivio_RIASSEGNATO(started_runners):
    """`handle_save_models_config` non muta il dizionario, lo SOSTITUISCE. Se
    la chiusura si fosse portata via il dizionario (o peggio il valore) invece
    di `app`, ogni salvataggio sarebbe rimasto invisibile ai runner -- che e'
    esattamente il difetto da cui questo task esiste.

    Mutazione ESEGUITA (03/10/2026): `_model_of` legge il dizionario preso
    alla costruzione (`cfg = app.get("models_config")` fuori da `read`) --
    rossa."""
    leggi = _reader(started_runners, "claude")
    with _assigned(started_runners,
                   {"provider_models": {"claude": "claude-opus-4-7"}}):
        assert leggi() == "claude-opus-4-7"
        started_runners["models_config"] = {
            "provider_models": {"claude": "claude-sonnet-4-6"}}
        assert leggi() == "claude-sonnet-4-6"


@pytest.mark.asyncio(loop_scope="module")
async def test_la_lettura_del_locale_NON_passa_da_provider_models(started_runners):
    """Il modello di Ollama non vive in `provider_models` (`_clean_provider_models`
    lo scarta in lettura E in scrittura): la sua unica casa e'
    `models_config["ollama"]["modello"]`. Una lettura che lo cercasse fra gli
    altri troverebbe sempre "" e il runner locale partirebbe senza modello.

    Mutazione ESEGUITA (03/10/2026): il runner locale costruito con
    `read_model=_model_of("ollama")` -- rossa (`'un-fantasma'`)."""
    modello_locale = _reader(started_runners, "ollama")
    with _assigned(started_runners,
                   {"ollama": {"modello": "llama3.1:8b"},
                    "provider_models": {"ollama": "un-fantasma"}}):
        assert modello_locale() == "llama3.1:8b"
        started_runners["models_config"] = {"ollama": {"modello": "qwen2.5:14b"}}
        assert modello_locale() == "qwen2.5:14b"


@pytest.mark.asyncio(loop_scope="module")
async def test_la_lettura_regge_un_archivio_che_non_c_e_ancora(started_runners):
    """Un turno puo' arrivare con l'archivio assente: la lettura deve
    rispondere "" invece di sollevare.

    Mutazione ESEGUITA (03/10/2026): `app.get("models_config") or {}` ->
    `app["models_config"]` in `_model_of` -- rossa (`KeyError`)."""
    modello_di = _reader(started_runners, "claude")
    modello_locale = _reader(started_runners, "ollama")
    with _assigned(started_runners, _MISSING):
        assert modello_di() == ""
        assert modello_locale() == ""


# ---------------------------------------------------------------------------
# Il timeout, l'unico valore della fetta che NON si puo' leggere all'uso
# ---------------------------------------------------------------------------


def test_apply_timeout_rifa_il_client_col_numero_nuovo(tmp_path):
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        timeout_s=120)
    assert runner._client.timeout.read == 120.0
    vecchio = runner._client

    runner.apply_timeout(300)
    assert runner._client is not vecchio
    assert runner._client.timeout.read == 300.0
    assert runner._client.max_retries == 0, "il locale resta fail-fast"


def test_apply_timeout_non_chiude_il_client_vecchio(tmp_path):
    """Una richiesta puo' essere in volo sul client di prima proprio adesso:
    chiuderlo la ucciderebbe a meta' turno. Il vecchio resta al garbage
    collector, che lo raccoglie quando l'ultima richiesta finisce."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        timeout_s=120)
    vecchio = runner._client
    runner.apply_timeout(300)
    assert vecchio.is_closed() is False


def test_apply_timeout_e_un_no_op_quando_il_numero_non_cambia(tmp_path):
    """Senza questa guardia OGNI salvataggio della pagina Modelli lascerebbe
    dietro un pool di connessioni -- anche quando l'utente ha solo riordinato
    la catena, che e' il gesto piu' frequente della pagina."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        timeout_s=120)
    stesso = runner._client
    runner.apply_timeout(120)
    runner.apply_timeout(120.0)
    assert runner._client is stesso


@pytest.mark.parametrize("locale,atteso", [(True, 120.0), (False, 600.0)])
def test_senza_un_numero_restano_i_due_predefiniti_di_sempre(tmp_path, locale, atteso):
    runner = OpenAICompatRunner(
        base_url=("http://192.168.1.50:11434/v1" if locale
                  else "https://api.openai.com/v1"),
        api_key="k", local=locale)
    assert runner._client.timeout.read == atteso


# Tappa 7 T10 (M-02): le due prove «il modello che ESCE VERAMENTE verso il
# provider» sono diventate il metodo di tutte quelle qui sopra
# (`_modello_spedito`), e sono uscite come prove a parte.


@pytest.mark.asyncio
async def test_una_lettura_che_torna_None_non_arriva_MAI_al_provider():
    """Il locale e' il caso pericoloso: `_resolve_model` restituisce il valore
    scelto senza ripiego (quell'istanza ha un modello solo), quindi un `None`
    finirebbe dritto nel `model=` della richiesta. `_chosen_model` normalizza
    a "" per tutti e due i runner, cosi' il ripiego esiste sempre."""
    locale = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        read_model=lambda: None)
    assert locale._chosen_model() == ""
    assert await _modello_spedito(locale) == ""

    claude = ClaudeRunner(api_key="sk-test",
                          read_model=lambda: None)
    assert claude._chosen_model() == ""
