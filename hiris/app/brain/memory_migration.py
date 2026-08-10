# hiris/app/brain/memory_migration.py
"""One-time migration of the legacy per-agent memory store into the unified
KnowledgeStore (Slice 3).

Historically each agent's long-term memory lived in its own SQLite database
(`hiris_memory.db`, table `agent_memories` -- see `proxy/memory_store.py`).
Slice 3 unifies all memory/knowledge under `knowledge_items` in
`knowledge.db`.

fetta E4 Task 9 (il conto): qui c'era scritto che `knowledge_items` usa la
colonna `chatbot_id` "to keep memories scoped per agent". Non e' piu' vero e
non lo e' da un pezzo: la delimitazione per chatbot e' uscita dai filtri con
"Task 3, memoria unica" (vedi `KnowledgeStore._clausole_di_scope`, che lo
dichiara: l'unico asse di riservatezza e' `owner`), e l'entita' Chatbot
stessa e' uscita con la fetta E4 Task 4. La colonna resta in tabella come
sola provenienza, e la riga migrata continua a portarla valorizzata
(`chatbot_id=<agent_id>`, sotto) perche' e' l'unico posto dove il vecchio
`agent_id` puo' ancora dire da dove veniva quel ricordo -- ma non delimita
piu' chi lo vede.

`migrate_agent_memories()` copies every legacy row into KnowledgeStore as a
`kind="memory"` item (`chatbot_id=<agent_id>`, `source="migrated"`), then renames
the legacy DB to `hiris_memory.db.migrated` so it is never processed again.
It must be safe to call on every startup: idempotent, and it must never drop
a row (including rows with a NULL embedding).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3

from ..backends.embeddings import blob_to_vec

logger = logging.getLogger(__name__)

_LEGACY_DB_NAME = "hiris_memory.db"
_MARKER_SUFFIX = ".migrated"


def migrate_agent_memories(data_dir: str, knowledge_store) -> int:
    """Migrate legacy `agent_memories` rows into `knowledge_store`, once.

    Returns the number of rows migrated. Returns 0 (no-op) when:
    - the legacy DB (`<data_dir>/hiris_memory.db`) does not exist, or
    - the `.migrated` marker (the previously-renamed legacy DB) already
      exists -- this is what makes repeated calls (e.g. every add-on
      startup) idempotent.

    Rows with a NULL/undecodable embedding are still migrated with
    `embedding=None` -- they are never dropped.

    The rename of the legacy DB to `hiris_memory.db.migrated` is the commit
    point for "never run again". If migration succeeds but the rename fails
    (e.g. the file is still locked by another open handle), the migrated
    rows already landed safely in KnowledgeStore; the only consequence is
    that a later restart may see the legacy DB again and re-migrate (and
    thus duplicate) those rows. This is logged loudly and accepted as a
    rare, non-data-losing edge case rather than solved with cross-process
    locking here.
    """
    legacy_path = os.path.join(data_dir, _LEGACY_DB_NAME)
    marker_path = legacy_path + _MARKER_SUFFIX

    if os.path.exists(marker_path) or not os.path.exists(legacy_path):
        return 0

    conn = sqlite3.connect(legacy_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, agent_id, content, tags, embedding, created_at, expires_at "
            "FROM agent_memories"
        ).fetchall()
    finally:
        conn.close()

    migrated = 0
    for row in rows:
        embedding: list[float] | None = None
        blob = row["embedding"]
        if blob:
            try:
                embedding = blob_to_vec(blob)
            except Exception as exc:
                logger.warning(
                    "memory_migration: could not decode embedding for legacy "
                    "memory id=%s (agent=%s), migrating without a vector: %s",
                    row["id"], row["agent_id"], exc,
                )
                embedding = None

        tags: list = []
        try:
            raw_tags = row["tags"]
            if raw_tags:
                tags = json.loads(raw_tags)
        except Exception as exc:
            logger.debug(
                "memory_migration: could not parse tags for legacy memory "
                "id=%s (agent=%s): %s", row["id"], row["agent_id"], exc,
            )
            tags = []

        # `row["expires_at"]` era la scadenza di CONSERVAZIONE del vecchio
        # store per-agente (stessa semantica del `retention_days` che
        # `handle_save_memory` calcolava, mai validita' di un fatto). Task 6
        # ("la memoria non evapora") ha rimosso quel calcolo ovunque nel
        # prodotto vivo; portarlo qui pari pari ricreerebbe esattamente il
        # difetto appena chiuso -- una riga kind='memory' che evapora da
        # sola -- per chiunque avesse ancora un `hiris_memory.db` legacy da
        # migrare. Ignorato deliberatamente: ogni riga migrata nasce senza
        # scadenza, come ogni riga scritta oggi da handle_save_memory.
        knowledge_store.add_item(
            kind="memory",
            content=row["content"],
            owner="home",
            chatbot_id=row["agent_id"],
            status="approved",
            sensitivity="normal",
            embedding=embedding,
            source="migrated",
            data={"tags": tags} if tags else None,
        )
        migrated += 1

    try:
        os.replace(legacy_path, marker_path)
    except OSError as exc:
        logger.error(
            "memory_migration: migrated %d row(s) from %s into KnowledgeStore "
            "but failed to rename it to %s (%s) -- a later restart may "
            "re-migrate (and duplicate) these rows",
            migrated, legacy_path, marker_path, exc,
        )
    else:
        logger.info(
            "memory_migration: migrated %d legacy agent_memories row(s) into "
            "KnowledgeStore from %s; legacy DB renamed to %s",
            migrated, legacy_path, marker_path,
        )

    return migrated
