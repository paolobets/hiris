"""Shared SQLite helpers: robustness PRAGMAs + schema versioning/migrations.

Every HIRIS store should open its connection via connect() and initialise via
init_schema() so all DBs get WAL/busy_timeout/foreign_keys and a consistent,
data-safe migration path across add-on upgrades.

E la scrittura di un file JSON in `/data` (`write_json_atomic`), una sola."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from contextlib import suppress
from typing import Any

# Migration callable: receives the connection, transforms schema from version k-1 to k.
Migration = Callable[[sqlite3.Connection], None]


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with HIRIS-standard robustness PRAGMAs.

    - WAL journal: survives power loss far better and allows concurrent readers
      while the capture/scheduler threads write.
    - busy_timeout: blocks briefly instead of raising 'database is locked'.
    - synchronous=NORMAL: good durability/perf balance under WAL.
    - foreign_keys=ON: enforce referential integrity.
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
                migrations: dict[int, Migration] | None = None) -> int:
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
        # **Un gradino mancante non passa in silenzio.** Prima si saltava, e
        # l'archivio veniva timbrato alla versione nuova lo stesso: chi scrive
        # `7: _migration_7` come `8: _migration_7` otteneva un archivio che si
        # dichiara migrato e non lo e', senza una riga di log. Trovato dalla
        # revisione indipendente il 15/09/2026. Se una versione non ha niente
        # da fare, si dichiara con una funzione vuota e la sua ragione.
        if target not in (migrations or {}):
            raise ValueError(
                f"manca la migrazione per la versione {target}: l'archivio e' "
                f"alla {current} e si vuole portarlo alla {version}. Una "
                "versione senza migrazione si dichiara con una funzione vuota, "
                "non si lascia come un buco nel dizionario")
        migrations[target](conn)
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()
    return version


#: I file JSON dell'add-on si creano leggibili e scrivibili dal solo
#: proprietario: c'e' dentro testo che l'utente ha scritto (il prompt della
#: chat) e le sue decisioni (la catena dei modelli).
_JSON_PERMISSIONS = 0o600

# Due scritture concorrenti non devono poter accavallare il `.tmp` e
# l'`os.replace`.
_json_lock = threading.Lock()


def write_json_atomic(path: str, data: Any) -> None:
    """Scrive un file JSON in modo atomico e durevole: temporaneo, `fsync`,
    `os.replace`.

    **Una scrittura sola** (Tappa 7, Task 10; F-11). Erano tre -- le
    impostazioni della chat, l'archivio dei modelli, la cornice dell'anagrafe
    -- e solo la prima faceva `fsync`: le altre due potevano pubblicare, su una
    perdita di alimentazione, un nome che punta a un file vuoto. L'atomicita'
    del rename non e' durabilita' del contenuto: sono due garanzie distinte, e
    servono entrambe.

    - **Permessi stretti alla creazione** (`os.open` con `_JSON_PERMISSIONS`,
      non un `chmod` dopo). Su Windows, dove gira solo la suite, la chiamata
      incide di fatto solo sul flag di sola lettura.
    - **Il temporaneo si rimuove se la scrittura fallisce**, invece di restare
      a sporcare `/data`.

    Solleva `OSError` se il disco non collabora: decide il chiamante se
    dichiararlo o lasciarlo salire.
    """
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
    with _json_lock:
        descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                             _JSON_PERMISSIONS)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp)
            raise
        os.replace(tmp, path)
