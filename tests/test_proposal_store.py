import pytest
from datetime import datetime, timezone, timedelta
from hiris.app.proxy.proposal_store import ProposalStore


@pytest.fixture
def store(tmp_path):
    s = ProposalStore(
        db_path=str(tmp_path / "proposals.db"),
        scheduler=None,
    )
    yield s
    s.close()


def _sample_proposal(**overrides):
    base = {
        "type": "ha_automation",
        "name": "Luci mezzanotte",
        "description": "Spegne le luci del soggiorno a mezzanotte",
        "config": {"alias": "Luci mezzanotte", "trigger": [], "action": []},
        "routing_reason": "Regola semplice: trigger orario + azione diretta",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_save_and_get(store):
    pid = await store.save(_sample_proposal())
    proposal = await store.get(pid)
    assert proposal is not None
    assert proposal["status"] == "pending"
    assert proposal["name"] == "Luci mezzanotte"


@pytest.mark.asyncio
async def test_list_by_status(store):
    await store.save(_sample_proposal(name="A"))
    await store.save(_sample_proposal(name="B"))
    proposals = await store.list(status="pending")
    assert len(proposals) == 2


@pytest.mark.asyncio
async def test_reject_proposal(store):
    pid = await store.save(_sample_proposal())
    result = await store.reject(pid)
    assert result is True
    assert (await store.get(pid))["status"] == "rejected"


@pytest.mark.asyncio
async def test_apply_proposal(store):
    pid = await store.save(_sample_proposal())
    result = await store.apply(pid)
    assert result is True
    assert (await store.get(pid))["status"] == "applied"


@pytest.mark.asyncio
async def test_lifecycle_pending_to_archived(store):
    pid = await store.save(_sample_proposal())
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute(
        "UPDATE automation_proposals SET created_at = ? WHERE id = ?",
        (cutoff, pid),
    )
    store._conn.commit()
    store._run_lifecycle()
    assert (await store.get(pid))["status"] == "archived"


@pytest.mark.asyncio
async def test_lifecycle_archived_to_deleted(store):
    pid = await store.save(_sample_proposal())
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute(
        "UPDATE automation_proposals SET status = 'archived', created_at = ?, archived_at = ? WHERE id = ?",
        (old_ts, old_ts, pid),
    )
    store._conn.commit()
    store._run_lifecycle()
    assert (await store.get(pid)) is None


@pytest.mark.asyncio
async def test_applied_never_deleted(store):
    pid = await store.save(_sample_proposal())
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute(
        "UPDATE automation_proposals SET status = 'applied', created_at = ? WHERE id = ?",
        (old_ts, pid),
    )
    store._conn.commit()
    store._run_lifecycle()
    assert (await store.get(pid)) is not None


# ------------------------------------------------------------------
# Edge-case tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_returns_false_for_missing_id(store):
    result = await store.apply("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_reject_returns_false_for_missing_id(store):
    result = await store.reject("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_list_empty_returns_empty_list(store):
    result = await store.list()
    assert result == []


@pytest.mark.asyncio
async def test_get_missing_returns_none(store):
    result = await store.get("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_save_raises_on_missing_required_fields(store):
    with pytest.raises(ValueError, match="missing required fields"):
        await store.save({"name": "Incomplete"})
