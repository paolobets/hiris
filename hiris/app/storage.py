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


def add_missing_columns(conn: sqlite3.Connection, table: str,
                        columns: dict[str, str]) -> None:
    """Aggiunge a `table` le colonne di `columns` (`{nome: tipo}`) che non ci
    sono ancora, nell'ordine dato.

    **L'idioma delle migrazioni, scritto una volta** (G-13, Tappa 8, Task 6).
    Era ricopiato in nove archivi -- `PRAGMA table_info` e poi un `ALTER TABLE
    ... ADD COLUMN` per colonna -- e una copia sola, in `mind/store`, era
    diventata un aiuto, per una tabella sola.

    Il controllo su `PRAGMA table_info`, e non un `try`/`except` attorno
    all'`ALTER`, e' una scelta: un `except sqlite3.OperationalError`
    inghiottirebbe QUALUNQUE errore dell'`ALTER`, non solo «la colonna c'e'
    gia'» -- anche un archivio bloccato o un disco pieno -- e `init_schema`
    timbrerebbe l'archivio alla versione nuova senza la colonna.

    **Perche' una colonna gia' presente non e' un errore**: il DDL di SQLite
    fa commit da solo, e una caduta fra un `ALTER` e il timbro lascia un
    archivio alla versione vecchia con parte delle colonne; e un archivio che
    nasce oggi le porta gia' dal suo schema. In entrambi i casi la migrazione
    rigira e deve trovare il lavoro fatto."""
    existing = table_columns(conn, table)
    for name, kind in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """I nomi delle colonne di `table`, chiesti a SQLite (`PRAGMA
    table_info`): l'insieme vuoto se la tabella non c'e'.

    E' l'unico posto del prodotto che fa questa domanda (il cancello di
    `tests/test_archivi.py`): la chiedono `add_missing_columns`,
    `rebuild_table` e le migrazioni che decidono se c'e' ancora lavoro da
    fare."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def rebuild_table(conn: sqlite3.Connection, table: str, create_sql: str,
                  columns: tuple[str, ...], *, select_sql: str | None = None,
                  indexes: tuple[str, ...] = ()) -> None:
    """Ricostruisce `table` con `create_sql`, ricopiando le righe: **la forma
    sola con cui una colonna esce da un archivio** (Tappa 8, Task 5).

    `DROP COLUMN` vuole SQLite 3.35, e la versione dentro l'immagine
    dell'add-on non e' stata misurata: la ricostruzione funziona su tutte. Era
    scritta a mano due volte in `mind/store` (`_migration_12`, e il passo
    della 15 che toglie le colonne di `cambi`), e la Tappa 8 ne chiedeva
    altre tre.

    - `columns` sono le colonne della tabella nuova che si riempiono; le
      righe vengono da `SELECT <columns> FROM` la vecchia, o da `select_sql`
      quando un valore si calcola (deve restituire le colonne nello stesso
      ordine, leggendo dalla tabella `<table>_old`).
    - Gli indici seguono la tabella rinominata e se ne vanno con lei: si
      ricreano con `indexes`, dopo il `DROP`, quando i nomi sono di nuovo
      liberi.
    - **Tutto o niente, in una transazione** (G14-1): il modulo `sqlite3`
      non ne apre una davanti ad `ALTER` e `CREATE`, e una ricostruzione
      interrotta dopo il `RENAME` lascerebbe la tabella vuota con le righe
      dove nessuno le legge. Se ce n'e' gia' una aperta (una migrazione
      precedente dello stesso avvio) si continua in quella; se un passo
      fallisce si torna indietro, e l'archivio resta alla versione di prima.

    Il nome di `table` lo scrive chi chiama, in chiaro: e' un nome di
    tabella dello schema, mai un valore che arriva da fuori."""
    old = f"{table}_old"
    names = ",".join(columns)
    if not conn.in_transaction:
        conn.execute("BEGIN")
    try:
        conn.execute(f"ALTER TABLE {table} RENAME TO {old}")
        conn.execute(create_sql)
        conn.execute(f"INSERT INTO {table}({names}) "
                     + (select_sql or f"SELECT {names} FROM {old}"))
        conn.execute(f"DROP TABLE {old}")
        for statement in indexes:
            conn.execute(statement)
    except BaseException:
        conn.rollback()
        raise


#: **Per quanto tiene ogni tabella di un archivio, e perche'**: la forma che
#: `mind/store.CONSERVAZIONE` ha dal reperto C-6 (23/09/2026), e che dalla
#: Tappa 8 (Task 6) ogni archivio dichiara accanto al suo schema.
#:
#: `{tabella: (giorni | None, ragione, cancellazione)}`. `giorni` a `None` =
#: per sempre, e allora la `cancellazione` e' `None` anche lei. La
#: `cancellazione` e' una frase SQL intera, col nome della tabella scritto in
#: chiaro accanto a `DELETE FROM` (il censimento vede una scrittura solo
#: cosi'), e con un solo `?`, la soglia `now - giorni`; o nessuno, se la
#: tabella segue un'altra e non ha una soglia sua (le righe di un turno
#: seguono il turno). Lo pretende `tests/test_conservazione_archivi.py`.
Retention = dict[str, tuple[int | None, str, str | None]]

DAY_S = 86400


def prune_declared(conn: sqlite3.Connection, conservation: Retention,
                   now: float) -> int:
    """Applica una dichiarazione di conservazione, tabella per tabella, e
    torna quante righe ha tolto. Una tabella `None` non si tocca.

    Le cancellazioni girano nell'ordine della dichiarazione, che e' quindi
    anche l'ordine in cui una tabella che ne segue un'altra deve stare: dopo
    quella che segue. Il lock, se l'archivio ne ha uno, lo prende chi chiama;
    il commit e' qui, una volta, per tutte le tabelle -- e solo se una
    cancellazione e' girata: un archivio che tiene tutto per sempre non
    committa la transazione aperta di qualcun altro."""
    removed = 0
    deleted = False
    for days, _reason, deletion in conservation.values():
        if days is None or deletion is None:
            continue
        params = (float(now) - days * DAY_S,) if "?" in deletion else ()
        removed += conn.execute(deletion, params).rowcount or 0
        deleted = True
    if deleted:
        conn.commit()
    return removed


def database_name(conn: sqlite3.Connection) -> str:
    """Il nome del file su cui `conn` e' aperta, chiesto a SQLite (`PRAGMA
    database_list`) e non ricordato a parte: e' cio' che `/api/health`
    mostra come nome dell'archivio."""
    row = conn.execute("PRAGMA database_list").fetchone()
    return os.path.basename(row[2]) if row and row[2] else ""


def init_schema(conn: sqlite3.Connection, schema_sql: str, *, version: int,
                migrations: dict[int, Migration] | None = None,
                after_sql: str | None = None) -> int:
    """Ensure the schema exists and is at `version`, migrating idempotently.

    Detection (before creating tables): a DB with NO user tables is 'fresh' and
    `schema_sql` already produces the LATEST layout → stamp `version`, run no
    migrations. A pre-versioning existing DB (has tables but user_version==0) is
    baselined to 1, then migrations 2..version run in order. A DB already at
    version N runs only N+1..version. `migrations[k]` migrates k-1 → k.

    `after_sql` runs AFTER the migrations, before the version is stamped: the
    indexes on columns that a migration adds. In `schema_sql` they would make
    an old archive fail to open (the script runs before the migrations, and a
    `CREATE INDEX` on a column that does not exist yet raises), so the
    archives created them by hand after this call. One statement, and
    idempotent (`IF NOT EXISTS`): it runs at every opening.

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
    if after_sql:
        # `execute` e non `executescript`: il secondo fa commit prima di
        # cominciare, e separerebbe le scritture delle migrazioni dal timbro.
        # Una frase sola, quindi -- due farebbero sollevare subito.
        conn.execute(after_sql)
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


def rekey(conn: sqlite3.Connection, update_sql: str, renames: dict[str, str], *,
          commit: Callable[[], None] | None = None) -> int:
    """`update_sql` -- `UPDATE <tabella> SET <colonna> = ? WHERE <colonna> = ?`
    -- per ogni coppia (vecchia, nuova) di `renames`, in una transazione;
    ritorna quante righe.

    E' la migrazione dei fili dei servizi dal nome all'impronta della chiave
    (`servizi.migrate_service_threads`, Tappa 7 T8 e G83-3), scritta una volta
    per gli archivi che portano il soggetto in una colonna. L'istruzione la
    scrive per intero l'archivio che chiama, e non si compone qui: un nome di
    tabella composto a runtime acceca il censimento delle scritture
    (`scripts/censimento.py`, misurato il 07/10/2026). Il lock, se l'archivio
    ne ha uno, lo prende chi chiama; `commit`, se l'archivio ne ha uno suo
    (il sapere fa avanzare la sua versione a ogni scrittura), lo passa."""
    try:
        moved = sum(conn.execute(update_sql, (new, old)).rowcount
                    for old, new in renames.items())
        (commit or conn.commit)()
    except Exception:
        conn.rollback()
        raise
    return moved


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
