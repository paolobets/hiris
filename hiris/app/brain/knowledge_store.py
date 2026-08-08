from __future__ import annotations
import os
import sqlite3
import threading
import json
from datetime import datetime, timezone
from ..backends.embeddings import vec_to_blob, blob_to_vec, cosine_similarity
from ..storage import connect, init_schema

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Task 4 ("memoria unica 3a"): i valori di `source` scritti in produzione
# (verificati con un grep su `source=` in tutto `hiris/`) si dividono in due
# gruppi. DICHIARATI -- una PERSONA lo ha detto -- sono 'chat' (il tool
# remember_this durante una conversazione, tools/memory_tools.py),
# 'manual' (l'API di knowledge management, api/handlers_knowledge.py, ed e'
# anche il default di add_item quando nessun source e' specificato) e
# 'migrated' (le memorie dell'agente legacy, migrate una tantum in Slice 3 da
# brain/memory_migration.py: erano gia' parole di una persona, scritte
# attraverso il vecchio tool di memoria -- solo con provenienza diversa da
# 'chat'). DEDOTTI -- HIRIS li ha prodotti da solo -- sono 'history-digest'
# (le medie settimanali del digest notturno, brain/history_digest.py),
# 'brain' (le tracce del brain, brain/brain_trace.py) e 'mayan' (i documenti
# ingeriti da Mayan, brain/mayan_ingest.py: contenuto esterno importato, non
# dedotto da HIRIS ne' dichiarato a voce da una persona in questa
# conversazione).
# "gateway" (Fix 1, whole-branch review, final fix wave: tools/memory_tools.py's
# handle_save_memory, chosen by ToolDispatcher.dispatch based on
# from_remote_gateway -- both the remote gateway and that dispatcher are
# since gone, fetta E2 Tasks 4 and 7) is DELIBERATELY absent here: a save arriving through
# the remote MCP gateway is recallable (search()/recent()) but never
# auto-injected as "declared by a person" -- see the docstring on
# handle_save_memory for why.
DECLARED_SOURCES = ("chat", "manual", "migrated")

# Quanti elementi dichiarati al massimo entrano in un prompt (chat e
# ragionatore proattivo, vedi api/handlers_chat.py e
# brain/reasoner_memory.py). 30 e' la cifra che il brief del Task 4 stesso
# usa come esempio di "ci sta comodamente" (duecento medie settimanali NON
# stanno in un prompt; trenta fatti dichiarati da chi abita la casa si',
# sempre) -- in produzione, quattro mesi di uso ne hanno prodotti 3. Quando
# i dichiarati superano questo numero, KnowledgeStore.declared() NON tronca
# in silenzio: restituisce anche il conteggio totale, cosi' chi rende il
# prompt (handlers_chat._render_declared_block,
# reasoner_memory._declared_snippets) puo' dirlo esplicitamente invece di
# far sparire un fatto dichiarato senza che nessuno se ne accorga -- e'
# esattamente il guasto che questa fetta esiste per eliminare.
DECLARED_MAX = 30


def render_declared_overflow_note(total: int, shown: int, limit: int) -> str:
    """Il testo -- SEMPRE lo stesso, ovunque venga reso -- che dice "e
    altri N piu' vecchi, non mostrati" quando `KnowledgeStore.declared()` ha
    trovato piu' righe di quante `limit` ne abbia lasciate passare (`total`
    e' il conteggio PRIMA del limite, `shown` quante ne sono arrivate al
    chiamante -- normalmente `len(items)`).

    Fix 2 (review wave, task-4-fixes): prima viveva come una f-string
    IDENTICA duplicata in due file (`api/handlers_chat.
    _render_declared_block` e `brain/reasoner_memory._declared_snippets`),
    e ciascuna copia hardcodava `DECLARED_MAX` nel testo invece di leggere
    il limite EFFETTIVAMENTE passato a `declared()` -- cosi' un futuro
    chiamante con un limite personalizzato avrebbe visto nella nota il
    numero sbagliato. Vive qui, accanto a `DECLARED_MAX`, con `limit` come
    parametro esplicito: i due chiamanti non possono piu' divergere sul
    testo, e il numero mostrato e' sempre quello vero.

    Ritorna "" quando non c'e' overflow (`total <= shown`) -- i chiamanti
    aggiungono la nota solo se questa stringa non e' vuota."""
    overflow = total - shown
    if overflow <= 0:
        return ""
    return (
        f"(+ altri {overflow} elementi dichiarati più vecchi, non "
        f"mostrati — limite {limit})"
    )


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


def _migrate_v5(conn: sqlite3.Connection) -> None:
    """v4 -> v5 (Task 3, memoria unica): `chatbot_id` smette di essere una
    clausola di ambito (vedi `_clausole_di_scope`) -- resta in tabella solo
    come provenienza (quale chatbot ha scritto la riga; azzerato da
    `detach_chatbot_id` alla cancellazione di un chatbot). Le righe
    kind='memory' gia' esistenti erano scritte quando chatbot_id ANCORA
    delimitava la visibilita': azzerarlo qui e' cio' che le rende
    immediatamente di tutta la casa all'aggiornamento, invece di restarci
    intrappolate finche' qualcuno non le riscrive. Non tocca altri kind (non
    hanno mai portato un chatbot_id, per costruzione di
    `handle_save_memory`) ne' `valid_until` (task 4 -- diventata task 6,
    "la memoria non evapora": vedi `_migrate_v6`)."""
    conn.execute("UPDATE knowledge_items SET chatbot_id = NULL"
                 " WHERE kind = 'memory' AND chatbot_id IS NOT NULL")


def _migrate_v6(conn: sqlite3.Connection) -> None:
    """v5 -> v6 (Task 6, "la memoria non evapora"): azzera `valid_until` su
    ogni riga kind='memory' esistente.

    Prima di questa fetta l'UNICO scrittore che valorizzava `valid_until`
    per kind='memory' era `handle_save_memory` (tools/memory_tools.py),
    sempre e solo come scadenza di CONSERVAZIONE calcolata da
    `retention_days` -- mai come validita' di un fatto (quella semantica,
    dove esiste, vive su altri kind: es. obligation/due_date, o un
    kind='fact' con un proprio `valid_until`, mai toccati qui). Quel calcolo
    e' stato rimosso: kind='memory' non guadagna piu' una scadenza al
    salvataggio, esattamente come ogni altro kind.

    Questa migrazione bonifica due difetti sulle righe scritte PRIMA della
    fetta:

    - righe gia' scadute sotto il vecchio schema, invisibili su ogni
      percorso di lettura (`_clausole_di_scope` filtra su `valid_until`);
    - le "righe immortali e invisibili" del brief: una riga distaccata dal
      suo chatbot (`chatbot_id` azzerato da `detach_chatbot_id` o da
      `_migrate_v5`) ma con `valid_until` ancora impostato. Una volta
      scaduta, il filtro di ambito la nasconde su ogni lettura, e il
      vecchio `purge_expired_chatbot` -- che cercava per chatbot -- non la
      trovava piu': restava nel database per sempre, invisibile e
      impurgabile (`purge_expired_chatbot` stesso e' stato rimosso in
      questa fetta, non avendo piu' nessun chiamante che gli producesse
      lavoro).

    `WHERE kind = 'memory'` senza altre condizioni, apposta: tocca sia le
    righe ancora agganciate a un chatbot sia quelle gia' orfane, perche' in
    entrambi i casi il `valid_until` presente era comunque conservazione,
    mai altro."""
    conn.execute("UPDATE knowledge_items SET valid_until = NULL WHERE kind = 'memory'")


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
            self._conn, _SCHEMA, version=6,
            migrations={2: _migrate_v2, 3: _migrate_v3, 4: _migrate_v4, 5: _migrate_v5,
                        6: _migrate_v6},
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
        self, *, owner: str | None,
        allow_sensitive: bool, kinds: list[str] | str | None,
    ) -> tuple[list[str], dict]:
        """Filtri condivisi da search() e recent().

        Stanno qui, e non duplicati nei due metodi, perche' governano la
        riservatezza: due copie che divergono sono una falla, non un difetto
        di stile. L'unica clausola che resta fuori e' `embedding IS NOT
        NULL`, perche' e' l'unica specifica del percorso vettoriale.

        `chatbot_id` NON e' (piu') una clausola qui (Task 3, memoria unica):
        cio' che dici lo sa HIRIS, non il chatbot con cui parlavi. Prima di
        questa fetta una riga scritta parlando con un chatbot restava
        invisibile parlando con un altro anche a parita' di owner -- costo
        gia' osservato in produzione sulle tre memorie reali del sistema
        (chi amministra la casa, come rispondere a "chi c'e' in casa", e il
        fatto che il modulo meteo esterno e' guasto), tutte legate a
        chatbot_id='hiris-default': il giorno in cui nasce un secondo
        chatbot, quello non avrebbe saputo del guasto meteo e avrebbe ripreso
        a proporre soluzioni basate su sensori inesistenti. La colonna
        `chatbot_id` resta in tabella (provenienza: quale chatbot ha
        scritto la riga; azzerata da `detach_chatbot_id` alla cancellazione
        di un chatbot), ma non delimita piu' chi puo' vedere cosa.

        L'unica eccezione che NON si tocca e' `owner`: resta l'unico asse di
        riservatezza. Cio' che riguarda la casa e' di tutti (owner='home', o
        owner uguale al chiamante) e porta il nome di chi l'ha detto; cio'
        che e' marcato `sensitivity='sensitive'` (sotto) resta visibile solo
        a chi l'ha detto."""
        clauses: list[str] = ["status='approved'"]
        params: dict = {}
        if owner is not None:
            clauses.append("(owner = :owner OR owner = 'home')")
            params["owner"] = owner
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
        owner: str | None = None,
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
                k=k, owner=owner,
                allow_sensitive=allow_sensitive, kinds=kinds,
            )
        clauses, bind = self._clausole_di_scope(
            owner=owner,
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
        allow_sensitive: bool = False,
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
            owner=owner,
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

    def declared(
        self, *, owner: str | None = None, allow_sensitive: bool = False,
        kinds: list[str] | str | None = None, limit: int = DECLARED_MAX,
    ) -> tuple[list[dict], int]:
        """Le righe che una PERSONA ha dichiarato: `source` in
        DECLARED_SOURCES (vedi il commento li' sopra per l'elenco completo e
        perche'). Esclude tutto cio' che HIRIS ha dedotto da solo
        ('history-digest', 'brain', 'mayan') -- quello si richiama
        (search()/recent()), questo entra sempre.

        Stessi filtri di riservatezza di search()/recent(), RIUSATI da
        _clausole_di_scope (mai una seconda copia: e' la clausola che
        governa la riservatezza, e due copie che divergono sono una falla,
        non un difetto di stile -- vedi il docstring di
        _clausole_di_scope). L'unica clausola propria di questo metodo e'
        il filtro su `source`.

        Ordinate per recenza (stessa convenzione di recent()). Il secondo
        elemento della tupla restituita e' il conteggio TOTALE che rispetta
        lo scope, PRIMA di applicare `limit`: chi chiama puo' cosi' dire "e
        altri N piu' vecchi, non mostrati" invece di troncare in silenzio --
        vedi DECLARED_MAX qui sopra."""
        clauses, params = self._clausole_di_scope(
            owner=owner, allow_sensitive=allow_sensitive, kinds=kinds,
        )
        src_placeholders = []
        for i, s in enumerate(DECLARED_SOURCES):
            key = f"decl_src{i}"
            src_placeholders.append(f":{key}")
            params[key] = s
        clauses.append("source IN (%s)" % ",".join(src_placeholders))
        where = " AND ".join(clauses)
        with self._mu:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM knowledge_items WHERE " + where, params,
            ).fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM knowledge_items WHERE " + where
                + " ORDER BY created_at DESC, id DESC LIMIT :lim",
                {**params, "lim": limit},
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out, total

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

    def detach_chatbot_id(self, chatbot_id: str) -> int:
        """A chatbot was deleted: dissociate its rows, never delete them.

        Before Task 3 this method (`delete_by_chatbot`) DELETEd every row
        carrying this chatbot_id, because chatbot_id was a scope: those rows
        were unreachable by anyone else anyway, so deleting them on chatbot
        deletion just cleaned up otherwise-orphaned dead weight.

        That premise is gone. `_clausole_di_scope` no longer reads
        chatbot_id -- a row saved through this chatbot is, and was already,
        visible to the whole house (subject only to owner/sensitivity). It
        is HIRIS's knowledge now, not the chatbot's. Deleting the chatbot
        must not delete it: doing so would silently wipe house knowledge
        that has nothing to do with the chatbot going away (e.g. the
        production 'external weather module is broken' memory, if it had
        been re-saved through a since-deleted second chatbot). So this NULLs
        chatbot_id instead of dropping the rows -- the same operation
        `_migrate_v5` performs on upgrade for the rows that predate this
        change, and for the same reason: a dangling reference to a chatbot
        that no longer exists should be cleared, not used as a deletion
        trigger for content that outlives it."""
        with self._mu:
            cur = self._conn.execute(
                "UPDATE knowledge_items SET chatbot_id = NULL WHERE chatbot_id = ?",
                (chatbot_id,),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._mu:
            self._conn.close()
