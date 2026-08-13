"""Regression tests for OpenRouter model listing (v0.9.8).

Free models without tool-use support (e.g. nousresearch/hermes-3-llama-3.1-405b:free)
were surfaced in the dropdown but failed with HTTP 404 "No endpoints found that
support tool use" on every call. The fix filters by the model's
`supported_parameters` array.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.api import handlers_models


def _mock_openrouter_response(payload: dict):
    """Build the (session, response) mock pair for aiohttp's context manager."""
    response_cm = MagicMock()
    response_cm.__aenter__ = AsyncMock(return_value=MagicMock(
        status=200,
        json=AsyncMock(return_value=payload),
    ))
    response_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=response_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm


def test_supports_tools_with_tools_param():
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": ["max_tokens", "tools", "tool_choice"]}
    ) is True


def test_supports_tools_with_function_calling_alias():
    """Older OpenRouter responses used 'function_calling' instead of 'tools'."""
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": ["function_calling"]}
    ) is True


def test_supports_tools_missing_param_returns_false():
    assert handlers_models._supports_tools({"id": "x"}) is False
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": []}
    ) is False
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": ["max_tokens", "temperature"]}
    ) is False


def test_supports_tools_handles_malformed_input():
    """Defensive: capability field is None or wrong type → False, not crash."""
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": None}
    ) is False
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": "tools"}  # string, not list
    ) is False


@pytest.mark.asyncio
async def test_fetch_filters_out_non_tool_capable_models():
    """Models without 'tools' in supported_parameters must not be listed."""
    payload = {
        "data": [
            {"id": "anthropic/claude-sonnet-4-6",
             "supported_parameters": ["tools", "max_tokens"]},
            {"id": "nousresearch/hermes-3-llama-3.1-405b:free",
             "supported_parameters": ["max_tokens"]},  # NO tools
            {"id": "meta-llama/llama-3.3-70b-instruct:free",
             "supported_parameters": ["tools"]},
        ],
    }
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models, fonte = await handlers_models._fetch_openrouter_models("sk-or-test")

    assert fonte == "viva"
    assert "openrouter:anthropic/claude-sonnet-4-6" in models
    assert "openrouter:meta-llama/llama-3.3-70b-instruct:free" in models
    # The model that ACTUALLY broke for the user
    assert "openrouter:nousresearch/hermes-3-llama-3.1-405b:free" not in models


@pytest.mark.asyncio
async def test_fetch_keeps_free_models_when_tool_capable():
    """Free models with tool support must still be added (even outside presets)."""
    payload = {
        "data": [
            {"id": "anthropic/claude-sonnet-4-6",
             "supported_parameters": ["tools"]},
            {"id": "some-new-provider/cool-model:free",
             "supported_parameters": ["tools"]},
        ],
    }
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models, fonte = await handlers_models._fetch_openrouter_models("sk-or-test")

    assert fonte == "viva"
    assert "openrouter:some-new-provider/cool-model:free" in models


@pytest.mark.asyncio
async def test_fetch_falls_back_when_capability_field_missing():
    """If OpenRouter response shape changes (no capability data), use presets."""
    payload = {"data": [{"id": "x"}, {"id": "y"}]}
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models, fonte = await handlers_models._fetch_openrouter_models("sk-or-test")

    assert models == handlers_models._OPENROUTER_PRESETS
    assert fonte == "riserva", (
        "una risposta 200 senza dati di capacita' NON e' una lettura riuscita: "
        "quello che si mostra viene dal sorgente"
    )


def test_presets_no_longer_include_known_broken_hermes3():
    """Regression: hermes-3-llama-3.1-405b:free does not support tools and was
    removed from presets (v0.9.8) after observed 404s."""
    assert "openrouter:nousresearch/hermes-3-llama-3.1-405b:free" not in (
        handlers_models._OPENROUTER_PRESETS
    )


# fetta E4 Task 3 ("un bot solo"): the six test_capability_check_* tests
# that lived here pinned `handlers_models.is_openrouter_model_tool_capable`,
# used only to validate an OpenRouter model choice at chatbot save time
# (v0.9.9 regression). Its only caller, `handlers_chatbots.
# _validate_openrouter_model`, is gone with `handle_create_chatbot`/
# `handle_update_chatbot` (the CRUD routes -- the three creation paths that
# survived the E3 all converged on POST /api/chatbots with `enabled: true`
# by default, the opposite of what the scope prescribes). Orphaned by that
# removal (not anticipated by the brief, caught by the census), the
# function itself is gone too now -- verified failing for construction
# (`AttributeError: module 'hiris.app.api.handlers_models' has no attribute
# 'is_openrouter_model_tool_capable'`) before deletion. Every other test in
# this file (`_supports_tools`/`_fetch_openrouter_models`/
# `_hide_free_models_enabled`) stays untouched: those feed GET /api/models,
# the model dropdown, independent of chatbot CRUD.

# ---------------------------------------------------------------------------
# «nascondi i gratuiti» — la casella che sta sotto l'elenco che filtra
#
# Fino alla 2.4.1 il valore si leggeva da `HIRIS_HIDE_FREE_MODELS`, cioe'
# dall'ambiente, cioe' dall'opzione dell'add-on: la casella del pannello scrive
# nell'archivio (`nascondi_gratuiti`, seminato dal Task 6 proprio da quella
# variabile) e la lista avrebbe continuato a filtrare sull'ambiente -- una
# casella che non fa niente. `_hide_free_models_enabled()` e' uscita col
# Task 9 e il valore arriva come argomento.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_il_filtro_dei_gratuiti_viene_DALL_ARGOMENTO_non_dall_ambiente(monkeypatch):
    """La prova che la casella agisce davvero: l'ambiente dice il CONTRARIO
    dell'argomento, e vince l'argomento. Con il lettore d'ambiente al suo posto
    questo test cade: e' l'unica forma che distingue «filtra» da «filtra per la
    ragione di prima»."""
    monkeypatch.setenv("HIRIS_HIDE_FREE_MODELS", "false")
    payload = {
        "data": [
            {"id": "anthropic/claude-sonnet-4-6", "supported_parameters": ["tools"]},
            {"id": "meta-llama/llama-3.3-70b-instruct:free",
             "supported_parameters": ["tools"]},
            {"id": "deepseek/deepseek-chat:free", "supported_parameters": ["tools"]},
        ],
    }
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models, fonte = await handlers_models._fetch_openrouter_models(
            "sk-or-test", nascondi_gratuiti=True)

    assert fonte == "viva"
    assert "openrouter:anthropic/claude-sonnet-4-6" in models
    for m in models:
        assert not m.endswith(":free"), f":free model leaked through: {m}"


@pytest.mark.asyncio
async def test_senza_la_casella_i_gratuiti_restano_anche_con_l_ambiente_acceso(monkeypatch):
    """Il gemello, dall'altra parte: l'ambiente acceso non nasconde piu'
    niente. Senza questo, togliere il lettore d'ambiente e passare sempre
    `True` passerebbe il test qui sopra."""
    monkeypatch.setenv("HIRIS_HIDE_FREE_MODELS", "1")
    payload = {
        "data": [
            {"id": "meta-llama/llama-3.3-70b-instruct:free",
             "supported_parameters": ["tools"]},
        ],
    }
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models, _ = await handlers_models._fetch_openrouter_models(
            "sk-or-test", nascondi_gratuiti=False)

    assert "openrouter:meta-llama/llama-3.3-70b-instruct:free" in models


def test_il_lettore_d_ambiente_non_esiste_piu():
    """Il nome non deve tornare da nessuna porta: un `_hide_free_models_enabled()`
    rimesso accanto all'argomento farebbe due sorgenti per lo stesso valore --
    la forma esatta del difetto che questa fetta chiude."""
    assert not hasattr(handlers_models, "_hide_free_models_enabled")


# ---------------------------------------------------------------------------
# La PROVENIENZA: da dove viene l'elenco che il pannello mostra
#
# Le tre `_fetch_*` hanno cinque secondi di pazienza e, se falliscono,
# restituiscono una lista scritta a mano nel sorgente con un `logger.warning` e
# niente altro. Oggi un elenco di riserva e' indistinguibile da uno vero: sono
# gli stessi identificatori, senza una riga che dica da dove vengono.
# ---------------------------------------------------------------------------


def _mock_che_solleva():
    """La finta SCOMODA: il provider non risponde, e continua a non rispondere.

    Non basta una lista vuota -- quella e' una risposta -- serve che la
    sessione sollevi, come solleva un timeout o una connessione rifiutata.
    """
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(side_effect=OSError("rete assente"))
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm


@pytest.mark.asyncio
async def test_una_lettura_riuscita_si_dichiara_viva():
    payload = {"data": [{"id": "anthropic/claude-sonnet-4-6",
                         "supported_parameters": ["tools"]}]}
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        modelli, fonte = await handlers_models._fetch_openrouter_models(
            "k", nascondi_gratuiti=False)
    assert fonte == "viva"
    assert modelli


@pytest.mark.asyncio
async def test_una_lettura_fallita_dichiara_la_riserva_invece_di_fingere():
    """Chi lo legge puo' stare davanti a un elenco che sembra vero, che viene
    da una costante di due anni fa, per un provider che non risponderebbe
    comunque."""
    with patch("aiohttp.ClientSession", return_value=_mock_che_solleva()):
        modelli, fonte = await handlers_models._fetch_openrouter_models(
            "k", nascondi_gratuiti=False)
    assert fonte == "riserva"
    assert modelli == handlers_models._OPENROUTER_PRESETS


@pytest.mark.asyncio
async def test_sulla_riserva_i_gratuiti_ricompaiono_anche_con_la_casella_spuntata():
    """Il difetto gemello, dichiarato invece che nascosto: il ripiego
    restituisce i preset NON filtrati. Non si corregge qui (filtrarli
    renderebbe la riserva una lista diversa da quella scritta nel sorgente,
    cioe' una terza cosa): si rende leggibile, e il pannello lo dice."""
    with patch("aiohttp.ClientSession", return_value=_mock_che_solleva()):
        modelli, fonte = await handlers_models._fetch_openrouter_models(
            "k", nascondi_gratuiti=True)
    assert fonte == "riserva"
    assert any(m.endswith(":free") for m in modelli)


@pytest.mark.asyncio
async def test_un_200_senza_modelli_utili_non_e_una_lettura_riuscita():
    """OpenAI: una risposta valida che non contiene nessun modello di
    interesse. Il ripiego e' la lista del sorgente, e si dichiara per quello
    che e' -- «viva» qui sarebbe una parola piu' larga del fatto."""
    session_cm = _mock_openrouter_response({"data": [{"id": "davinci-002"}]})
    with patch("aiohttp.ClientSession", return_value=session_cm):
        modelli, fonte = await handlers_models._fetch_openai_models("sk-test")
    assert modelli == handlers_models._OPENAI_FALLBACK
    assert fonte == "riserva"


@pytest.mark.asyncio
async def test_openai_che_non_risponde_dichiara_la_riserva():
    with patch("aiohttp.ClientSession", return_value=_mock_che_solleva()):
        modelli, fonte = await handlers_models._fetch_openai_models("sk-test")
    assert modelli == handlers_models._OPENAI_FALLBACK
    assert fonte == "riserva"


@pytest.mark.asyncio
async def test_openai_letta_davvero_si_dichiara_viva():
    session_cm = _mock_openrouter_response(
        {"data": [{"id": "gpt-4.1"}, {"id": "gpt-4o-mini"}]})
    with patch("aiohttp.ClientSession", return_value=session_cm):
        modelli, fonte = await handlers_models._fetch_openai_models("sk-test")
    assert fonte == "viva"
    assert modelli == ["gpt-4.1", "gpt-4o-mini"]


@pytest.mark.asyncio
async def test_ollama_che_non_risponde_ripiega_sul_modello_scelto_e_lo_dichiara():
    """Il ripiego di Ollama non e' un catalogo: e' «quello che so, e non ho
    potuto verificare che ci sia ancora»."""
    with patch("aiohttp.ClientSession", return_value=_mock_che_solleva()):
        modelli, fonte = await handlers_models._fetch_ollama_models(
            "http://192.168.1.42:11434", "llama3.1:8b")
    assert modelli == ["llama3.1:8b"]
    assert fonte == "riserva"


def _mock_stato(code: int):
    """Una risposta HTTP con uno stato scelto. La finta e' SCOMODA: `json()`
    solleva, perche' un provider che risponde 500 non manda un corpo
    leggibile -- un mock che ne restituisse uno lascerebbe passare un ramo che
    in produzione esploderebbe."""
    response_cm = MagicMock()
    response_cm.__aenter__ = AsyncMock(return_value=MagicMock(
        status=code, json=AsyncMock(side_effect=ValueError("nessun corpo"))))
    response_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=response_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm


@pytest.mark.asyncio
async def test_ollama_che_risponde_MALE_dichiara_la_riserva():
    """Il ramo gemello di quello sopra, e l'unico che li distingue: qui Ollama
    risponde -- quindi non solleva -- ma risponde 500. Una lettura che non ha
    letto niente non e' viva."""
    with patch("aiohttp.ClientSession", return_value=_mock_stato(500)):
        modelli, fonte = await handlers_models._fetch_ollama_models(
            "http://192.168.1.42:11434", "llama3.1:8b")
    assert fonte == "riserva"
    assert modelli == ["llama3.1:8b"]


@pytest.mark.asyncio
async def test_openai_che_risponde_MALE_dichiara_la_riserva():
    with patch("aiohttp.ClientSession", return_value=_mock_stato(401)):
        modelli, fonte = await handlers_models._fetch_openai_models("sk-sbagliata")
    assert fonte == "riserva"
    assert modelli == handlers_models._OPENAI_FALLBACK


@pytest.mark.asyncio
async def test_openrouter_che_risponde_MALE_dichiara_la_riserva():
    with patch("aiohttp.ClientSession", return_value=_mock_stato(429)):
        modelli, fonte = await handlers_models._fetch_openrouter_models(
            "k", nascondi_gratuiti=False)
    assert fonte == "riserva"
    assert modelli == handlers_models._OPENROUTER_PRESETS


@pytest.mark.asyncio
async def test_ollama_letta_davvero_si_dichiara_viva():
    session_cm = _mock_openrouter_response(
        {"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5:14b"}]})
    with patch("aiohttp.ClientSession", return_value=session_cm):
        modelli, fonte = await handlers_models._fetch_ollama_models(
            "http://192.168.1.42:11434", "llama3.1:8b")
    assert fonte == "viva"
    assert modelli == ["llama3.1:8b", "qwen2.5:14b"]


@pytest.mark.asyncio
async def test_un_indirizzo_ollama_invalido_non_e_una_lettura():
    modelli, fonte = await handlers_models._fetch_ollama_models(
        "ftp://cattivo", "llama3.1:8b")
    assert fonte == "riserva"
    assert modelli == ["llama3.1:8b"]


def test_i_modelli_di_claude_non_offrono_piu_la_parola_auto():
    """«auto» non era un modello: era la parola con cui il vecchio picker
    diceva «scegli tu», e salvarla come valore fa partire la richiesta con
    `model="auto"` verso un provider che quel nome non lo conosce
    (`resolve_model("auto", "chat", "auto") == "auto"`). Nell'archivio auto e'
    la stringa vuota, e il pannello la offre come prima voce."""
    from hiris.app.claude_runner import resolve_model
    assert "auto" not in handlers_models._CLAUDE_MODELS
    assert resolve_model("auto", "chat", "auto") == "auto", (
        "se un giorno resolve_model imparasse a scartare la parola, questa "
        "prova va riscritta: oggi il difetto e' reale"
    )
