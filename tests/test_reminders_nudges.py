from datetime import date

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reminders import (
    _URGENT_THRESHOLDS,
    ReminderSeen,
    due_nudges,
    urgency_of,
)


def test_urgent_thresholds_order():
    assert _URGENT_THRESHOLDS == ["overdue", "today", "tomorrow"]


def test_urgency_of_overdue_today_tomorrow_and_beyond():
    today = date(2026, 7, 25)
    assert urgency_of("2026-07-24", today) == "overdue"
    assert urgency_of("2026-07-25", today) == "today"
    assert urgency_of("2026-07-26", today) == "tomorrow"
    assert urgency_of("2026-07-27", today) is None


def test_urgency_of_invalid_or_none_never_crashes():
    today = date(2026, 7, 25)
    assert urgency_of(None, today) is None
    assert urgency_of("", today) is None
    assert urgency_of("not-a-date", today) is None
    assert urgency_of("2026-13-40", today) is None


def test_due_nudges_returns_tomorrow_then_dedups_after_mark(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Bolletta", status="approved",
                    due_date="2026-07-26", sensitivity="normal")
    seen = ReminderSeen(str(tmp_path / "data"))

    nudges = due_nudges(store, today=today, seen=seen)
    assert len(nudges) == 1
    assert nudges[0]["threshold"] == "tomorrow"
    assert nudges[0]["item"]["content"] == "Bolletta"
    key = nudges[0]["key"]

    # due_nudges never marks by itself — calling again returns the same nudge.
    again = due_nudges(store, today=today, seen=seen)
    assert len(again) == 1

    seen.mark(key, "tomorrow")
    after_mark = due_nudges(store, today=today, seen=seen)
    assert after_mark == []
    store.close()


def test_due_nudges_new_threshold_when_due_date_arrives(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    tomorrow_ref = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Bolletta", status="approved",
                    due_date="2026-07-26", sensitivity="normal")
    seen = ReminderSeen(str(tmp_path / "data"))

    first = due_nudges(store, today=tomorrow_ref, seen=seen)
    key = first[0]["key"]
    seen.mark(key, "tomorrow")
    assert due_nudges(store, today=tomorrow_ref, seen=seen) == []

    # The next day, the SAME obligation is now due today — a different
    # threshold, not yet seen, must be returned even though "tomorrow" was
    # already marked for this key.
    today = date(2026, 7, 26)
    second = due_nudges(store, today=today, seen=seen)
    assert len(second) == 1
    assert second[0]["threshold"] == "today"
    assert second[0]["key"] == key
    store.close()


def test_due_nudges_overdue(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Scaduta", status="approved",
                    due_date="2026-07-20", sensitivity="normal")
    seen = ReminderSeen(str(tmp_path / "data"))

    nudges = due_nudges(store, today=today, seen=seen)
    assert len(nudges) == 1
    assert nudges[0]["threshold"] == "overdue"
    store.close()


def test_due_nudges_ignores_invalid_due_date(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    # Not a real ISO date but still non-null so it passes the SQL NOT NULL
    # filter in upcoming_obligations and reaches urgency_of().
    store.add_item(kind="obligation", content="Data invalida", status="approved",
                    due_date="not-a-date", sensitivity="normal")
    seen = ReminderSeen(str(tmp_path / "data"))

    assert due_nudges(store, today=today, seen=seen) == []
    store.close()


def test_due_nudges_orders_overdue_today_tomorrow(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Domani", status="approved",
                    due_date="2026-07-26", sensitivity="normal")
    store.add_item(kind="obligation", content="Scaduta", status="approved",
                    due_date="2026-07-20", sensitivity="normal")
    store.add_item(kind="obligation", content="Oggi", status="approved",
                    due_date="2026-07-25", sensitivity="normal")
    seen = ReminderSeen(str(tmp_path / "data"))

    nudges = due_nudges(store, today=today, seen=seen)
    assert [n["threshold"] for n in nudges] == ["overdue", "today", "tomorrow"]
    store.close()


def test_due_nudges_key_uses_source_ref_when_present(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    obl_id = store.add_item(kind="obligation", content="Con ref", status="approved",
                             due_date="2026-07-25", sensitivity="normal",
                             source_ref="email:msg-123")
    seen = ReminderSeen(str(tmp_path / "data"))

    nudges = due_nudges(store, today=today, seen=seen)
    assert len(nudges) == 1
    assert nudges[0]["key"] == "email:msg-123"
    assert nudges[0]["key"] != str(obl_id)
    store.close()


def test_due_nudges_excludes_private_obligations(tmp_path):
    """Review C/#2: due_nudges is a home-wide broadcast (single ha_push
    target, no per-user delivery) -- a PRIVATE obligation (owner='paolo')
    must never be nudged to the whole household, only owner='home' ones."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Segreto di Paolo", owner="paolo",
                   status="approved", due_date="2026-07-26", sensitivity="normal")
    store.add_item(kind="obligation", content="Bolletta di casa", owner="home",
                   status="approved", due_date="2026-07-26", sensitivity="normal")
    seen = ReminderSeen(str(tmp_path / "data"))

    nudges = due_nudges(store, today=today, seen=seen)
    contents = [n["item"]["content"] for n in nudges]
    assert "Bolletta di casa" in contents
    assert "Segreto di Paolo" not in contents
    store.close()


def test_reminder_seen_persists_across_reinstantiation(tmp_path):
    data_dir = str(tmp_path / "data")
    seen1 = ReminderSeen(data_dir)
    assert seen1.seen("email:msg-1", "today") is False
    seen1.mark("email:msg-1", "today")

    seen2 = ReminderSeen(data_dir)
    assert seen2.seen("email:msg-1", "today") is True
    # A different threshold on the same key is independently unseen.
    assert seen2.seen("email:msg-1", "tomorrow") is False


def test_reminder_seen_no_crash_on_missing_sidecar(tmp_path):
    seen = ReminderSeen(str(tmp_path / "does-not-exist-yet"))
    assert seen.seen("k", "today") is False


def test_reminder_seen_no_crash_on_corrupt_sidecar(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "reminders_seen.json").write_text("{not valid json", encoding="utf-8")

    seen = ReminderSeen(str(data_dir))
    assert seen.seen("k", "today") is False
    # Still writable/functional after recovering from corruption.
    seen.mark("k", "today")
    assert seen.seen("k", "today") is True
