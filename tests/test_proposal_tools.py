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
    mock_store = MagicMock()
    mock_store.save = AsyncMock(side_effect=Exception("db error"))
    result = await create_automation_proposal(mock_store, **_sample_args())
    assert "error" in result
    assert "db error" in result["error"]
