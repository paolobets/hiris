import pytest
from datetime import date
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reminders import due_obligations_to_notify, run_due_reminders


def test_due_within_horizon(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-03")
    store.add_item(kind="obligation", content="Lontano", due_date="2026-09-01")
    out = due_obligations_to_notify(store, today=date(2026, 6, 30), horizon_days=7)
    assert [o["content"] for o in out] == ["TARI"]
    store.close()


@pytest.mark.asyncio
async def test_run_due_reminders_notifies_due_only(tmp_path):
    """run_due_reminders must call notify once for the TARI item (due within 7 days)
    and ignore the far-future obligation; it must return 1."""
    store = KnowledgeStore(str(tmp_path / "reminders.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-03")
    store.add_item(kind="obligation", content="Lontano", due_date="2026-09-01")

    captured: list[dict] = []

    async def fake_notify(item: dict) -> None:
        captured.append(item)

    count = await run_due_reminders(
        store, fake_notify, today=date(2026, 6, 30), horizon_days=7
    )

    assert count == 1
    assert len(captured) == 1
    assert captured[0]["content"] == "TARI"
    store.close()
