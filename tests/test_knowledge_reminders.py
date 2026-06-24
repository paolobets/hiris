from datetime import date
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reminders import due_obligations_to_notify


def test_due_within_horizon(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-03")
    store.add_item(kind="obligation", content="Lontano", due_date="2026-09-01")
    out = due_obligations_to_notify(store, today=date(2026, 6, 30), horizon_days=7)
    assert [o["content"] for o in out] == ["TARI"]
    store.close()
