# Piano 2A — MCP interno nell'addon HIRIS (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L'addon HIRIS espone, su `127.0.0.1` all'interno del container, un server MCP con gli stessi tool del gateway, inoltrando ogni chiamata alla execute-API di HIRIS su localhost (allowlist + semaforo + provenienza riusati). Prepara la sostituzione del gateway `.31` senza toccarlo.

**Architecture:** Un modulo `app/mcp/` porta il catalogo tool (`tiers.py`) dal gateway e un server FastMCP; i tool inoltrano a `POST http://127.0.0.1:8099/api/execute` con l'internal token (stesso contratto del gateway `hiris_client`, ma su loopback e senza OAuth). Il server MCP parte come task asyncio in `_on_startup` dell'app aiohttp esistente, su una porta di sola loopback. Nessuna esposizione, nessun OAuth: l'unico chiamante sarà il runner in-addon (Piano 2B) su localhost.

**Tech Stack:** Python 3.14, aiohttp (app esistente), **FastMCP** (nuovo), uvicorn (trascinato da FastMCP), httpx (già presente), pytest/pytest-asyncio (già presenti).

## Global Constraints

- Repo `hiris`, branch `feat/internal-mcp`. Solo codice addon; il gateway `.31` NON si tocca (resta fallback live fino al Piano 2B verificato).
- **Solo loopback:** il server MCP fa bind su `127.0.0.1` (mai `0.0.0.0`); nessun OAuth, nessuna porta esposta in `config.yaml`.
- **Riuso, non riproduzione:** i tool inoltrano alla execute-API esistente (`/api/execute`, contratto `{"tool","input","origin"}`) con l'`INTERNAL_TOKEN` dell'addon — allowlist, semaforo e provenienza restano quelli di HIRIS.
- **Catalogo unico:** `app/mcp/tiers.py` è l'unica fonte dei tool MCP (portata nel repo addon → fine del drift cross-repo). Esclude i tool ponte `claim_reasoning_job`/`submit_decision` (non servono all'interno).
- `confirm_actions = False` lato MCP (il gate delle azioni è il semaforo HIRIS a valle); nessuno store/pending lato MCP.
- Fail-safe: se l'internal token manca o l'execute-API risponde errore, il tool restituisce `{"error": ...}` senza sollevare verso l'esterno.

---

### Task 1: Dipendenza FastMCP + client loopback verso l'execute-API

**Files:**
- Modify: `hiris/requirements.txt`
- Create: `hiris/app/mcp/__init__.py` (vuoto)
- Create: `hiris/app/mcp/local_client.py`
- Test: `tests/test_mcp_local_client.py`

**Interfaces:**
- Produces: `app.mcp.local_client.LocalExecuteClient(base_url: str, internal_token: str)` con `async def execute(self, tool: str, inputs: dict) -> dict` → `POST {base_url}/api/execute` body `{"tool": tool, "input": inputs, "origin": "hiris-chat"}` header `X-HIRIS-Internal-Token`; ritorna il JSON deserializzato, o `{"error": "..."}` su fallimento HTTP/errore.

- [ ] **Step 1: Aggiungi le dipendenze**

In `hiris/requirements.txt` aggiungi (dopo `httpx`):
```
fastmcp>=2.11.0,<3.0.0
```
(uvicorn/starlette arrivano transitivamente da fastmcp.)

- [ ] **Step 2: Scrivi il test del client**

Crea `tests/test_mcp_local_client.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.mcp.local_client import LocalExecuteClient


@pytest.mark.asyncio
async def test_execute_posts_to_execute_api_with_token():
    captured = {}

    class _Resp:
        status = 200
        async def json(self): return {"result": {"ok": True}}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    def fake_post(url, json=None, headers=None):
        captured["url"] = url; captured["json"] = json; captured["headers"] = headers
        return _Resp()

    c = LocalExecuteClient("http://127.0.0.1:8099", "TOK")
    with patch.object(c, "_session") as sess:
        sess.post = MagicMock(side_effect=fake_post)
        out = await c.execute("get_home_status", {"a": 1})

    assert out == {"result": {"ok": True}}
    assert captured["url"] == "http://127.0.0.1:8099/api/execute"
    assert captured["json"] == {"tool": "get_home_status", "input": {"a": 1}, "origin": "hiris-chat"}
    assert captured["headers"]["X-HIRIS-Internal-Token"] == "TOK"


@pytest.mark.asyncio
async def test_execute_returns_error_dict_on_http_failure():
    class _Resp:
        status = 502
        async def text(self): return "bad"
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    c = LocalExecuteClient("http://127.0.0.1:8099", "TOK")
    with patch.object(c, "_session") as sess:
        sess.post = MagicMock(return_value=_Resp())
        out = await c.execute("call_service", {})
    assert "error" in out
```

- [ ] **Step 3: Esegui i test → falliscono**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_local_client.py -q`
Expected: FAIL (`ModuleNotFoundError: hiris.app.mcp.local_client`).

- [ ] **Step 4: Implementa il client**

Crea `hiris/app/mcp/__init__.py` vuoto e `hiris/app/mcp/local_client.py`:
```python
from __future__ import annotations
import logging
import aiohttp

logger = logging.getLogger(__name__)


class LocalExecuteClient:
    """Inoltra i tool MCP alla execute-API di HIRIS su loopback, riusando
    allowlist + semaforo + provenienza server-side. Nessun OAuth: l'auth e'
    l'internal token, la raggiungibilita' e' solo 127.0.0.1."""

    def __init__(self, base_url: str, internal_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = internal_token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def execute(self, tool: str, inputs: dict) -> dict:
        headers = {"X-HIRIS-Internal-Token": self._token} if self._token else {}
        body = {"tool": tool, "input": inputs, "origin": "hiris-chat"}
        try:
            async with self._session.post(
                f"{self._base_url}/api/execute", json=body, headers=headers
            ) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    logger.warning("execute-API %s -> %s: %s", tool, resp.status, detail[:200])
                    return {"error": f"execute-API status {resp.status}"}
                return await resp.json()
        except Exception as exc:
            logger.warning("execute-API %s non raggiungibile: %s", tool, type(exc).__name__)
            return {"error": "execute-API non raggiungibile"}
```

- [ ] **Step 5: Esegui i test → passano; commit**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_local_client.py -q` → PASS.
```bash
git add hiris/requirements.txt hiris/app/mcp/__init__.py hiris/app/mcp/local_client.py tests/test_mcp_local_client.py
git commit -m "feat(mcp): loopback execute-API client for internal MCP (task 1)"
```

---

### Task 2: Catalogo tool + server FastMCP interno

**Files:**
- Create: `hiris/app/mcp/tiers.py` (portato dal gateway, adattato)
- Create: `hiris/app/mcp/server.py`
- Test: `tests/test_mcp_server_build.py`

**Interfaces:**
- Consumes: `LocalExecuteClient.execute(tool, inputs)` (Task 1).
- Produces:
  - `app.mcp.tiers.TOOLS: list[ToolDef]` e `get_tool(name)`; `ToolDef(name, tier, hiris_tool, description)`.
  - `app.mcp.server.build_mcp(client: LocalExecuteClient) -> FastMCP` che registra un tool MCP per ogni `ToolDef`, ciascuno → `client.execute(t.hiris_tool, inputs)`.
  - `app.mcp.server.make_asgi_app(mcp) -> ASGI app` (`mcp.http_app()`).

- [ ] **Step 1: Porta il catalogo tool (senza i tool ponte)**

Crea `hiris/app/mcp/tiers.py` copiando da `hiris-mcp-gateway/app/tiers.py` **solo** le voci READ/SCHEDULE/ACTION (NON `claim_reasoning_job`/`submit_decision`, che erano per il ponte esterno). Mantieni `Tier`, `ToolDef` (campi `name`, `tier`, `hiris_tool`, `description`), `TOOLS`, `get_tool`. Rimuovi il campo `http_path` e `confirm/always_confirm` (non usati qui: il gate e' il semaforo HIRIS). Lista tool: `get_home_status, get_area_entities, get_entity_states, get_history, get_automation_config, recall_knowledge, create_task, list_tasks, cancel_task, create_automation_proposal, send_notification, save_knowledge, call_service` (13; `hiris_tool` di `call_service` = `call_ha_service`).

- [ ] **Step 2: Scrivi il test del build**

Crea `tests/test_mcp_server_build.py`:
```python
import pytest
from hiris.app.mcp.tiers import TOOLS, get_tool
from hiris.app.mcp.server import build_mcp


def test_catalog_has_13_tools_no_bridge():
    names = {t.name for t in TOOLS}
    assert "call_service" in names and get_tool("call_service").hiris_tool == "call_ha_service"
    assert "claim_reasoning_job" not in names and "submit_decision" not in names
    assert len(TOOLS) == 13


@pytest.mark.asyncio
async def test_build_mcp_registers_all_tools_and_forwards():
    calls = []

    class _Client:
        async def execute(self, tool, inputs):
            calls.append((tool, inputs)); return {"result": "ok"}

    mcp = build_mcp(_Client())
    tools = await mcp.get_tools()          # FastMCP async introspection
    assert set(tools.keys()) >= {t.name for t in TOOLS}
```

- [ ] **Step 3: Esegui → fallisce**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_server_build.py -q`
Expected: FAIL (`ModuleNotFoundError: hiris.app.mcp.server`).

- [ ] **Step 4: Implementa il server**

Crea `hiris/app/mcp/server.py`:
```python
from __future__ import annotations
import logging
from typing import Any
from fastmcp import FastMCP
from .tiers import TOOLS

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Controlli la smart home tramite HIRIS. Letture sempre permesse; le azioni "
    "(call_service) passano dal semaforo e possono tornare 'in attesa di conferma' "
    "(verde=eseguita, giallo=conferma su iPhone, rosso=conferma in HIRIS): non e' un "
    "errore. Non eseguire azioni senza consenso esplicito dell'utente."
)


def build_mcp(client: Any) -> FastMCP:
    mcp = FastMCP("HIRIS", instructions=_INSTRUCTIONS)

    def _make(hiris_tool: str):
        async def _handler(inputs: dict | None = None) -> Any:
            return await client.execute(hiris_tool, inputs or {})
        return _handler

    for t in TOOLS:
        h = _make(t.hiris_tool)
        h.__name__ = t.name
        h.__doc__ = t.description
        mcp.tool(name=t.name, description=t.description)(h)
    return mcp


def make_asgi_app(mcp: FastMCP):
    return mcp.http_app()
```

- [ ] **Step 5: Esegui → passano; commit**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_server_build.py -q` → PASS.
(Se `get_tools()` differisce nella versione FastMCP installata, adatta l'introspezione — l'asserzione chiave e' che ogni `t.name` risulti registrato.)
```bash
git add hiris/app/mcp/tiers.py hiris/app/mcp/server.py tests/test_mcp_server_build.py
git commit -m "feat(mcp): tool catalog + FastMCP internal server forwarding to execute-API (task 2)"
```

---

### Task 3: Avvio del server MCP come task loopback in `_on_startup`

**Files:**
- Modify: `hiris/app/server.py` (funzione `_on_startup` e cleanup)
- Modify: `hiris/run.sh` (esporta `INTERNAL_MCP_PORT`)
- Test: `tests/test_mcp_startup_wiring.py`

**Interfaces:**
- Consumes: `LocalExecuteClient` (Task 1), `build_mcp`/`make_asgi_app` (Task 2).
- Produces: all'avvio dell'app, un server uvicorn su `127.0.0.1:${INTERNAL_MCP_PORT:-8199}` che serve l'MCP; riferimenti in `app["internal_mcp_task"]` e `app["internal_mcp_client"]` per cleanup.

- [ ] **Step 1: Scrivi il test di wiring (funzione factory isolata)**

Crea `tests/test_mcp_startup_wiring.py`:
```python
import pytest
from hiris.app.server import build_internal_mcp_server


def test_build_internal_mcp_server_binds_loopback(monkeypatch):
    monkeypatch.setenv("INTERNAL_MCP_PORT", "8199")
    monkeypatch.setenv("INTERNAL_TOKEN", "TOK")
    client, config = build_internal_mcp_server(hiris_base_url="http://127.0.0.1:8099")
    # uvicorn.Config bound to loopback only, on the configured port
    assert config.host == "127.0.0.1"
    assert config.port == 8199
    assert client._token == "TOK"
```

- [ ] **Step 2: Esegui → fallisce**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_startup_wiring.py -q`
Expected: FAIL (`ImportError: cannot import name 'build_internal_mcp_server'`).

- [ ] **Step 3: Implementa la factory + avvio in `_on_startup`**

In `hiris/app/server.py` aggiungi (a livello modulo) la factory testabile:
```python
def build_internal_mcp_server(*, hiris_base_url: str = "http://127.0.0.1:8099"):
    """Costruisce (client, uvicorn.Config) per il server MCP interno su loopback.
    Isolato dall'avvio dell'app cosi' e' testabile senza bootare tutto."""
    import os, uvicorn
    from .mcp.local_client import LocalExecuteClient
    from .mcp.server import build_mcp, make_asgi_app
    port = int(os.environ.get("INTERNAL_MCP_PORT", "8199"))
    token = os.environ.get("INTERNAL_TOKEN", "")
    client = LocalExecuteClient(hiris_base_url, token)
    asgi = make_asgi_app(build_mcp(client))
    config = uvicorn.Config(asgi, host="127.0.0.1", port=port, log_level="warning")
    return client, config
```
Poi, dentro `_on_startup(app)` (dove vengono avviati gli altri job/scheduler), aggiungi l'avvio come task asyncio:
```python
    import uvicorn
    _mcp_client, _mcp_config = build_internal_mcp_server()
    await _mcp_client.start()
    _mcp_server = uvicorn.Server(_mcp_config)
    app["internal_mcp_client"] = _mcp_client
    app["internal_mcp_task"] = asyncio.create_task(_mcp_server.serve())
    logger.info("Internal MCP server avviato su 127.0.0.1:%s", _mcp_config.port)
```
E in `_on_cleanup`/shutdown dell'app (dove si chiudono le risorse) aggiungi:
```python
    task = app.get("internal_mcp_task")
    if task is not None:
        task.cancel()
    client = app.get("internal_mcp_client")
    if client is not None:
        await client.stop()
```
(Se `asyncio` non e' importato in `server.py`, aggiungi `import asyncio` in cima.)

- [ ] **Step 4: `run.sh` esporta la porta**

In `hiris/run.sh`, accanto agli altri `export`, aggiungi:
```bash
export INTERNAL_MCP_PORT=$(bashio::config 'internal_mcp_port' '8199')
```
E in `hiris/config.yaml`, nello schema opzioni, aggiungi (con default, non esposto in rete):
```yaml
  internal_mcp_port: 8199
```
più la voce corrispondente in `schema:` come `internal_mcp_port: port?`.

- [ ] **Step 5: Esegui il test di wiring + suite mcp; commit**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_startup_wiring.py tests/test_mcp_local_client.py tests/test_mcp_server_build.py -q` → PASS.
```bash
git add hiris/app/server.py hiris/run.sh hiris/config.yaml tests/test_mcp_startup_wiring.py
git commit -m "feat(mcp): start internal MCP server on loopback in _on_startup (task 3)"
```

---

### Task 4: Verifica in-container + suite completa

**Files:** nessuna modifica di codice (task di verifica); eventuale `docs/` runbook.

- [ ] **Step 1: Suite completa verde**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest -q`
Expected: tutti i test passano (i nuovi + i preesistenti).

- [ ] **Step 2: Build immagine addon (fastmcp installabile)**

Verifica che `pip install -r requirements.txt` risolva `fastmcp` sull'immagine base HA (Alpine): build locale dell'addon o `docker run` della base + `pip install fastmcp`. Expected: install OK, nessun conflitto con `aiohttp>=3.14`.

- [ ] **Step 3: Smoke test loopback (dopo deploy dell'addon aggiornato)**

Con l'addon in esecuzione, dall'interno del container:
`curl -s -X POST http://127.0.0.1:8199/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`
Expected: risposta MCP con l'elenco dei 13 tool. (Il flusso end-to-end con `claude -p` e' il Piano 2B.)

- [ ] **Step 4: Commit del runbook (se scritto)**

```bash
git add docs/design/2026-07-27-piano-2A-mcp-interno.md
git commit -m "docs: runbook verifica MCP interno (task 4)"
```

---

## Note di rollout / confine con 2B

- 2A **non tocca** `.31`: il gateway resta il fornitore live della chat via abbonamento finche' il Piano 2B (runner in-addon che usa questo MCP su localhost) non e' verificato.
- La verifica end-to-end vera (runner `claude -p` → MCP loopback → execute-API → semaforo) e' nel Piano 2B; qui ci si ferma allo smoke `tools/list` + test unit.
- Fuori scope 2A: node/Claude CLI nell'immagine, worker runner, `CLAUDE_CODE_OAUTH_TOKEN`, dismissione `.31` (tutto 2B/C3).
