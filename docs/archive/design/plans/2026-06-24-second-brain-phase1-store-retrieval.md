# Second Brain — Fase 1: Knowledge Store + Retrieval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Costruire il substrato dati persistente del second brain (store sqlite ibrido) e il retrieval, esponendolo all'LLM via tool, gestendo end-to-end la conoscenza `normal` (i `sensitive` si memorizzano ma non entrano nei prompt finché Fase 2).

**Architecture:** Nuovo package `hiris/app/brain/` con una `KnowledgeStore` sqlite (tabelle `knowledge_items` + `knowledge_links`), embedding locali riusati da `backends/embeddings.py`, retrieval ibrido (vettore brute-force + query strutturate + grafo 1-hop). Tre tool LLM (`save_knowledge`/`recall_knowledge`/`link_knowledge`) wired nel dispatcher esistente. Loop pending/approve via API. Hook promemoria su `due_date` via `task_engine` esistente.

**Tech Stack:** Python 3.14, sqlite3, aiohttp, pytest/pytest-asyncio, model2vec (embedding locali). Riuso: `backends/embeddings.py` (`vec_to_blob`/`blob_to_vec`/`cosine_similarity`/`EmbeddingProvider`), `tools/dispatcher.py`, `claude_runner.ALL_TOOL_DEFS`, `task_engine`.

**Spec di riferimento:** `docs/design/2026-06-24-second-brain-foundation-design.md` (Sezioni 1–4, 6, 7, 9, 10).

---

## File Structure

| File | Responsabilità |
|---|---|
| `hiris/app/brain/__init__.py` | Package marker |
| `hiris/app/brain/knowledge_store.py` | `KnowledgeStore`: schema items+links, CRUD, vector/structured/graph retrieval |
| `hiris/app/brain/identity.py` | Risoluzione `owner` dall'utente HA (header ingress) |
| `hiris/app/tools/knowledge_tools.py` | Tool def `save_knowledge`/`recall_knowledge`/`link_knowledge` |
| `hiris/app/tools/dispatcher.py` (modify) | Routing dei 3 tool al `KnowledgeStore` |
| `hiris/app/claude_runner.py` (modify) | Aggiunta dei 3 tool def a `ALL_TOOL_DEFS` |
| `hiris/app/api/handlers_knowledge.py` | API REST: list pending, approve, reject, manual add |
| `hiris/app/server.py` (modify) | Init `KnowledgeStore`, registrazione rotte, hook promemoria |
| `tests/test_knowledge_store.py` | Test store |
| `tests/test_knowledge_identity.py` | Test identità |
| `tests/test_knowledge_tools.py` | Test tool+dispatch |
| `tests/test_handlers_knowledge.py` | Test API |

**Nota di convenzione:** seguire i pattern degli store esistenti (`memory_store.py`, `chat_store.py`): `sqlite3.connect(check_same_thread=False)`, `row_factory=Row`, lock `threading.Lock()` su scrittura, `CREATE TABLE IF NOT EXISTS`, timestamp ISO UTC.

---

## Task 1: Schema e init di `KnowledgeStore`

**Files:**
- Create: `hiris/app/brain/__init__.py` (vuoto)
- Create: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_store.py
import sqlite3
from hiris.app.brain.knowledge_store import KnowledgeStore


def test_init_creates_tables(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    conn = sqlite3.connect(str(tmp_path / "brain.db"))
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "knowledge_items" in names
    assert "knowledge_links" in names
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_init_creates_tables -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.knowledge_store`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/knowledge_store.py
from __future__ import annotations
import os
import sqlite3
import threading
from datetime import datetime, timezone

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
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ki_owner    ON knowledge_items(owner);
CREATE INDEX IF NOT EXISTS idx_ki_kind     ON knowledge_items(kind);
CREATE INDEX IF NOT EXISTS idx_ki_due      ON knowledge_items(due_date);
CREATE INDEX IF NOT EXISTS idx_ki_status   ON knowledge_items(status);
CREATE INDEX IF NOT EXISTS idx_ki_category ON knowledge_items(category);

CREATE TABLE IF NOT EXISTS knowledge_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id      INTEGER NOT NULL,
    dst_id      INTEGER NOT NULL,
    relation    TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    UNIQUE(src_id, dst_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_kl_src ON knowledge_links(src_id);
CREATE INDEX IF NOT EXISTS idx_kl_dst ON knowledge_links(dst_id);
"""


class KnowledgeStore:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._mu = threading.Lock()
        with self._mu:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime(_TS_FMT)

    def close(self) -> None:
        with self._mu:
            self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_init_creates_tables -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/__init__.py hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): KnowledgeStore schema (knowledge_items + knowledge_links)"
```

---

## Task 2: `add_item` / `get_item`

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

`add_item` accetta un embedding già calcolato (vettore `list[float]`) per non accoppiare lo store all'embedder. Chi chiama (i tool) calcola l'embedding e lo passa.

- [ ] **Step 1: Write the failing test**

```python
def test_add_and_get_item(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    item_id = store.add_item(
        kind="preference", owner="home",
        title="Intolleranza lattosio",
        content="Paolo è intollerante al lattosio",
        embedding=[0.1, 0.2, 0.3],
        sensitivity="normal", source="manual", status="approved",
    )
    got = store.get_item(item_id)
    assert got["kind"] == "preference"
    assert got["content"] == "Paolo è intollerante al lattosio"
    assert got["status"] == "approved"
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_add_and_get_item -v`
Expected: FAIL — `AttributeError: 'KnowledgeStore' object has no attribute 'add_item'`

- [ ] **Step 3: Write minimal implementation**

Aggiungere in cima al file: `import json` e `from .. backends.embeddings import vec_to_blob` (riga import: `from ..backends.embeddings import vec_to_blob, blob_to_vec, cosine_similarity`). Poi i metodi:

```python
    def add_item(
        self, *, kind: str, content: str, owner: str = "home",
        title: str = "", data: dict | None = None,
        amount: float | None = None, due_date: str | None = None,
        category: str | None = None, embedding: list[float] | None = None,
        sensitivity: str = "normal", source: str = "manual",
        source_ref: str | None = None, confidence: float = 1.0,
        status: str = "approved", valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> int:
        now = self._now()
        blob = vec_to_blob(embedding) if embedding else None
        with self._mu:
            cur = self._conn.execute(
                "INSERT INTO knowledge_items"
                "(kind, owner, title, content, data, amount, due_date, category,"
                " embedding, sensitivity, source, source_ref, confidence, status,"
                " valid_from, valid_until, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (kind, owner, title, content, json.dumps(data or {}), amount,
                 due_date, category, blob, sensitivity, source, source_ref,
                 confidence, status, valid_from, valid_until, now, now),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def get_item(self, item_id: int) -> dict | None:
        with self._mu:
            row = self._conn.execute(
                "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d.pop("embedding", None)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_add_and_get_item -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): KnowledgeStore.add_item/get_item"
```

---

## Task 3: `list_items` / `approve` / `delete_item`

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_list_approve_delete(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="proposto", status="pending")
    assert [i["id"] for i in store.list_items(status="pending")] == [pid]
    store.approve(pid)
    assert store.get_item(pid)["status"] == "approved"
    assert store.list_items(status="pending") == []
    store.delete_item(pid)
    assert store.get_item(pid) is None
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_list_approve_delete -v`
Expected: FAIL — `AttributeError: ... 'list_items'`

- [ ] **Step 3: Write minimal implementation**

```python
    def list_items(
        self, *, status: str | None = None, owner: str | None = None,
        kind: str | None = None, limit: int = 100,
    ) -> list[dict]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status=?"); params.append(status)
        if owner is not None:
            clauses.append("owner=?"); params.append(owner)
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

    def approve(self, item_id: int) -> None:
        with self._mu:
            self._conn.execute(
                "UPDATE knowledge_items SET status='approved', updated_at=? WHERE id=?",
                (self._now(), item_id),
            )
            self._conn.commit()

    def delete_item(self, item_id: int) -> None:
        with self._mu:
            self._conn.execute("DELETE FROM knowledge_items WHERE id=?", (item_id,))
            self._conn.execute(
                "DELETE FROM knowledge_links WHERE src_id=? OR dst_id=?",
                (item_id, item_id),
            )
            self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_list_approve_delete -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): KnowledgeStore.list_items/approve/delete_item"
```

---

## Task 4: `search` (retrieval vettoriale brute-force)

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

Filtra per `status='approved'`, opzionale `owner` (item della persona + `home`) e `allow_sensitive` (Fase 2 lo userà; default False → esclude `sensitive`). Brute-force cosine come `memory_store`.

- [ ] **Step 1: Write the failing test**

```python
def test_search_ranks_by_cosine_and_excludes_sensitive(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="fact", content="vicino", embedding=[1.0, 0.0])
    store.add_item(kind="fact", content="lontano", embedding=[0.0, 1.0])
    store.add_item(kind="fact", content="segreto", embedding=[1.0, 0.0],
                   sensitivity="sensitive")
    res = store.search(query_vec=[1.0, 0.0], k=5, allow_sensitive=False)
    contents = [r["content"] for r in res]
    assert contents[0] == "vicino"          # cosine = 1.0
    assert "segreto" not in contents        # sensitive escluso
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_search_ranks_by_cosine_and_excludes_sensitive -v`
Expected: FAIL — `AttributeError: ... 'search'`

- [ ] **Step 3: Write minimal implementation**

```python
    def search(
        self, *, query_vec: list[float], k: int = 5,
        owner: str | None = None, allow_sensitive: bool = False,
        kinds: list[str] | None = None,
    ) -> list[dict]:
        clauses = ["status='approved'", "embedding IS NOT NULL"]
        params: list = []
        if owner is not None:
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        if not allow_sensitive:
            clauses.append("sensitivity='normal'")
        if kinds:
            clauses.append("kind IN (%s)" % ",".join("?" * len(kinds)))
            params.extend(kinds)
        sql = "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
        with self._mu:
            rows = self._conn.execute(sql, params).fetchall()
        scored = []
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_search_ranks_by_cosine_and_excludes_sensitive -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): KnowledgeStore.search (vector, owner/sensitivity filters)"
```

---

## Task 5: Query strutturate (scadenze + spese)

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_structured_queries(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-01")
    store.add_item(kind="obligation", content="Bollo", due_date="2026-12-31")
    store.add_item(kind="expense", content="Spesa", amount=42.0, category="cibo")
    store.add_item(kind="expense", content="Cena", amount=8.0, category="cibo")

    due = store.upcoming_obligations(before="2026-08-01")
    assert [d["content"] for d in due] == ["TARI"]

    agg = store.expenses_by_category()
    assert agg["cibo"] == 50.0
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_structured_queries -v`
Expected: FAIL — `AttributeError: ... 'upcoming_obligations'`

- [ ] **Step 3: Write minimal implementation**

```python
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
            d = dict(r); d.pop("embedding", None); d.pop("data", None)
            out.append(d)
        return out

    def expenses_by_category(self, *, owner: str | None = None) -> dict[str, float]:
        clauses = ["kind='expense'", "status='approved'", "amount IS NOT NULL"]
        params: list = []
        if owner is not None:
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        with self._mu:
            rows = self._conn.execute(
                "SELECT COALESCE(category,'(nessuna)') AS cat, SUM(amount) AS tot"
                " FROM knowledge_items WHERE " + " AND ".join(clauses)
                + " GROUP BY cat", params,
            ).fetchall()
        return {r["cat"]: float(r["tot"]) for r in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_structured_queries -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): structured queries (upcoming_obligations, expenses_by_category)"
```

---

## Task 6: Grafo (`add_link` + `neighbors` 1-hop)

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_links_and_neighbors(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a = store.add_item(kind="expense", content="Cena")
    b = store.add_item(kind="preference", content="Pizza")
    store.add_link(src_id=a, dst_id=b, relation="related")
    nb = store.neighbors(a)
    assert [n["content"] for n in nb] == ["Pizza"]
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_links_and_neighbors -v`
Expected: FAIL — `AttributeError: ... 'add_link'`

- [ ] **Step 3: Write minimal implementation**

```python
    def add_link(
        self, *, src_id: int, dst_id: int, relation: str,
        weight: float = 1.0, source: str = "manual",
    ) -> None:
        with self._mu:
            self._conn.execute(
                "INSERT OR IGNORE INTO knowledge_links"
                "(src_id, dst_id, relation, weight, source, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (src_id, dst_id, relation, weight, source, self._now()),
            )
            self._conn.commit()

    def neighbors(self, item_id: int) -> list[dict]:
        with self._mu:
            rows = self._conn.execute(
                "SELECT i.* FROM knowledge_items i"
                " JOIN knowledge_links l ON l.dst_id = i.id"
                " WHERE l.src_id = ? AND i.status='approved'", (item_id,),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_links_and_neighbors -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): graph links (add_link, neighbors 1-hop)"
```

---

## Task 7: Identità utente HA (`owner`)

**Files:**
- Create: `hiris/app/brain/identity.py`
- Test: `tests/test_knowledge_identity.py`

HA Supervisor ingress aggiunge `X-Remote-User-Id`/`X-Remote-User-Name`. Risolviamo `owner`: l'id utente se presente, altrimenti `home`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_identity.py
from hiris.app.brain.identity import resolve_owner


class _Req:
    def __init__(self, headers):
        self.headers = headers


def test_resolve_owner_from_header():
    req = _Req({"X-Remote-User-Id": "abc123"})
    assert resolve_owner(req) == "abc123"


def test_resolve_owner_defaults_home():
    assert resolve_owner(_Req({})) == "home"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.identity`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/identity.py
from __future__ import annotations


def resolve_owner(request) -> str:
    """Owner = HA user id dagli header ingress, altrimenti 'home' (condiviso)."""
    uid = request.headers.get("X-Remote-User-Id", "").strip()
    return uid or "home"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/identity.py tests/test_knowledge_identity.py
git commit -m "feat(brain): resolve_owner from HA ingress user header"
```

---

## Task 8: Tool LLM `save_knowledge` / `recall_knowledge` / `link_knowledge`

**Files:**
- Create: `hiris/app/tools/knowledge_tools.py`
- Modify: `hiris/app/tools/dispatcher.py`
- Modify: `hiris/app/claude_runner.py` (import + `ALL_TOOL_DEFS`)
- Test: `tests/test_knowledge_tools.py`

I tool def seguono il formato esistente (vedi `tools/memory_tools.py`). `save_knowledge` crea un item `status='pending'` (loop conferma). `recall_knowledge` fa una `search` (embeddando la query). Lo store e l'embedder sono iniettati nel dispatcher.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_tools.py
import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.knowledge_tools import (
    SAVE_KNOWLEDGE_TOOL_DEF, RECALL_KNOWLEDGE_TOOL_DEF, LINK_KNOWLEDGE_TOOL_DEF,
)
from hiris.app.brain.knowledge_store import KnowledgeStore


def test_tool_defs_have_names():
    assert SAVE_KNOWLEDGE_TOOL_DEF["name"] == "save_knowledge"
    assert RECALL_KNOWLEDGE_TOOL_DEF["name"] == "recall_knowledge"
    assert LINK_KNOWLEDGE_TOOL_DEF["name"] == "link_knowledge"


@pytest.mark.asyncio
async def test_save_knowledge_creates_pending(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_save_knowledge
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])
    res = await handle_save_knowledge(
        store, embedder,
        {"kind": "preference", "content": "Paolo ama la pizza"},
        owner="home",
    )
    assert res["status"] == "pending"
    pending = store.list_items(status="pending")
    assert pending[0]["content"] == "Paolo ama la pizza"
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.tools.knowledge_tools`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/tools/knowledge_tools.py
from __future__ import annotations
from typing import Any

SAVE_KNOWLEDGE_TOOL_DEF = {
    "name": "save_knowledge",
    "description": "Proponi di salvare un fatto/preferenza/scadenza/spesa nel "
                   "second brain di casa. Crea una proposta che l'utente approva.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string",
                     "enum": ["fact", "preference", "obligation", "expense", "note"]},
            "content": {"type": "string", "description": "Il testo da ricordare"},
            "title": {"type": "string"},
            "amount": {"type": "number"},
            "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            "category": {"type": "string"},
            "sensitivity": {"type": "string", "enum": ["normal", "sensitive"]},
        },
        "required": ["kind", "content"],
    },
}

RECALL_KNOWLEDGE_TOOL_DEF = {
    "name": "recall_knowledge",
    "description": "Cerca nel second brain di casa fatti/preferenze rilevanti.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "Quanti risultati (default 5)"},
        },
        "required": ["query"],
    },
}

LINK_KNOWLEDGE_TOOL_DEF = {
    "name": "link_knowledge",
    "description": "Collega due item del second brain (proposta).",
    "input_schema": {
        "type": "object",
        "properties": {
            "src_id": {"type": "integer"},
            "dst_id": {"type": "integer"},
            "relation": {"type": "string"},
        },
        "required": ["src_id", "dst_id", "relation"],
    },
}


async def handle_save_knowledge(store, embedder, tool_input: dict, *, owner: str) -> dict:
    content = tool_input["content"]
    try:
        emb = await embedder.embed(content)
    except Exception:
        emb = []
    item_id = store.add_item(
        kind=tool_input["kind"], content=content, owner=owner,
        title=tool_input.get("title", ""), amount=tool_input.get("amount"),
        due_date=tool_input.get("due_date"), category=tool_input.get("category"),
        embedding=emb or None,
        sensitivity=tool_input.get("sensitivity", "normal"),
        source="chat", status="pending",
    )
    return {"id": item_id, "status": "pending"}


async def handle_recall_knowledge(store, embedder, tool_input: dict, *, owner: str,
                                  allow_sensitive: bool = False) -> dict:
    try:
        qv = await embedder.embed(tool_input["query"])
    except Exception:
        qv = []
    if not qv:
        return {"results": []}
    res = store.search(query_vec=qv, k=int(tool_input.get("k", 5)),
                       owner=owner, allow_sensitive=allow_sensitive)
    return {"results": [{"id": r["id"], "kind": r["kind"],
                         "content": r["content"]} for r in res]}


async def handle_link_knowledge(store, tool_input: dict) -> dict:
    store.add_link(src_id=int(tool_input["src_id"]),
                   dst_id=int(tool_input["dst_id"]),
                   relation=tool_input["relation"], source="inferred")
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_tools.py -v`
Expected: PASS

- [ ] **Step 5: Wire dispatcher + ALL_TOOL_DEFS**

In `hiris/app/tools/dispatcher.py`: nel costruttore aggiungere parametri opzionali `knowledge_store=None, embedder=None` e memorizzarli; in `dispatch()` aggiungere il routing (seguire lo stile dei tool esistenti, recuperando `owner` dal contesto passato — per ora `owner="home"`, l'owner per-richiesta arriva in Task 9):

```python
        if name == "save_knowledge" and self._knowledge_store:
            return await handle_save_knowledge(
                self._knowledge_store, self._embedder, tool_input, owner="home")
        if name == "recall_knowledge" and self._knowledge_store:
            return await handle_recall_knowledge(
                self._knowledge_store, self._embedder, tool_input, owner="home")
        if name == "link_knowledge" and self._knowledge_store:
            return await handle_link_knowledge(self._knowledge_store, tool_input)
```

con import in cima al dispatcher:
```python
from .knowledge_tools import (
    handle_save_knowledge, handle_recall_knowledge, handle_link_knowledge,
)
```

In `hiris/app/claude_runner.py`: importare i tre tool def e aggiungerli a `ALL_TOOL_DEFS`:
```python
from .tools.knowledge_tools import (
    SAVE_KNOWLEDGE_TOOL_DEF, RECALL_KNOWLEDGE_TOOL_DEF, LINK_KNOWLEDGE_TOOL_DEF,
)
# ... dentro ALL_TOOL_DEFS = [ ... , SAVE_KNOWLEDGE_TOOL_DEF,
#     RECALL_KNOWLEDGE_TOOL_DEF, LINK_KNOWLEDGE_TOOL_DEF, ]
```

- [ ] **Step 6: Run the full suite to verify no regression**

Run: `python -m pytest tests/test_knowledge_tools.py tests/test_claude_runner.py -v`
Expected: PASS (tutti)

- [ ] **Step 7: Commit**

```bash
git add hiris/app/tools/knowledge_tools.py hiris/app/tools/dispatcher.py hiris/app/claude_runner.py tests/test_knowledge_tools.py
git commit -m "feat(brain): knowledge tools (save/recall/link) wired into dispatcher + runner"
```

---

## Task 9: API pending/approve + manual add

**Files:**
- Create: `hiris/app/api/handlers_knowledge.py`
- Modify: `hiris/app/server.py` (registrazione rotte + init store + owner per-richiesta)
- Test: `tests/test_handlers_knowledge.py`

Rotte: `GET /api/knowledge/pending`, `POST /api/knowledge/{id}/approve`, `POST /api/knowledge/{id}/reject` (= delete), `POST /api/knowledge` (manual add → `approved`, con `owner` via `resolve_owner`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_knowledge.py
import pytest
from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_pending_and_approve(aiohttp_client, tmp_path):
    from aiohttp import web
    from hiris.app.api.handlers_knowledge import (
        handle_list_pending, handle_approve,
    )
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="x", status="pending")
    app = web.Application()
    app["knowledge_store"] = store
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    client = await aiohttp_client(app)

    r = await client.get("/api/knowledge/pending")
    data = await r.json()
    assert [i["id"] for i in data["items"]] == [pid]

    r2 = await client.post(f"/api/knowledge/{pid}/approve")
    assert r2.status == 200
    assert store.get_item(pid)["status"] == "approved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_knowledge.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.api.handlers_knowledge`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/api/handlers_knowledge.py
from aiohttp import web
from ..brain.identity import resolve_owner


async def handle_list_pending(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    if store is None:
        return web.json_response({"items": []})
    return web.json_response({"items": store.list_items(status="pending")})


async def handle_approve(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    item_id = int(request.match_info["id"])
    store.approve(item_id)
    return web.json_response({"ok": True})


async def handle_reject(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    item_id = int(request.match_info["id"])
    store.delete_item(item_id)
    return web.json_response({"ok": True})


async def handle_manual_add(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    content = (body.get("content") or "").strip()
    if not content:
        return web.json_response({"error": "content required"}, status=400)
    item_id = store.add_item(
        kind=body.get("kind", "note"), content=content,
        owner=resolve_owner(request), title=body.get("title", ""),
        amount=body.get("amount"), due_date=body.get("due_date"),
        category=body.get("category"),
        sensitivity=body.get("sensitivity", "normal"),
        source="manual", status="approved",
    )
    return web.json_response({"id": item_id, "status": "approved"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handlers_knowledge.py -v`
Expected: PASS

- [ ] **Step 5: Wire in server.py**

In `hiris/app/server.py`, dove vengono inizializzati gli altri store e registrate le rotte (cercare `memory_store` / `app.router.add_get`), aggiungere:
```python
from .brain.knowledge_store import KnowledgeStore
# init (vicino agli altri store, data_dir = /data):
knowledge_store = KnowledgeStore(os.path.join(data_dir, "knowledge.db"))
app["knowledge_store"] = knowledge_store
# passare store+embedder al dispatcher dove viene costruito il ToolDispatcher
# (knowledge_store=knowledge_store, embedder=<embedding_provider già costruito>)
# rotte:
from .api.handlers_knowledge import (
    handle_list_pending, handle_approve, handle_reject, handle_manual_add,
)
app.router.add_get("/api/knowledge/pending", handle_list_pending)
app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
app.router.add_post("/api/knowledge", handle_manual_add)
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (nessuna regressione)

- [ ] **Step 7: Commit**

```bash
git add hiris/app/api/handlers_knowledge.py hiris/app/server.py tests/test_handlers_knowledge.py
git commit -m "feat(brain): knowledge pending/approve/reject + manual add API"
```

---

## Task 10: Hook promemoria scadenze (task_engine)

**Files:**
- Modify: `hiris/app/server.py` (job periodico) **oppure** `hiris/app/agent_engine.py` (scheduler già presente)
- Test: `tests/test_knowledge_reminders.py`

Funzione pura `due_obligations_to_notify(store, today, horizon_days)` testabile, che ritorna gli item con `due_date` entro l'orizzonte; la schedulazione effettiva riusa lo scheduler esistente.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_reminders.py
from datetime import date
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reminders import due_obligations_to_notify


def test_due_within_horizon(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-03")
    store.add_item(kind="obligation", content="Lontano", due_date="2026-09-01")
    out = due_obligations_to_notify(store, today=date(2026, 6, 30), horizon_days=7)
    assert [o["content"] for o in out] == ["TARI"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_reminders.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.reminders`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/reminders.py
from __future__ import annotations
from datetime import date, timedelta


def due_obligations_to_notify(store, *, today: date, horizon_days: int = 7) -> list[dict]:
    before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    return store.upcoming_obligations(before=before)
```

(firma reale: `due_obligations_to_notify(store, today=..., horizon_days=...)` — keyword-only; aggiornare il test se necessario per usare i kwargs.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_reminders.py -v`
Expected: PASS

- [ ] **Step 5: Wire schedulazione**

In `server.py` (o `agent_engine`), registrare un job giornaliero che chiama `due_obligations_to_notify(store, today=date.today(), horizon_days=7)` e per ogni risultato invia una notifica via il dispatcher/`task_engine` esistente (riusare il percorso `send_notification`). Throttling/dedup: tenere traccia degli item già notificati (campo in `data` JSON o tabella a parte — definirlo qui se serve, altrimenti notifica una volta al giorno).

- [ ] **Step 6: Commit**

```bash
git add hiris/app/brain/reminders.py hiris/app/server.py tests/test_knowledge_reminders.py
git commit -m "feat(brain): due-date reminders hook via task engine"
```

---

## Self-Review (compilata)

**Spec coverage (Fase 1):** store items+links (Task 1-3,6 ✓), retrieval vettoriale (Task 4 ✓), strutturato (Task 5 ✓), grafo 1-hop (Task 6 ✓), identità HA (Task 7 ✓), tool LLM (Task 8 ✓), loop pending/approve + manual (Task 9 ✓), promemoria (Task 10 ✓). **Esclusi per design da Fase 1:** privacy egress/pseudonimizzazione (Fase 2), `document_chunks`/Mayan (Fase 3), policy `knowledge_access` (Fase 2, dove serve l'egress sui sensibili) — i `sensitive` qui sono memorizzati ed esclusi da `search` di default (`allow_sensitive=False`), quindi non finiscono nei prompt.

**Placeholder scan:** i wiring (Task 8 Step 5, Task 9 Step 5, Task 10 Step 5) rimandano a punti del codice esistente da localizzare (`dispatcher.dispatch`, `server.py` init store/rotte, scheduler); sono indicazioni precise su *dove* e *cosa*, non logica mancante. L'unico punto aperto è il dedup notifiche (Task 10 Step 5): l'implementatore sceglie campo `data` JSON o tabellina — esplicitato.

**Type consistency:** firme coerenti tra task — `KnowledgeStore.search(query_vec=..., allow_sensitive=...)`, `add_item(**kw)`, `handle_recall_knowledge(store, embedder, tool_input, owner=...)`. I tool def usano i nomi `save_knowledge`/`recall_knowledge`/`link_knowledge` ovunque.

**UI:** non inclusa in Fase 1 (solo API). Una UI minima per i pending è un follow-up leggero (consuma `/api/knowledge/pending` + approve/reject), pianificabile separatamente.
