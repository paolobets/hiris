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
    runner = ClaudeRunner(api_key="x", registra_consumo=registro,
                          leggi_modello=lambda: "claude-sonnet-4-6")

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
    runner = ClaudeRunner(api_key="x", registra_consumo=registro,
                          leggi_modello=lambda: "claude-opus-4-8")

    async def _finta(**kwargs):
        return _RispostaClaude()

    monkeypatch.setattr(runner, "_call_api", _finta)
    await runner.chat(user_message="ciao")

    assert registro.scritte[0]["cost_state"] == "non_noto"
    assert registro.scritte[0]["cost_usd"] is None


@pytest.mark.asyncio
async def test_senza_archivio_il_runner_funziona_lo_stesso(monkeypatch):
    """`registra_consumo=None` e' il ramo di libreria e dei test: non deve
    diventare un AttributeError dentro il ciclo del modello."""
    runner = ClaudeRunner(api_key="x", leggi_modello=lambda: "claude-sonnet-4-6")

    async def _finta(**kwargs):
        return _RispostaClaude()

    monkeypatch.setattr(runner, "_call_api", _finta)
    assert await runner.chat(user_message="ciao") == "fatto"


# ── OpenAI-compat, OpenRouter, Ollama ───────────────────────────────────────

class _Uso:
    def __init__(self, prompt=100, completion=20, cost=None):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        if cost is not None:
            self.cost = cost


class _Risposta:
    def __init__(self, usage):
        self.usage = usage


def test_openrouter_scrive_il_costo_REALE_dichiarato_dalla_risposta():
    """Il difetto da cui nasce la fetta: la risposta di OpenRouter porta
    SEMPRE `usage.cost`, e non lo leggevamo."""
    registro = Registro()
    runner = OpenRouterRunner(api_key="x", registra_consumo=registro)

    runner._track_usage(_Risposta(_Uso(cost=0.0031)), "anthropic/claude-sonnet-4-6")

    s = registro.scritte[0]
    assert s["provider"] == "openrouter", "non «openai»: e' una sottoclasse"
    assert s["cost_state"] == "reale"
    assert s["cost_usd"] == 0.0031


def test_openrouter_senza_cost_dichiara_non_noto_e_non_zero():
    registro = Registro()
    runner = OpenRouterRunner(api_key="x", registra_consumo=registro)

    runner._track_usage(_Risposta(_Uso()), "un/modello-mai-visto")

    assert registro.scritte[0]["cost_state"] == "non_noto"
    assert registro.scritte[0]["cost_usd"] is None


def test_openai_resta_openai():
    registro = Registro()
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="x",
                                registra_consumo=registro)

    runner._track_usage(_Risposta(_Uso()), "gpt-4o")

    assert registro.scritte[0]["provider"] == "openai"
    assert registro.scritte[0]["cost_state"] == "misurato"


def test_ollama_dichiara_lo_zero_invece_di_calcolarlo():
    registro = Registro()
    runner = OpenAICompatRunner(base_url="http://localhost:11434/v1",
                                api_key="ollama", locale=True,
                                registra_consumo=registro)

    runner._track_usage(_Risposta(_Uso()), "qwen2.5:7b")

    assert registro.scritte[0]["provider"] == "ollama"
    assert registro.scritte[0]["cost_state"] == "gratuito"
    assert registro.scritte[0]["cost_usd"] == 0.0


def test_una_risposta_senza_usage_non_scrive_niente():
    """Tipico di alcuni modelli via OpenRouter: senza `usage` non c'e' niente
    da contare, e inventare uno zero sarebbe peggio del silenzio."""
    registro = Registro()
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="x",
                                registra_consumo=registro)

    runner._track_usage(_Risposta(None), "gpt-4o")

    assert registro.scritte == []
