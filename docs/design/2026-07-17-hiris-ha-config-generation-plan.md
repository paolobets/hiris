# HIRIS — Generazione config HA (dashboard/script/scene) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettere a HIRIS di creare dashboard Lovelace, script e scene su Home Assistant — scrittura diretta se la richiesta arriva dalla chat, proposta con approvazione dell'operatore se arriva dal gateway MCP.

**Architecture:** Un unico tool `create_ha_config` che scrive direttamente quando dispatchato. La distinzione chat/MCP è al confine: la chat passa da `dispatcher.dispatch` (scrittura immediata); l'MCP passa da `/api/execute`, che **intercetta** il tool prima del dispatch e salva una proposta `pending` nel `ProposalStore` esistente. L'operatore approva dalla pagina Proposte, che materializza l'artefatto su HA. Logica di validazione e di scrittura condivise in un nuovo modulo `tools/config_tools.py`.

**Tech Stack:** Python 3.13, aiohttp, pytest + pytest-asyncio, SQLite (ProposalStore esistente), HA REST config API (script/scene), HA WebSocket (Lovelace).

Spec: [docs/design/2026-07-17-hiris-ha-config-generation-design.md](2026-07-17-hiris-ha-config-generation-design.md)

## Global Constraints

- Python 3.13; **nessuna nuova dipendenza** (compatibilità Alpine/musl del container add-on).
- Le dashboard Lovelace si creano **solo via WebSocket** (REST dà 404 su lovelace).
- Solo **creazione additiva**: mai sovrascrivere dashboard/script/scene esistenti in v1.
- Tool `create_ha_config` **chat-only**: NON va aggiunto a `EVALUATION_ONLY_TOOLS` (gli agent proattivi/reattivi restano read-only).
- Da MCP il codice di scrittura non deve mai essere raggiungibile: l'execute-API crea solo proposte `pending`.
- Test con `python -m pytest`; ogni test async usa `@pytest.mark.asyncio`.
- Commit via **Bash** (non PowerShell), messaggio che termina con:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: `ha_client.create_script` + `create_scene` (REST config API)

**Files:**
- Modify: `hiris/app/proxy/ha_client.py` (aggiungere metodi dopo `create_automation`, ~riga 95)
- Test: `tests/test_ha_client_config.py` (nuovo)

**Interfaces:**
- Produces:
  - `async def create_script(self, object_id: str, config: dict) -> dict` → `{"ok": True, "id": object_id}` | `{"error": str}`
  - `async def create_scene(self, scene_id: str, config: dict) -> dict` → `{"ok": True, "id": scene_id}` | `{"error": str}`
  - `async def _post_config(self, path: str, config: dict) -> dict` (privato) → `{"ok": True}` | `{"error": str}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ha_client_config.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.ha_client import HAClient


@pytest.fixture
def client():
    return HAClient(base_url="http://supervisor/core", token="test-token")


def _post_mock(status=200):
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value="Bad" if status >= 400 else "OK")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


@pytest.mark.asyncio
async def test_create_script_ok(client):
    post_resp = _post_mock(200)
    reload_resp = _post_mock(200)
    with patch("aiohttp.ClientSession.post", side_effect=[post_resp, reload_resp]):
        await client.start()
        res = await client.create_script("luci_sera", {"sequence": []})
        await client.stop()
    assert res == {"ok": True, "id": "luci_sera"}


@pytest.mark.asyncio
async def test_create_script_bad_slug(client):
    res = await client.create_script("Luci Sera!", {"sequence": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_script_ha_rejects(client):
    with patch("aiohttp.ClientSession.post", return_value=_post_mock(400)):
        await client.start()
        res = await client.create_script("luci_sera", {"sequence": []})
        await client.stop()
    assert "error" in res


@pytest.mark.asyncio
async def test_create_scene_ok(client):
    post_resp = _post_mock(200)
    reload_resp = _post_mock(200)
    with patch("aiohttp.ClientSession.post", side_effect=[post_resp, reload_resp]):
        await client.start()
        res = await client.create_scene("relax", {"entities": {}})
        await client.stop()
    assert res == {"ok": True, "id": "relax"}


@pytest.mark.asyncio
async def test_create_script_empty_config(client):
    res = await client.create_script("luci_sera", {})
    assert "error" in res
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ha_client_config.py -v`
Expected: FAIL (AttributeError: 'HAClient' object has no attribute 'create_script')

- [ ] **Step 3: Implement the methods**

In `hiris/app/proxy/ha_client.py`, add right after `create_automation` (before `get_automation_config`):

```python
    @staticmethod
    def _is_slug(value: str) -> bool:
        return bool(value) and all(c.islower() or c.isdigit() or c == "_" for c in value)

    async def _post_config(self, path: str, config: dict) -> dict:
        """POST a UI-managed config to /api/config/{path}. Returns ok/error."""
        url = f"{self._base_url}/api/config/{path}"
        try:
            async with self._session.post(url, json=config) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    return {"error": f"HA ha rifiutato la config ({resp.status}): {body[:200]}"}
        except Exception as exc:
            return {"error": f"scrittura config fallita: {exc}"}
        return {"ok": True}

    async def create_script(self, object_id: str, config: dict) -> dict:
        """Create a UI-managed script via HA config API, then reload. Human-gated upstream."""
        if not isinstance(config, dict) or not config:
            return {"error": "config script vuota o non valida"}
        if not self._is_slug(object_id):
            return {"error": "object_id script non valido (usa a-z 0-9 _)"}
        res = await self._post_config(f"script/config/{object_id}", config)
        if res.get("error"):
            return res
        try:
            await self.call_service("script", "reload", {})
        except Exception as exc:
            logger.warning("script.reload after create failed (script %s persisted): %s", object_id, exc)
        return {"ok": True, "id": object_id}

    async def create_scene(self, scene_id: str, config: dict) -> dict:
        """Create a UI-managed scene via HA config API, then reload. Human-gated upstream."""
        if not isinstance(config, dict) or not config:
            return {"error": "config scena vuota o non valida"}
        if not self._is_slug(scene_id):
            return {"error": "scene_id non valido (usa a-z 0-9 _)"}
        res = await self._post_config(f"scene/config/{scene_id}", config)
        if res.get("error"):
            return res
        try:
            await self.call_service("scene", "reload", {})
        except Exception as exc:
            logger.warning("scene.reload after create failed (scene %s persisted): %s", scene_id, exc)
        return {"ok": True, "id": scene_id}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ha_client_config.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/ha_client.py tests/test_ha_client_config.py
git commit -m "$(cat <<'EOF'
feat(ha): create_script/create_scene via HA config API

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `ha_client.create_dashboard` (WebSocket Lovelace)

**Files:**
- Modify: `hiris/app/proxy/ha_client.py` (aggiungere `_ws_command` accanto a `_ws_request`, ~riga 250; e `create_dashboard`)
- Test: `tests/test_ha_client_config.py` (append)

**Interfaces:**
- Consumes: nulla dei task precedenti.
- Produces:
  - `async def _ws_command(self, msg_type: str, extra: dict | None = None, timeout: float = 10.0) -> dict | None` → l'intero messaggio WS `{"success": bool, "result": ..., "error": ...}` o `None` su errore di connessione.
  - `async def create_dashboard(self, url_path: str, title: str, config: dict, icon: str | None = None, show_in_sidebar: bool = True) -> dict` → `{"ok": True, "url_path": url_path}` | `{"error": str}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ha_client_config.py`:

```python
@pytest.mark.asyncio
async def test_create_dashboard_ok(client):
    client._ws_command = AsyncMock(side_effect=[
        {"success": True, "result": {"url_path": "casa-mia"}},   # dashboards/create
        {"success": True, "result": None},                        # config/save
    ])
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": [{"cards": []}]})
    assert res == {"ok": True, "url_path": "casa-mia"}
    assert client._ws_command.await_count == 2


@pytest.mark.asyncio
async def test_create_dashboard_missing_views(client):
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"cards": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_dashboard_create_fails(client):
    client._ws_command = AsyncMock(return_value={"success": False, "error": {"message": "exists"}})
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_dashboard_save_fails(client):
    client._ws_command = AsyncMock(side_effect=[
        {"success": True, "result": {"url_path": "casa-mia"}},
        {"success": False, "error": {"message": "bad config"}},
    ])
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": []})
    assert "error" in res
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ha_client_config.py -k dashboard -v`
Expected: FAIL (AttributeError: no attribute 'create_dashboard')

- [ ] **Step 3: Implement `_ws_command` and `create_dashboard`**

In `hiris/app/proxy/ha_client.py`, add `_ws_command` right after `_ws_request` (it mirrors it but returns the full envelope):

```python
    async def _ws_command(self, msg_type: str, extra: dict | None = None,
                          timeout: float = 10.0) -> dict | None:
        """Single WS command → the FULL result message ({success, result, error}).
        Unlike _ws_request, this exposes the success flag so writes can be verified.
        Returns None only on connection/auth failure."""
        ws_url = (
            self._base_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/websocket"
        )
        token = self._headers["Authorization"].removeprefix("Bearer ")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    handshake = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                    if handshake.get("type") == "auth_required":
                        await ws.send_json({"type": "auth", "access_token": token})
                        auth_resp = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        if auth_resp.get("type") != "auth_ok":
                            logger.warning("HA WS auth failed in _ws_command(%s)", msg_type)
                            return None
                    payload = {"id": 1, "type": msg_type}
                    if extra is not None:
                        payload.update(extra)
                    await ws.send_json(payload)
                    while True:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        if msg.get("id") == 1:
                            return msg
        except Exception as exc:
            logger.debug("_ws_command(%s) failed: %s", msg_type, exc)
            return None
```

Then add `create_dashboard` after `create_scene` (from Task 1):

```python
    @staticmethod
    def _ws_error(msg: dict | None) -> str:
        if not msg:
            return "nessuna risposta WS"
        err = msg.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        return str(err or "errore WS sconosciuto")

    async def create_dashboard(self, url_path: str, title: str, config: dict,
                               icon: str | None = None, show_in_sidebar: bool = True) -> dict:
        """Create a new storage-mode Lovelace dashboard + save its config (two WS commands).
        Additive: appears as a new sidebar entry; never touches existing dashboards."""
        if not isinstance(config, dict) or "views" not in config:
            return {"error": "config dashboard non valida (manca 'views')"}
        created = await self._ws_command("lovelace/dashboards/create", {
            "url_path": url_path,
            "title": title,
            "icon": icon,
            "show_in_sidebar": bool(show_in_sidebar),
            "require_admin": False,
            "mode": "storage",
        })
        if not created or not created.get("success"):
            return {"error": f"creazione dashboard fallita: {self._ws_error(created)}"}
        saved = await self._ws_command("lovelace/config/save", {
            "url_path": url_path,
            "config": config,
        })
        if not saved or not saved.get("success"):
            return {"error": f"salvataggio config dashboard fallito: {self._ws_error(saved)}"}
        return {"ok": True, "url_path": url_path}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ha_client_config.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/ha_client.py tests/test_ha_client_config.py
git commit -m "$(cat <<'EOF'
feat(ha): create_dashboard via WebSocket Lovelace (create + config/save)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `config_tools.py` — validazione + tool + write layer condiviso

**Files:**
- Create: `hiris/app/tools/config_tools.py`
- Test: `tests/test_config_tools.py` (nuovo)

**Interfaces:**
- Consumes: `ha_client.create_script/create_scene/create_dashboard` (Task 1+2).
- Produces:
  - `VALID_KINDS: frozenset[str]` = {"dashboard", "script", "scene"}
  - `CREATE_HA_CONFIG_TOOL_DEF: dict` (Anthropic tool schema; `name` = "create_ha_config")
  - `def normalize_config_inputs(inputs: dict) -> dict` → normalizzato `{"kind","slug","name","icon","show_in_sidebar","ha_config"}`; solleva `ValueError`.
  - `async def apply_ha_config(ha_client, normalized: dict) -> dict` → risultato di `ha_client.create_*`.
  - `def build_config_proposal(normalized: dict) -> dict` → `{"type","name","description","config","routing_reason"}` (config = normalized).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_tools.py`:

```python
import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.config_tools import (
    normalize_config_inputs, apply_ha_config, build_config_proposal, VALID_KINDS,
)


def _script_inputs(**o):
    base = {"kind": "script", "name": "Luci sera", "slug": "luci_sera",
            "config": {"sequence": []}}
    base.update(o)
    return base


def _dash_inputs(**o):
    base = {"kind": "dashboard", "name": "Casa Mia", "slug": "casa-mia",
            "config": {"views": [{"cards": []}]}, "icon": "mdi:home",
            "show_in_sidebar": True}
    base.update(o)
    return base


def test_normalize_script_ok():
    n = normalize_config_inputs(_script_inputs())
    assert n["kind"] == "script" and n["slug"] == "luci_sera"
    assert n["ha_config"] == {"sequence": []}


def test_normalize_dashboard_ok():
    n = normalize_config_inputs(_dash_inputs())
    assert n["kind"] == "dashboard" and n["slug"] == "casa-mia"
    assert n["icon"] == "mdi:home" and n["show_in_sidebar"] is True


def test_normalize_bad_kind():
    with pytest.raises(ValueError):
        normalize_config_inputs(_script_inputs(kind="automation"))


def test_normalize_bad_script_slug():
    with pytest.raises(ValueError):
        normalize_config_inputs(_script_inputs(slug="Luci Sera"))


def test_normalize_dashboard_slug_needs_hyphen():
    with pytest.raises(ValueError):
        normalize_config_inputs(_dash_inputs(slug="casa"))


def test_normalize_empty_config():
    with pytest.raises(ValueError):
        normalize_config_inputs(_script_inputs(config={}))


def test_normalize_dashboard_missing_views():
    with pytest.raises(ValueError):
        normalize_config_inputs(_dash_inputs(config={"cards": []}))


@pytest.mark.asyncio
async def test_apply_ha_config_routes_to_script():
    ha = AsyncMock()
    ha.create_script = AsyncMock(return_value={"ok": True, "id": "luci_sera"})
    n = normalize_config_inputs(_script_inputs())
    res = await apply_ha_config(ha, n)
    ha.create_script.assert_awaited_once_with("luci_sera", {"sequence": []})
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_apply_ha_config_routes_to_dashboard():
    ha = AsyncMock()
    ha.create_dashboard = AsyncMock(return_value={"ok": True, "url_path": "casa-mia"})
    n = normalize_config_inputs(_dash_inputs())
    res = await apply_ha_config(ha, n)
    ha.create_dashboard.assert_awaited_once_with(
        "casa-mia", "Casa Mia", {"views": [{"cards": []}]},
        icon="mdi:home", show_in_sidebar=True,
    )
    assert res["ok"] is True


def test_build_config_proposal():
    n = normalize_config_inputs(_dash_inputs())
    p = build_config_proposal(n)
    assert p["type"] == "ha_dashboard"
    assert p["name"] == "Casa Mia"
    assert p["config"] == n
    assert p["routing_reason"] and p["description"]


def test_valid_kinds():
    assert VALID_KINDS == frozenset({"dashboard", "script", "scene"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config_tools.py -v`
Expected: FAIL (ModuleNotFoundError: hiris.app.tools.config_tools)

- [ ] **Step 3: Implement `config_tools.py`**

Create `hiris/app/tools/config_tools.py`:

```python
from __future__ import annotations
import re
from typing import Any

VALID_KINDS = frozenset({"dashboard", "script", "scene"})

_KIND_PROPOSAL_TYPE = {
    "dashboard": "ha_dashboard",
    "script": "ha_script",
    "scene": "ha_scene",
}
_KIND_LABEL = {"dashboard": "Dashboard", "script": "Script", "scene": "Scena"}

_SLUG_RE = re.compile(r"^[a-z0-9_]+$")                 # script/scene object_id
_URL_PATH_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")  # dashboard: HA richiede un trattino

_MAX_CONFIG_BYTES = 256 * 1024  # cap difensivo sulla dimensione del config

CREATE_HA_CONFIG_TOOL_DEF = {
    "name": "create_ha_config",
    "description": (
        "Crea un artefatto di configurazione Home Assistant: una dashboard Lovelace "
        "('plancia'), uno script o una scena. Dalla chat viene creato subito su HA. "
        "Le dashboard sono additive (nuova voce in sidebar). Fornisci un config HA valido."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["dashboard", "script", "scene"]},
            "name": {"type": "string", "description": "Titolo leggibile dell'artefatto"},
            "slug": {
                "type": "string",
                "description": ("id tecnico. script/scene: a-z 0-9 _ . "
                               "dashboard: url_path con almeno un trattino (es. 'casa-mia')."),
            },
            "config": {
                "type": "object",
                "description": ("Config HA. script: {sequence:[...]}. scene: {entities:{...}}. "
                               "dashboard: {views:[...]} (config Lovelace)."),
            },
            "icon": {"type": "string", "description": "Solo dashboard: icona mdi (opzionale)"},
            "show_in_sidebar": {"type": "boolean", "description": "Solo dashboard (default true)"},
        },
        "required": ["kind", "name", "slug", "config"],
    },
}


def normalize_config_inputs(inputs: dict) -> dict:
    """Validate + normalize the tool inputs. Raises ValueError on any problem.

    Returned dict shape (re-used verbatim as the pending proposal's `config`):
    {"kind","slug","name","icon","show_in_sidebar","ha_config"}
    """
    kind = inputs.get("kind")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind non valido: {kind!r} (usa dashboard|script|scene)")
    name = inputs.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name mancante o vuoto")
    slug = inputs.get("slug")
    if not isinstance(slug, str):
        raise ValueError("slug mancante")
    config = inputs.get("config")
    if not isinstance(config, dict) or not config:
        raise ValueError("config vuoto o non valido")
    if len(str(config).encode("utf-8", "ignore")) > _MAX_CONFIG_BYTES:
        raise ValueError("config troppo grande")

    if kind == "dashboard":
        if not _URL_PATH_RE.match(slug):
            raise ValueError("slug dashboard non valido: serve un url_path con un trattino (es. 'casa-mia')")
        if "views" not in config or not isinstance(config.get("views"), list):
            raise ValueError("config dashboard non valida: manca la lista 'views'")
    else:
        if not _SLUG_RE.match(slug):
            raise ValueError(f"slug {kind} non valido: usa solo a-z 0-9 _")

    return {
        "kind": kind,
        "slug": slug,
        "name": name.strip(),
        "icon": inputs.get("icon") if kind == "dashboard" else None,
        "show_in_sidebar": bool(inputs.get("show_in_sidebar", True)) if kind == "dashboard" else None,
        "ha_config": config,
    }


async def apply_ha_config(ha_client: Any, normalized: dict) -> dict:
    """Materialize a normalized config on HA. Shared by the chat dispatch path and
    the pending-proposal apply path."""
    kind = normalized["kind"]
    if kind == "script":
        return await ha_client.create_script(normalized["slug"], normalized["ha_config"])
    if kind == "scene":
        return await ha_client.create_scene(normalized["slug"], normalized["ha_config"])
    if kind == "dashboard":
        return await ha_client.create_dashboard(
            normalized["slug"], normalized["name"], normalized["ha_config"],
            icon=normalized.get("icon"),
            show_in_sidebar=normalized.get("show_in_sidebar", True),
        )
    return {"error": f"kind non supportato: {kind}"}


def build_config_proposal(normalized: dict) -> dict:
    """Build the ProposalStore record for an MCP-originated creation (pending)."""
    kind = normalized["kind"]
    label = _KIND_LABEL[kind]
    return {
        "type": _KIND_PROPOSAL_TYPE[kind],
        "name": normalized["name"],
        "description": f"{label} '{normalized['name']}' generata via MCP — in attesa di approvazione.",
        "config": normalized,
        "routing_reason": (
            "Richiesta via gateway MCP: la creazione di config HA richiede "
            "l'approvazione dell'operatore nella pagina Proposte di HIRIS."
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config_tools.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/config_tools.py tests/test_config_tools.py
git commit -m "$(cat <<'EOF'
feat(tools): config_tools — validazione + write layer per create_ha_config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Dispatcher branch + esposizione chat-only

**Files:**
- Modify: `hiris/app/tools/dispatcher.py` (import in cima ~riga 29; branch nella `dispatch`, accanto a `create_automation_proposal` ~riga 338)
- Modify: `hiris/app/claude_runner.py` (import ~riga 45; append a `ALL_TOOL_DEFS` ~riga 132; commento in `EVALUATION_ONLY_TOOLS` ~riga 151)
- Test: `tests/test_dispatcher_config.py` (nuovo)

**Interfaces:**
- Consumes: `config_tools.normalize_config_inputs`, `config_tools.apply_ha_config`, `config_tools.CREATE_HA_CONFIG_TOOL_DEF`.
- Produces: il tool `create_ha_config` è dispatchabile (scrittura diretta) ed è presente in `ALL_TOOL_DEFS` ma **non** in `EVALUATION_ONLY_TOOLS`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dispatcher_config.py`:

```python
import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS


def _dispatcher(ha):
    return ToolDispatcher(ha_client=ha, notify_config={})


@pytest.mark.asyncio
async def test_dispatch_create_ha_config_writes_directly():
    ha = AsyncMock()
    ha.create_script = AsyncMock(return_value={"ok": True, "id": "luci_sera"})
    d = _dispatcher(ha)
    res = await d.dispatch("create_ha_config", {
        "kind": "script", "name": "Luci sera", "slug": "luci_sera",
        "config": {"sequence": []},
    })
    assert res == {"ok": True, "id": "luci_sera"}
    ha.create_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_create_ha_config_bad_input():
    ha = AsyncMock()
    d = _dispatcher(ha)
    res = await d.dispatch("create_ha_config", {"kind": "nope", "name": "x",
                                                "slug": "x", "config": {"a": 1}})
    assert "error" in res


def test_create_ha_config_in_all_tool_defs():
    assert any(t["name"] == "create_ha_config" for t in ALL_TOOL_DEFS)


def test_create_ha_config_is_chat_only():
    assert "create_ha_config" not in EVALUATION_ONLY_TOOLS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dispatcher_config.py -v`
Expected: FAIL (`test_dispatch_create_ha_config_writes_directly` returns the unknown-tool error; `test_create_ha_config_in_all_tool_defs` fails)

- [ ] **Step 3a: Wire the dispatcher**

In `hiris/app/tools/dispatcher.py`, add to the import block (after line 29, `from .proposal_tools import create_automation_proposal`):

```python
from .config_tools import normalize_config_inputs, apply_ha_config
```

Add this branch right after the `create_automation_proposal` branch (after line ~346, before the `save_knowledge` branch):

```python
            if name == "create_ha_config":
                try:
                    normalized = normalize_config_inputs(inputs)
                except ValueError as exc:
                    return {"error": str(exc)}
                return await apply_ha_config(self._ha, normalized)
```

- [ ] **Step 3b: Register the tool as chat-only**

In `hiris/app/claude_runner.py`, add to imports (after line 45):

```python
from .tools.config_tools import CREATE_HA_CONFIG_TOOL_DEF
```

Append to `ALL_TOOL_DEFS` (after `CREATE_AUTOMATION_PROPOSAL_TOOL_DEF,` line 132):

```python
    CREATE_HA_CONFIG_TOOL_DEF,
```

In the `EVALUATION_ONLY_TOOLS` comment block (after line 151), add a line documenting the exclusion:

```python
    # create_ha_config excluded: writes to HA (dashboard/script/scene) — chat-only
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dispatcher_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/dispatcher.py hiris/app/claude_runner.py tests/test_dispatcher_config.py
git commit -m "$(cat <<'EOF'
feat(chat): dispatch create_ha_config con scrittura diretta (chat-only)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Intercept MCP nell'execute-API (proposta pending)

**Files:**
- Modify: `hiris/app/api/handlers_gateway_policy.py` (`PROPOSE_TOOLS`, ~riga 31 — aggiunge anche l'hard-allow, che deriva da `PROPOSE_TOOLS`)
- Modify: `hiris/app/api/handlers_execute.py` (nuovo blocco intercept dopo il blocco `create_task`, ~riga 185)
- Test: `tests/test_execute_config.py` (nuovo)

**Interfaces:**
- Consumes: `config_tools.normalize_config_inputs`, `config_tools.build_config_proposal`; `proposal_store.save`.
- Produces: da `/api/execute`, `create_ha_config` NON viene mai dispatchato — ritorna `{"result": {"status": "pending_approval", "proposal_id": ...}}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_execute_config.py`:

```python
import pytest
from aiohttp import web
from unittest.mock import AsyncMock

from hiris.app.api.handlers_execute import handle_execute
from hiris.app.api.handlers_gateway_policy import PROPOSE_TOOLS


class _FakeDispatcher:
    def __init__(self):
        self.calls = []
    async def dispatch(self, name, inputs, **kw):
        self.calls.append(name)
        return {"ok": name}


def _make_app(store):
    app = web.Application()
    app["internal_token"] = "secret"
    app["execute_policy"] = {"tools": ["create_ha_config"], "allowed_entities": None,
                             "allowed_services": None, "tiers": {}, "entity_tiers": {}}
    app["tool_dispatcher"] = _FakeDispatcher()
    app["proposal_store"] = store
    app.router.add_post("/api/execute", handle_execute)
    return app


async def _post(client, body):
    return await client.post("/api/execute", json=body,
                             headers={"X-HIRIS-Internal-Token": "secret"})


def test_create_ha_config_in_propose_tools():
    assert "create_ha_config" in PROPOSE_TOOLS


@pytest.mark.asyncio
async def test_mcp_create_ha_config_is_pending_not_dispatched(aiohttp_client):
    store = AsyncMock()
    store.save = AsyncMock(return_value="prop-123")
    app = _make_app(store)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_ha_config", "input": {
        "kind": "script", "name": "Luci sera", "slug": "luci_sera",
        "config": {"sequence": []},
    }})
    assert resp.status == 200
    data = await resp.json()
    assert data["result"]["status"] == "pending_approval"
    assert data["result"]["proposal_id"] == "prop-123"
    store.save.assert_awaited_once()
    # crucially NOT dispatched (would be a direct write):
    assert app["tool_dispatcher"].calls == []


@pytest.mark.asyncio
async def test_mcp_create_ha_config_bad_input(aiohttp_client):
    store = AsyncMock()
    store.save = AsyncMock(return_value="x")
    app = _make_app(store)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_ha_config", "input": {
        "kind": "nope", "name": "x", "slug": "x", "config": {"a": 1},
    }})
    data = await resp.json()
    assert data["result"]["ok"] is False
    store.save.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_execute_config.py -v`
Expected: FAIL (`test_create_ha_config_in_propose_tools` fails; the dispatch test hits the "not exposed" 403 or dispatches)

- [ ] **Step 3a: Expose the tool to MCP**

In `hiris/app/api/handlers_gateway_policy.py`, add `"create_ha_config"` to `PROPOSE_TOOLS` (line 31-32):

```python
PROPOSE_TOOLS = ["create_automation_proposal", "save_knowledge", "list_tasks",
                 "cancel_task", "create_ha_config"]
```

(This automatically adds it to `_HARD_EXECUTE_ALLOWED` in `handlers_execute.py`, which is built from `PROPOSE_TOOLS`, and to the derived policy tools.)

- [ ] **Step 3b: Intercept before dispatch**

In `hiris/app/api/handlers_execute.py`, add this block right after the `create_task` validation block (after line 184, before the `# Reads are non-destructive` comment):

```python
    # create_ha_config from the gateway is NEVER executed directly. It is held as a
    # pending proposal the operator reviews+approves in HIRIS (spec: MCP = convalida).
    if tool == "create_ha_config":
        from .config_tools import normalize_config_inputs, build_config_proposal
        store = request.app.get("proposal_store")
        if store is None:
            return web.json_response({"error": "ProposalStore non disponibile"}, status=503)
        try:
            normalized = normalize_config_inputs(inputs)
        except ValueError as exc:
            return web.json_response({"result": {"ok": False, "error": str(exc)}})
        pid = await store.save(build_config_proposal(normalized))
        return web.json_response({"result": {
            "status": "pending_approval", "proposal_id": pid,
            "message": (f"Creazione '{normalized['name']}' in attesa di approvazione "
                        "dell'operatore in HIRIS (pagina Proposte)."),
        }})
```

Note the import path: `handlers_execute.py` is in `app/api/`, `config_tools.py` is in `app/tools/`. Use `from ..tools.config_tools import ...`:

```python
        from ..tools.config_tools import normalize_config_inputs, build_config_proposal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_execute_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_gateway_policy.py hiris/app/api/handlers_execute.py tests/test_execute_config.py
git commit -m "$(cat <<'EOF'
feat(mcp): execute-API intercetta create_ha_config come proposta pending

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Apply delle proposte config + anteprima UI

**Files:**
- Modify: `hiris/app/api/handlers_proposals.py` (`handle_apply_proposal`, ~riga 43)
- Modify: `hiris/app/static/config/proposals.js` (riga 27 label; blocco anteprima config)
- Test: `tests/test_proposals_apply_config.py` (nuovo)

**Interfaces:**
- Consumes: `config_tools.apply_ha_config` (Task 3); i tipi proposta `ha_dashboard`/`ha_script`/`ha_scene` con `config` = dict normalizzato (Task 5).
- Produces: approvando una proposta config, l'artefatto viene materializzato su HA; `applied` solo se HA accetta.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_proposals_apply_config.py`:

```python
import pytest
from aiohttp import web
from hiris.app.api.handlers_proposals import handle_apply_proposal


class _FakeProposalStore:
    def __init__(self, proposal):
        self._p = proposal
        self.applied = []
    async def get(self, pid):
        return dict(self._p) if self._p and self._p.get("id") == pid else None
    async def apply(self, pid):
        self.applied.append(pid)
        return True


class _FakeHA:
    def __init__(self, result):
        self._result = result
        self.calls = []
    async def create_script(self, object_id, config):
        self.calls.append(("script", object_id)); return self._result
    async def create_scene(self, scene_id, config):
        self.calls.append(("scene", scene_id)); return self._result
    async def create_dashboard(self, url_path, title, config, icon=None, show_in_sidebar=True):
        self.calls.append(("dashboard", url_path)); return self._result


def _app(store, ha=None):
    app = web.Application()
    app["proposal_store"] = store
    if ha is not None:
        app["ha_client"] = ha
    app.router.add_post("/api/proposals/{proposal_id}/apply", handle_apply_proposal)
    return app


def _script_proposal():
    return {"id": "p1", "status": "pending", "type": "ha_script",
            "config": {"kind": "script", "slug": "luci_sera", "name": "Luci sera",
                       "icon": None, "show_in_sidebar": None, "ha_config": {"sequence": []}}}


@pytest.mark.asyncio
async def test_apply_script_writes_to_ha(aiohttp_client):
    store = _FakeProposalStore(_script_proposal())
    ha = _FakeHA({"ok": True, "id": "luci_sera"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    assert ha.calls == [("script", "luci_sera")]
    assert store.applied == ["p1"]


@pytest.mark.asyncio
async def test_apply_script_not_marked_when_ha_fails(aiohttp_client):
    store = _FakeProposalStore(_script_proposal())
    ha = _FakeHA({"error": "HA ha rifiutato la config (400): bad"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 502
    assert store.applied == []


@pytest.mark.asyncio
async def test_apply_dashboard_proposal(aiohttp_client):
    store = _FakeProposalStore({"id": "p1", "status": "pending", "type": "ha_dashboard",
        "config": {"kind": "dashboard", "slug": "casa-mia", "name": "Casa Mia",
                   "icon": "mdi:home", "show_in_sidebar": True,
                   "ha_config": {"views": []}}})
    ha = _FakeHA({"ok": True, "url_path": "casa-mia"})
    client = await aiohttp_client(_app(store, ha))
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 200
    assert ha.calls == [("dashboard", "casa-mia")]


@pytest.mark.asyncio
async def test_apply_config_without_ha_client_returns_503(aiohttp_client):
    store = _FakeProposalStore(_script_proposal())
    client = await aiohttp_client(_app(store))   # no ha_client
    r = await client.post("/api/proposals/p1/apply", headers={"X-Requested-With": "x"})
    assert r.status == 503
    assert store.applied == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_proposals_apply_config.py -v`
Expected: FAIL (current `handle_apply_proposal` treats these types as status-only apply, so no HA call / wrong status)

- [ ] **Step 3a: Extend `handle_apply_proposal`**

In `hiris/app/api/handlers_proposals.py`, add a module-level constant after `_VALID_STATUSES` (line 3):

```python
_CONFIG_TYPES = frozenset({"ha_dashboard", "ha_script", "ha_scene"})
```

Then, inside `handle_apply_proposal`, add this branch immediately after the `ha_automation` branch (after line 54, before the `# Other proposal types` comment):

```python
    if proposal.get("type") in _CONFIG_TYPES:
        ha = request.app.get("ha_client")
        if ha is None:
            return web.json_response({"error": "HA client non disponibile"}, status=503)
        from ..tools.config_tools import apply_ha_config
        result = await apply_ha_config(ha, proposal.get("config") or {})
        if not isinstance(result, dict) or result.get("error"):
            msg = result.get("error") if isinstance(result, dict) else "errore sconosciuto"
            return web.json_response(
                {"error": f"Config non creata in HA: {msg}"}, status=502
            )
        applied = await proposal_store.apply(proposal_id)
        return web.json_response({"ok": bool(applied), "result": result})
```

- [ ] **Step 3b: Run apply tests to verify they pass**

Run: `python -m pytest tests/test_proposals_apply_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 3c: Extend the review UI**

In `hiris/app/static/config/proposals.js`, replace line 27:

```javascript
    var typeLabel = '→ automazione HA';
```

with a type→label map and a config preview for the new types. Replace line 27 with:

```javascript
    var TYPE_LABELS = {
      ha_automation: '→ automazione HA', hiris_agent: '→ agent HIRIS',
      ha_dashboard: '→ dashboard', ha_script: '→ script', ha_scene: '→ scena'
    };
    var typeLabel = TYPE_LABELS[p.type] || ('→ ' + (p.type || 'config'));
    var configPreview = '';
    if (p.type === 'ha_dashboard' || p.type === 'ha_script' || p.type === 'ha_scene') {
      try {
        configPreview = '<pre class="proposal-config" style="max-height:180px;overflow:auto;'
          + 'background:var(--surface-sunken,#00000010);padding:8px;border-radius:6px;'
          + 'font-family:var(--font-mono);font-size:11px;margin-top:6px">'
          + escHtml(JSON.stringify((p.config && p.config.ha_config) || p.config, null, 2))
          + '</pre>';
      } catch(e) { configPreview = ''; }
    }
```

Then insert `configPreview` into the row markup: change the `proposal-reason` line (line 39) to append it. Replace line 39:

```javascript
      + '<div class="proposal-reason"><strong>Motivo:</strong> ' + escHtml(p.routing_reason || '') + '</div>'
```

with:

```javascript
      + '<div class="proposal-reason"><strong>Motivo:</strong> ' + escHtml(p.routing_reason || '') + '</div>'
      + configPreview
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (all tests green, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_proposals.py hiris/app/static/config/proposals.js tests/test_proposals_apply_config.py
git commit -m "$(cat <<'EOF'
feat(proposals): apply dashboard/script/scene + anteprima config in review UI

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- Write layer (script/scene REST, dashboard WS) → Task 1, Task 2 ✓
- Tool `create_ha_config` + validazione condivisa → Task 3 ✓
- Chat = scrittura diretta → Task 4 (dispatcher branch) ✓
- Chat-only (escluso agli agent non-chat) → Task 4 (non in `EVALUATION_ONLY_TOOLS`) ✓
- MCP = proposta pending + convalida operatore → Task 5 (intercept) + Task 6 (apply) ✓
- Riuso ProposalStore senza modifiche schema → Task 5/6 (type TEXT libero, config JSON) ✓
- Pagina review con anteprima → Task 6 (proposals.js) ✓
- Sicurezza: da MCP mai scrittura diretta → Task 5 (intercept prima del dispatch, test `calls == []`) ✓
- Additivo, validazione slug/config, cap dimensione → Task 3 (`normalize_config_inputs`) ✓

**2. Placeholder scan:** nessun TBD/TODO; ogni step ha codice completo e comandi con output atteso.

**3. Type consistency:**
- `normalize_config_inputs` → dict `{kind,slug,name,icon,show_in_sidebar,ha_config}` usato identico in `apply_ha_config`, `build_config_proposal`, e come `proposal["config"]` in Task 5/6. ✓
- `apply_ha_config(ha_client, normalized)` firma coerente tra Task 3, Task 4 (dispatcher), Task 6 (apply). ✓
- `create_script(object_id, config)` / `create_scene(scene_id, config)` / `create_dashboard(url_path, title, config, icon=, show_in_sidebar=)` coerenti tra Task 1/2 (def), Task 3 (`apply_ha_config`), e i fake nei test di Task 6. ✓
- Tipi proposta `ha_dashboard`/`ha_script`/`ha_scene` coerenti tra `build_config_proposal` (Task 3), `_CONFIG_TYPES` (Task 6), e i test. ✓
