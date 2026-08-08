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


# fetta E4 Task 3 ("un bot solo"): `create_chatbot`/`update_chatbot`/
# `delete_chatbot` are gone -- the three creation paths that survived the E3
# (wizard, empty editor, chat onboarding) all converged on POST
# /api/chatbots with `enabled: true` by default, the opposite of what the
# scope prescribes; killing the route kills them together. Every test that
# built its fixture by calling one of those three methods is gone with them
# (verified failing for construction --
# `AttributeError: 'ChatbotEngine' object has no attribute 'create_chatbot'`
# -- before deletion): test_create_agent_stores_agent,
# test_list_agents_returns_dict, test_delete_agent_removes_agent,
# test_create_agent_with_new_fields, test_create_agent_new_fields_default_empty,
# test_create_agent_thinking_budget_default_zero,
# test_create_agent_thinking_budget_persists, test_update_agent_thinking_budget,
# test_create_agent_thinking_budget_negative_clamped_to_zero,
# test_update_agent_new_fields, test_list_agents_includes_new_fields,
# test_create_agent_persists_to_file, test_delete_agent_removes_from_file,
# test_update_agent_persists_to_file, test_delete_default_agent_returns_false
# (calls delete_chatbot directly), test_get_agent_returns_correct,
# test_agent_model_defaults_to_auto, test_agent_per_agent_config_persists,
# test_agent_update_model_and_max_tokens,
# test_agent_require_confirmation_defaults_false,
# test_update_agent_require_confirmation, test_agent_require_confirmation_persists,
# test_execution_log_not_in_updatable_fields (UPDATABLE_FIELDS itself is
# gone), test_execution_log_persists_across_reload,
# test_update_agent_without_require_confirmation_preserves_existing_value,
# test_create_agent_without_require_confirmation_defaults_false,
# test_update_agent_with_require_confirmation_false_from_ui,
# test_execution_log_initialises_empty_for_new_agents,
# test_agent_knowledge_access_default_and_update.
#
# What survives: `_load`/`_save`/migration round-trips built from literal
# JSON (never call the retired methods), `get_chatbot`/`get_default_chatbot`/
# `set_entity_cache` exercised against chatbots inserted directly into
# `engine._chatbots` (still live -- `get_chatbot` is read by `handle_chat`
# and by `_seed_default_chatbot`; `list_chatbots`/`get_chatbot_status` feed
# `handle_list_chatbots`, the compatibility surface).


def test_load_agents_from_existing_file(mock_ha, tmp_path):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "agents": [{
            "id": "loaded-001",
            "name": "Loaded Agent",
            "type": "monitor",
            "trigger": {"type": "schedule", "interval_minutes": 10},
            "system_prompt": "loaded",
            "allowed_tools": [],
            "enabled": False,
            "is_default": False,
            "last_run": None,
            "last_result": None,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }]
    }))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    assert "loaded-001" in eng._chatbots
    assert eng._chatbots["loaded-001"].name == "Loaded Agent"


def test_load_missing_file_is_noop(mock_ha, tmp_path):
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "nonexistent.json"))
    eng._load()  # must not raise
    assert len(eng._chatbots) == 0


def test_load_agent_with_legacy_tool_names_maps_to_current_names(mock_ha, tmp_path):
    """Fix 4 (Important, whole-branch review): a Chatbot persisted BEFORE the
    memoria-unica merge (Task 2) may still name the retired
    recall_knowledge/save_knowledge tools in allowed_tools (they were two
    separate checkboxes). fetta E3 Task 9: claude_runner.py has no
    allowed_tools filter anymore (the Task 8 catalog it used to gate is
    gone, and Task 9 dropped the now-inert parameter itself) -- today
    `Chatbot.allowed_tools` is only persisted config feeding the checkbox
    catalog in static/config/templates.js (stays until E5). Loading must
    still rewrite the old names to recall_memory/save_memory so that editor
    doesn't show checkboxes for tool names that no longer exist."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 4,
        "chatbots": [{
            "id": "legacy-001",
            "name": "Legacy Bot",
            "system_prompt": "legacy",
            "allowed_tools": ["get_home_status", "recall_knowledge", "save_knowledge"],
            "enabled": True,
            "is_default": False,
        }]
    }))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    loaded = eng._chatbots["legacy-001"]
    assert loaded.allowed_tools == ["get_home_status", "recall_memory", "save_memory"]


def test_load_agent_with_both_legacy_and_current_names_dedupes(mock_ha, tmp_path):
    """A config that (however it happened) carries BOTH the legacy and the
    current name for the same tool must not end up with a duplicate --
    normalize_tool_names is idempotent and de-duplicates on the mapped name,
    preserving first-seen order."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({
        "schema_version": 4,
        "chatbots": [{
            "id": "legacy-002",
            "name": "Legacy Bot 2",
            "system_prompt": "legacy",
            "allowed_tools": ["recall_knowledge", "recall_memory", "save_knowledge"],
            "enabled": True,
            "is_default": False,
        }]
    }))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._load()
    loaded = eng._chatbots["legacy-002"]
    assert loaded.allowed_tools == ["recall_memory", "save_memory"]


@pytest.mark.asyncio
async def test_default_agent_seeded_after_load(mock_ha, tmp_path):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_chatbot()
    assert DEFAULT_CHATBOT_ID in eng._chatbots
    assert eng._chatbots[DEFAULT_CHATBOT_ID].is_default is True
    assert not hasattr(eng._chatbots[DEFAULT_CHATBOT_ID], "type")
    eng._scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_default_agent_not_seeded_if_already_present(mock_ha, tmp_path):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"schema_version": 1, "agents": [{
        "id": DEFAULT_CHATBOT_ID, "name": "Custom HIRIS", "type": "chat",
        "trigger": {"type": "manual"}, "system_prompt": "custom",
        "allowed_tools": [], "enabled": True, "is_default": True,
        "last_run": None, "last_result": None, "strategic_context": "",
        "allowed_entities": [], "allowed_services": [],
    }]}))
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(path))
    eng._scheduler.start()
    eng._load()
    eng._seed_default_chatbot()
    assert eng._chatbots[DEFAULT_CHATBOT_ID].name == "Custom HIRIS"
    eng._scheduler.shutdown(wait=False)


def test_get_default_agent(engine):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS",
        system_prompt="",
        allowed_tools=[], enabled=True, is_default=True,
    )
    assert engine.get_default_chatbot() is engine._chatbots[DEFAULT_CHATBOT_ID]


# ---------------------------------------------------------------------------
# Backward-compatibility / no-regression tests (Cycle 3 → v0.1.1)
# These tests codify the contracts that must hold for users upgrading from
# v0.1.0 agents.json files that do not contain the new Cycle 3 fields.
# ---------------------------------------------------------------------------

def test_load_old_json_without_cycle3_fields_defaults_safely(mock_ha, tmp_path):
    """agents.json from v0.1.0 (no require_confirmation / execution_log) loads without error."""
    data_path = str(tmp_path / "agents.json")
    old_payload = {
        "schema_version": 1,
        "agents": [{
            "id": "legacy-001",
            "name": "Legacy Agent",
            "type": "monitor",
            "trigger": {"type": "schedule", "interval_minutes": 10},
            "system_prompt": "do stuff",
            "allowed_tools": [],
            "enabled": False,
            "last_run": None,
            "last_result": None,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
            "is_default": False,
            "model": "auto",
            "max_tokens": 4096,
            "restrict_to_home": False,
            # NO require_confirmation, NO execution_log  ← v0.1.0 file
        }],
    }
    with open(data_path, "w") as f:
        json.dump(old_payload, f)

    eng = ChatbotEngine(ha_client=mock_ha, data_path=data_path)
    eng._load()
    agent = eng.get_chatbot("legacy-001")
    assert agent is not None
    assert agent.require_confirmation is False
    assert agent.execution_log == []


def _make_entity_cache(entities):
    cache = MagicMock()
    cache.get_all_useful.return_value = entities
    return cache


def test_set_entity_cache_stores_cache(engine):
    cache = _make_entity_cache([])
    engine.set_entity_cache(cache)
    assert engine._entity_cache is cache


# ---------------------------------------------------------------------------
# SP-4 Fase A Task 1: one-time agents.json -> chatbots.json migration
# ---------------------------------------------------------------------------

def test_load_migrates_legacy_agents_json_to_chatbots_json(mock_ha, tmp_path):
    """When chatbots.json is absent but a legacy agents.json sits next to it,
    _load() must migrate it once (rename the key, bump schema_version, write
    chatbots.json) and load the chatbots from the migrated file — idempotent,
    non-fatal, no data loss."""
    legacy_path = tmp_path / "agents.json"
    legacy_path.write_text(json.dumps({
        "schema_version": 3,
        "agents": [{
            "id": "legacy-chat-001",
            "name": "Legacy Chatbot",
            "system_prompt": "hello",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    chatbots_path = tmp_path / "chatbots.json"
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng._load()

    # Migrated file now exists on disk, in the new shape.
    assert chatbots_path.exists()
    migrated = json.loads(chatbots_path.read_text())
    assert migrated["schema_version"] == 4
    assert any(c["id"] == "legacy-chat-001" for c in migrated["chatbots"])
    assert "agents" not in migrated

    # And the engine loaded the chatbot from the migrated file.
    chatbot = eng.get_chatbot("legacy-chat-001")
    assert chatbot is not None
    assert chatbot.name == "Legacy Chatbot"
    assert chatbot.system_prompt == "hello"


def test_load_migration_is_idempotent_and_non_fatal(mock_ha, tmp_path):
    """A second _load() call after migration must not re-migrate (chatbots.json
    already exists) and must not touch/require the legacy file any further."""
    legacy_path = tmp_path / "agents.json"
    legacy_path.write_text(json.dumps({
        "schema_version": 3,
        "agents": [{
            "id": "legacy-chat-002",
            "name": "Legacy Chatbot 2",
            "system_prompt": "",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    chatbots_path = tmp_path / "chatbots.json"
    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng._load()
    first_migrated_mtime = chatbots_path.stat().st_mtime_ns

    # Delete the legacy file to prove the second _load() does not depend on it.
    legacy_path.unlink()
    eng2 = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng2._load()  # must not raise even though agents.json is now gone

    assert eng2.get_chatbot("legacy-chat-002") is not None
    # chatbots.json was not rewritten by the second _load() (no re-migration).
    assert chatbots_path.stat().st_mtime_ns == first_migrated_mtime


def test_load_no_migration_when_chatbots_json_already_present(mock_ha, tmp_path):
    """If chatbots.json already exists, a sibling agents.json (however stale)
    must be ignored entirely — no migration, no overwrite."""
    (tmp_path / "agents.json").write_text(json.dumps({
        "schema_version": 3,
        "agents": [{
            "id": "should-not-load",
            "name": "Stale",
            "system_prompt": "",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))
    chatbots_path = tmp_path / "chatbots.json"
    chatbots_path.write_text(json.dumps({
        "schema_version": 4,
        "chatbots": [{
            "id": "current-chat",
            "name": "Current",
            "system_prompt": "",
            "allowed_tools": [],
            "enabled": True,
            "is_default": False,
            "strategic_context": "",
            "allowed_entities": [],
            "allowed_services": [],
        }],
    }))

    eng = ChatbotEngine(ha_client=mock_ha, data_path=str(chatbots_path))
    eng._load()

    assert eng.get_chatbot("current-chat") is not None
    assert eng.get_chatbot("should-not-load") is None
