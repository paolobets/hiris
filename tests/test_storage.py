import sqlite3
from hiris.app.storage import connect, init_schema


def test_connect_sets_robustness_pragmas(tmp_path):
    conn = connect(str(tmp_path / "a.db"))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # row_factory is sqlite3.Row
    conn.execute("CREATE TABLE t(x)")
    conn.execute("INSERT INTO t VALUES (1)")
    row = conn.execute("SELECT x FROM t").fetchone()
    assert row["x"] == 1
    conn.close()


_SCHEMA_V1 = "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT);"


def test_fresh_db_stamps_version_no_migration(tmp_path):
    conn = connect(str(tmp_path / "fresh.db"))
    called = []
    init_schema(conn, _SCHEMA_V1, version=1, migrations={})
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()


def test_fresh_db_at_v2_does_not_run_migration(tmp_path):
    # A brand-new DB created with the LATEST schema must NOT run the v1->v2 migration.
    schema_v2 = "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT, tag TEXT);"
    conn = connect(str(tmp_path / "fresh2.db"))
    ran = []
    init_schema(conn, schema_v2, version=2, migrations={2: lambda c: ran.append("v2")})
    assert ran == []                                         # migration NOT called on fresh DB
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


def test_existing_preversioning_db_is_migrated(tmp_path):
    p = str(tmp_path / "old.db")
    # Simulate a pre-versioning DB: v1 tables + data, user_version still 0.
    c0 = connect(p)
    c0.executescript(_SCHEMA_V1)
    c0.execute("INSERT INTO items (name) VALUES ('keep')")
    c0.commit()
    assert c0.execute("PRAGMA user_version").fetchone()[0] == 0   # pre-versioning
    c0.close()
    # Reopen at version 2 with a migration that adds a column.
    def mig_v2(c):
        c.execute("ALTER TABLE items ADD COLUMN tag TEXT")
    c1 = connect(p)
    init_schema(c1, _SCHEMA_V1, version=2, migrations={2: mig_v2})
    assert c1.execute("PRAGMA user_version").fetchone()[0] == 2
    # data preserved + new column present
    row = c1.execute("SELECT name, tag FROM items").fetchone()
    assert row["name"] == "keep" and row["tag"] is None
    c1.close()


def test_init_schema_idempotent(tmp_path):
    p = str(tmp_path / "idem.db")
    conn = connect(p)
    calls = []
    init_schema(conn, _SCHEMA_V1, version=2, migrations={2: lambda c: calls.append(1) or c.execute("ALTER TABLE items ADD COLUMN tag TEXT")})
    # second open at same version: migration must NOT run again
    init_schema(conn, _SCHEMA_V1, version=2, migrations={2: lambda c: calls.append(1)})
    assert calls == []  # fresh DB at v2 never runs the migration (schema already latest)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()
