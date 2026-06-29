"""Shared SQLite helpers: robustness PRAGMAs + schema versioning/migrations.

Every HIRIS store should open its connection via connect() and initialise via
init_schema() so all DBs get WAL/busy_timeout/foreign_keys and a consistent,
data-safe migration path across add-on upgrades."""
from __future__ import annotations

import os
import sqlite3
from typing import Callable, Optional

# Migration callable: receives the connection, transforms schema from version k-1 to k.
Migration = Callable[[sqlite3.Connection], None]


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with HIRIS-standard robustness PRAGMAs.

    - WAL journal: survives power loss far better and allows concurrent readers
      while the capture/scheduler threads write.
    - busy_timeout: blocks briefly instead of raising 'database is locked'.
    - synchronous=NORMAL: good durability/perf balance under WAL.
    - foreign_keys=ON: enforce referential integrity (e.g. knowledge_links).
    row_factory = sqlite3.Row. Creates the parent directory.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_schema(conn: sqlite3.Connection, schema_sql: str, *, version: int,
                migrations: Optional[dict[int, Migration]] = None) -> int:
    """Ensure the schema exists and is at `version`, migrating idempotently.

    Detection (before creating tables): a DB with NO user tables is 'fresh' and
    `schema_sql` already produces the LATEST layout → stamp `version`, run no
    migrations. A pre-versioning existing DB (has tables but user_version==0) is
    baselined to 1, then migrations 2..version run in order. A DB already at
    version N runs only N+1..version. `migrations[k]` migrates k-1 → k.

    The caller is responsible for holding any lock if called concurrently
    (normally this runs once at store construction, single-threaded).
    """
    pre_tables = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    conn.executescript(schema_sql)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == 0:
        current = version if pre_tables == 0 else 1
    for target in range(current + 1, version + 1):
        mig = (migrations or {}).get(target)
        if mig is not None:
            mig(conn)
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()
    return version
