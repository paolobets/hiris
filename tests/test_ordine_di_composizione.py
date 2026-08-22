"""Fix della review totale della fetta «il ponte riceve il nucleo» (parita' A,
m-4): l'ordine di composizione del system prompt, pinnato in tutti e tre i
punti che lo compongono.

Il difetto. `hiris/app/claude_runner.py::ClaudeRunner.chat` DICHIARA
l'invariante in un commento -- «Behaviour modifiers ... must precede
context_str» -- ma la dichiarava per se' sola: `backends/openai_compat_runner
.py`, in `chat()` e in `chat_stream()`, componeva BASE -> persona ->
**contesto -> modificatori**, cioe' l'ordine invertito. Due punti su tre
violavano un'invariante scritta nel terzo, e la fetta ha toccato esattamente
quelle righe (Task 3, sostituendo i letterali `compact`/`minimal` con
`COMPACT_PROMPT`/`MINIMAL_PROMPT`) senza accorgersene: un commento non e' un
meccanismo, ed e' il motivo per cui questo file esiste.

Perche' l'invariante e' VERA (verificata prima di muovere il codice, non data
per buona). I blocchi BASE, persona e modificatori sono STABILI: dipendono
dalla configurazione, non dal turno. `context_str` e' VOLATILE: e' il nucleo,
ricomposto a ogni messaggio. Tenere gli stabili davanti al volatile e' cio'
che rende riusabile il prefisso della richiesta:

- su Anthropic (`ClaudeRunner.chat`) e' esplicito -- un solo `cache_control`
  cumulativo, posato sull'ultimo blocco stabile: se `context_str` finisse
  dentro il prefisso cacheato, la cache verrebbe invalidata a ogni turno;
- su OpenAI/OpenRouter/Ollama (`OpenAICompatRunner`) non ci sono breakpoint da
  posare, ma il caching e' anch'esso PER PREFISSO: un blocco volatile davanti
  ai modificatori li butta fuori dal prefisso riusabile a ogni turno.

Stessa invariante, stessa ragione, mezzo diverso. E in piu' c'e' la parita'
che da' il nome alla fetta: `agent/prompts.py::build_chat_messages` (il ponte)
compone gia' BASE -> persona -> modificatori -> guida -> contesto, e i tre
composer del prodotto devono mettere le stesse cose nello stesso posto o
divergono in silenzio -- che e' esattamente cio' che era successo.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app.agent import prompts
from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import (
    COMPACT_PROMPT,
    MINIMAL_PROMPT,
    RESTRICT_PROMPT,
)

_PERSONA = "Sei HIRIS, la persona della chat."
_CONTESTO = "## La casa\nSalotto: luce accesa."


def _fake_openai_client():
    class _FakeMessage:
        content = "ok"
        tool_calls = None

    class _FakeChoice:
        finish_reason = "stop"
        message = _FakeMessage()

    class _FakeResponse:
        usage = None
        choices = [_FakeChoice()]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_FakeResponse())
    return client


def _runner(tmp_path):
    return OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )


def _asserisci_ordine(system_text: str):
    """L'invariante, in una forma sola: persona < modificatori < contesto."""
    i_persona = system_text.index(_PERSONA)
    i_restrict = system_text.index(RESTRICT_PROMPT)
    i_compact = system_text.index(COMPACT_PROMPT)
    i_contesto = system_text.index(_CONTESTO)
    assert i_persona < i_restrict < i_compact < i_contesto, (
        "i modificatori di comportamento sono finiti DOPO il contesto: e' il "
        "difetto m-4, riaperto. I blocchi stabili stanno davanti al volatile "
        "(caching per prefisso) e i tre composer devono concordare.")


@pytest.mark.asyncio
async def test_openai_compat_chat_mette_i_modificatori_prima_del_contesto(tmp_path):
    """`OpenAICompatRunner.chat` -- il punto violato n.1."""
    runner = _runner(tmp_path)
    runner._client = _fake_openai_client()

    await runner.chat(
        user_message="ciao",
        system_prompt=_PERSONA,
        context_str=_CONTESTO,
        model="gpt-4o",
        max_tokens=64,
        restrict_to_home=True,
        response_mode="compact",
    )

    messaggi = runner._client.chat.completions.create.call_args.kwargs["messages"]
    assert messaggi[0]["role"] == "system"
    _asserisci_ordine(messaggi[0]["content"])


@pytest.mark.asyncio
async def test_openai_compat_chat_stream_mette_i_modificatori_prima_del_contesto(tmp_path):
    """`OpenAICompatRunner.chat_stream` -- il punto violato n.2. Lo streaming
    non e' una porta di servizio: stessa invariante, stesso pin."""
    runner = _runner(tmp_path)
    runner._client = _fake_openai_client()

    async def _stream_vuoto(*_a, **_kw):
        if False:  # pragma: no cover - generatore vuoto, ci basta la chiamata
            yield None

    runner._client.chat.completions.create = AsyncMock(return_value=_stream_vuoto())

    async for _chunk in runner.chat_stream(
        user_message="ciao",
        system_prompt=_PERSONA,
        context_str=_CONTESTO,
        model="gpt-4o",
        max_tokens=64,
        restrict_to_home=True,
        response_mode="compact",
    ):
        pass

    messaggi = runner._client.chat.completions.create.call_args.kwargs["messages"]
    assert messaggi[0]["role"] == "system"
    _asserisci_ordine(messaggi[0]["content"])


@pytest.mark.asyncio
async def test_claude_runner_mette_i_modificatori_prima_del_contesto(tmp_path):
    """Il punto che DICHIARAVA l'invariante: deve continuare a rispettarla.
    Qui i blocchi sono una lista di dict (prompt caching), quindi si guarda
    l'ordine dei blocchi e non gli indici in una stringa -- e si verifica
    anche cio' che l'invariante SERVE a garantire: il breakpoint di cache sta
    sull'ultimo blocco stabile, mai sul contesto volatile."""
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(api_key="sk-test")

    catturate: list[dict] = []

    async def _cattura(**kwargs):
        catturate.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client = MagicMock()
    runner._client.messages.create = _cattura

    await runner.chat(
        user_message="ciao",
        system_prompt=_PERSONA,
        context_str=_CONTESTO,
        model="claude-sonnet-4-6",
        max_tokens=64,
        restrict_to_home=True,
        response_mode="compact",
    )

    blocchi = catturate[0]["system"]
    testi = [b["text"] for b in blocchi]
    _asserisci_ordine("\n\n".join(testi))

    assert testi[-1] == _CONTESTO, "il contesto volatile non e' l'ultimo blocco"
    assert "cache_control" not in blocchi[-1], (
        "il breakpoint di cache e' finito sul blocco VOLATILE: e' proprio "
        "cio' che l'ordine dei blocchi esiste per evitare")
    assert "cache_control" in blocchi[-2], (
        "il breakpoint cumulativo non e' piu' sull'ultimo blocco stabile")


def test_il_ponte_compone_nello_stesso_ordine():
    """Il terzo composer (`agent/prompts.py`), che l'ordine giusto ce l'aveva
    gia'. Sta qui, accanto agli altri due, perche' l'invariante e' UNA e la
    sua violazione e' stata possibile proprio perche' viveva in un posto
    solo."""
    system, _user = prompts.build_chat_messages(
        _PERSONA, [], contesto=_CONTESTO,
        restrict_to_home=True, response_mode="compact")
    _asserisci_ordine(system)


def test_minimal_segue_la_stessa_regola_di_compact(tmp_path):
    """`response_mode="minimal"` prende l'altro ramo dello stesso `elif`: se
    qualcuno riordinasse solo il ramo `compact`, questo lo prenderebbe."""
    system, _user = prompts.build_chat_messages(
        _PERSONA, [], contesto=_CONTESTO, response_mode="minimal")
    assert system.index(MINIMAL_PROMPT) < system.index(_CONTESTO)
