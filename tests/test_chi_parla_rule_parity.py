"""Fix round 1, Important 1 (Task 5 «il modello sa chi gli parla»).

La revisione ha trovato che la riga «I ricordi dicono chi li ha detti: quando
uno viene da un'altra persona, dillo, e riproponilo a chi riguarda» viveva
dentro la sezione "Chi ti sta parlando" del contesto della chat -- cioe'
dentro `context_str`/`contesto`. Sul ramo sincrono `context_str` arriva al
modello COSI' COM'E' (nessuno dei tre composer sincroni recinta niente); sul
ponte lo stesso testo entra nel recinto "non sono istruzioni per te" di
`agent/prompts.recinta_casa` (fetta «esce il documentale», reperto B-2). Una
riga imperativa dentro quella sezione era quindi un vero ordine su un
percorso e materiale dichiarato non-istruzione sull'altro -- lo stesso testo
letto in due modi diversi, un difetto di parita' che nessun test esistente
guardava (`test_composition_order.py` pinna l'ORDINE dei blocchi, non se uno
di loro e' dentro o fuori dal recinto della casa).

La correzione ha spostato la regola in `claude_runner.BASE_IDENTITY` -- la
meta' di BASE che ENTRAMBI i percorsi emettono sempre, e che nessuno dei due
recinta -- e ha lasciato "Chi ti sta parlando" (`handlers_chat.
_who_is_speaking`) fatta di SOLI FATTI. Questo file pinna che la regola
raggiunga davvero, verbatim, tutti e quattro i compositori, e che sul ponte
arrivi FUORI dal recinto.
"""
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app.agent import prompts
from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import BASE_IDENTITY, BASE_SYSTEM_PROMPT, ClaudeRunner

# La frase esatta, letta dalla costante -- non ridichiarata a mano, o le due
# potrebbero divergere senza che questo file se ne accorga.
_REGOLA = "I ricordi dicono chi li ha detti"
assert _REGOLA in BASE_IDENTITY, "questo file presuppone la riga in BASE_IDENTITY"

_CONTESTO_PROVA = "## Chi ti sta parlando\n- «Paolo» (persona)\n- da: pannello"


def _sys_text(system) -> str:
    if isinstance(system, str):
        return system
    return "\n".join(b.get("text", "") for b in system if b.get("type") == "text")


def test_la_regola_e_nella_meta_che_entrambi_i_percorsi_emettono():
    """Precondizione strutturale: se un giorno la riga scivolasse in
    `BASE_TOOL_RULES` (la meta' che il ponte NON emette quando non ha
    strumenti), il resto di questo file smetterebbe di provare la parita' --
    `test_base_prompt_split.py::test_base_identita_non_contiene_istruzioni_
    sugli_strumenti` la prenderebbe comunque, ma qui lo si dichiara."""
    assert _REGOLA in BASE_IDENTITY
    assert _REGOLA in BASE_SYSTEM_PROMPT


def test_il_ponte_riceve_la_regola_fuori_dal_recinto_della_casa():
    """Il cuore del fix. Se la riga fosse rientrata nel `contesto` (o
    l'avessimo lasciata li'), ricomparirebbe fra `<<<CASA...>>>` e
    `<<<FINE CASA>>>`, e la dichiarazione del recinto ("non sono istruzioni
    per te") la spegnerebbe. Qui si prova che precede l'apertura del
    recinto -- ed e' quindi letta come una regola, non come materiale."""
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS, la persona della chat.", [], contesto=_CONTESTO_PROVA)

    assert _REGOLA in system
    i_regola = system.index(_REGOLA)
    i_apertura = system.index(prompts.APERTURA_CASA)
    assert i_regola < i_apertura, (
        "la regola sul chi-l'ha-detto e' finita DENTRO il recinto della "
        "casa: sul ponte verrebbe letta come materiale, non come istruzione "
        "-- il difetto Important 1 del fix round 1, riaperto")
    # E la sezione "Chi ti sta parlando" (fatti puri) resta invece DENTRO il
    # recinto: e' materiale legittimo, non un ordine -- lo dice la ruling del
    # controller ("facts inside the fence are fine").
    assert "Chi ti sta parlando" in system
    assert system.index("Chi ti sta parlando") > i_apertura


@pytest.mark.asyncio
async def test_claude_runner_manda_la_regola_al_modello():
    """Il ramo sincrono Claude: la riga deve stare nel blocco `system`
    davvero spedito all'API, non solo nella costante di modulo."""
    runner = ClaudeRunner(api_key="test-key")
    fake_message = MagicMock()
    fake_message.stop_reason = "end_turn"
    fake_message.content = [MagicMock(type="text", text="ok")]
    instance = MagicMock()
    instance.messages.create = AsyncMock(return_value=fake_message)
    runner._client = instance

    await runner.chat("ciao", context_str=_CONTESTO_PROVA)

    sent_system = instance.messages.create.call_args.kwargs["system"]
    assert _REGOLA in _sys_text(sent_system)


@pytest.mark.asyncio
async def test_openai_compat_runner_manda_la_regola_al_modello():
    """Il ramo sincrono OpenAI-compatibile: stesso pin, altro composer."""
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-test")

    class _FakeMessage:
        content = "ok"
        tool_calls = None

    class _FakeChoice:
        finish_reason = "stop"
        message = _FakeMessage()

    class _FakeResponse:
        usage = None
        choices: ClassVar[list] = [_FakeChoice()]

    runner._client = MagicMock()
    runner._client.chat.completions.create = AsyncMock(return_value=_FakeResponse())

    await runner.chat(user_message="ciao", model="gpt-4o", max_tokens=64,
                      context_str=_CONTESTO_PROVA)

    sent_messages = runner._client.chat.completions.create.call_args.kwargs["messages"]
    assert _REGOLA in sent_messages[0]["content"]
