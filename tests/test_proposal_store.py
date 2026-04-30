import pytest
from datetime import datetime, timezone, timedelta
from hiris.app.proxy.proposal_store import ProposalStore


@pytest.fixture
def store(tmp_path):
    s = ProposalStore(
        db_path=str(tmp_path / "proposals.db"),
        scheduler=None,
    )
    return s


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


def test_save_and_get(store):
    pid = store.save(_sample_proposal())
    proposal = store.get(pid)
    assert proposal is not None
    assert proposal["status"] == "pending"
    assert proposal["name"] == "Luci mezzanotte"


def test_list_by_status(store):
    store.save(_sample_proposal(name="A"))
    store.save(_sample_proposal(name="B"))
    proposals = store.list(status="pending")
    assert len(proposals) == 2


def test_reject_proposal(store):
    pid = store.save(_sample_proposal())
    result = store.reject(pid)
    assert result is True
    assert store.get(pid)["status"] == "rejected"


def test_apply_proposal(store):
    pid = store.save(_sample_proposal())
    result = store.apply(pid)
    assert result is True
    assert store.get(pid)["status"] == "applied"


def test_lifecycle_pending_to_archived(store):
    pid = store.save(_sample_proposal())
    # Forza created_at a 8 giorni fa
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute(
        "UPDATE automation_proposals SET created_at = ? WHERE id = ?",
        (cutoff, pid),
    )
    store._conn.commit()
    store._run_lifecycle()
    assert store.get(pid)["status"] == "archived"


def test_lifecycle_archived_to_deleted(store):
    pid = store.save(_sample_proposal())
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute(
        "UPDATE automation_proposals SET status = 'archived', created_at = ?, archived_at = ? WHERE id = ?",
        (old_ts, old_ts, pid),
    )
    store._conn.commit()
    store._run_lifecycle()
    assert store.get(pid) is None


def test_applied_never_deleted(store):
    pid = store.save(_sample_proposal())
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store._conn.execute(
        "UPDATE automation_proposals SET status = 'applied', created_at = ? WHERE id = ?",
        (old_ts, pid),
    )
    store._conn.commit()
    store._run_lifecycle()
    assert store.get(pid) is not None
