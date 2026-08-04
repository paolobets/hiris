# Piano 2B — Runner claude -p INTERNO all'addon + dismissione .31 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La chat via abbonamento gira interamente dentro l'addon HIRIS: un worker asyncio consuma i job della reasoning queue e lancia `claude -p` (autenticato via `CLAUDE_CODE_OAUTH_TOKEN`) contro l'MCP interno su localhost (Piano 2A), scrivendo la reply. Poi si dismette il gateway `.31`.

**Architecture:** L'immagine addon aggiunge node + Claude CLI (Alpine). Il codice runner del gateway (`agent/runner.py`+`prompts.py`, con il wiring MCP fatto il 2026-07-26) viene portato in `hiris/app/agent/`, con `base_url=http://127.0.0.1:8099` (execute/reasoning API) e MCP `http://127.0.0.1:8199/mcp` (2A). Il suo loop gira come task asyncio in `_on_startup`, attivo solo se `chat_via_subscription` + token presenti. Kill-switch/audit (item I2 della review 2A) portati accanto all'MCP interno.

**Tech Stack:** Alpine 3.21 base (`ghcr.io/home-assistant/*-base-python:3.13-alpine3.21`), node 22 + `@anthropic-ai/claude-code`, Python 3.13/aiohttp, fastmcp 2.14.7 (2A), pytest/pytest-asyncio.

## Global Constraints

- Repo `hiris`, branch `feat/internal-mcp` (continua sopra 2A). Il gateway `.31` **NON** si tocca fino al gate di verifica live (Task 6/C3).
- **Ordine sicuro:** costruire+verificare il worker in-addon con `.31` acceso come fallback; durante il test **spegnere il runner `.31`** (non i due consumer insieme sulla stessa queue → doppio-claim); solo dopo la verifica, dismissione definitiva.
- **Auth abbonamento:** `CLAUDE_CODE_OAUTH_TOKEN` (da `claude setup-token`, ~1 anno) via config secret; `CLAUDE_CONFIG_DIR=/data/claude`. Nessun `setup-token` interattivo nell'addon.
- **Alpine/musl:** claude-code richiede `apk add nodejs npm libgcc libstdc++ ripgrep` + `ENV USE_BUILTIN_RIPGREP=0`; node **22+** (Alpine 3.21 ok).
- **Solo loopback:** il worker chiama `127.0.0.1:8099` (API) e `127.0.0.1:8199` (MCP, 2A); nessuna rete esterna, nessun `.31`.
- **Attivazione condizionata:** il worker parte solo se `chat_via_subscription=true` E `CLAUDE_CODE_OAUTH_TOKEN` non vuoto; altrimenti resta spento (utenti API-key non pagano peso a runtime).
- **Fail-safe runner:** su errore `claude -p` (rc!=0/timeout) sottomette comunque una reply d'errore leggibile (mai job appeso), come il runner `.31` oggi.

---

### Task 1: Config + run.sh per l'auth abbonamento

**Files:**
- Modify: `hiris/config.yaml` (options + schema)
- Modify: `hiris/run.sh`
- Test: `tests/test_subscription_env_wiring.py`

**Interfaces:**
- Produces: env `CLAUDE_CODE_OAUTH_TOKEN` e `CLAUDE_CONFIG_DIR=/data/claude` disponibili al processo addon.

- [ ] **Step 1: Test che run.sh esporta il token e imposta CLAUDE_CONFIG_DIR**

Crea `tests/test_subscription_env_wiring.py`:
```python
import re, pathlib

RUN_SH = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "run.sh"


def test_run_sh_exports_oauth_token_and_config_dir():
    txt = RUN_SH.read_text(encoding="utf-8")
    assert re.search(r"export CLAUDE_CODE_OAUTH_TOKEN=\$\(bashio::config 'claude_code_oauth_token'", txt)
    assert "export CLAUDE_CONFIG_DIR=/data/claude" in txt
```

- [ ] **Step 2: Esegui → fallisce**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_subscription_env_wiring.py -q` → FAIL.

- [ ] **Step 3: Implementa config + run.sh**

In `hiris/config.yaml`, sotto `options:` (accanto a `chat_via_subscription`), aggiungi:
```yaml
  claude_code_oauth_token: ""
```
e sotto `schema:`:
```yaml
  claude_code_oauth_token: password
```
In `hiris/run.sh`, accanto agli altri export (dopo `CHAT_VIA_SUBSCRIPTION`), aggiungi:
```bash
export CLAUDE_CODE_OAUTH_TOKEN=$(bashio::config 'claude_code_oauth_token' '')
export CLAUDE_CONFIG_DIR=/data/claude
```

- [ ] **Step 4: Esegui → passa; valida shell/yaml**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_subscription_env_wiring.py -q` → PASS.
Run: `bash -n hiris/run.sh` (clean) e `python -c "import yaml; yaml.safe_load(open('hiris/config.yaml'))"` (nessun errore).

- [ ] **Step 5: Commit**

```bash
git add hiris/config.yaml hiris/run.sh tests/test_subscription_env_wiring.py
git commit -m "feat(subscription): CLAUDE_CODE_OAUTH_TOKEN config + CLAUDE_CONFIG_DIR (2B task 1)"
```

---

### Task 2: Immagine addon con node + Claude CLI

**Files:**
- Modify: `hiris/Dockerfile`
- Test: `tests/test_dockerfile_has_claude_cli.py`

**Interfaces:**
- Produces: nell'immagine addon, `claude` CLI eseguibile (node 22+), `USE_BUILTIN_RIPGREP=0`.

- [ ] **Step 1: Test statico sul Dockerfile**

Crea `tests/test_dockerfile_has_claude_cli.py`:
```python
import pathlib
DF = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "Dockerfile"


def test_dockerfile_installs_node_and_claude_cli():
    txt = DF.read_text(encoding="utf-8")
    assert "nodejs" in txt and "npm" in txt
    assert "@anthropic-ai/claude-code" in txt
    for pkg in ("libgcc", "libstdc++", "ripgrep"):
        assert pkg in txt, pkg
    assert "USE_BUILTIN_RIPGREP=0" in txt
```

- [ ] **Step 2: Esegui → fallisce**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_dockerfile_has_claude_cli.py -q` → FAIL.

- [ ] **Step 3: Implementa nel Dockerfile**

In `hiris/Dockerfile`, dopo il blocco `pip3 install` e prima della `COPY app/`, aggiungi:
```dockerfile
# Chat via abbonamento (Piano 2B): node + Claude CLI. Alpine/musl -> ripgrep di
# sistema (il ripgrep bundle di claude e' glibc). Node 22+ e' in Alpine 3.21.
RUN apk add --no-cache nodejs npm libgcc libstdc++ ripgrep \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force
ENV USE_BUILTIN_RIPGREP=0
```
(`CLAUDE_CONFIG_DIR` è già esportato da run.sh in Task 1; qui basta il CLI.)

- [ ] **Step 4: Esegui il test → passa**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_dockerfile_has_claude_cli.py -q` → PASS.

- [ ] **Step 5: Commit (build/smoke = gate al deploy, Task 6)**

```bash
git add hiris/Dockerfile tests/test_dockerfile_has_claude_cli.py
git commit -m "feat(image): node + Claude CLI (musl) nell'addon per la chat via abbonamento (2B task 2)"
```

---

### Task 3: Worker runner in-addon (port + loopback)

**Files:**
- Create: `hiris/app/agent/__init__.py` (vuoto)
- Create: `hiris/app/agent/prompts.py` (portato dal gateway)
- Create: `hiris/app/agent/runner.py` (portato dal gateway, adattato a loopback)
- Test: `tests/test_agent_runner_inaddon.py`

**Interfaces:**
- Consumes: reasoning API su `127.0.0.1:8099` (`/api/reasoning/claim`, `/api/reasoning/submit`), MCP su `127.0.0.1:8199/mcp` (2A), env `INTERNAL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `HIRIS_AGENT_CHAT_MODEL` (default `sonnet`).
- Produces: `app.agent.runner.run_once(client, base_url, headers, mode)` e `configure_chat_mcp()`/`_reason_chat()` (stessa forma del gateway); una coroutine `run_loop(base_url, get_headers, mode, poll_seconds)` per il task asyncio.

- [ ] **Step 1: Porta i file dal gateway**

Copia `C:\Work\Sviluppo\hiris-mcp-gateway\agent\prompts.py` → `hiris/app/agent/prompts.py` **verbatim** (contiene `build_holistic_prompt` + `build_chat_messages`, già a forma system/user con il fix identità del 2026-07-26).
Copia `C:\Work\Sviluppo\hiris-mcp-gateway\agent\runner.py` → `hiris/app/agent/runner.py`, con questi adattamenti loopback:
- `import prompts` → `from . import prompts`.
- L'MCP config: `HIRIS_AGENT_MCP_URL` default → `http://127.0.0.1:8199/mcp`. **L'MCP interno di 2A è SENZA auth** (FastMCP `auth=None`, sicurezza = solo loopback), quindi `build_mcp_config` NON mette header di auth: `{"mcpServers": {"hiris": {"type": "http", "url": url}}}`. (L'internal token serve al forward MCP→execute-API dentro 2A `LocalExecuteClient`, NON alla connessione claude→MCP.)
- Rimuovi ogni residuo CF-Access/JWT di servizio/`Authorization: Bearer` (non servono: MCP su loopback senza auth).
- `claude -p` usa `CLAUDE_CODE_OAUTH_TOKEN` dall'ambiente (già esportato); mantieni `--output-format json`, `--system-prompt`, `--mcp-config`, `--strict-mcp-config`, `--allowedTools`, `--disallowedTools` (tool locali), `--exclude-dynamic-system-prompt-sections`.

- [ ] **Step 2: Scrivi i test (claim→reason→submit con subprocess+HTTP mockati)**

Crea `tests/test_agent_runner_inaddon.py`:
```python
import pytest
from unittest.mock import patch
from hiris.app.agent import runner, prompts


def test_build_chat_messages_available():
    system, user = prompts.build_chat_messages("Sei HIRIS.", [{"role": "user", "content": "ciao"}])
    assert "Sei HIRIS." in system and "Utente: ciao" in user


def test_mcp_config_loopback_no_auth():
    # 2A internal MCP is unauthenticated (loopback only) -> no auth header.
    cfg = runner.build_mcp_config("http://127.0.0.1:8199/mcp")
    srv = cfg["mcpServers"]["hiris"]
    assert srv["type"] == "http" and srv["url"] == "http://127.0.0.1:8199/mcp"
    assert "Authorization" not in srv.get("headers", {})
    assert "X-HIRIS-Internal-Token" not in srv.get("headers", {})


class _Resp:
    def __init__(self, data): self._d = data
    def json(self): return self._d
    def raise_for_status(self): pass


class _Client:
    def __init__(self, claim_body): self.claim_body = claim_body; self.submitted = []
    def post(self, url, headers=None, json=None):
        if url.endswith("/api/reasoning/claim"): return _Resp(self.claim_body)
        if url.endswith("/api/reasoning/submit"): self.submitted.append(json); return _Resp({"ok": True})
        raise AssertionError(url)


def test_run_once_chat_reasons_and_submits(monkeypatch):
    job = {"job_id": "J", "nonce": "N", "kind": "chat",
           "context": {"system_prompt": "Sei HIRIS.", "history": [{"role": "user", "content": "che luci?"}]}}
    c = _Client({"job": job})

    class _Proc: returncode = 0; stdout = '{"result": "2 luci accese"}'; stderr = ""
    monkeypatch.setattr(runner, "_CHAT_MCP_CONFIG_PATH", "/tmp/hiris-mcp.json")
    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        out = runner.run_once(c, "http://127.0.0.1:8099", {"X-HIRIS-Internal-Token": "TOK"}, "live")
    assert out == "done"
    assert c.submitted and c.submitted[0]["decision"] == {"reply": "2 luci accese"}
```
(Il metodo esatto di build/config MCP e i nomi `_CHAT_MCP_CONFIG_PATH`/`build_mcp_config` provengono dal runner del gateway; se differiscono, allinea test e port allo stesso nome — devono coincidere tra `runner.py` e il test.)

- [ ] **Step 3: Esegui → fallisce, poi adatta il port finché passa**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_agent_runner_inaddon.py -q`. Itera l'adattamento del port (Step 1) finché verde.

- [ ] **Step 4: Suite mcp+agent verde**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_agent_runner_inaddon.py tests/test_mcp_*.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/agent/ tests/test_agent_runner_inaddon.py
git commit -m "feat(agent): in-addon runner (port del gateway, loopback API+MCP, internal token) (2B task 3)"
```

---

### Task 4: Avvio condizionato del worker in `_on_startup`

**Files:**
- Modify: `hiris/app/server.py` (`_on_startup` + cleanup)
- Test: `tests/test_agent_worker_startup.py`

**Interfaces:**
- Consumes: `app.agent.runner.run_loop(...)` (Task 3); env `CHAT_VIA_SUBSCRIPTION`, `CLAUDE_CODE_OAUTH_TOKEN`.
- Produces: `app.server.should_start_agent_worker() -> bool` (True sse `CHAT_VIA_SUBSCRIPTION=="true"` e `CLAUDE_CODE_OAUTH_TOKEN` non vuoto); il worker come task `_spawn(...)` in `app["agent_worker_task"]`, cancellato in cleanup.

- [ ] **Step 1: Test del gate**

Crea `tests/test_agent_worker_startup.py`:
```python
from hiris.app.server import should_start_agent_worker


def test_worker_off_by_default(monkeypatch):
    monkeypatch.delenv("CHAT_VIA_SUBSCRIPTION", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False


def test_worker_needs_both_flag_and_token(monkeypatch):
    monkeypatch.setenv("CHAT_VIA_SUBSCRIPTION", "true")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker() is True
```

- [ ] **Step 2: Esegui → fallisce**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_agent_worker_startup.py -q` → FAIL.

- [ ] **Step 3: Implementa gate + avvio**

In `hiris/app/server.py` a livello modulo:
```python
def should_start_agent_worker() -> bool:
    import os
    return (os.environ.get("CHAT_VIA_SUBSCRIPTION", "").strip().lower() == "true"
            and bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()))
```
In `_on_startup`, dopo l'avvio dell'MCP interno (2A), aggiungi:
```python
    if should_start_agent_worker():
        from .agent import runner as _agent_runner
        _agent_runner.configure_chat_mcp()   # scrive /tmp/hiris-mcp.json (header internal token)
        def _agent_headers():
            return {"X-HIRIS-Internal-Token": os.environ.get("INTERNAL_TOKEN", "")}
        app["agent_worker_task"] = _spawn(
            _agent_runner.run_loop("http://127.0.0.1:8099", _agent_headers,
                                   os.environ.get("HIRIS_AGENT_MODE", "live"),
                                   int(os.environ.get("HIRIS_AGENT_POLL_SECONDS", "3"))),
            name="agent_worker")
        logger.info("Chat-via-abbonamento worker in-addon avviato")
    else:
        logger.info("Chat-via-abbonamento worker NON avviato (flag/token assenti)")
```
In cleanup, accanto alla cancellazione dell'MCP task:
```python
    aw = app.get("agent_worker_task")
    if aw is not None:
        aw.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await aw
```
(`run_loop` in `runner.py` è un `async def` che cicla `run_once` con `await asyncio.sleep(poll)`, usando un `httpx.AsyncClient`; se il runner del gateway usa `httpx.Client` sincrono, adatta `run_loop` ad async in Task 3.)

- [ ] **Step 4: Esegui test + full suite**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_agent_worker_startup.py -q` → PASS; poi `python -m pytest -q` full verde.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/server.py tests/test_agent_worker_startup.py
git commit -m "feat(agent): avvio condizionato del worker chat-abbonamento in _on_startup (2B task 4)"
```

---

### Task 5: Kill-switch + audit sull'MCP interno (item I2)

**Files:**
- Modify: `hiris/app/mcp/server.py` (o `hiris/app/mcp/local_client.py`)
- Create: `hiris/app/mcp/guard.py`
- Test: `tests/test_mcp_guard.py`

**Interfaces:**
- Produces: `app.mcp.guard.McpGuard` con `is_killed()`, `set_killed(bool)`, `record(tool, outcome, latency_ms)` (audit in-memory + log), e un check chiamato da ogni tool prima dell'inoltro; se killed → `{"error": "kill-switch attivo", "blocked": True}`.

- [ ] **Step 1: Test del guard**

Crea `tests/test_mcp_guard.py`:
```python
from hiris.app.mcp.guard import McpGuard


def test_killed_blocks_and_toggles():
    g = McpGuard()
    assert g.is_killed() is False
    g.set_killed(True)
    assert g.is_killed() is True
    g.set_killed(False)
    assert g.is_killed() is False


def test_record_keeps_bounded_audit():
    g = McpGuard(audit_max=2)
    g.record("get_home_status", "ok", 5)
    g.record("call_service", "ok", 9)
    g.record("get_history", "ok", 3)
    assert len(g.audit) == 2 and g.audit[-1]["tool"] == "get_history"
```

- [ ] **Step 2: Esegui → fallisce**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_guard.py -q` → FAIL.

- [ ] **Step 3: Implementa il guard + aggancialo ai tool**

Crea `hiris/app/mcp/guard.py`:
```python
from __future__ import annotations
import logging
from collections import deque

logger = logging.getLogger(__name__)


class McpGuard:
    """Kill-switch + audit in-memory per l'MCP interno (item I2). Il semaforo
    HIRIS resta il gate delle azioni; questo aggiunge stop d'emergenza + traccia."""

    def __init__(self, audit_max: int = 200) -> None:
        self._killed = False
        self.audit: deque = deque(maxlen=audit_max)

    def is_killed(self) -> bool:
        return self._killed

    def set_killed(self, value: bool) -> None:
        self._killed = bool(value)
        logger.warning("MCP kill-switch %s", "ON" if self._killed else "OFF")

    def record(self, tool: str, outcome: str, latency_ms: int) -> None:
        self.audit.append({"tool": tool, "outcome": outcome, "latency_ms": latency_ms})
```
In `hiris/app/mcp/server.py`, `build_mcp(client, guard=None)`: nel `_handler`, prima dell'inoltro `if guard is not None and guard.is_killed(): return {"error": "kill-switch attivo", "blocked": True}`; dopo l'inoltro `guard.record(...)` con latenza (usa `time.monotonic`). Passa un `McpGuard()` condiviso da `build_internal_mcp_server` (2A). (Non serve persistenza per 2B; il kill-switch è runtime — la persistenza è un follow-up.)

- [ ] **Step 4: Esegui test + suite mcp**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_mcp_guard.py tests/test_mcp_*.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/mcp/guard.py hiris/app/mcp/server.py tests/test_mcp_guard.py
git commit -m "feat(mcp): kill-switch + audit in-memory sull'MCP interno (review 2A item I2) (2B task 5)"
```

---

### Task 6: Verifica end-to-end (gate al deploy) + runbook dismissione .31 (C3)

**Files:** nessun codice; runbook in questo doc.

- [ ] **Step 1: Suite completa + build immagine**

Run: `cd /c/Work/Sviluppo/hiris && python -m pytest -q` → tutti verdi.
Build addon (Alpine 3.21): verifica `claude --version` → node 22+, `claude` presente; `pip`+`fastmcp` ok.

- [ ] **Step 2: Auth una-tantum**

Su qualsiasi macchina con browser: `claude setup-token` → copia il token OAuth (~1 anno) → incollalo nell'addon HIRIS in **`claude_code_oauth_token`** (campo secret) → salva.

- [ ] **Step 3: Verifica end-to-end con .31 come fallback, SENZA doppio-claim**

**Spegni il runner `.31`** (`ssh processlens-31 "cd /opt/hiris-mcp-gateway && docker compose stop hiris-agent"`) così l'unico consumer della queue è il worker in-addon. Aggiorna l'addon (`chat_via_subscription=true` + token) e riavvia. Poi dalla chat HIRIS:
- "che luci sono accese?" → risposta su **stato reale** (identità HIRIS);
- azione **verde** → eseguita; **gialla/rossa** → in attesa di conferma.
Se qualcosa non va, riaccendi `hiris-agent` su `.31` (fallback) e diagnostica.

- [ ] **Step 4: Dismissione definitiva `.31` (C3, dopo verifica OK)**

Con conferma esplicita dell'utente: backup di `/opt/hiris-mcp-gateway/.env` + `data/oauth_key.pem` fuori dal `.31`; `docker compose down` dei 3 container gateway; rimozione tunnel/Access app/hostname (`mcp.ha-betarena.it`, `mcp-panel`, `hiris-internal`) e del **connector Claude.ai**. Io preparo lo script di stop/rimozione container; i passi Cloudflare/Claude sono manuali dell'utente.

- [ ] **Step 5: Commit runbook**

```bash
git add docs/design/2026-07-27-piano-2B-runner-in-addon.md
git commit -m "docs: runbook verifica end-to-end + dismissione .31 (2B task 6)"
```

---

## Note

- **Doppio-claim:** durante la transizione NON tenere acceso sia il runner `.31` sia il worker in-addon (competono sulla stessa queue). Test = solo worker in-addon; `.31` spento (ma pronto a riaccendersi come fallback finché non si decommissiona).
- **Peso immagine:** node+CLI (~100-150MB) sono "morti" per utenti solo-API-key; accettato per l'obiettivo "un'app sola".
- **Fuori scope 2B:** modello permessi per-utente (sotto-progetto #1 chat-per-tutti), gestione integrazioni esterne/RetroPanel (futuro).
