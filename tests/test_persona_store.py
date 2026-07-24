"""Slice 5 — Lenti + Personas, Task 1.

AgentEngine is now purely a persona store: create/read/update/delete a
persona without any proactive/action-execution field being required, and no
autonomous scheduling happening as a side effect.

Also guards the one thing that must NOT break when `run_with_actions` loses
its action_mode/AZIONI branch: the Sentinella's `_llm_reason` (server.py) →
`watcher.reasoner.reason` path. `_llm_reason` calls
`runner.run_with_actions(user_message=..., system_prompt=..., allowed_tools=[],
model=..., max_tokens=..., agent_type="agent")` (no `action_mode` kwarg since
Slice 5) and feeds the returned text into `reason()`, which parses its own
```json``` block independently of anything `run_with_actions` does to the
prompt. This test replicates that exact call shape against the real
`ClaudeRunner.run_with_actions` (mocking only the underlying `chat()` call) to
prove the reasoner still produces a Decision.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app.agent_engine import AgentEngine, Agent


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha, tmp_path):
    return AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))


# ---------------------------------------------------------------------------
# Persona store: create / read / update / delete without proactive fields
# ---------------------------------------------------------------------------

def test_create_persona_without_proactive_fields(engine):
    """A persona (type='chat') can be created with no triggers/rules/action_mode
    in the payload at all — those are proactive-only concerns the engine no
    longer executes."""
    persona = engine.create_agent({
        "name": "Assistente di casa",
        "type": "chat",
        "system_prompt": "Sei l'assistente per la casa.",
        "allowed_tools": ["get_home_status"],
    })
    assert persona.id in engine.list_agents()
    assert persona.type == "chat"
    assert persona.name == "Assistente di casa"


def test_read_persona(engine):
    persona = engine.create_agent({
        "name": "Cuoco", "type": "chat",
        "system_prompt": "Suggerisci ricette.", "allowed_tools": [],
    })
    fetched = engine.get_agent(persona.id)
    assert fetched is persona
    assert fetched.system_prompt == "Suggerisci ricette."


def test_update_persona(engine):
    persona = engine.create_agent({
        "name": "Cuoco", "type": "chat",
        "system_prompt": "v1", "allowed_tools": [],
    })
    updated = engine.update_agent(persona.id, {"system_prompt": "v2"})
    assert updated.system_prompt == "v2"


def test_delete_persona(engine):
    persona = engine.create_agent({
        "name": "Temporanea", "type": "chat",
        "system_prompt": "", "allowed_tools": [],
    })
    assert engine.delete_agent(persona.id) is True
    assert persona.id not in engine.list_agents()


@pytest.mark.asyncio
async def test_run_persona_produces_text_only_no_actions(engine):
    """Manual "run" of a persona calls the plain chat() path and returns text
    — there is no action/rules execution left in AgentEngine to trigger."""
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Ciao! Come posso aiutarti?")
    mock_runner.run_with_actions = AsyncMock(return_value=("should not be used", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    persona = engine.create_agent({
        "name": "Assistente", "type": "chat",
        "system_prompt": "Sei utile.", "allowed_tools": [],
    })
    result = await engine.run_agent(persona)

    assert result == "Ciao! Come posso aiutarti?"
    mock_runner.chat.assert_called_once()
    mock_runner.run_with_actions.assert_not_called()


# ---------------------------------------------------------------------------
# Guard: Sentinella _llm_reason (server.py) → reasoner.reason still works
# after run_with_actions dropped its action_mode/AZIONI branch.
# ---------------------------------------------------------------------------

from hiris.app.claude_runner import ClaudeRunner
from hiris.app.watcher.signals import WakeEvent
from hiris.app.watcher.reasoner import reason, SENTINEL_SYSTEM


async def _llm_reason_like_server(runner, system, user, *, model, max_tokens):
    """Mirrors server.py's `_llm_reason` closure verbatim (post Slice-5 edit):
    no `action_mode` kwarg, `allowed_tools=[]`, unwraps the (text, structured)
    tuple and returns only the text."""
    out = await runner.run_with_actions(
        user_message=user, system_prompt=system,
        allowed_tools=[], model=model, max_tokens=max_tokens, agent_type="agent")
    if isinstance(out, tuple):
        return out[0] or ""
    return out or ""


@pytest.mark.asyncio
async def test_llm_reason_via_run_with_actions_still_produces_decision():
    """End-to-end guard: ClaudeRunner.run_with_actions (simplified, no
    action_mode) feeding the Sentinella reasoner must still yield a Decision
    parsed from the model's ```json``` block, unmodified by any AZIONI/
    VALUTAZIONE prompt injection (there is none anymore)."""
    runner = ClaudeRunner.__new__(ClaudeRunner)
    llm_text = (
        "Il livello della batteria è basso ma non critico.\n"
        "```json\n"
        + json.dumps({
            "verdict": "anomalia",
            "severity": "info",
            "message": "Batteria al 8%, sostituirla presto.",
            "action": None,
        })
        + "\n```"
    )
    runner.chat = AsyncMock(return_value=llm_text)

    we = WakeEvent("battery", "sensor.porta_garage_battery", "info", {"pct": 8}, 1.0)

    async def llm_reason(system, user, *, model, max_tokens):
        return await _llm_reason_like_server(runner, system, user, model=model, max_tokens=max_tokens)

    decision = await reason(
        we, gather_context=lambda w: {"friendly_name": "Porta garage"},
        llm_reason=llm_reason, system=SENTINEL_SYSTEM,
    )

    assert decision.verdict == "anomalia"
    assert decision.severity == "info"
    assert "Batteria al 8%" in decision.message

    # The reasoner's system prompt (SENTINEL_SYSTEM, already asking for a
    # ```json``` block) must reach chat() untouched — run_with_actions no
    # longer appends VALUTAZIONE/AZIONI instructions to it.
    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["system_prompt"] == SENTINEL_SYSTEM
    assert "AZIONI:" not in call_kwargs["system_prompt"]
    # allowed_tools=[] is falsy, so run_with_actions keeps the full
    # EVALUATION_ONLY_TOOLS whitelist (read-only) rather than narrowing to
    # nothing — this is what makes allowed_tools=[] a safe "no actuation"
    # signal rather than a "no tools at all" one.
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS
    assert set(call_kwargs["allowed_tools"]) == set(EVALUATION_ONLY_TOOLS)
