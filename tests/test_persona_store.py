"""Slice 5 — Lenti + Personas, Task 1 + Task 2.

Task 1: ChatbotEngine is now purely a persona store: create/read/update/delete a
persona without any proactive/action-execution field being required, and no
autonomous scheduling happening as a side effect.

Task 2: trims the `Agent` dataclass itself — `type`, `triggers`,
`action_mode`, `rules`, `states`, `fallback_action`, `budget_eur_limit` are
gone (Task 1 already stopped executing them; nothing read them anymore).
`_save` bumps `schema_version` to 3; `_load` does not migrate — a legacy dict
carrying those fields just has them ignored via the explicit `.get()` field
list, per "no migration" in the brief (Step 1 chose "discard" over "reject").
"""
import json
import pytest
from unittest.mock import AsyncMock

from hiris.app.chatbot_engine import ChatbotEngine, Chatbot


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha, tmp_path):
    return ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))


# fetta E4 Task 3 ("un bot solo"): test_create_persona_without_proactive_fields
# / test_read_persona / test_update_persona / test_delete_persona pinned
# `create_chatbot`/`update_chatbot`/`delete_chatbot` themselves -- gone with
# the three creation paths (wizard, empty editor, chat onboarding) that all
# converged on POST /api/chatbots with `enabled: true` by default, the
# opposite of what the scope prescribes. Verified failing for construction
# (`AttributeError: 'ChatbotEngine' object has no attribute 'create_chatbot'`)
# before deletion. `get_chatbot`/`list_chatbots` themselves are still live
# (see test_get_default_agent-equivalent coverage in test_chatbot_engine.py
# and the persistence round-trip below, both built without create_chatbot).


# ---------------------------------------------------------------------------
# fetta E3 Task 7: il guard "Sentinella _llm_reason (server.py) →
# reasoner.reason still works after run_with_actions dropped its
# action_mode/AZIONI branch" viveva qui. Entrambi gli estremi del percorso
# che pinnava sono usciti per intero in questo task: `_llm_reason` (la
# closure della Sentinella, server.py) e `watcher.reasoner.reason`/
# `SENTINEL_SYSTEM` (l'intero pacchetto watcher/). A quel punto restava
# orfano di ogni chiamante di produzione, dichiarato ma non raccolto
# (fuori dal perimetro del Task 7) -- promessa mantenuta al Task 8 di
# questa fetta: `run_with_actions` e' uscito per intero da ClaudeRunner,
# LLMRouter e OpenAICompatRunner, insieme ai due cataloghi che esistevano
# solo per lui (`EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS`) e alla
# cartella `tools/`.
# ---------------------------------------------------------------------------


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


# fetta E4 Task 3: test_updatable_fields_excludes_removed_fields pinned
# `ChatbotEngine.UPDATABLE_FIELDS`, gone with `update_chatbot` (its only
# reader). Verified failing for construction (`AttributeError: type object
# 'ChatbotEngine' has no attribute 'UPDATABLE_FIELDS'`) before deletion.


def test_persona_with_only_valid_fields_persists_and_reloads(engine):
    """Step 1: a persona built from only the fields the trimmed dataclass
    still has round-trips through _save/_load unchanged.

    fetta E4 Task 3: moved off `create_chatbot` (gone, along with
    `update_chatbot`/`delete_chatbot` -- see the module docstring/comment
    above). The subject here -- `_save`/`_load` round-tripping every field
    the trimmed `Chatbot` dataclass still has -- is unrelated to the CRUD
    HTTP surface and stays alive: built by inserting a `Chatbot` directly
    into `engine._chatbots` and calling `engine._save()`, exactly what
    `create_chatbot` itself used to do internally."""
    persona = Chatbot(
        id="solo-campi-validi",
        name="Solo campi validi",
        system_prompt="Sei utile.",
        allowed_tools=["get_home_status"],
        enabled=True,
        strategic_context="Contesto.",
        allowed_entities=["light.*"],
        allowed_services=[],
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        restrict_to_home=True,
        require_confirmation=True,
        max_chat_turns=5,
        response_mode="compact",
        thinking_budget=1024,
        knowledge_access={"allow_sensitive": True, "kinds": "all"},
    )
    engine._chatbots[persona.id] = persona
    engine._save()

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
    """fetta E4 Task 3: moved off `create_chatbot` (gone) -- `_save`'s
    schema_version bump is independent of how a Chatbot was constructed."""
    engine._chatbots["x"] = Chatbot(
        id="x", name="X", system_prompt="", allowed_tools=[], enabled=True,
    )
    engine._save()
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
