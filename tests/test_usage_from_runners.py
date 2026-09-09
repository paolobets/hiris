"""Chi scrive nell'archivio dei consumi: i runner, a ogni risposta.

Le finte qui restituiscono la forma VERA della risposta degli SDK -- una senza
`usage.cost` (Anthropic, OpenAI) e una con (OpenRouter) -- perche' e' la
differenza fra `misurato` e `reale`, ed e' il difetto da cui nasce la fetta:
`_prezzo` non conosce nessun identificativo OpenRouter, cade su `_default` a
zero, e il costo usciva 0,00 senza che niente lo dicesse. Una finta che non sa
produrre quella differenza non la puo' provare.
"""
from __future__ import annotations

from typing import ClassVar

import pytest
from openai.types import CompletionUsage

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.backends.openrouter_runner import OpenRouterRunner
from hiris.app.claude_runner import ClaudeRunner


class Registro:
    """Il doppio della callback `UsageStore.log`."""

    def __init__(self) -> None:
        self.scritte: list[dict] = []

    def __call__(self, provider, model, **kw):
        self.scritte.append({"provider": provider, "model": model, **kw})


# ── Claude ──────────────────────────────────────────────────────────────────

class _UsoClaude:
    input_tokens = 100
    output_tokens = 20
    cache_creation_input_tokens = 30
    cache_read_input_tokens = 40


class _BloccoTesto:
    type = "text"
    text = "fatto"


class _RispostaClaude:
    usage = _UsoClaude()
    content: ClassVar[list] = [_BloccoTesto()]
    stop_reason = "end_turn"


@pytest.mark.asyncio
async def test_claude_scrive_il_modello_i_token_e_la_cache(monkeypatch):
    registro = Registro()
    runner = ClaudeRunner(api_key="x", log_usage=registro,
                          read_model=lambda: "claude-sonnet-4-6")

    async def _finta(**kwargs):
        return _RispostaClaude()

    monkeypatch.setattr(runner, "_call_api", _finta)
    await runner.chat(user_message="ciao")

    assert len(registro.scritte) == 1
    s = registro.scritte[0]
    assert s["provider"] == "claude"
    assert s["model"] == "claude-sonnet-4-6"
    assert s["token_in"] == 100, "i token d'ingresso PURI, senza la cache dentro"
    assert s["cache_write"] == 30 and s["cache_read"] == 40
    assert s["token_out"] == 20
    assert s["cost_state"] == "misurato"
    assert s["cost_usd"] > 0


@pytest.mark.asyncio
async def test_un_modello_claude_fuori_listino_esce_non_noto(monkeypatch):
    """Misurato sull'installazione vera: il modello scelto era
    `claude-opus-4-8`, che in pricing.py non c'e'. Il suo costo NON deve
    uscire come uno zero."""
    registro = Registro()
    runner = ClaudeRunner(api_key="x", log_usage=registro,
                          read_model=lambda: "claude-opus-4-8")

    async def _finta(**kwargs):
        return _RispostaClaude()

    monkeypatch.setattr(runner, "_call_api", _finta)
    await runner.chat(user_message="ciao")

    assert registro.scritte[0]["cost_state"] == "non_noto"
    assert registro.scritte[0]["cost_usd"] is None


@pytest.mark.asyncio
async def test_senza_archivio_il_runner_funziona_lo_stesso(monkeypatch):
    """`log_usage=None` e' il ramo di libreria e dei test: non deve
    diventare un AttributeError dentro il ciclo del modello."""
    runner = ClaudeRunner(api_key="x", read_model=lambda: "claude-sonnet-4-6")

    async def _finta(**kwargs):
        return _RispostaClaude()

    monkeypatch.setattr(runner, "_call_api", _finta)
    assert await runner.chat(user_message="ciao") == "fatto"


# ── OpenAI-compat, OpenRouter, Ollama ───────────────────────────────────────

def _uso(prompt=100, completion=20, cost=None, cached=None, cache_write=None):
    """L'oggetto `usage` VERO di `openai`, non una finta comoda.

    **La finta che c'era prima era il difetto.** `class _Uso` costruiva
    `prompt_tokens`, `completion_tokens` e -- quando serviva -- `cached_tokens`
    come attributi di PRIMO livello: cioe' esattamente la forma che il codice
    si aspettava, invece della forma che il fornitore manda. Con quella finta
    `getattr(usage, "cached_tokens", 0)` trovava il numero e la prova era
    verde, mentre in produzione trovava sempre 0 (audit delle fondamenta,
    rilievo 8). Una finta scritta contro il proprio codice non puo' che
    confermarlo.

    Adesso l'oggetto e' `openai.types.CompletionUsage` costruito con
    `model_validate`, cioe' la stessa strada che percorre una risposta vera:
    se domani l'SDK spostasse i campi, queste prove lo scoprirebbero da sole.
    `cost` -- che e' di OpenRouter e non di OpenAI -- passa dal ramo dei campi
    extra, che quel tipo ammette (`additionalProperties: true`): e' cosi' che
    arriva anche in casa, dentro la stessa busta `CompletionUsage`.
    """
    payload = {"prompt_tokens": prompt, "completion_tokens": completion,
               "total_tokens": prompt + completion}
    if cost is not None:
        payload["cost"] = cost
    if cached is not None or cache_write is not None:
        # DOVE stanno davvero: `usage.prompt_tokens_details`, misurato il
        # 09/09/2026 su `openai` 3.1.0 e documentato identico da OpenRouter
        # (Prompt Caching). Mai al primo livello di `usage`.
        payload["prompt_tokens_details"] = {"cached_tokens": cached or 0,
                                            "cache_write_tokens": cache_write or 0}
    return CompletionUsage.model_validate(payload)


class _Risposta:
    def __init__(self, usage):
        self.usage = usage


def test_openrouter_scrive_il_costo_REALE_dichiarato_dalla_risposta():
    """Il difetto da cui nasce la fetta: la risposta di OpenRouter porta
    SEMPRE `usage.cost`, e non lo leggevamo."""
    registro = Registro()
    runner = OpenRouterRunner(api_key="x", log_usage=registro)

    runner._track_usage(_Risposta(_uso(cost=0.0031)), "anthropic/claude-sonnet-4-6")

    s = registro.scritte[0]
    assert s["provider"] == "openrouter", "non «openai»: e' una sottoclasse"
    assert s["cost_state"] == "reale"
    assert s["cost_usd"] == 0.0031


def test_openrouter_senza_cost_dichiara_non_noto_e_non_zero():
    registro = Registro()
    runner = OpenRouterRunner(api_key="x", log_usage=registro)

    runner._track_usage(_Risposta(_uso()), "un/modello-mai-visto")

    assert registro.scritte[0]["cost_state"] == "non_noto"
    assert registro.scritte[0]["cost_usd"] is None


def test_openai_resta_openai():
    registro = Registro()
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="x",
                                log_usage=registro)

    runner._track_usage(_Risposta(_uso()), "gpt-4o")

    assert registro.scritte[0]["provider"] == "openai"
    assert registro.scritte[0]["cost_state"] == "misurato"


def test_ollama_dichiara_lo_zero_invece_di_calcolarlo():
    registro = Registro()
    runner = OpenAICompatRunner(base_url="http://localhost:11434/v1",
                                api_key="ollama", local=True,
                                log_usage=registro)

    runner._track_usage(_Risposta(_uso()), "qwen2.5:7b")

    assert registro.scritte[0]["provider"] == "ollama"
    assert registro.scritte[0]["cost_state"] == "gratuito"
    assert registro.scritte[0]["cost_usd"] == 0.0


def test_i_token_di_cache_si_leggono_DOVE_il_fornitore_li_mette():
    """Audit delle fondamenta, rilievo 8. `cached_tokens` e
    `cache_write_tokens` stanno dentro `usage.prompt_tokens_details`, non al
    primo livello: `openai` 3.1.0 (`CompletionUsage`/`PromptTokensDetails`) e
    la documentazione di OpenRouter (Prompt Caching) dicono la stessa cosa,
    misurate entrambe il 09/09/2026. Leggerli dal primo livello faceva uscire
    SEMPRE zero, e quello zero arrivava all'archivio dei consumi marcato
    `misurato`: un numero mai misurato scritto come misurato."""
    registro = Registro()
    runner = OpenRouterRunner(api_key="x", log_usage=registro)

    runner._track_usage(_Risposta(_uso(prompt=100, cached=80, cache_write=20)),
                        "anthropic/claude-sonnet-4-6")

    scritta = registro.scritte[0]
    assert scritta["cache_read"] == 80
    assert scritta["cache_write"] == 20


def test_un_fornitore_che_NON_dichiara_la_cache_scrive_zero_e_non_solleva():
    """Il confine: `prompt_tokens_details` assente (Ollama, e OpenAI quando
    nessun prefisso e' stato riusato) significa «niente da dire sulla cache».
    Zero e' la risposta giusta, e non e' un AttributeError."""
    registro = Registro()
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="x",
                                log_usage=registro)

    runner._track_usage(_Risposta(_uso()), "gpt-4o")

    assert registro.scritte[0]["cache_read"] == 0
    assert registro.scritte[0]["cache_write"] == 0


def test_la_forma_del_fornitore_NON_porta_i_contatori_al_primo_livello():
    """La prova che tiene la prova: se un domani qualcuno ricostruisse la
    finta «comoda» -- gli attributi al primo livello -- questo test lo direbbe
    subito. E' il pinning della MISURA su cui il fix si regge, fatto sul tipo
    vero dell'SDK invece che a parole in un commento."""
    usage = _uso(cached=80, cache_write=20)

    assert getattr(usage, "cached_tokens", None) is None, (
        "«cached_tokens» al primo livello di CompletionUsage non esiste: se "
        "esistesse, la correzione del rilievo 8 non servirebbe piu' e questo "
        "test andrebbe riscritto contro la nuova forma dell'SDK")
    assert usage.prompt_tokens_details.cached_tokens == 80
    assert usage.prompt_tokens_details.cache_write_tokens == 20


def test_una_risposta_senza_usage_non_scrive_niente():
    """Tipico di alcuni modelli via OpenRouter: senza `usage` non c'e' niente
    da contare, e inventare uno zero sarebbe peggio del silenzio."""
    registro = Registro()
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="x",
                                log_usage=registro)

    runner._track_usage(_Risposta(None), "gpt-4o")

    assert registro.scritte == []
