# Second Brain — Fase 2: Privacy Egress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sbloccare la conoscenza `sensitive` nel ragionamento in modo sicuro: pseudonimizzazione reversibile della PII prima dell'invio a un modello **cloud**, controllo d'accesso per-agente, e de-tokenizzazione locale della risposta. Rispetta il multi-modello (la trasformazione si applica in base al modello dell'agente selezionato; se locale, in chiaro).

**Architecture:** Nuovo `hiris/app/brain/privacy.py` con un `VaultStore` sqlite (`pseudonym_vault`) e un `Pseudonymizer` (recognizer regex IT + `pseudonymize`/`detokenize` token-stabili). Un helper `backend_is_cloud(model)` nel `llm_router`. Una policy `knowledge_access` sull'`Agent`. Wiring: il tool `recall_knowledge` filtra per accesso dell'agente e pseudonimizza i risultati `sensitive` quando il modello target è cloud; la risposta finale viene de-tokenizzata in locale.

**Tech Stack:** Python 3.14, sqlite3, regex (`re`), pytest/pytest-asyncio. Riuso: `brain/knowledge_store.py`, `tools/dispatcher.py`, `claude_runner.py`, `llm_router.py`, `agent_engine.py`, `api/handlers_chat.py`.

**Spec di riferimento:** `docs/design/2026-06-24-second-brain-foundation-design.md` (Sezioni 5, 6).

**Decisioni implementative (questa fase):**
- **Vault separato** (`brain/privacy.py`, `vault.db`) — non accoppiato a `KnowledgeStore`.
- **At-rest encryption del vault DIFFERITA** (uniforme con la cifratura whole-DB / SQLCipher, anch'essa differita): `pseudonym_vault.value` è in chiaro come il resto del DB. Il valore della Fase 2 è la protezione **in transito**. Documentato come rischio noto.
- **"Minimize/aggregati" rimandato** ai piani di dominio (finanze): la Fase 2 fa pseudonimizzazione, non aggregazione.
- **De-tokenizzazione senza stato per-turno**: i token sono stabili nel vault, quindi `detokenize(text)` fa lookup nel vault (nessun threading di mapping per-turno).

---

## File Structure

| File | Responsabilità |
|---|---|
| `hiris/app/brain/privacy.py` | `VaultStore` (pseudonym_vault) + `Pseudonymizer` (recognizer IT, pseudonymize/detokenize) |
| `hiris/app/llm_router.py` (modify) | `backend_is_cloud(model) -> bool` |
| `hiris/app/agent_engine.py` (modify) | campo `knowledge_access` su `Agent` + load/create/update |
| `hiris/app/tools/dispatcher.py` (modify) | `recall_knowledge`: filtro accesso + pseudonimizzazione cloud; iniezione vault/pseudonymizer |
| `hiris/app/tools/knowledge_tools.py` (modify) | `handle_recall_knowledge`: opzioni `allow_sensitive` + `pseudonymizer` + `cloud` |
| `hiris/app/api/handlers_chat.py` (modify) | de-tokenizzazione della risposta finale |
| `hiris/app/server.py` (modify) | init `VaultStore`/`Pseudonymizer`, iniezione nel dispatcher |
| `tests/test_privacy.py` | Test vault + recognizer + pseudonymize/detokenize |
| `tests/test_llm_router.py` (modify) | Test `backend_is_cloud` |
| `tests/test_knowledge_tools.py` (modify) | Test recall: filtro accesso + pseudonimizzazione |

---

## Task 1: `VaultStore` (tabella `pseudonym_vault`)

**Files:**
- Create: `hiris/app/brain/privacy.py`
- Test: `tests/test_privacy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_privacy.py
from hiris.app.brain.privacy import VaultStore


def test_token_for_is_stable_and_typed(tmp_path):
    v = VaultStore(str(tmp_path / "vault.db"))
    t1 = v.token_for("iban", "IT60X0542811101000000123456")
    t2 = v.token_for("iban", "IT60X0542811101000000123456")
    t3 = v.token_for("iban", "IT00A0000000000000000000000")
    assert t1 == t2                 # stesso valore → stesso token
    assert t1 != t3                 # valori diversi → token diversi
    assert t1.startswith("[IBAN_") and t1.endswith("]")
    assert v.value_for(t1) == "IT60X0542811101000000123456"
    v.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_privacy.py::test_token_for_is_stable_and_typed -v`
Expected: FAIL — `ModuleNotFoundError: hiris.app.brain.privacy`

- [ ] **Step 3: Write minimal implementation**

```python
# hiris/app/brain/privacy.py
from __future__ import annotations
import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_VAULT_SCHEMA = """
CREATE TABLE IF NOT EXISTS pseudonym_vault (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT NOT NULL UNIQUE,
    value_hash  TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    pii_type    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_type ON pseudonym_vault(pii_type);
"""


class VaultStore:
    """Mappa locale, reversibile, PII<->token. NB: `value` è in chiaro
    (la cifratura at-rest è differita, uniforme con la cifratura whole-DB)."""

    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._mu = threading.Lock()
        with self._mu:
            self._conn.executescript(_VAULT_SCHEMA)
            self._conn.commit()

    @staticmethod
    def _hash(pii_type: str, value: str) -> str:
        return hashlib.sha256(f"{pii_type}:{value}".encode("utf-8")).hexdigest()

    def token_for(self, pii_type: str, value: str) -> str:
        h = self._hash(pii_type, value)
        with self._mu:
            row = self._conn.execute(
                "SELECT token FROM pseudonym_vault WHERE value_hash=?", (h,)
            ).fetchone()
            if row:
                return row["token"]
            n = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pseudonym_vault WHERE pii_type=?",
                (pii_type,),
            ).fetchone()["c"] + 1
            token = f"[{pii_type.upper()}_{n}]"
            self._conn.execute(
                "INSERT INTO pseudonym_vault(token, value_hash, value, pii_type, created_at)"
                " VALUES(?,?,?,?,?)",
                (token, h, value, pii_type, datetime.now(timezone.utc).strftime(_TS_FMT)),
            )
            self._conn.commit()
            return token

    def value_for(self, token: str) -> str | None:
        with self._mu:
            row = self._conn.execute(
                "SELECT value FROM pseudonym_vault WHERE token=?", (token,)
            ).fetchone()
        return row["value"] if row else None

    def close(self) -> None:
        with self._mu:
            self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_privacy.py::test_token_for_is_stable_and_typed -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/privacy.py tests/test_privacy.py
git commit -m "feat(brain): pseudonym VaultStore (stable reversible PII tokens)"
```

---

## Task 2: Recognizer PII (regex IT)

**Files:**
- Modify: `hiris/app/brain/privacy.py`
- Test: `tests/test_privacy.py`

Recognizer best-effort (NER deferito). Ordine: tipi più specifici prima (IBAN, codice fiscale, carta) poi email/telefono, per evitare sovrapposizioni.

- [ ] **Step 1: Write the failing test**

```python
def test_detect_pii_italian():
    from hiris.app.brain.privacy import detect_pii
    text = ("IBAN IT60X0542811101000000123456, CF RSSMRA85T10A562S, "
            "carta 4111 1111 1111 1111, mail a@b.it, tel +39 333 1234567")
    found = {t for _, _, t, _ in detect_pii(text)}
    assert {"iban", "codice_fiscale", "card", "email", "phone"} <= found
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_privacy.py::test_detect_pii_italian -v`
Expected: FAIL — `ImportError: cannot import name 'detect_pii'`

- [ ] **Step 3: Write minimal implementation**

Aggiungere in cima al file `import re` e:

```python
# Recognizer ordinati: specifici prima. Best-effort (NER deferito).
_PII_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("iban", re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Za-z]{12}\b")),
    ("codice_fiscale", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", re.compile(r"(?:\+39\s?)?\b3\d{2}[\s.-]?\d{6,7}\b")),
]


def detect_pii(text: str) -> list[tuple[int, int, str, str]]:
    """Ritorna [(start, end, pii_type, value)] senza sovrapposizioni,
    privilegiando i match più a sinistra e i tipi più specifici."""
    spans: list[tuple[int, int, str, str]] = []
    taken: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(s < te and e > ts for ts, te in taken)

    for pii_type, pat in _PII_PATTERNS:
        for m in pat.finditer(text):
            s, e = m.start(), m.end()
            if overlaps(s, e):
                continue
            taken.append((s, e))
            spans.append((s, e, pii_type, m.group()))
    spans.sort(key=lambda x: x[0])
    return spans
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_privacy.py::test_detect_pii_italian -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/privacy.py tests/test_privacy.py
git commit -m "feat(brain): Italian PII recognizers (iban, codice fiscale, card, email, phone)"
```

---

## Task 3: `Pseudonymizer` (pseudonymize + detokenize)

**Files:**
- Modify: `hiris/app/brain/privacy.py`
- Test: `tests/test_privacy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pseudonymize_and_detokenize_roundtrip(tmp_path):
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer
    p = Pseudonymizer(VaultStore(str(tmp_path / "vault.db")))
    raw = "Bonifico a Mario su IT60X0542811101000000123456 di 50 euro"
    masked = p.pseudonymize(raw)
    assert "IT60X0542811101000000123456" not in masked
    assert "[IBAN_1]" in masked
    # la risposta del modello cita il token: lo riportiamo al valore reale
    reply = "Ho registrato il bonifico su [IBAN_1]."
    assert p.detokenize(reply) == "Ho registrato il bonifico su IT60X0542811101000000123456."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_privacy.py::test_pseudonymize_and_detokenize_roundtrip -v`
Expected: FAIL — `ImportError: cannot import name 'Pseudonymizer'`

- [ ] **Step 3: Write minimal implementation**

```python
_TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")


class Pseudonymizer:
    def __init__(self, vault: VaultStore) -> None:
        self._vault = vault

    def pseudonymize(self, text: str) -> str:
        spans = detect_pii(text)
        if not spans:
            return text
        out = []
        last = 0
        for s, e, pii_type, value in spans:
            out.append(text[last:s])
            out.append(self._vault.token_for(pii_type, value))
            last = e
        out.append(text[last:])
        return "".join(out)

    def detokenize(self, text: str) -> str:
        def repl(m: "re.Match") -> str:
            val = self._vault.value_for(m.group())
            return val if val is not None else m.group()
        return _TOKEN_RE.sub(repl, text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_privacy.py::test_pseudonymize_and_detokenize_roundtrip -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/privacy.py tests/test_privacy.py
git commit -m "feat(brain): Pseudonymizer pseudonymize/detokenize over vault"
```

---

## Task 4: `backend_is_cloud(model)` nel router

**Files:**
- Modify: `hiris/app/llm_router.py`
- Test: `tests/test_llm_router.py`

Cloud = claude / openai / openrouter; locale = ollama (modelli senza prefisso noto). Riusa i predicati esistenti `_is_openai_model`, `_is_openrouter_model` e il prefisso `claude-`.

- [ ] **Step 1: Write the failing test**

```python
def test_backend_is_cloud():
    from hiris.app.llm_router import backend_is_cloud
    assert backend_is_cloud("claude-sonnet-4-6") is True
    assert backend_is_cloud("gpt-4o-mini") is True
    assert backend_is_cloud("openrouter:meta/llama") is True
    assert backend_is_cloud("llama3.1:8b") is False   # Ollama locale
    # 'auto' è cloud-first nelle strategie default → trattato come cloud (prudente)
    assert backend_is_cloud("auto") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_router.py::test_backend_is_cloud -v`
Expected: FAIL — `ImportError: cannot import name 'backend_is_cloud'`

- [ ] **Step 3: Write minimal implementation**

In `hiris/app/llm_router.py`, a livello modulo (vicino a `_is_openai_model`):

```python
def backend_is_cloud(model: str) -> bool:
    """True se il modello esce verso un provider cloud (claude/openai/openrouter).
    Ollama (e modelli senza prefisso noto) sono locali. 'auto' è trattato come
    cloud per prudenza (le strategie default partono dal cloud)."""
    if model == "auto":
        return True
    if model.startswith("claude-"):
        return True
    if _is_openrouter_model(model):
        return True
    if _is_openai_model(model):
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_router.py::test_backend_is_cloud -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/llm_router.py tests/test_llm_router.py
git commit -m "feat(router): backend_is_cloud(model) helper for privacy routing"
```

---

## Task 5: Policy `knowledge_access` sull'`Agent`

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Test: `tests/test_agent_engine.py`

Aggiungere il campo `knowledge_access: dict` all'`Agent` dataclass, default `{"allow_sensitive": False, "kinds": "all"}`. Va caricato in `_load`, accettato in `create_agent`/`UPDATABLE_FIELDS`/`update_agent`, e serializzato (è già coperto da `asdict`).

- [ ] **Step 1: Write the failing test**

```python
def test_agent_knowledge_access_default_and_update(engine):
    a = engine.create_agent({
        "name": "Chat", "type": "chat", "triggers": [],
        "system_prompt": "x", "allowed_tools": [], "enabled": True,
    })
    assert a.knowledge_access == {"allow_sensitive": False, "kinds": "all"}
    engine.update_agent(a.id, {"knowledge_access": {"allow_sensitive": True, "kinds": "all"}})
    assert engine.get_agent(a.id).knowledge_access["allow_sensitive"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_engine.py::test_agent_knowledge_access_default_and_update -v`
Expected: FAIL — `AttributeError: 'Agent' object has no attribute 'knowledge_access'`

- [ ] **Step 3: Write minimal implementation**

Nell'`Agent` dataclass (`agent_engine.py`), aggiungere (vicino agli altri campi con default factory):
```python
    knowledge_access: dict = field(default_factory=lambda: {"allow_sensitive": False, "kinds": "all"})
```
In `_load(...)` aggiungere alla costruzione dell'`Agent`:
```python
        knowledge_access=raw.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
```
In `create_agent(...)` aggiungere:
```python
        knowledge_access=data.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
```
In `UPDATABLE_FIELDS` aggiungere `"knowledge_access"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_agent_engine.py::test_agent_knowledge_access_default_and_update -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/agent_engine.py tests/test_agent_engine.py
git commit -m "feat(agent): knowledge_access policy field (allow_sensitive, kinds)"
```

---

## Task 6: `recall_knowledge` — filtro accesso + pseudonimizzazione cloud

**Files:**
- Modify: `hiris/app/tools/knowledge_tools.py`
- Modify: `hiris/app/tools/dispatcher.py`
- Modify: `hiris/app/server.py` (init VaultStore/Pseudonymizer + iniezione)
- Test: `tests/test_knowledge_tools.py`

`handle_recall_knowledge` riceve `allow_sensitive` (dalla policy dell'agente), un `pseudonymizer` opzionale e un flag `cloud`. Se `allow_sensitive` è True recupera anche i `sensitive`; per ogni risultato, se l'item è `sensitive` E `cloud` E c'è il pseudonymizer → il `content` viene pseudonimizzato prima di tornare al modello.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_recall_pseudonymizes_sensitive_for_cloud(tmp_path):
    from hiris.app.tools.knowledge_tools import handle_recall_knowledge
    from hiris.app.brain.knowledge_store import KnowledgeStore
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer
    from unittest.mock import AsyncMock

    store = KnowledgeStore(str(tmp_path / "b.db"))
    store.add_item(kind="expense", content="Bonifico su IT60X0542811101000000123456",
                   embedding=[1.0, 0.0], sensitivity="sensitive")
    embedder = AsyncMock(); embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    pz = Pseudonymizer(VaultStore(str(tmp_path / "v.db")))

    res = await handle_recall_knowledge(
        store, embedder, {"query": "bonifico"}, owner="home",
        allow_sensitive=True, pseudonymizer=pz, cloud=True)
    txt = res["results"][0]["content"]
    assert "IT60X0542811101000000123456" not in txt
    assert "[IBAN_1]" in txt
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge_tools.py::test_recall_pseudonymizes_sensitive_for_cloud -v`
Expected: FAIL — `TypeError: handle_recall_knowledge() got an unexpected keyword argument 'pseudonymizer'`

- [ ] **Step 3: Write minimal implementation**

In `knowledge_tools.py`, estendere la firma e la logica di `handle_recall_knowledge`:

```python
async def handle_recall_knowledge(store, embedder, tool_input: dict, *, owner: str,
                                  allow_sensitive: bool = False,
                                  pseudonymizer=None, cloud: bool = True) -> dict:
    try:
        qv = await embedder.embed(tool_input["query"])
    except Exception:
        qv = []
    if not qv:
        return {"results": []}
    import asyncio
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, lambda: store.search(
        query_vec=qv, k=int(tool_input.get("k", 5)),
        owner=owner, allow_sensitive=allow_sensitive))
    out = []
    for r in res:
        content = r["content"]
        is_sensitive = r.get("sensitivity") == "sensitive"
        if is_sensitive and cloud and pseudonymizer is not None:
            content = pseudonymizer.pseudonymize(content)
        out.append({"id": r["id"], "kind": r["kind"], "content": content})
    return {"results": out}
```

NB: `store.search` deve includere `sensitivity` nei dict risultato (già presente: `search` fa `dict(r)` che include la colonna `sensitivity`). Verificarlo; se assente, aggiungerlo.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge_tools.py::test_recall_pseudonymizes_sensitive_for_cloud -v`
Expected: PASS

- [ ] **Step 5: Wire dispatcher + server**

Il dispatcher deve conoscere, al momento del `recall`, la policy dell'agente (`allow_sensitive`) e se il modello è cloud. Questi arrivano già nel flusso del runner: `ToolDispatcher.dispatch(...)` è chiamato da `claude_runner.chat` che conosce `effective_model` e `agent_id`. Strategia minimale e a basso rischio:
- Aggiungere a `dispatch(...)` due parametri opzionali `knowledge_allow_sensitive: bool = False` e `model: str = "auto"` (passati dal runner — vedi sotto), default prudenti.
- Nel routing di `recall_knowledge`, calcolare `cloud = backend_is_cloud(model)` (import `from ..llm_router import backend_is_cloud`) e passare `allow_sensitive=knowledge_allow_sensitive, pseudonymizer=self._pseudonymizer, cloud=cloud`.
- Iniettare `self._pseudonymizer` nel costruttore del dispatcher (nuovo param opzionale `pseudonymizer=None`).
- In `claude_runner.chat`, quando chiama `self._dispatcher.dispatch(...)`, passare `model=effective_model` e `knowledge_allow_sensitive=<policy>`. La policy dell'agente non è oggi disponibile nel runner: passarla come nuovo kwarg `knowledge_allow_sensitive` a `chat(...)` (default False), risolto a monte in `handlers_chat`/`agent_engine` da `agent.knowledge_access["allow_sensitive"]`, e propagato a `dispatch`. Rispettare [[feedback_hiris_runner_signature_contract]]: il NUOVO kwarg `knowledge_allow_sensitive` di `chat` va aggiunto anche a `OpenAICompatRunner.chat` (accettato anche se ignorato) e accettato da `LLMRouter.chat` (passthrough **kwargs).
- In `server.py`: costruire `VaultStore(os.path.join(data_dir, "vault.db"))` e `Pseudonymizer(vault)`, salvarli su `app["pseudonymizer"]`, e passare `pseudonymizer=` al `ToolDispatcher`. Chiudere il vault nel cleanup.

Implementare seguendo i pattern esistenti; se la firma reale di `dispatch`/`chat` diverge, adattare e annotare.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (nessuna regressione; i runner non-Claude accettano il nuovo kwarg)

- [ ] **Step 7: Commit**

```bash
git add hiris/app/tools/knowledge_tools.py hiris/app/tools/dispatcher.py hiris/app/claude_runner.py hiris/app/backends/openai_compat_runner.py hiris/app/server.py tests/test_knowledge_tools.py
git commit -m "feat(brain): recall filters by agent access + pseudonymizes sensitive for cloud"
```

---

## Task 7: De-tokenizzazione della risposta in chat

**Files:**
- Modify: `hiris/app/api/handlers_chat.py`
- Test: `tests/test_handlers_chat_history.py` (o un nuovo test mirato)

Dopo aver ottenuto la risposta dal runner, prima di restituirla/persisterla, sostituire eventuali token con i valori reali via `pseudonymizer.detokenize(...)` (se configurato). Vale sia per il path non-streaming sia per il testo accumulato dello streaming.

- [ ] **Step 1: Write the failing test**

```python
# in un test mirato (handler chat con pseudonymizer)
@pytest.mark.asyncio
async def test_chat_detokenizes_response(aiohttp_client, tmp_path):
    # Costruire un'app minima con un runner fake che ritorna "Saldo su [IBAN_1]."
    # e un pseudonymizer il cui vault mappa [IBAN_1] -> "IT60...". Dopo POST /api/chat
    # la `response` restituita deve contenere l'IBAN reale, non il token.
    ...
```
(L'implementatore costruisce il test mirato seguendo la struttura di `tests/test_api.py` per `/api/chat`, con `app["pseudonymizer"]` impostato e un runner mock.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest <il nuovo test> -v`
Expected: FAIL (la risposta contiene ancora il token)

- [ ] **Step 3: Write minimal implementation**

In `handlers_chat.py`, dopo aver ottenuto `response` (path non-streaming) e prima di `_is_toxic_assistant`/persistenza/serializzazione:
```python
pseudonymizer = request.app.get("pseudonymizer")
if pseudonymizer is not None and isinstance(response, str) and response:
    response = pseudonymizer.detokenize(response)
```
Per lo streaming: applicare `detokenize` su `full_response` accumulato prima della persistenza (i token non vengono spezzati perché la risposta è già completa lato server prima del chunking — vedi `chat_stream` Phase-1, che calcola tutto e poi affetta).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest <il nuovo test> -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_chat.py tests/<file>
git commit -m "feat(brain): detokenize pseudonymized tokens in chat responses"
```

---

## Self-Review (compilata)

**Spec coverage (Fase 2):** vault + pseudonimizzazione (Task 1-3 ✓, spec §5 strati 2-3), recognizer IT (Task 2 ✓), routing cloud/locale (Task 4 + wiring Task 6 ✓, spec §5 D6), policy `knowledge_access` per-agente (Task 5 + filtro recall Task 6 ✓, spec §6), de-tokenizzazione (Task 7 ✓, spec §5). **Differiti per design:** at-rest encryption del vault e whole-DB (spec §5 strato 4, §11); "minimize/aggregati" (→ piani di dominio); redaction NER (→ oltre regex).

**Placeholder scan:** Task 6 Step 5 e Task 7 Step 1 rimandano a punti del codice esistente da localizzare (firma reale di `dispatch`/`chat`, struttura del test `/api/chat`); sono indicazioni precise, non logica mancante. Il nuovo kwarg `knowledge_allow_sensitive` è esplicitato come da propagare a tutti i runner ([[feedback_hiris_runner_signature_contract]]).

**Type consistency:** `VaultStore.token_for/value_for`, `Pseudonymizer.pseudonymize/detokenize`, `detect_pii`, `backend_is_cloud` usati coerentemente. `handle_recall_knowledge(..., allow_sensitive, pseudonymizer, cloud)` coerente tra test e dispatcher. `search` deve esporre `sensitivity` nei risultati (verificare in Task 6 Step 3).

**Rischio principale:** il wiring di Task 6 Step 5 tocca la firma di `chat` su tutti i runner — è l'integrazione più delicata; richiede attenzione al contratto multi-runner e alla review finale sull'event-loop/threading come in Fase 1.
