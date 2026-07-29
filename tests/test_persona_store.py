"""Slice 5 — Lenti + Personas, Task 1 + Task 2.

Task 1: ChatbotEngine is now purely a persona store: create/read/update/delete a
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

Task 2: trims the `Agent` dataclass itself — `type`, `triggers`,
`action_mode`, `rules`, `states`, `fallback_action`, `budget_eur_limit` are
gone (Task 1 already stopped executing them; nothing read them anymore).
`_save` bumps `schema_version` to 3; `_load` does not migrate — a legacy dict
carrying those fields just has them ignored via the explicit `.get()` field
list, per "no migration" in the brief (Step 1 chose "discard" over "reject").
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app.chatbot_engine import ChatbotEngine, Chatbot


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha, tmp_path):
    return ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))


# ---------------------------------------------------------------------------
# Persona store: create / read / update / delete without proactive fields
# ---------------------------------------------------------------------------

def test_create_persona_without_proactive_fields(engine):
    """A persona can be created with no type/triggers/rules/action_mode in
    the payload at all — those are proactive-only concerns the engine no
    longer executes, and (Task 2) no longer even exist on the dataclass. A
    stray "type" key in the payload is silently ignored (create_agent never
    reads it)."""
    persona = engine.create_chatbot({
        "name": "Assistente di casa",
        "type": "chat",
        "system_prompt": "Sei l'assistente per la casa.",
        "allowed_tools": ["get_home_status"],
    })
    assert persona.id in engine.list_chatbots()
    assert not hasattr(persona, "type")
    assert persona.name == "Assistente di casa"


def test_read_persona(engine):
    persona = engine.create_chatbot({
        "name": "Cuoco", "type": "chat",
        "system_prompt": "Suggerisci ricette.", "allowed_tools": [],
    })
    fetched = engine.get_chatbot(persona.id)
    assert fetched is persona
    assert fetched.system_prompt == "Suggerisci ricette."


def test_update_persona(engine):
    persona = engine.create_chatbot({
        "name": "Cuoco", "type": "chat",
        "system_prompt": "v1", "allowed_tools": [],
    })
    updated = engine.update_chatbot(persona.id, {"system_prompt": "v2"})
    assert updated.system_prompt == "v2"


def test_delete_persona(engine):
    persona = engine.create_chatbot({
        "name": "Temporanea", "type": "chat",
        "system_prompt": "", "allowed_tools": [],
    })
    assert engine.delete_chatbot(persona.id) is True
    assert persona.id not in engine.list_chatbots()


@pytest.mark.asyncio
async def test_run_persona_produces_text_only_no_actions(engine):
    """Manual "run" of a persona calls the plain chat() path and returns text
    — there is no action/rules execution left in ChatbotEngine to trigger."""
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Ciao! Come posso aiutarti?")
    mock_runner.run_with_actions = AsyncMock(return_value=("should not be used", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    persona = engine.create_chatbot({
        "name": "Assistente", "type": "chat",
        "system_prompt": "Sei utile.", "allowed_tools": [],
    })
    result = await engine.run_chatbot(persona)

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
    """Mirrors the ANONYMOUS/UNSCOPED shape of server.py's `_llm_reason`
    closure -- the one every built-in sentinel caller still uses (post
    Slice-5 edit): no `action_mode` kwarg, `allowed_tools=[]`, unwraps the
    (text, structured) tuple and returns only the text.

    Agenti v1.1 Fase 2 Task 3 added optional `agent_id`/`allowed_entities`/
    `allowed_services` to the real closure, supplied ONLY by an Agentbot with
    a perimeter; they are deliberately absent here because this test guards
    the run_with_actions -> reason() path, not the perimeter propagation
    (that lives in tests/test_run_agentbot.py, against the REAL closure)."""
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


# ---------------------------------------------------------------------------
# Task 2: Agent dataclass trimmed to a persona (proactive fields removed)
# ---------------------------------------------------------------------------

_REMOVED_FIELDS = (
    "type", "triggers", "action_mode", "rules", "states",
    "fallback_action", "budget_eur_limit",
)


def test_agent_dataclass_has_no_proactive_fields():
    """The seven proactive-only fields are gone from the dataclass — not just
    unused, actually absent (no attribute, no default)."""
    field_names = {f for f in Chatbot.__dataclass_fields__}
    for removed in _REMOVED_FIELDS:
        assert removed not in field_names


def test_updatable_fields_excludes_removed_fields():
    for removed in _REMOVED_FIELDS:
        assert removed not in ChatbotEngine.UPDATABLE_FIELDS


def test_persona_with_only_valid_fields_persists_and_reloads(engine):
    """Step 1: a persona built from only the fields the trimmed dataclass
    still has round-trips through _save/_load unchanged."""
    persona = engine.create_chatbot({
        "name": "Solo campi validi",
        "system_prompt": "Sei utile.",
        "allowed_tools": ["get_home_status"],
        "strategic_context": "Contesto.",
        "allowed_entities": ["light.*"],
        "allowed_services": [],
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2048,
        "restrict_to_home": True,
        "require_confirmation": True,
        "max_chat_turns": 5,
        "response_mode": "compact",
        "thinking_budget": 1024,
        "knowledge_access": {"allow_sensitive": True, "kinds": "all"},
    })

    reloaded_engine = ChatbotEngine(ha_client=engine._ha, data_path=engine._data_path)
    reloaded_engine._load()
    reloaded = reloaded_engine.get_chatbot(persona.id)

    assert reloaded is not None
    assert reloaded.name == "Solo campi validi"
    assert reloaded.system_prompt == "Sei utile."
    assert reloaded.allowed_tools == ["get_home_status"]
    assert reloaded.strategic_context == "Contesto."
    assert reloaded.allowed_entities == ["light.*"]
    assert reloaded.model == "claude-haiku-4-5-20251001"
    assert reloaded.max_tokens == 2048
    assert reloaded.restrict_to_home is True
    assert reloaded.require_confirmation is True
    assert reloaded.max_chat_turns == 5
    assert reloaded.response_mode == "compact"
    assert reloaded.thinking_budget == 1024
    assert reloaded.knowledge_access == {"allow_sensitive": True, "kinds": "all"}


def test_save_bumps_schema_version_to_4(engine, tmp_path):
    engine.create_chatbot({"name": "X", "system_prompt": "", "allowed_tools": []})
    data = json.loads((tmp_path / "agents.json").read_text())
    assert data["schema_version"] == 4


def test_load_legacy_dict_with_proactive_fields_discards_them(mock_ha, tmp_path):
    """A v2 (or older) agents.json entry that still carries the removed
    proactive fields loads fine — _load()'s explicit per-field `.get()` list
    simply never reads `type`/`triggers`/`action_mode`/`rules`/`states`/
    `fallback_action`/`budget_eur_limit`, so they're silently discarded
    rather than migrated or rejected."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 2,
        "agents": [{
            "id": "legacy-proactive-001",
            "name": "Legacy Proactive",
            "type": "agent",
            "triggers": [{"type": "schedule", "interval_minutes": 5}],
            "action_mode": "configured",
            "rules": [{"states": ["ANOMALIA"], "actions": ["turn_on switch.x"]}],
            "states": ["OK", "ANOMALIA"],
            "fallback_action": {"service": "notify.notify"},
            "budget_eur_limit": 2.5,
            "system_prompt": "loaded",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()

    agent = eng.get_chatbot("legacy-proactive-001")
    assert agent is not None
    assert agent.name == "Legacy Proactive"
    assert agent.system_prompt == "loaded"
    for removed in _REMOVED_FIELDS:
        assert not hasattr(agent, removed)


@pytest.mark.asyncio
async def test_seed_default_agent_is_a_persona_with_no_type_field(mock_ha, tmp_path):
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_chatbot()

    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID
    default = eng._chatbots[DEFAULT_CHATBOT_ID]
    assert default.is_default is True
    assert not hasattr(default, "type")
    eng._scheduler.shutdown(wait=False)
