# Second Brain — Fase 3: Connettore Mayan (documenti) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingerire i documenti di Mayan EDMS (192.168.1.31:8090) come conoscenza ricercabile del second brain: OCR preso via API → chunk → embedding locale → `document_chunks` collegati a un `knowledge_items` `kind='document'`, ricercabili via `recall_knowledge` (con lo strato privacy della Fase 2). Scoping a un **tag** "HIRIS" curato dall'utente.

**Architecture:** Nuovo `hiris/app/brain/mayan_client.py` (client REST httpx, auth a token, circuit-breaker come `OpenAICompatRunner`). Tabella `document_chunks` su `KnowledgeStore`. Pipeline `brain/mayan_ingest.py` (lista doc del tag → OCR → chunk → embed locale → store). Retrieval esteso: `recall_knowledge` cerca anche nei chunk. Config `mayan` in `config.yaml` + job di polling in `server.py`.

**Tech Stack:** Python 3.14, httpx (già dipendenza), sqlite3, model2vec (embedding locali), pytest/pytest-asyncio. Riuso: `brain/knowledge_store.py`, `backends/embeddings.py`, `brain/privacy.py`, pattern circuit-breaker.

**Spec di riferimento:** `docs/design/2026-06-24-second-brain-foundation-design.md` (§4.3, §8).

**⚠️ Dipendenza esterna (Mayan):** gli endpoint REST esatti dipendono dalla versione di Mayan. Quelli usati qui sono best-known per **v4** e sono **centralizzati** in `mayan_client.py` (costanti in cima). I test unitari **mockano** l'HTTP, quindi non dipendono dagli endpoint reali. La **verifica reale** (path OCR, filtro tag) si fa contro l'istanza live `.31` dopo il merge; se un path differisce, si corregge una sola costante.

**Decisioni implementative:**
- Scoping per **tag** (id configurabile), non cabinet.
- Phase 3 ingerisce documenti **ricercabili**; l'**estrazione strutturata** (spese/scadenze dai documenti) è rimandata ai piani di dominio.
- Sensibilità: i documenti ingeriti sono `sensitivity` configurabile (default `sensitive`, prudente — estratti conto). Lo strato privacy della Fase 2 li protegge automaticamente in retrieval.
- Dedup ingestion: si tiene traccia dei `mayan_doc_id` già ingeriti (via `source_ref` sugli item `kind='document'`).

---

## File Structure

| File | Responsabilità |
|---|---|
| `hiris/app/brain/knowledge_store.py` (modify) | tabella `document_chunks` + `add_document_chunk` / `search_chunks` + `document_exists(mayan_doc_id)` |
| `hiris/app/brain/mayan_client.py` (create) | client REST Mayan (token, circuit-breaker): `list_tag_documents`, `get_document_label`, `get_ocr_text` |
| `hiris/app/brain/chunking.py` (create) | `chunk_text(text, size, overlap)` |
| `hiris/app/brain/mayan_ingest.py` (create) | `ingest_tag(client, store, embedder, tag_id, sensitivity)` |
| `hiris/app/tools/knowledge_tools.py` (modify) | `handle_recall_knowledge` include i chunk documentali |
| `hiris/app/server.py` (modify) | init MayanClient + job polling ingestion |
| `hiris/config.yaml` (modify) | blocco opzioni `mayan` + schema |
| tests | `test_mayan_client.py`, `test_chunking.py`, `test_mayan_ingest.py`, additions to `test_knowledge_store.py` / `test_knowledge_tools.py` |

---

## Task 1: tabella `document_chunks` + metodi store

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_document_chunks_add_search_exists(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    doc = store.add_item(kind="document", content="Estratto conto giugno",
                         source="mayan", source_ref="42", sensitivity="sensitive")
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=0,
                             content="bonifico 50 euro", embedding=[1.0, 0.0])
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=1,
                             content="prelievo bancomat", embedding=[0.0, 1.0])
    assert store.document_exists("42") is True
    assert store.document_exists("99") is False
    hits = store.search_chunks(query_vec=[1.0, 0.0], k=1, allow_sensitive=True)
    assert hits[0]["content"] == "bonifico 50 euro"
    assert hits[0]["sensitivity"] == "sensitive"
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_store.py::test_document_chunks_add_search_exists -v`
Expected: FAIL — `AttributeError: ... 'add_document_chunk'`

- [ ] **Step 3: Write minimal implementation**

In `_SCHEMA` (dopo `knowledge_links`) aggiungere:
```python
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
```

Metodi:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_store.py::test_document_chunks_add_search_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(brain): document_chunks table + add/search/exists"
```

---

## Task 2: `chunk_text` helper

**Files:**
- Create: `hiris/app/brain/chunking.py`
- Test: `tests/test_chunking.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chunking.py
from hiris.app.brain.chunking import chunk_text


def test_chunk_text_sizes_and_overlap():
    text = "abcdefghij"  # 10 char
    chunks = chunk_text(text, size=4, overlap=1)
    # passo = size-overlap = 3 → 0:4, 3:7, 6:10, 9:10
    assert chunks[0] == "abcd"
    assert chunks[1] == "defg"
    assert all(len(c) <= 4 for c in chunks)
    assert "".join(c[0] for c in chunks)  # non vuoto


def test_chunk_text_empty():
    assert chunk_text("", size=4, overlap=1) == []
    assert chunk_text("   ", size=4, overlap=1) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.chunking`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/chunking.py
from __future__ import annotations


def chunk_text(text: str, *, size: int = 800, overlap: int = 100) -> list[str]:
    """Spezza `text` in finestre di `size` caratteri con `overlap` di sovrapposizione.
    Passo = max(1, size - overlap). Ritorna [] per testo vuoto/whitespace."""
    if not text or not text.strip():
        return []
    if size <= 0:
        return [text]
    step = max(1, size - max(0, overlap))
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i:i + size])
        if i + size >= n:
            break
        i += step
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/chunking.py tests/test_chunking.py
git commit -m "feat(brain): chunk_text sliding-window helper"
```

---

## Task 3: `MayanClient` (REST + circuit-breaker)

**Files:**
- Create: `hiris/app/brain/mayan_client.py`
- Test: `tests/test_mayan_client.py`

Client async httpx. Auth header `Authorization: Token <token>`. Endpoint v4 **centralizzati** in costanti (da verificare contro la live). Circuit-breaker come `OpenAICompatRunner` (3 fallimenti connessione → skip 60s). Metodi: `list_tag_documents(tag_id) -> list[dict]` (id+label), `get_ocr_text(doc_id) -> str`.

- [ ] **Step 1: Write the failing test** (HTTP mockato — non tocca la rete)

```python
# tests/test_mayan_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.brain.mayan_client import MayanClient


@pytest.mark.asyncio
async def test_list_tag_documents_parses_results():
    c = MayanClient(base_url="http://x/api/v4", token="t")
    resp = MagicMock(); resp.status_code = 200
    resp.json = MagicMock(return_value={"results": [
        {"id": 42, "label": "Estratto conto"}, {"id": 43, "label": "Bolletta"}]})
    resp.raise_for_status = MagicMock()
    c._client.get = AsyncMock(return_value=resp)
    docs = await c.list_tag_documents(7)
    assert [d["id"] for d in docs] == [42, 43]
    await c.aclose()


@pytest.mark.asyncio
async def test_circuit_opens_after_connection_failures():
    import httpx
    from hiris.app.brain.mayan_client import _MAYAN_CIRCUIT_THRESHOLD
    c = MayanClient(base_url="http://dead/api/v4", token="t")
    c._client.get = AsyncMock(side_effect=httpx.ConnectError("no dns"))
    for _ in range(_MAYAN_CIRCUIT_THRESHOLD + 3):
        assert await c.list_tag_documents(7) == []   # degrada a lista vuota
    assert c._client.get.await_count == _MAYAN_CIRCUIT_THRESHOLD  # poi salta la rete
    await c.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mayan_client.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.mayan_client`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/mayan_client.py
from __future__ import annotations
import logging
import time
import httpx

logger = logging.getLogger(__name__)

_MAYAN_CIRCUIT_THRESHOLD = 3
_MAYAN_CIRCUIT_COOLDOWN_SEC = 60

# ── Endpoint v4 (VERIFICARE contro la propria istanza Mayan) ────────────────
# Filtro documenti per tag e recupero testo OCR variano per versione: questi
# sono i path best-known per Mayan v4.x. Se differiscono, correggere QUI.
_EP_TAG_DOCUMENTS = "/tags/{tag_id}/documents/"          # GET → {results:[{id,label}]}
_EP_DOCUMENT_OCR = "/documents/{doc_id}/ocr/"            # GET → testo OCR concatenato


class MayanClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 20.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"Authorization": f"Token {token}"},
            timeout=httpx.Timeout(timeout, connect=5.0),
        )
        self._conn_fail = 0
        self._circuit_until = 0.0

    def _circuit_open(self) -> bool:
        return time.monotonic() < self._circuit_until

    def _record_fail(self) -> None:
        self._conn_fail += 1
        if self._conn_fail >= _MAYAN_CIRCUIT_THRESHOLD and not self._circuit_open():
            self._circuit_until = time.monotonic() + _MAYAN_CIRCUIT_COOLDOWN_SEC
            logger.warning("Mayan unreachable (%d fails) — circuit open %ds",
                           self._conn_fail, _MAYAN_CIRCUIT_COOLDOWN_SEC)

    def _record_ok(self) -> None:
        self._conn_fail = 0
        self._circuit_until = 0.0

    async def _get(self, path: str):
        if self._circuit_open():
            return None
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            self._record_ok()
            return resp
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
            self._record_fail()
            logger.warning("Mayan GET %s connection error: %s", path, exc)
            return None
        except Exception as exc:
            logger.error("Mayan GET %s failed: %s", path, exc)
            return None

    async def list_tag_documents(self, tag_id: int) -> list[dict]:
        resp = await self._get(_EP_TAG_DOCUMENTS.format(tag_id=tag_id))
        if resp is None:
            return []
        data = resp.json()
        return [{"id": r["id"], "label": r.get("label", "")}
                for r in data.get("results", [])]

    async def get_ocr_text(self, doc_id: int) -> str:
        resp = await self._get(_EP_DOCUMENT_OCR.format(doc_id=doc_id))
        if resp is None:
            return ""
        try:
            data = resp.json()
            # alcune versioni ritornano {content: "..."}; altre testo grezzo
            return data.get("content", "") if isinstance(data, dict) else str(data)
        except Exception:
            return resp.text or ""

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mayan_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/mayan_client.py tests/test_mayan_client.py
git commit -m "feat(brain): MayanClient REST (tag documents, OCR) with circuit-breaker"
```

---

## Task 4: pipeline `ingest_tag`

**Files:**
- Create: `hiris/app/brain/mayan_ingest.py`
- Test: `tests/test_mayan_ingest.py`

Per ogni documento del tag non ancora ingerito (`store.document_exists` False): prendi OCR → chunk → embed locale → crea item `kind='document'` (source='mayan', source_ref=id, sensitivity) → salva i chunk. Ritorna il numero di documenti ingeriti.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mayan_ingest.py
import pytest
from unittest.mock import AsyncMock
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.mayan_ingest import ingest_tag


@pytest.mark.asyncio
async def test_ingest_tag_creates_document_and_chunks(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    client = AsyncMock()
    client.list_tag_documents = AsyncMock(return_value=[{"id": 42, "label": "Estratto"}])
    client.get_ocr_text = AsyncMock(return_value="riga uno " * 200)  # testo lungo
    embedder = AsyncMock(); embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    n = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")
    assert n == 1
    assert store.document_exists("42") is True
    # idempotente: una seconda passata non re-ingerisce
    n2 = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")
    assert n2 == 0
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mayan_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.mayan_ingest`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/mayan_ingest.py
from __future__ import annotations
import asyncio
import logging
from .chunking import chunk_text

logger = logging.getLogger(__name__)


async def ingest_tag(client, store, embedder, *, tag_id: int,
                     sensitivity: str = "sensitive", owner: str = "home") -> int:
    docs = await client.list_tag_documents(tag_id)
    loop = asyncio.get_running_loop()
    ingested = 0
    for d in docs:
        doc_id = str(d["id"])
        if await loop.run_in_executor(None, lambda: store.document_exists(doc_id)):
            continue
        text = await client.get_ocr_text(d["id"])
        if not text or not text.strip():
            continue
        item_id = await loop.run_in_executor(None, lambda: store.add_item(
            kind="document", content=d.get("label", "") or f"doc {doc_id}",
            owner=owner, source="mayan", source_ref=doc_id,
            sensitivity=sensitivity, status="approved"))
        for idx, ch in enumerate(chunk_text(text)):
            try:
                emb = await embedder.embed(ch)
            except Exception:
                emb = []
            await loop.run_in_executor(None, lambda i=item_id, idx=idx, ch=ch, emb=emb:
                store.add_document_chunk(item_id=i, mayan_doc_id=doc_id,
                                         chunk_index=idx, content=ch,
                                         embedding=emb or None))
        ingested += 1
        logger.info("Mayan: ingerito documento %s (%s)", doc_id, d.get("label", ""))
    return ingested
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mayan_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/mayan_ingest.py tests/test_mayan_ingest.py
git commit -m "feat(brain): Mayan tag ingestion pipeline (OCR -> chunk -> embed)"
```

---

## Task 5: recall include i chunk documentali

**Files:**
- Modify: `hiris/app/tools/knowledge_tools.py`
- Test: `tests/test_knowledge_tools.py`

`handle_recall_knowledge` deve cercare anche nei `document_chunks` e includerli nei risultati, applicando la stessa pseudonimizzazione (sensibile + cloud) ai chunk.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_recall_includes_document_chunks(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.knowledge_store import KnowledgeStore
    from unittest.mock import AsyncMock
    store = KnowledgeStore(str(tmp_path / "b.db"))
    doc = store.add_item(kind="document", content="Estratto", source="mayan",
                         source_ref="42", sensitivity="normal")
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=0,
                             content="canone mensile 9.99", embedding=[1.0, 0.0])
    embedder = AsyncMock(); embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    res = await handle_recall_knowledge(store, embedder, {"query": "canone"},
                                        owner="home", allow_sensitive=False)
    contents = [r["content"] for r in res["results"]]
    assert "canone mensile 9.99" in contents
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_tools.py::test_recall_includes_document_chunks -v`
Expected: FAIL (i chunk non sono nei risultati)

- [ ] **Step 3: Write minimal implementation**

In `handle_recall_knowledge`, dentro il `_build`/processing eseguito in executor, dopo `store.search(...)` aggiungere `store.search_chunks(...)` con gli stessi filtri (`owner`, `allow_sensitive`), e unire i risultati. Ogni chunk sensibile passa per la stessa pseudonimizzazione (`is_sensitive and cloud and pseudonymizer`). Mantenere il formato `{"id","kind","content"}` (per i chunk usare `kind="document_chunk"`). Cap totale a `k`. Esempio dello unione (sync, in executor):
```python
def _build():
    items = store.search(query_vec=qv, k=k, owner=owner, allow_sensitive=allow_sensitive)
    chunks = store.search_chunks(query_vec=qv, k=k, owner=owner, allow_sensitive=allow_sensitive)
    merged = []
    for r in items:
        merged.append((r.get("score", 0.0), r["id"], r["kind"], r["content"],
                       r.get("sensitivity")))
    for c in chunks:
        merged.append((c.get("score", 0.0), c["id"], "document_chunk", c["content"],
                       c.get("sensitivity")))
    merged.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, _id, kind, content, sens in merged[:k]:
        if sens == "sensitive" and cloud:
            content = (pseudonymizer.pseudonymize(content)
                       if pseudonymizer is not None
                       else "[contenuto sensibile non disponibile]")
        out.append({"id": _id, "kind": kind, "content": content})
    return out
out = await loop.run_in_executor(None, _build)
return {"results": out}
```
(Adattare alla struttura reale già presente; mantenere il comportamento Fase 2 su item sensibili.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_tools.py::test_recall_includes_document_chunks -v`
Expected: PASS

- [ ] **Step 5: Run full suite + commit**

Run: `python -m pytest tests/ -q` (verde, nessuna regressione sui test recall Fase 2)
```bash
git add hiris/app/tools/knowledge_tools.py tests/test_knowledge_tools.py
git commit -m "feat(brain): recall_knowledge includes Mayan document chunks"
```

---

## Task 6: config `mayan` + job di polling

**Files:**
- Modify: `hiris/config.yaml` (options + schema)
- Modify: `hiris/app/server.py` (init MayanClient + job ingestion)
- Test: `tests/test_release_script.py` o un test mirato per la validità del config

Aggiungere il blocco config (UI add-on prima, come da prassi) e un job che fa polling dell'ingestione.

- [ ] **Step 1: config.yaml**

In `options:` aggiungere:
```yaml
  # ── Mayan EDMS (documenti) ────────────────────────────────────────────────
  mayan:
    url: ""            # es. http://192.168.1.31:8090/api/v4
    token: ""          # API token Mayan
    tag_id: 0          # id del tag "HIRIS" da ingerire (0 = disabilitato)
    sensitivity: "sensitive"
    poll_minutes: 60
```
In `schema:` aggiungere:
```yaml
  mayan:
    url: str
    token: password
    tag_id: int
    sensitivity: "list(normal|sensitive)"
    poll_minutes: int(5,1440)?
```

- [ ] **Step 2: server.py wiring**

All'avvio, se `mayan.url` e `mayan.tag_id>0` e `mayan.token`: costruire `MayanClient(url, token)`, salvarlo su `app["mayan_client"]`, e registrare un job APScheduler ogni `poll_minutes` (e uno all'avvio dopo un breve delay) che chiama:
```python
await ingest_tag(app["mayan_client"], app["knowledge_store"],
                 app["embedding_provider"], tag_id=tag_id, sensitivity=sensitivity)
```
Chiudere il client (`await aclose()`) nel cleanup. Se la config è incompleta, NON registrare il job (no-op). Seguire i pattern di scheduling già presenti (vedi job promemoria Fase 1).

- [ ] **Step 3: test**

Aggiungere un test che, dato un config con `mayan` valorizzato, la app si avvia e registra il client (mock di `MayanClient`/`ingest_tag` per non toccare la rete); e che con `tag_id=0` non registra nulla. Mantenere verde `python -m pytest tests/ -q`.

- [ ] **Step 4: Commit**

```bash
git add hiris/config.yaml hiris/app/server.py tests/<file>
git commit -m "feat(brain): mayan config + polling ingestion job"
```

---

## Self-Review (compilata)

**Spec coverage (Fase 3, §4.3 + §8):** `document_chunks` (Task 1 ✓), chunking (Task 2 ✓), connettore Mayan REST + circuit-breaker (Task 3 ✓), pipeline OCR→chunk→embed scoped al tag, idempotente (Task 4 ✓), retrieval sui chunk con privacy Fase 2 (Task 5 ✓), config + polling (Task 6 ✓). **Differiti:** estrazione strutturata per banca, webhook Mayan (push) al posto del polling, de-tokenizzazione chunk SSE.

**Placeholder scan:** gli endpoint Mayan (Task 3) sono best-known e centralizzati, **esplicitamente da verificare** contro la live; i test mockano l'HTTP quindi non dipendono dai path. Task 5/6 rimandano a punti del codice esistente da localizzare (struttura reale di `handle_recall_knowledge`, scheduling in `server.py`) — indicazioni precise, non logica mancante.

**Type consistency:** `add_document_chunk`/`search_chunks`/`document_exists`, `MayanClient.list_tag_documents`/`get_ocr_text`/`aclose`, `chunk_text(text, size, overlap)`, `ingest_tag(client, store, embedder, tag_id, sensitivity, owner)` coerenti tra task e test.

**Rischi:** (1) endpoint Mayan reali da confermare in real (singola costante da correggere); (2) Task 5 modifica il path recall già toccato in Fase 2 — attenzione a non rompere la pseudonimizzazione esistente (la suite Fase 2 deve restare verde); (3) embedding in bulk di documenti lunghi = throttling (già off-loop via executor).
