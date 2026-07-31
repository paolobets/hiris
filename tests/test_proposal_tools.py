import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.proxy.proposal_store import ProposalStore
from hiris.app.tools.proposal_tools import create_automation_proposal


@pytest.fixture
def store(tmp_path):
    s = ProposalStore(
        db_path=str(tmp_path / "proposals.db"),
        scheduler=None,
    )
    yield s
    s.close()


def _sample_args(**overrides):
    base = {
        "proposal_type": "ha_automation",
        "name": "Luci off mezzanotte",
        "description": "Spegne le luci del soggiorno a mezzanotte",
        "config": {"alias": "Luci off", "trigger": [], "action": []},
        "routing_reason": "Trigger orario semplice — Layer 1 è sufficiente",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_proposal_injects_automation_id_into_config(store):
    """MODIFY: automation_id is carried INTO the persisted config as 'id', so
    apply overwrites that automation instead of duplicating it."""
    res = await create_automation_proposal(store, **_sample_args(automation_id="1699999999"))
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "1699999999"


@pytest.mark.asyncio
async def test_create_proposal_without_automation_id_leaves_config(store):
    """NEW: no automation_id → no 'id' injected → apply mints a fresh one."""
    res = await create_automation_proposal(store, **_sample_args())
    saved = await store.get(res["proposal_id"])
    assert "id" not in saved["config"]


@pytest.mark.asyncio
async def test_create_proposal_keeps_config_id_as_modify(store):
    """MODIFY (bug #2 fix): l'LLM legge un'automazione con get_automation_config
    e ne riporta il config INCLUSO l'id, ma spesso NON compila il param separato
    automation_id. Prima l'id veniva strippato -> l'apply coniava un id nuovo ->
    DUPLICATO invece di overwrite. Ora l'id presente nel config viene PRESERVATO
    (= modifica). Per una NUOVA automazione l'LLM omette l'id."""
    args = _sample_args(config={"id": "1699999999", "alias": "Modifica", "trigger": [], "action": []})
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "1699999999"


@pytest.mark.asyncio
async def test_create_proposal_explicit_automation_id_beats_config_id(store):
    """L'automation_id esplicito vince sull'id copiato nel config."""
    args = _sample_args(config={"id": "111", "alias": "x", "trigger": [], "action": []},
                        automation_id="999")
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "999"


@pytest.mark.asyncio
async def test_create_proposal_normalizes_automation_type_alias(store):
    """BUG #2 root cause: il Chatbot ha usato type='automation' (alias) invece di
    'ha_automation' -> l'apply cadeva nel ramo status-only che non scrive in HA.
    Ora l'alias e' normalizzato a 'ha_automation'."""
    res = await create_automation_proposal(store, **_sample_args(proposal_type="automation"))
    saved = await store.get(res["proposal_id"])
    assert saved["type"] == "ha_automation"


@pytest.mark.asyncio
async def test_create_proposal_rejects_unknown_type(store):
    """Un tipo davvero sconosciuto non viene salvato in silenzio (che poi
    sparirebbe nel ramo status-only): errore chiaro, niente save."""
    res = await create_automation_proposal(store, **_sample_args(proposal_type="banana"))
    assert "error" in res
    assert "proposal_id" not in res


@pytest.mark.asyncio
async def test_create_proposal_hiris_agent_config_untouched(store):
    """A hiris_agent proposal must not have its config['id'] touched (the id
    logic is scoped to ha_automation only)."""
    args = _sample_args(proposal_type="hiris_agent",
                        config={"id": "keep-me", "role": "x"}, automation_id="999")
    res = await create_automation_proposal(store, **args)
    saved = await store.get(res["proposal_id"])
    assert saved["config"]["id"] == "keep-me"


@pytest.mark.asyncio
async def test_create_proposal_returns_pending(store):
    result = await create_automation_proposal(store, **_sample_args())
    assert "proposal_id" in result
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_create_proposal_saved_in_store(store):
    args = _sample_args(name="Test automation")
    result = await create_automation_proposal(store, **args)
    saved = await store.get(result["proposal_id"])
    assert saved is not None
    assert saved["name"] == "Test automation"


@pytest.mark.asyncio
async def test_create_proposal_no_store_returns_error():
    result = await create_automation_proposal(None, **_sample_args())
    assert "error" in result


@pytest.mark.asyncio
async def test_create_proposal_exception_returns_error():
    """No-leak policy (mirrors dispatcher.py's catch-all): the raw exception
    text must never reach the caller, only a generic-but-useful message."""
    mock_store = MagicMock()
    mock_store.save = AsyncMock(side_effect=Exception("db error"))
    result = await create_automation_proposal(mock_store, **_sample_args())
    assert "error" in result
    assert "db error" not in result["error"]
