import pytest
from hiris.app.watcher.wake import maybe_wake
from hiris.app.watcher.sentinel_store import SentinelStore


@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "s.db")); yield s; s.close()


async def _noop():
    return None


@pytest.mark.asyncio
async def test_woke_then_cooldown(store):
    woke = []
    async def on_wake(w): woke.append(w)
    r1 = await maybe_wake(store, "k", "W", on_wake=on_wake, clock=lambda: 1000.0,
                          today=lambda: "2026-07-21", cooldown_sec=1800, daily_cap=10)
    assert r1 == "woke" and woke == ["W"]
    r2 = await maybe_wake(store, "k", "W2", on_wake=on_wake, clock=lambda: 1000.0 + 600,
                          today=lambda: "2026-07-21", cooldown_sec=1800, daily_cap=10)
    assert r2 == "cooldown" and woke == ["W"]


@pytest.mark.asyncio
async def test_cap_per_scope(store):
    async def on_wake(w): pass
    r = await maybe_wake(store, "k", "W", on_wake=on_wake, clock=lambda: 1.0,
                         today=lambda: "2026-07-21", cooldown_sec=0, daily_cap=0, cap_scope="holistic")
    assert r == "cap"
    # scope diverso non è intaccato
    r2 = await maybe_wake(store, "k2", "W", on_wake=on_wake, clock=lambda: 1.0,
                          today=lambda: "2026-07-21", cooldown_sec=0, daily_cap=1, cap_scope="events")
    assert r2 == "woke"


@pytest.mark.asyncio
async def test_cap_records_event_with_scope_as_kind(store):
    async def on_wake(w): pass
    r = await maybe_wake(store, "k", "W", on_wake=on_wake, clock=lambda: 1.0,
                         today=lambda: "2026-07-21", cooldown_sec=0, daily_cap=0, cap_scope="situations")
    assert r == "cap"
    ev = store.recent_events(1)[0]
    assert ev["outcome"] == "cap" and ev["kind"] == "situations"


def test_store_scope_isolation(store):
    assert store.incr_wakes_today("2026-07-21", "events") == 1
    assert store.incr_wakes_today("2026-07-21", "situations") == 1
    assert store.wakes_today("2026-07-21", "events") == 1
    assert store.wakes_today("2026-07-21", "situations") == 1
    assert store.incr_wakes_today("2026-07-21", "events") == 2
    assert store.wakes_today("2026-07-21", "situations") == 1


def test_v1_db_migrates_to_v2_preserving_events_scope(tmp_path):
    """Simulate a pre-existing Fetta-1 DB (schema v1, no scope column) and
    verify SentinelStore migrates it to v2 without losing counter data."""
    import sqlite3
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "CREATE TABLE timers (key TEXT PRIMARY KEY, started_at REAL NOT NULL);"
        "CREATE TABLE cooldowns (key TEXT PRIMARY KEY, last_wake REAL NOT NULL);"
        "CREATE TABLE wake_counts (day TEXT PRIMARY KEY, n INTEGER NOT NULL);"
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
        "kind TEXT, entity_id TEXT, verdict TEXT, severity TEXT, outcome TEXT, message TEXT);"
    )
    conn.execute("INSERT INTO wake_counts(day, n) VALUES('2026-07-20', 3)")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    s = SentinelStore(db_path)
    try:
        assert s.wakes_today("2026-07-20", "events") == 3
        assert s.wakes_today("2026-07-20", "situations") == 0
        assert s.incr_wakes_today("2026-07-20", "events") == 4
    finally:
        s.close()
