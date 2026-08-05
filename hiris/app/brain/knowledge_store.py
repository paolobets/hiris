from __future__ import annotations
import os
import sqlite3
import threading
import json
from datetime import datetime, timezone
from ..backends.embeddings import vec_to_blob, blob_to_vec, cosine_similarity
from ..storage import connect, init_schema

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    owner        TEXT NOT NULL DEFAULT 'home',
    title        TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL,
    data         TEXT NOT NULL DEFAULT '{}',
    amount       REAL,
    due_date     TEXT,
    category     TEXT,
    embedding    BLOB,
    sensitivity  TEXT NOT NULL DEFAULT 'normal',
    source       TEXT NOT NULL DEFAULT 'manual',
    source_ref   TEXT,
    confidence   REAL NOT NULL DEFAULT 1.0,
    status       TEXT NOT NULL DEFAULT 'approved',
    valid_from   TEXT,
    valid_until  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    chatbot_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ki_owner    ON knowledge_items(owner);
CREATE INDEX IF NOT EXISTS idx_ki_kind     ON knowledge_items(kind);
CREATE INDEX IF NOT EXISTS idx_ki_due      ON knowledge_items(due_date);
CREATE INDEX IF NOT EXISTS idx_ki_status   ON knowledge_items(status);
CREATE INDEX IF NOT EXISTS idx_ki_category ON knowledge_items(category);

CREATE TABLE IF NOT EXISTS document_chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       INTEGER NOT NULL,
    mayan_doc_id  TEXT NOT NULL,
    chunk_index   INTEGER NOT NULL,
    content       TEXT NOT NULL,
    embedding     BLOB,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dc_item ON document_chunks(item_id);
CREATE INDEX IF NOT EXISTS idx_dc_doc  ON document_chunks(mayan_doc_id);
"""


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: knowledge_items gains a nullable `lens` column (per-agent scope,
    used to unify per-agent RAG memory with shared knowledge in Slice 3)."""
    conn.execute("ALTER TABLE knowledge_items ADD COLUMN lens TEXT")


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """v2 -> v3: rinomina la colonna `lens` (id del Chatbot che scopa la memoria)
    in `chatbot_id`. Idempotente: salta se gia' rinominata."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(knowledge_items)").fetchall()]
    if "lens" in cols and "chatbot_id" not in cols:
        conn.execute("ALTER TABLE knowledge_items RENAME COLUMN lens TO chatbot_id")


def _migrate_v4(conn: sqlite3.Connection) -> None:
    """v3 -> v4: via `knowledge_links`. `neighbors` (il suo unico lettore) e'
    stato tolto in precedenza; senza un lettore la scrittura (`add_link`,
    dietro il tool `link_knowledge`) restava una funzione morta con una
    superficie viva. Nessuna riscrittura: i collegamenti gia' salvati non
    erano letti da nulla."""
    conn.execute("DROP TABLE IF EXISTS knowledge_links")


def confronta_significati(query_vec: list[float] | None) -> bool:
    """Unica definizione di "abbiamo confrontato i significati, o siamo
    degradati ai piu' recenti?" -- vera quando `query_vec` e' un vettore di
    query utilizzabile (non None, non vuoto).

    `search()` la usa per decidere se confrontare gli embedding o cadere su
    `recent()`. Chi la importa invece di ricalcolare `bool(query_vec)` per conto
    proprio:

    - `api/handlers_chat.py` -- intestazione del blocco RAG della chat
    - `brain/reasoner_memory.py` -- `MemoryRecall.by_meaning`, da cui prendono
      l'intestazione il reasoner per-evento e la revisione olistica
    - `tools/memory_tools.handle_recall_memory` -- flag `degraded` verso il
      modello, e il gate della ricerca sui chunk documentali (fusione Task 2
      del vecchio `tools/knowledge_tools.handle_recall_knowledge`, oggi
      rimosso)

    Cosi' se `search` guadagnasse un altro motivo di degradazione (es. un
    mismatch di dimensione dell'embedding) etichette e flag resterebbero coerenti
    senza dover essere toccati uno per uno -- ed e' proprio la deriva fra copie
    del criterio che questa funzione esiste per impedire."""
    return bool(query_vec)


class KnowledgeStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._mu = threading.Lock()
        init_schema(
            self._conn, _SCHEMA, version=4,
            migrations={2: _migrate_v2, 3: _migrate_v3, 4: _migrate_v4},
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime(_TS_FMT)

    def add_item(
        self, *, kind: str, content: str, owner: str = "home",
        title: str = "", data: dict | None = None,
        amount: float | None = None, due_date: str | None = None,
        category: str | None = None, embedding: list[float] | None = None,
        sensitivity: str = "normal", source: str = "manual",
        source_ref: str | None = None, confidence: float = 1.0,
        status: str = "approved", valid_from: str | None = None,
        valid_until: str | None = None, chatbot_id: str | None = None,
    ) -> int:
        now = self._now()
        blob = vec_to_blob(embedding) if embedding else None
        with self._mu:
            cur = self._conn.execute(
                "INSERT INTO knowledge_items"
                "(kind, owner, title, content, data, amount, due_date, category,"
                " embedding, sensitivity, source, source_ref, confidence, status,"
                " valid_from, valid_until, created_at, updated_at, chatbot_id)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (kind, owner, title, content, json.dumps(data or {}), amount,
                 due_date, category, blob, sensitivity, source, source_ref,
                 confidence, status, valid_from, valid_until, now, now, chatbot_id),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def get_item(self, item_id: int, owner: str | None = None) -> dict | None:
        """L'elemento, o None se non esiste (o, con `owner`, se appartiene a un
        altro owner: stesso contratto di scoping di `approve()`).

        Il vettore non esce mai da qui -- e' un blob, non un dato da mostrare --
        ma la sua PRESENZA si', come `has_embedding`: la ricerca filtra anche su
        `embedding IS NOT NULL`, quindi "approvato" e "richiamabile" non
        coincidono e chi approva deve poterlo sapere."""
        with self._mu:
            if owner is not None and not self._owner_allowed(item_id, owner):
                return None
            row = self._conn.execute(
                "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["has_embedding"] = d.get("embedding") is not None
        d.pop("embedding", None)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        return d

    def list_items(
        self, *, status: str | None = None, owner: str | None = None,
        kind: str | None = None, limit: int = 100,
    ) -> list[dict]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status=?"); params.append(status)
        if owner is not None:
            # Unified scope (mirrors search()): a caller sees their own rows
            # plus anything shared as 'home'. This is the fix for review
            # B/#16 -- handle_list_pending must never return another
            # owner's private rows.
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        if kind is not None:
            clauses.append("kind=?"); params.append(kind)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_items" + where
                + " ORDER BY created_at DESC LIMIT ?", (*params, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def approve(self, item_id: int, owner: str | None = None,
                embedding: list[float] | None = None) -> bool:
        """Approve a pending item. If `owner` is given, the item is only
        approved when its own owner matches `owner` or is 'home' (shared) --
        a cross-owner id is rejected (returns False, no mutation). `owner`
        omitted (None) preserves the pre-fix unscoped behavior for internal
        callers (brain_trace, history_digest) that manage their own rows and
        don't carry a caller identity.

        `embedding` scrive il vettore INSIEME allo stato, in un solo UPDATE: e'
        il caso degli elementi salvati da una versione precedente, che finivano
        in coda senza vettore. Approvarli cambiando il solo stato li lasciava
        irraggiungibili (la ricerca filtra anche su `embedding IS NOT NULL`),
        cioe' approvati e muti. Un solo statement perche' non esista uno stato
        intermedio "approvato ma non indicizzato"."""
        with self._mu:
            if owner is not None and not self._owner_allowed(item_id, owner):
                return False
            if embedding:
                self._conn.execute(
                    "UPDATE knowledge_items SET status='approved', embedding=?,"
                    " updated_at=? WHERE id=?",
                    (vec_to_blob(embedding), self._now(), item_id),
                )
            else:
                self._conn.execute(
                    "UPDATE knowledge_items SET status='approved', updated_at=? WHERE id=?",
                    (self._now(), item_id),
                )
            self._conn.commit()
            return True

    def delete_item(self, item_id: int, owner: str | None = None) -> bool:
        """Delete an item. See `approve()` for the `owner` scoping contract."""
        with self._mu:
            if owner is not None and not self._owner_allowed(item_id, owner):
                return False
            self._conn.execute("DELETE FROM knowledge_items WHERE id=?", (item_id,))
            # Also drop any document chunks bound to this item, otherwise a
            # deleted document leaves orphan rows in document_chunks (they are
            # already excluded from search via the item JOIN, but should not
            # linger — and the Mayan ingest rollback relies on this).
            self._conn.execute(
                "DELETE FROM document_chunks WHERE item_id=?", (item_id,)
            )
            self._conn.commit()
            return True

    def _owner_allowed(self, item_id: int, owner: str) -> bool:
        """Must be called while holding self._mu. True iff item_id exists and
        its owner is `owner` or the shared 'home' owner."""
        row = self._conn.execute(
            "SELECT owner FROM knowledge_items WHERE id=?", (item_id,)
        ).fetchone()
        return row is not None and row["owner"] in (owner, "home")

    def _clausole_di_scope(
        self, *, owner: str | None, chatbot_id: str | None,
        allow_sensitive: bool, kinds: list[str] | str | None,
    ) -> tuple[list[str], dict]:
        """Filtri condivisi da search() e recent().

        Stanno qui, e non duplicati nei due metodi, perche' governano la
        riservatezza: due copie che divergono sono una falla, non un difetto
        di stile. L'unica clausola che resta fuori e' `embedding IS NOT
        NULL`, perche' e' l'unica specifica del percorso vettoriale."""
        clauses: list[str] = ["status='approved'"]
        params: dict = {}
        if owner is not None:
            # Unified scope (Slice 3): a row must always be scoped to this
            # owner (or shared as 'home') -- the owner check applies whether
            # or not the row carries a chatbot_id. On top of that, chatbot_id
            # rows are further restricted to the caller's own chatbot_id (or
            # knowledge rows with no chatbot_id at all). This prevents two
            # different HA users chatting with the SAME chatbot (same
            # chatbot_id) from seeing each other's save_memory items: owner
            # is no longer ignored just because chatbot_id matched. With
            # chatbot_id=None this reduces to the pre-Slice3 filter
            # `(owner=? OR owner='home')` restricted to un-scoped (knowledge)
            # rows, preserving backward compatibility.
            clauses.append(
                "(owner = :owner OR owner = 'home') AND"
                " (chatbot_id = :chatbot_id OR chatbot_id IS NULL)"
            )
            params["chatbot_id"] = chatbot_id
            params["owner"] = owner
        elif chatbot_id is not None:
            # No owner passed but a chatbot_id was: don't fail open and
            # expose all chatbot memory across owners -- still scope by
            # chatbot_id (or knowledge rows with no chatbot_id). Current
            # production callers always pass owner alongside chatbot_id;
            # this branch only guards future callers.
            clauses.append("(chatbot_id = :chatbot_id OR chatbot_id IS NULL)")
            params["chatbot_id"] = chatbot_id
        if not allow_sensitive:
            clauses.append("sensitivity='normal'")
        if isinstance(kinds, str):
            # A plain string like "fact" must be treated as a single-kind
            # filter (["fact"]), not iterated char-by-char (which would
            # produce `kind IN ('f','a','c','t')` and match nothing).
            kinds = None if kinds == "all" else [kinds]
        if kinds is not None:
            if not kinds:
                # An explicitly empty list is the deny-all sentinel (e.g. an
                # agent configured with knowledge_access.kinds=[] meaning "no
                # knowledge access"). `kind IN ()` is invalid SQL, so short-
                # circuit with an always-false predicate instead of falling
                # through to "no filter" (which `if kinds:` used to do).
                clauses.append("1=0")
            else:
                placeholders = []
                for i, kind_val in enumerate(kinds):
                    key = f"kind{i}"
                    placeholders.append(f":{key}")
                    params[key] = kind_val
                clauses.append("kind IN (%s)" % ",".join(placeholders))
        clauses.append("(valid_until IS NULL OR valid_until >= :valid_now)")
        params["valid_now"] = self._now()
        return clauses, params

    def search(
        self, *, query_vec: list[float], k: int = 5,
        owner: str | None = None, chatbot_id: str | None = None,
        allow_sensitive: bool = False,
        kinds: list[str] | str | None = None,
    ) -> list[dict]:
        if not confronta_significati(query_vec):
            # Regola unica: la ricerca confronta i significati quando puo';
            # quando non puo' -- nessun embedder configurato, quindi nessun
            # vettore di query -- da' i piu' recenti. Il default di fabbrica
            # e' il NullEmbedder, che ritorna [], quindi questo e' il
            # percorso NORMALE, non un caso limite.
            return self.recent(
                k=k, owner=owner, chatbot_id=chatbot_id,
                allow_sensitive=allow_sensitive, kinds=kinds,
            )
        clauses, bind = self._clausole_di_scope(
            owner=owner, chatbot_id=chatbot_id,
            allow_sensitive=allow_sensitive, kinds=kinds,
        )
        clauses.append("embedding IS NOT NULL")
        sql = "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
        scored = []
        with self._mu:
            rows = self._conn.execute(sql, bind).fetchall()
            for r in rows:
                sim = cosine_similarity(query_vec, blob_to_vec(r["embedding"]))
                scored.append((sim, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, r in scored[:k]:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            d["score"] = sim
            out.append(d)
        return out

    def recent(
        self, *, k: int = 5, owner: str | None = None,
        chatbot_id: str | None = None, allow_sensitive: bool = False,
        kinds: list[str] | str | None = None,
    ) -> list[dict]:
        """Il percorso di degradazione di `search()` quando non c'e' un
        vettore di query con cui confrontare i significati: gli stessi
        filtri di riservatezza di `search()` (via `_clausole_di_scope`), ma
        ordinati per recenza invece che per similarita'. A differenza di
        `search()`, non richiede `embedding IS NOT NULL` -- e' proprio il
        punto: include anche le righe senza vettore, che il percorso
        vettoriale esclude per costruzione."""
        clauses, params = self._clausole_di_scope(
            owner=owner, chatbot_id=chatbot_id,
            allow_sensitive=allow_sensitive, kinds=kinds,
        )
        params["k"] = k
        sql = (
            "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
            + " ORDER BY created_at DESC, id DESC LIMIT :k"
        )
        with self._mu:
            rows = self._conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def upcoming_obligations(
        self, *, before: str, owner: str | None = None,
    ) -> list[dict]:
        clauses = ["kind='obligation'", "status='approved'",
                   "due_date IS NOT NULL", "due_date <= ?"]
        params: list = [before]
        if owner is not None:
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
                + " ORDER BY due_date ASC", params,
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def add_document_chunk(self, *, item_id: int, mayan_doc_id: str,
                           chunk_index: int, content: str,
                           embedding: list[float] | None = None) -> int:
        blob = vec_to_blob(embedding) if embedding else None
        with self._mu:
            cur = self._conn.execute(
                "INSERT INTO document_chunks"
                "(item_id, mayan_doc_id, chunk_index, content, embedding, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (item_id, mayan_doc_id, chunk_index, content, blob, self._now()),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def document_exists(self, mayan_doc_id: str) -> bool:
        with self._mu:
            row = self._conn.execute(
                "SELECT 1 FROM knowledge_items"
                " WHERE kind='document' AND source='mayan' AND source_ref=? LIMIT 1",
                (mayan_doc_id,),
            ).fetchone()
        return row is not None

    def search_chunks(self, *, query_vec: list[float], k: int = 5,
                      owner: str | None = None, allow_sensitive: bool = False) -> list[dict]:
        clauses = ["c.embedding IS NOT NULL", "i.status='approved'"]
        params: list = []
        if owner is not None:
            clauses.append("(i.owner=? OR i.owner='home')"); params.append(owner)
        if not allow_sensitive:
            clauses.append("i.sensitivity='normal'")
        sql = ("SELECT c.id, c.content, c.embedding, c.mayan_doc_id, c.item_id,"
               " i.sensitivity, i.owner FROM document_chunks c"
               " JOIN knowledge_items i ON i.id = c.item_id"
               " WHERE " + " AND ".join(clauses))
        with self._mu:
            rows = self._conn.execute(sql, params).fetchall()
            scored = [(cosine_similarity(query_vec, blob_to_vec(r["embedding"])), r)
                      for r in rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, r in scored[:k]:
            out.append({"id": r["id"], "content": r["content"],
                        "mayan_doc_id": r["mayan_doc_id"], "item_id": r["item_id"],
                        "sensitivity": r["sensitivity"], "score": sim})
        return out

    def delete_by_chatbot(self, chatbot_id: str) -> int:
        """Delete every row scoped to this chatbot (a chatbot's own working
        memory), regardless of expiry. Used when a chatbot is deleted, to
        clean up its orphaned memory -- the KnowledgeStore equivalent of the
        legacy MemoryStore.delete_by_agent (Slice 3 Task 4)."""
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM knowledge_items WHERE chatbot_id = ?", (chatbot_id,),
            )
            self._conn.commit()
            return cur.rowcount

    def purge_expired_chatbot(self) -> int:
        """Delete chatbot-scoped rows (per-chatbot working memory) whose
        retention has elapsed. Rows with chatbot_id IS NULL (shared
        knowledge) or with no valid_until (no retention set) are never
        touched here."""
        now = self._now()
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM knowledge_items"
                " WHERE chatbot_id IS NOT NULL AND valid_until IS NOT NULL AND valid_until < ?",
                (now,),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._mu:
            self._conn.close()
