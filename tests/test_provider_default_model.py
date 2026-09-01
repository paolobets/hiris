"""Il modello si LEGGE al momento dell'uso, non si riceve alla costruzione.

Era il difetto peggiore trovato dal progetto (§0.5), e la parte peggiore era
che riguardava lo STESSO valore: il modello di Claude API aveva effetto
immediato sul ponte (`api/handlers_chat._enqueue_chat_job` rilegge
`app["models_config"]` a ogni turno) e solo al riavvio sull'API (i tre runner
lo ricevevano come argomento di costruzione, `default_model=`, e poi leggevano
`self._default_model`). La pagina Modelli ne dichiarava uno solo: **sbagliata,
non imprecisa**, cioe' l'invariante 4 della spec violato in due modi insieme.

Da qui la scelta (a) del progetto §11.3: togliere il problema invece della
frase. I runner ricevono una LETTURA (`leggi_modello`), e la pagina non ha piu'
nessuna didascalia da fare -- l'assenza di didascalie e' la cosa piu' onesta
che possa dire di se'.
"""
import inspect
import textwrap

import pytest

from hiris.app.backends.openai_compat_runner import AUTO_MODEL_MAP as AUTO_COMPAT
from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.backends.openrouter_runner import AUTO_OPENROUTER, OpenRouterRunner
from hiris.app.claude_runner import AUTO_MODEL_MAP, ClaudeRunner, resolve_model


def test_resolve_model_uses_provider_default_when_auto():
    # default esplicito vince su AUTO_MODEL_MAP quando model="auto"
    assert resolve_model("auto", "agent", "claude-opus-4-7") == "claude-opus-4-7"


def test_resolve_model_falls_back_to_auto_map_when_no_default():
    # nessun default -> comportamento odierno (AUTO_MODEL_MAP)
    assert resolve_model("auto", "agent", "") == "claude-haiku-4-5-20251001"


def test_resolve_model_explicit_wins_over_default():
    assert resolve_model("claude-sonnet-4-6", "agent", "claude-opus-4-7") == "claude-sonnet-4-6"


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


def test_il_modello_di_claude_cambia_dal_turno_dopo_non_dal_riavvio(tmp_path):
    app = _archivio(claude="claude-opus-4-7")
    runner = ClaudeRunner(api_key="sk-test",
                          leggi_modello=_lettura(app, "claude"))
    assert runner._resolve_current_model() == "claude-opus-4-7"

    app["models_config"] = {"provider_models": {"claude": "claude-haiku-4-5-20251001"}}
    assert runner._resolve_current_model() == "claude-haiku-4-5-20251001", (
        "il runner deve LEGGERE il modello al momento dell'uso, non averlo "
        "ricevuto alla costruzione"
    )


def test_il_modello_di_openai_cambia_dal_turno_dopo(tmp_path):
    app = _archivio(openai="gpt-4.1")
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-test",
                                leggi_modello=_lettura(app, "openai"))
    assert runner._resolve_current_model() == "gpt-4.1"
    app["models_config"] = {"provider_models": {"openai": "gpt-4o-mini"}}
    assert runner._resolve_current_model() == "gpt-4o-mini"


def test_il_modello_di_openrouter_cambia_dal_turno_dopo(tmp_path):
    app = _archivio(openrouter="openrouter:openai/gpt-4.1")
    runner = OpenRouterRunner(api_key="sk-or-test",
                              leggi_modello=_lettura(app, "openrouter"))
    # Il prefisso `openrouter:` viene tolto prima della chiamata, come sempre.
    assert runner._resolve_current_model() == "openai/gpt-4.1"
    app["models_config"] = {"provider_models": {"openrouter": ""}}
    assert runner._resolve_current_model() == AUTO_OPENROUTER.split("openrouter:")[-1]


def test_il_modello_di_ollama_cambia_dal_turno_dopo(tmp_path):
    """Il locale e' il caso in cui il valore vince SEMPRE, anche su un modello
    passato esplicitamente (quell'istanza ne ha scaricato uno solo). Prima
    quella vittoria era di un valore cotto nel costruttore (`fixed_model`);
    adesso e' di una lettura, ed e' l'unica differenza."""
    archivio = {"models_config": {"ollama": {"modello": "llama3.1:8b"}}}
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        leggi_modello=lambda: (
            (archivio.get("models_config") or {}).get("ollama", {}).get("modello", "")
        ),
    )
    assert runner._resolve_current_model() == "llama3.1:8b"
    assert runner._resolve_model("gpt-4o", "chat") == "llama3.1:8b"

    archivio["models_config"] = {"ollama": {"modello": "qwen2.5:14b"}}
    assert runner._resolve_current_model() == "qwen2.5:14b"
    assert runner._resolve_model("gpt-4o", "chat") == "qwen2.5:14b"


def test_senza_lettura_il_comportamento_e_quello_di_prima(tmp_path):
    """`leggi_modello=None` deve valere quanto valeva `default_model=""`: e' il
    ramo di libreria (chiunque costruisca un runner senza passare da
    `server.py`), e cambiarlo in silenzio sarebbe un ripiego nuovo."""
    claude = ClaudeRunner(api_key="sk-test")
    assert claude._resolve_current_model() == AUTO_MODEL_MAP["chat"]

    openai = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-test")
    assert openai._resolve_current_model() == AUTO_COMPAT["chat"]


def test_una_lettura_che_torna_None_non_rompe_il_turno(tmp_path):
    """`leggi_modello` e' fornita da chi costruisce il runner: se un giorno
    restituisse `None` (una chiave assente letta male), il runner deve ripiegare
    come se non ci fosse scelta, non mandare `None` al provider."""
    runner = ClaudeRunner(api_key="sk-test",
                          leggi_modello=lambda: None)
    assert runner._resolve_current_model() == AUTO_MODEL_MAP["chat"]


# ---------------------------------------------------------------------------
# Il CABLAGGIO: la lettura che ogni runner riceve chiude su `app`, non su un
# valore. Vive dentro `_on_startup`, che ogni fixture azzera
# (`app.on_startup.clear()` in tests/test_api.py), quindi si ESTRAE dal
# sorgente vero -- stessa tecnica di tests/test_model_activation.py.
# ---------------------------------------------------------------------------


def _letture_dallo_startup():
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index("    def _modello_di(provider: str):")
    marker = '.get("ollama", {}).get("modello", "")'
    end = src.index(marker, start) + len(marker)
    corpo = textwrap.dedent(src[start:end])
    func_src = ("def _avvio(app):\n" + textwrap.indent(corpo, "    ")
                + "\n    return _modello_di, _modello_locale")
    spazio: dict = {}
    exec(compile(func_src, "<_on_startup letture>", "exec"), spazio)
    return spazio["_avvio"]


def test_la_lettura_dell_avvio_vede_l_archivio_RIASSEGNATO():
    """`handle_save_models_config` non muta il dizionario, lo SOSTITUISCE. Se
    la chiusura si fosse portata via il dizionario (o peggio il valore) invece
    di `app`, ogni salvataggio sarebbe rimasto invisibile ai runner -- che e'
    esattamente il difetto da cui questo task esiste."""
    modello_di, _ = _letture_dallo_startup()(
        app := {"models_config": {"provider_models": {"claude": "claude-opus-4-7"}}})
    leggi = modello_di("claude")
    assert leggi() == "claude-opus-4-7"
    app["models_config"] = {"provider_models": {"claude": "claude-sonnet-4-6"}}
    assert leggi() == "claude-sonnet-4-6"


def test_la_lettura_del_locale_NON_passa_da_provider_models():
    """Il modello di Ollama non vive in `provider_models` (`_clean_provider_models`
    lo scarta in lettura E in scrittura): la sua unica casa e'
    `models_config["ollama"]["modello"]`. Una lettura che lo cercasse fra gli
    altri troverebbe sempre "" e il runner locale partirebbe senza modello."""
    _, modello_locale = _letture_dallo_startup()(
        app := {"models_config": {"ollama": {"modello": "llama3.1:8b"},
                                  "provider_models": {"ollama": "un-fantasma"}}})
    assert modello_locale() == "llama3.1:8b"
    app["models_config"] = {"ollama": {"modello": "qwen2.5:14b"}}
    assert modello_locale() == "qwen2.5:14b"


def test_la_lettura_regge_un_archivio_che_non_c_e_ancora():
    """`_on_startup` puo' non essere girato (ogni fixture lo azzera) e un turno
    puo' comunque arrivare: la lettura deve rispondere "" invece di sollevare."""
    modello_di, modello_locale = _letture_dallo_startup()({})
    assert modello_di("claude")() == ""
    assert modello_locale() == ""


# ---------------------------------------------------------------------------
# Il timeout, l'unico valore della fetta che NON si puo' leggere all'uso
# ---------------------------------------------------------------------------


def test_applica_timeout_rifa_il_client_col_numero_nuovo(tmp_path):
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        timeout_s=120)
    assert runner._client.timeout.read == 120.0
    vecchio = runner._client

    runner.apply_timeout(300)
    assert runner._client is not vecchio
    assert runner._client.timeout.read == 300.0
    assert runner._client.max_retries == 0, "il locale resta fail-fast"


def test_applica_timeout_non_chiude_il_client_vecchio(tmp_path):
    """Una richiesta puo' essere in volo sul client di prima proprio adesso:
    chiuderlo la ucciderebbe a meta' turno. Il vecchio resta al garbage
    collector, che lo raccoglie quando l'ultima richiesta finisce."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        timeout_s=120)
    vecchio = runner._client
    runner.apply_timeout(300)
    assert vecchio.is_closed() is False


def test_applica_timeout_e_un_no_op_quando_il_numero_non_cambia(tmp_path):
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


# ---------------------------------------------------------------------------
# Il modello che ESCE VERAMENTE verso il provider
#
# `_resolve_modello_corrente()` rende osservabile la lettura, ma e' un metodo
# che esiste per i test: da solo non prova che sia lo stesso valore a finire
# nella richiesta. Queste due prove guardano il `model=` della chiamata.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_la_chiamata_a_claude_parte_col_modello_LETTO_ADESSO(tmp_path):
    from unittest.mock import AsyncMock, MagicMock

    app = _archivio(claude="claude-opus-4-7")
    runner = ClaudeRunner(api_key="sk-test",
                          leggi_modello=_lettura(app, "claude"))
    blocco = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[blocco])
    msg.usage = MagicMock(input_tokens=1, output_tokens=1,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)

    await runner.chat("ciao", model="auto", agent_type="chat")
    assert runner._client.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"

    app["models_config"] = {"provider_models": {"claude": "claude-sonnet-4-6"}}
    await runner.chat("ciao", model="auto", agent_type="chat")
    assert runner._client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6", (
        "il turno successivo deve partire col modello nuovo, senza riavvio"
    )


@pytest.mark.asyncio
async def test_la_chiamata_a_ollama_parte_col_modello_LETTO_ADESSO(tmp_path):
    from unittest.mock import AsyncMock, MagicMock

    archivio = {"models_config": {"ollama": {"modello": "llama3.1:8b"}}}
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        leggi_modello=lambda: (
            (archivio.get("models_config") or {}).get("ollama", {}).get("modello", "")
        ),
    )
    m = MagicMock()
    m.content = "ok"
    m.tool_calls = None
    risposta = MagicMock(choices=[MagicMock(finish_reason="stop", message=m)])
    risposta.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    runner._client.chat.completions.create = AsyncMock(return_value=risposta)

    await runner.chat(user_message="ciao", model="auto")
    assert runner._client.chat.completions.create.call_args.kwargs["model"] == "llama3.1:8b"

    archivio["models_config"] = {"ollama": {"modello": "qwen2.5:14b"}}
    await runner.chat(user_message="ciao", model="auto")
    assert runner._client.chat.completions.create.call_args.kwargs["model"] == "qwen2.5:14b"


def test_una_lettura_che_torna_None_non_arriva_MAI_al_provider(tmp_path):
    """Il locale e' il caso pericoloso: `_resolve_model` restituisce il valore
    scelto senza ripiego (quell'istanza ha un modello solo), quindi un `None`
    finirebbe dritto nel `model=` della richiesta. `_modello_scelto` normalizza
    a "" per tutti e due i runner, cosi' il ripiego esiste sempre."""
    locale = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama", local=True,
        leggi_modello=lambda: None)
    assert locale._modello_scelto() == ""
    assert locale._resolve_current_model() == ""

    claude = ClaudeRunner(api_key="sk-test",
                          leggi_modello=lambda: None)
    assert claude._modello_scelto() == ""
