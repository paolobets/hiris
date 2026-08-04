# Plance a proposta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare le dashboard Lovelace sullo stesso modello delle automazioni — l'LLM propone, l'umano approva nella sezione Proposte, l'apply scrive su HA — eliminando la scrittura diretta dalla chat e aggiungendo snapshot/undo per le sostituzioni.

**Architecture:** Tre nuovi tool per il Chatbot (`list_dashboards`, `get_dashboard_config` in sola lettura; `propose_dashboard` che scrive una proposta `ha_dashboard`). Il tipo proposta `ha_dashboard` e il suo apply esistono già: si estende il formato `normalized` con un campo `mode` (`create`|`replace`) invece di introdurne uno parallelo, così le proposte MCP esistenti restano valide. Il ramo `replace` salva uno snapshot della config precedente prima di sovrascrivere, e un endpoint di restore lo ri-applica.

**Tech Stack:** Python 3.11+ / aiohttp / pytest (backend); JS ES5-compatibile in IIFE + `node --test` con jsdom (frontend). HA WebSocket API per Lovelace.

**Design doc:** `docs/design/2026-07-31-design-plance-a-proposta.md`

## Global Constraints

- **Comandi WS verificati:** `lovelace/config`, `lovelace/config/save`, `lovelace/dashboards/create`, `lovelace/dashboards/delete` sono **già usati e funzionanti** in `ha_client.py`. `lovelace/dashboards/list` è confermato dall'elenco ufficiale degli endpoint WebSocket HA. Nessun comando va inventato.
- **Solo storage mode:** le dashboard YAML non sono scrivibili via WS. Ogni errore va restituito come `{"error": ...}` leggibile, mai un'eccezione o una scrittura parziale.
- **`url_path` dashboard:** deve contenere almeno un trattino — regex esistente `_URL_PATH_RE` in `config_tools.py:15`. Non duplicarla.
- **Mai `raise` verso il dispatcher:** i tool restituiscono `{"error": "..."}`; è la convenzione di tutto `tools/`.
- **Mai fare echo di `str(exc)`** al chiamante (può rivelare path interni): logga server-side e restituisci un messaggio generico ma utile — vedi `proposal_tools.py:110-116`.
- **Chat-only:** i nuovi tool NON vanno aggiunti a `EVALUATION_ONLY_TOOLS` (`claude_runner.py:210`). Agentbot e Brain non devono poter toccare le plance.
- **Nessun emoji** nel codice, nei commenti o nelle stringhe UI.
- **Lingua:** commenti, descrizioni tool e stringhe UI in italiano, come il resto del codebase.
- **Test:** `python -m pytest` per il backend, `npm test` per il frontend. Entrambe le suite devono restare verdi.

---

## File Structure

| File | Responsabilità | Azione |
|---|---|---|
| `hiris/app/proxy/ha_client.py` | metodi WS Lovelace | Modify: +`list_dashboards`, +`save_dashboard_config` |
| `hiris/app/proxy/dashboard_backups.py` | store snapshot config plance | **Create** |
| `hiris/app/tools/config_tools.py` | validazione + apply config HA | Modify: `mode` in normalize/apply, snapshot su replace |
| `hiris/app/tools/dashboard_tools.py` | tool def + logica dei 3 nuovi tool | **Create** |
| `hiris/app/tools/dispatcher.py` | routing dei tool | Modify: +3 rami, −`add_dashboard_view`, −kind dashboard |
| `hiris/app/claude_runner.py` | registro tool | Modify: `ALL_TOOL_DEFS` |
| `hiris/app/api/handlers_dashboards.py` | endpoint restore | **Create** |
| `hiris/app/server.py` | rotte | Modify: +rotta restore |
| `hiris/app/static/config/proposals-core.js` | core condiviso proposte (FE) | Modify: +`restoreDashboard` |
| `hiris/app/static/config/proposals.js`, `chat/proposals.js` | rendering card proposta | Modify: intestazione create/replace + Annulla |

---

## Task 1: Metodi WS `list_dashboards` e `save_dashboard_config`

**Files:**
- Modify: `hiris/app/proxy/ha_client.py` (dopo `get_lovelace_config`, ~riga 256)
- Test: `tests/test_dashboard_client.py` (create)

**Interfaces:**
- Produces:
  - `async ha_client.list_dashboards() -> list[dict] | dict` — lista di `{"url_path","title","mode"}`; `{"error": str}` in caso di fallimento.
  - `async ha_client.save_dashboard_config(url_path: str, config: dict) -> dict` — `{"ok": True, "url_path": str}` oppure `{"error": str}`.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_dashboard_client.py`:

```python
import pytest
from hiris.app.proxy.ha_client import HAClient


class FakeWS:
    """Registra i comandi WS e risponde con code preimpostate."""
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def command(self, cmd, payload=None):
        self.calls.append((cmd, payload or {}))
        return self.responses.get(cmd, {"success": True, "result": None})


def _client(ws):
    c = HAClient.__new__(HAClient)          # niente __init__: serve solo il WS
    c._ws_command = ws.command
    return c


@pytest.mark.asyncio
async def test_list_dashboards_returns_url_path_and_title():
    ws = FakeWS({"lovelace/dashboards/list": {"success": True, "result": [
        {"id": "1", "url_path": "casa-mia", "title": "Casa Mia", "mode": "storage"},
    ]}})
    out = await _client(ws).list_dashboards()
    assert out == [{"url_path": "casa-mia", "title": "Casa Mia", "mode": "storage"}]
    assert ws.calls[0][0] == "lovelace/dashboards/list"


@pytest.mark.asyncio
async def test_list_dashboards_error_is_returned_not_raised():
    ws = FakeWS({"lovelace/dashboards/list": {"success": False, "error": {"message": "boom"}}})
    out = await _client(ws).list_dashboards()
    assert isinstance(out, dict) and "error" in out


@pytest.mark.asyncio
async def test_save_dashboard_config_sends_url_path_and_config():
    ws = FakeWS({"lovelace/config/save": {"success": True}})
    cfg = {"views": [{"title": "Home", "cards": []}]}
    out = await _client(ws).save_dashboard_config("casa-mia", cfg)
    assert out == {"ok": True, "url_path": "casa-mia"}
    assert ws.calls[0] == ("lovelace/config/save", {"url_path": "casa-mia", "config": cfg})


@pytest.mark.asyncio
async def test_save_dashboard_config_rejects_config_without_views():
    ws = FakeWS({})
    out = await _client(ws).save_dashboard_config("casa-mia", {"nope": 1})
    assert "error" in out
    assert ws.calls == [], "config invalida: non deve partire alcun comando WS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_client.py -v`
Expected: FAIL — `AttributeError: 'HAClient' object has no attribute 'list_dashboards'`

- [ ] **Step 3: Write minimal implementation**

In `hiris/app/proxy/ha_client.py`, subito dopo `get_lovelace_config`:

```python
    async def list_dashboards(self) -> list[dict] | dict:
        """Elenca le dashboard Lovelace (storage mode) via WS.
        Ritorna una lista di {url_path, title, mode} oppure {"error": ...}."""
        got = await self._ws_command("lovelace/dashboards/list", {})
        if not got or not got.get("success"):
            return {"error": f"elenco dashboard non leggibile: {self._ws_error(got)}"}
        result = got.get("result")
        if not isinstance(result, list):
            return {"error": "elenco dashboard vuoto o non valido"}
        out = []
        for d in result:
            if isinstance(d, dict):
                out.append({
                    "url_path": d.get("url_path"),
                    "title": d.get("title"),
                    "mode": d.get("mode"),
                })
        return out

    async def save_dashboard_config(self, url_path: str, config: dict) -> dict:
        """Sovrascrive la config di una dashboard storage-mode esistente.
        NON crea la dashboard: usare create_dashboard per quello."""
        if not isinstance(config, dict) or "views" not in config:
            return {"error": "config dashboard non valida (manca 'views')"}
        saved = await self._ws_command(
            "lovelace/config/save", {"url_path": url_path, "config": config}
        )
        if not saved or not saved.get("success"):
            return {"error": f"salvataggio config dashboard fallito: {self._ws_error(saved)}"}
        return {"ok": True, "url_path": url_path}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_client.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/ha_client.py tests/test_dashboard_client.py
git commit -m "feat(ha): list_dashboards + save_dashboard_config via WS Lovelace"
```

---

## Task 2: `DashboardBackupStore` — snapshot delle config

**Files:**
- Create: `hiris/app/proxy/dashboard_backups.py`
- Test: `tests/test_dashboard_backups.py` (create)

**Interfaces:**
- Produces:
  - `save_backup(data_dir: str, url_path: str, config: dict) -> None`
  - `latest_backup(data_dir: str, url_path: str) -> dict | None` — la config più recente, o `None`.
  - `MAX_BACKUPS_PER_DASHBOARD = 3`

- [ ] **Step 1: Write the failing test**

Crea `tests/test_dashboard_backups.py`:

```python
from hiris.app.proxy.dashboard_backups import (
    save_backup, latest_backup, MAX_BACKUPS_PER_DASHBOARD,
)


def test_latest_backup_is_none_when_nothing_saved(tmp_path):
    assert latest_backup(str(tmp_path), "casa-mia") is None


def test_save_then_latest_roundtrip(tmp_path):
    cfg = {"views": [{"title": "Home"}]}
    save_backup(str(tmp_path), "casa-mia", cfg)
    assert latest_backup(str(tmp_path), "casa-mia") == cfg


def test_latest_returns_most_recent(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "B"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "B"}]}


def test_keeps_at_most_three_per_dashboard(tmp_path):
    import json, os
    for i in range(5):
        save_backup(str(tmp_path), "casa-mia", {"views": [{"title": str(i)}]})
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data["casa-mia"]) == MAX_BACKUPS_PER_DASHBOARD
    # i piu' vecchi vengono scartati: resta la coda 2,3,4
    assert [b["config"]["views"][0]["title"] for b in data["casa-mia"]] == ["2", "3", "4"]


def test_dashboards_are_isolated(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "altra-casa", {"views": [{"title": "B"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "A"}]}
    assert latest_backup(str(tmp_path), "altra-casa") == {"views": [{"title": "B"}]}


def test_corrupt_file_does_not_raise(tmp_path):
    import os
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert latest_backup(str(tmp_path), "casa-mia") is None
    save_backup(str(tmp_path), "casa-mia", {"views": []})   # non deve sollevare
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_backups.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiris.app.proxy.dashboard_backups'`

- [ ] **Step 3: Write minimal implementation**

Crea `hiris/app/proxy/dashboard_backups.py`:

```python
"""Snapshot delle config Lovelace prima di una sostituzione.

Una proposta ha_dashboard in mode 'replace' riscrive INTERAMENTE la plancia.
La sicurezza non sta nell'attrito (niente OTP) ma nella reversibilita': prima
di sovrascrivere si salva qui la config precedente, cosi' un overwrite
sbagliato si annulla con un click. Bounded: solo gli ultimi N per plancia."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_PATH = "dashboard_backups.json"
MAX_BACKUPS_PER_DASHBOARD = 3


def _file(data_dir: str) -> str:
    return os.path.join(data_dir, _PATH)


def _load(data_dir: str) -> dict:
    """Mappa url_path -> lista di {"config": {...}}, dalla piu' vecchia alla piu'
    recente. Un file assente o corrotto vale come 'nessun backup': questo store
    e' una rete di sicurezza, non deve mai bloccare un apply."""
    path = _file(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("dashboard_backups: file illeggibile o corrotto, ignorato")
        return {}


def save_backup(data_dir: str, url_path: str, config: dict) -> None:
    """Accoda uno snapshot, scartando i piu' vecchi oltre il limite."""
    data = _load(data_dir)
    entries = data.get(url_path)
    if not isinstance(entries, list):
        entries = []
    entries.append({"config": config})
    data[url_path] = entries[-MAX_BACKUPS_PER_DASHBOARD:]
    try:
        with open(_file(data_dir), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("dashboard_backups: salvataggio snapshot fallito")


def latest_backup(data_dir: str, url_path: str) -> dict | None:
    """La config salvata piu' di recente per questa plancia, o None."""
    entries = _load(data_dir).get(url_path)
    if not isinstance(entries, list) or not entries:
        return None
    last = entries[-1]
    if not isinstance(last, dict):
        return None
    cfg = last.get("config")
    return cfg if isinstance(cfg, dict) else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_backups.py -v`
Expected: PASS (6 test)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/dashboard_backups.py tests/test_dashboard_backups.py
git commit -m "feat(dashboards): store snapshot config plance (max 3 per plancia)"
```

---

## Task 3: `mode: replace` in `apply_ha_config`, con snapshot prima della scrittura

**Files:**
- Modify: `hiris/app/tools/config_tools.py:130-159` (`apply_ha_config`)
- Test: `tests/test_dashboard_apply_replace.py` (create)

**Interfaces:**
- Consumes: `ha_client.save_dashboard_config` (Task 1), `save_backup` (Task 2).
- Produces: `apply_ha_config(ha_client, normalized, data_dir=None)` accetta ora `normalized["mode"]` con valori `"create"` (default, retro-compatibile) e `"replace"`.

**Nota di design (deviazione consapevole dalla spec):** la spec descriveva un payload con `mode`/`url_path`/`title`. Il grounding ha mostrato che `apply_ha_config` usa già il formato `normalized` = `{kind, slug, name, icon, show_in_sidebar, ha_config}`, condiviso col percorso MCP. Si **estende** quel formato con `mode` (default `create`), usando `slug` come `url_path`: stessa semantica, nessuna rottura delle proposte MCP già salvate.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_dashboard_apply_replace.py`:

```python
import pytest
from hiris.app.tools.config_tools import apply_ha_config
from hiris.app.proxy.dashboard_backups import latest_backup


class FakeHA:
    def __init__(self, current=None, save_result=None):
        self.current = current if current is not None else {"views": [{"title": "VECCHIA"}]}
        self.save_result = save_result or {"ok": True, "url_path": "casa-mia"}
        self.saved = None
        self.created = None
        self.order = []

    async def get_lovelace_config(self, url_path):
        self.order.append("read")
        return self.current

    async def save_dashboard_config(self, url_path, config):
        self.order.append("save")
        self.saved = (url_path, config)
        return self.save_result

    async def create_dashboard(self, slug, name, config, icon=None, show_in_sidebar=True):
        self.created = (slug, name, config)
        return {"ok": True, "url_path": slug}


NEW = {"views": [{"title": "NUOVA"}]}


@pytest.mark.asyncio
async def test_mode_create_still_calls_create_dashboard(tmp_path):
    ha = FakeHA()
    out = await apply_ha_config(
        ha, {"kind": "dashboard", "slug": "casa-mia", "name": "Casa", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert out.get("ok") is True
    assert ha.created is not None and ha.saved is None


@pytest.mark.asyncio
async def test_mode_replace_saves_snapshot_before_writing(tmp_path):
    ha = FakeHA(current={"views": [{"title": "VECCHIA"}]})
    out = await apply_ha_config(
        ha,
        {"kind": "dashboard", "mode": "replace", "slug": "casa-mia", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert out.get("ok") is True
    assert ha.saved == ("casa-mia", NEW)
    assert ha.created is None, "replace non deve creare una nuova plancia"
    # lo snapshot deve contenere la config PRECEDENTE
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "VECCHIA"}]}
    # e deve essere stato letto PRIMA di scrivere
    assert ha.order == ["read", "save"]


@pytest.mark.asyncio
async def test_replace_aborts_when_current_config_unreadable(tmp_path):
    ha = FakeHA(current={"error": "config dashboard non leggibile"})
    out = await apply_ha_config(
        ha,
        {"kind": "dashboard", "mode": "replace", "slug": "casa-mia", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert "error" in out
    assert ha.saved is None, "mai sovrascrivere senza aver messo al sicuro lo stato precedente"
    assert latest_backup(str(tmp_path), "casa-mia") is None


@pytest.mark.asyncio
async def test_replace_rejects_unknown_mode(tmp_path):
    ha = FakeHA()
    out = await apply_ha_config(
        ha,
        {"kind": "dashboard", "mode": "cancella", "slug": "casa-mia", "ha_config": NEW},
        data_dir=str(tmp_path),
    )
    assert "error" in out
    assert ha.saved is None and ha.created is None


@pytest.mark.asyncio
async def test_replace_without_data_dir_still_writes_but_warns(tmp_path):
    """data_dir assente (chiamanti legacy): si applica comunque, senza snapshot."""
    ha = FakeHA()
    out = await apply_ha_config(
        ha, {"kind": "dashboard", "mode": "replace", "slug": "casa-mia", "ha_config": NEW},
    )
    assert out.get("ok") is True
    assert ha.saved == ("casa-mia", NEW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_apply_replace.py -v`
Expected: FAIL — `apply_ha_config() got an unexpected keyword argument 'data_dir'`

- [ ] **Step 3: Write minimal implementation**

In `hiris/app/tools/config_tools.py`, sostituisci `apply_ha_config` (righe 130-159) con:

```python
VALID_DASHBOARD_MODES = frozenset({"create", "replace"})


async def apply_ha_config(ha_client: Any, normalized: dict,
                          data_dir: str | None = None) -> dict:
    """Materializza una config normalizzata su HA. Condivisa dal percorso chat e
    dall'apply di una proposta pending.

    Difensivo: `normalized` puo' arrivare da una proposta costruita fuori da
    `normalize_config_inputs` (es. dal gateway MCP), quindi le chiavi non sono
    garantite. Mai sollevare KeyError: si ritorna sempre un dict {"error": ...}.

    `mode` (solo dashboard): 'create' (default, retro-compatibile con le
    proposte gia' salvate) crea una nuova plancia; 'replace' sovrascrive la
    config di una plancia esistente, salvando prima uno snapshot in data_dir."""
    kind = normalized.get("kind")
    if kind not in VALID_KINDS:
        return {"error": "config non valida: kind mancante o non supportato"}
    if kind in ("script", "scene"):
        slug = normalized.get("slug")
        ha_config = normalized.get("ha_config")
        if not slug or not isinstance(ha_config, dict):
            return {"error": "config non valida: kind mancante o non supportato"}
        if kind == "script":
            return await ha_client.create_script(slug, ha_config)
        return await ha_client.create_scene(slug, ha_config)
    # kind == "dashboard"
    slug = normalized.get("slug")
    ha_config = normalized.get("ha_config")
    mode = normalized.get("mode") or "create"
    if mode not in VALID_DASHBOARD_MODES:
        return {"error": f"mode dashboard non valido: {mode!r} (usa create|replace)"}
    if not slug or not isinstance(ha_config, dict):
        return {"error": "config non valida: kind mancante o non supportato"}

    if mode == "replace":
        # Leggere PRIMA di scrivere: se la config attuale non e' leggibile
        # (plancia inesistente o in modalita' YAML) si annulla tutto, cosi' non
        # si sovrascrive mai senza aver messo al sicuro lo stato precedente.
        current = await ha_client.get_lovelace_config(slug)
        if not isinstance(current, dict) or current.get("error"):
            msg = current.get("error") if isinstance(current, dict) else "errore sconosciuto"
            return {"error": f"plancia non leggibile, sostituzione annullata: {msg}"}
        if data_dir:
            from ..proxy.dashboard_backups import save_backup
            save_backup(data_dir, slug, current)
        else:
            logger.warning(
                "apply dashboard replace su %s senza data_dir: nessuno snapshot salvato", slug)
        return await ha_client.save_dashboard_config(slug, ha_config)

    name = normalized.get("name")
    if not name:
        return {"error": "config non valida: kind mancante o non supportato"}
    return await ha_client.create_dashboard(
        slug, name, ha_config,
        icon=normalized.get("icon"),
        show_in_sidebar=normalized.get("show_in_sidebar", True),
    )
```

In cima al file, aggiungi l'import del logger (se assente):

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_apply_replace.py -v`
Expected: PASS (5 test)

- [ ] **Step 5: Verifica di non regressione sui percorsi esistenti**

Run: `python -m pytest tests/ -q -k "config or proposal"`
Expected: PASS — nessuna rottura del percorso MCP/script/scene.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/tools/config_tools.py tests/test_dashboard_apply_replace.py
git commit -m "feat(dashboards): mode replace con snapshot prima della sovrascrittura"
```

---

## Task 4: Passare `data_dir` all'apply della proposta

**Files:**
- Modify: `hiris/app/api/handlers_proposals.py:60-72`
- Test: `tests/test_dashboard_proposal_apply.py` (create)

**Interfaces:**
- Consumes: `apply_ha_config(..., data_dir=...)` (Task 3).

Senza questo task lo snapshot non verrebbe mai salvato dal percorso reale: `handle_apply_proposal` chiama `apply_ha_config` senza `data_dir`.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_dashboard_proposal_apply.py`:

```python
import pytest
from hiris.app.api.handlers_proposals import handle_apply_proposal


class FakeStore:
    def __init__(self, proposal):
        self.proposal = proposal
        self.applied = None

    async def get(self, pid):
        return self.proposal

    async def apply(self, pid):
        self.applied = pid
        return True


class FakeHA:
    def __init__(self):
        self.saved = None

    async def get_lovelace_config(self, url_path):
        return {"views": [{"title": "VECCHIA"}]}

    async def save_dashboard_config(self, url_path, config):
        self.saved = (url_path, config)
        return {"ok": True, "url_path": url_path}


class FakeRequest:
    def __init__(self, app, pid="p1"):
        self.app = app
        self.match_info = {"proposal_id": pid}


@pytest.mark.asyncio
async def test_apply_replace_proposal_writes_snapshot(tmp_path):
    from hiris.app.proxy.dashboard_backups import latest_backup
    new_cfg = {"views": [{"title": "NUOVA"}]}
    store = FakeStore({
        "id": "p1", "status": "pending", "type": "ha_dashboard",
        "config": {"kind": "dashboard", "mode": "replace",
                   "slug": "casa-mia", "ha_config": new_cfg},
    })
    ha = FakeHA()
    app = {"proposal_store": store, "ha_client": ha, "data_dir": str(tmp_path)}
    resp = await handle_apply_proposal(FakeRequest(app))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", new_cfg)
    assert store.applied == "p1"
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "VECCHIA"}]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_proposal_apply.py -v`
Expected: FAIL — `latest_backup(...)` è `None` (lo snapshot non viene salvato).

- [ ] **Step 3: Write minimal implementation**

In `hiris/app/api/handlers_proposals.py`, nel ramo `_CONFIG_TYPES` (riga ~65), sostituisci la chiamata:

```python
        from ..tools.config_tools import apply_ha_config
        result = await apply_ha_config(
            ha, proposal.get("config") or {}, data_dir=request.app.get("data_dir")
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_proposal_apply.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_proposals.py tests/test_dashboard_proposal_apply.py
git commit -m "fix(proposals): passa data_dir all'apply cosi' lo snapshot viene salvato"
```

---

## Task 5: I tre tool dashboard + rimozione dell'azione diretta

**Files:**
- Create: `hiris/app/tools/dashboard_tools.py`
- Modify: `hiris/app/tools/config_tools.py` (rimuovi `ADD_DASHBOARD_VIEW_TOOL_DEF`, `add_dashboard_view`, kind `dashboard` da `CREATE_HA_CONFIG_TOOL_DEF`)
- Modify: `hiris/app/tools/dispatcher.py:551-560`
- Modify: `hiris/app/claude_runner.py:171-204` (`ALL_TOOL_DEFS`)
- Test: `tests/test_dashboard_tools.py` (create)

**Interfaces:**
- Consumes: `ha_client.list_dashboards`, `ha_client.get_lovelace_config`, `proposal_store.save`.
- Produces:
  - `LIST_DASHBOARDS_TOOL_DEF`, `GET_DASHBOARD_CONFIG_TOOL_DEF`, `PROPOSE_DASHBOARD_TOOL_DEF`
  - `async propose_dashboard(proposal_store, mode, url_path, config, reason, title=None) -> dict`

- [ ] **Step 1: Write the failing test**

Crea `tests/test_dashboard_tools.py`:

```python
import pytest
from hiris.app.tools.dashboard_tools import propose_dashboard


class FakeStore:
    def __init__(self):
        self.saved = None

    async def save(self, record):
        self.saved = record
        return "p42"


CFG = {"views": [{"title": "Home", "cards": []}]}


@pytest.mark.asyncio
async def test_propose_create_builds_ha_dashboard_proposal():
    store = FakeStore()
    out = await propose_dashboard(store, "create", "casa-mia", CFG, "richiesto in chat", title="Casa Mia")
    assert out["proposal_id"] == "p42"
    rec = store.saved
    assert rec["type"] == "ha_dashboard"
    assert rec["config"]["kind"] == "dashboard"
    assert rec["config"]["mode"] == "create"
    assert rec["config"]["slug"] == "casa-mia"
    assert rec["config"]["name"] == "Casa Mia"
    assert rec["config"]["ha_config"] == CFG


@pytest.mark.asyncio
async def test_propose_replace_does_not_require_title():
    store = FakeStore()
    out = await propose_dashboard(store, "replace", "casa-mia", CFG, "riorganizzo")
    assert "proposal_id" in out
    assert store.saved["config"]["mode"] == "replace"


@pytest.mark.asyncio
async def test_create_without_title_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "create", "casa-mia", CFG, "motivo")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_invalid_url_path_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "create", "casamia", CFG, "motivo", title="X")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_invalid_mode_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "cancella", "casa-mia", CFG, "motivo", title="X")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_config_without_views_is_rejected():
    store = FakeStore()
    out = await propose_dashboard(store, "replace", "casa-mia", {"nope": 1}, "motivo")
    assert "error" in out and store.saved is None


@pytest.mark.asyncio
async def test_store_failure_returns_generic_error():
    class Boom:
        async def save(self, record):
            raise RuntimeError("/data/secret/path.db is locked")
    out = await propose_dashboard(Boom(), "replace", "casa-mia", CFG, "motivo")
    assert "error" in out
    assert "secret" not in out["error"], "mai fare echo del dettaglio interno"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiris.app.tools.dashboard_tools'`

- [ ] **Step 3: Write minimal implementation**

Crea `hiris/app/tools/dashboard_tools.py`:

```python
"""Tool plance (dashboard Lovelace) per il Chatbot.

L'LLM legge le plance esistenti e PROPONE una creazione o una sostituzione:
non scrive mai direttamente su HA. Il gate umano e' la review della proposta,
come per le automazioni; la rete di sicurezza sulle sostituzioni e' lo
snapshot/undo (proxy/dashboard_backups.py)."""
from __future__ import annotations

import logging
from typing import Any

from .config_tools import _URL_PATH_RE, _MAX_CONFIG_BYTES

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({"create", "replace"})

LIST_DASHBOARDS_TOOL_DEF = {
    "name": "list_dashboards",
    "description": (
        "Elenca le plance (dashboard Lovelace) esistenti su Home Assistant, "
        "con url_path e titolo. Usalo prima di proporre una modifica, per "
        "sapere quale plancia esiste e come si chiama."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

GET_DASHBOARD_CONFIG_TOOL_DEF = {
    "name": "get_dashboard_config",
    "description": (
        "Legge la configurazione completa (viste e card) di una plancia "
        "esistente. Usalo PRIMA di proporre una sostituzione, cosi' la nuova "
        "configurazione parte da quella attuale e non perdi contenuti."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url_path": {"type": "string", "description": "url_path della plancia (es. 'casa-mia')"},
        },
        "required": ["url_path"],
    },
}

PROPOSE_DASHBOARD_TOOL_DEF = {
    "name": "propose_dashboard",
    "description": (
        "Propone di creare una nuova plancia oppure di sostituire quella "
        "esistente. NON scrive su Home Assistant: salva una proposta che "
        "l'utente attiva dalla sezione Proposte. "
        "mode='create': nuova plancia, servono url_path (con almeno un "
        "trattino, es. 'casa-mia') e title. "
        "mode='replace': sostituisce INTERAMENTE la configurazione della "
        "plancia indicata — leggi prima get_dashboard_config e includi anche "
        "le viste da conservare, altrimenti spariscono. "
        "Per plance molto grandi proponi poche viste per volta."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["create", "replace"]},
            "url_path": {"type": "string", "description": "url_path della plancia"},
            "title": {"type": "string", "description": "Titolo in sidebar (obbligatorio con mode='create')"},
            "config": {"type": "object", "description": "Config Lovelace completa: {views:[...]}"},
            "reason": {"type": "string", "description": "Perche' proponi questa plancia"},
        },
        "required": ["mode", "url_path", "config", "reason"],
    },
}


async def propose_dashboard(proposal_store: Any, mode: str, url_path: str,
                            config: dict, reason: str,
                            title: str | None = None) -> dict:
    """Valida e salva una proposta ha_dashboard. Non tocca mai HA.

    Fail-closed come validate_agentbot: una proposta malformata viene
    RIFIUTATA, non salvata — la lezione del bug #2 era che le proposte non
    canoniche venivano marcate applied senza alcun effetto."""
    if proposal_store is None:
        return {"error": "ProposalStore non disponibile"}
    mode = (mode or "").strip()
    if mode not in VALID_MODES:
        return {"error": f"mode non valido: {mode!r} (usa create|replace)"}
    if not isinstance(url_path, str) or not _URL_PATH_RE.match(url_path):
        return {"error": "url_path non valido: serve un url_path con almeno un trattino (es. 'casa-mia')"}
    if not isinstance(config, dict) or not isinstance(config.get("views"), list):
        return {"error": "config non valida: serve un dict Lovelace con la lista 'views'"}
    if len(str(config).encode("utf-8", "ignore")) > _MAX_CONFIG_BYTES:
        return {"error": "config troppo grande: proponi meno viste per volta"}
    if mode == "create":
        if not isinstance(title, str) or not title.strip():
            return {"error": "title obbligatorio con mode='create'"}
        title = title.strip()

    label = title or url_path
    descr = (f"Crea la nuova plancia '{label}'." if mode == "create"
             else f"Sostituisce interamente la configurazione della plancia '{label}'.")
    record = {
        "type": "ha_dashboard",
        "name": label,
        "description": descr,
        "config": {
            "kind": "dashboard",
            "mode": mode,
            "slug": url_path,
            "name": title,
            "ha_config": config,
        },
        "routing_reason": reason,
    }
    try:
        pid = await proposal_store.save(record)
    except Exception:
        logger.exception("propose_dashboard: salvataggio proposta fallito")
        return {"error": "Impossibile salvare la proposta. Riprova piu' tardi."}
    return {
        "proposal_id": pid,
        "status": "pending",
        "message": (f"Proposta plancia '{label}' salvata. "
                    "L'utente puo' attivarla dalla sezione Proposte."),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_tools.py -v`
Expected: PASS (7 test)

- [ ] **Step 5: Rimuovi l'azione diretta sulle dashboard**

In `hiris/app/tools/config_tools.py`:
- elimina `ADD_DASHBOARD_VIEW_TOOL_DEF` (righe 53-75) e la funzione `add_dashboard_view` (righe 78-87);
- in `CREATE_HA_CONFIG_TOOL_DEF` sostituisci la `description` e l'enum `kind`:

```python
CREATE_HA_CONFIG_TOOL_DEF = {
    "name": "create_ha_config",
    "description": (
        "Crea uno script o una scena Home Assistant. Dalla chat viene creato "
        "subito su HA. Fornisci un config HA valido. "
        "Per le plance (dashboard Lovelace) NON usare questo strumento: usa "
        "propose_dashboard, che passa dall'approvazione dell'utente."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["script", "scene"]},
            "name": {"type": "string", "description": "Titolo leggibile dell'artefatto"},
            "slug": {"type": "string", "description": "id tecnico: a-z 0-9 _"},
            "config": {
                "type": "object",
                "description": "Config HA. script: {sequence:[...]}. scene: {entities:{...}}.",
            },
        },
        "required": ["kind", "name", "slug", "config"],
    },
}
```

`VALID_KINDS`, `normalize_config_inputs` e `apply_ha_config` **restano invariati**: continuano a gestire `dashboard` perché l'apply delle proposte (chat e MCP) ne ha bisogno. Cambia solo ciò che l'LLM può invocare direttamente.

- [ ] **Step 6: Wire nel dispatcher**

In `hiris/app/tools/dispatcher.py`, sostituisci il blocco `create_ha_config` / `add_dashboard_view` (righe ~551-560) con:

```python
            if name == "create_ha_config":
                try:
                    normalized = normalize_config_inputs(inputs)
                except ValueError as exc:
                    return {"error": str(exc)}
                return await apply_ha_config(self._ha, normalized)
            if name == "list_dashboards":
                return await self._ha.list_dashboards()
            if name == "get_dashboard_config":
                return await self._ha.get_lovelace_config(inputs.get("url_path", ""))
            if name == "propose_dashboard":
                return await propose_dashboard(
                    self._proposal_store,
                    inputs.get("mode", ""),
                    inputs.get("url_path", ""),
                    inputs.get("config", {}),
                    inputs.get("reason", ""),
                    title=inputs.get("title"),
                )
```

Aggiorna gli import: la riga 34 diventa

```python
from .config_tools import normalize_config_inputs, apply_ha_config
from .dashboard_tools import propose_dashboard
```

`self._proposal_store` è l'attributo già esistente (assegnato a `dispatcher.py:146`, usato dal ramo `create_automation_proposal` a `dispatcher.py:543`): usa quello, non introdurne uno nuovo.

- [ ] **Step 7: Registra i tool**

In `hiris/app/claude_runner.py`, nell'import da `tools.config_tools` rimuovi `ADD_DASHBOARD_VIEW_TOOL_DEF` e aggiungi:

```python
from .tools.dashboard_tools import (
    LIST_DASHBOARDS_TOOL_DEF,
    GET_DASHBOARD_CONFIG_TOOL_DEF,
    PROPOSE_DASHBOARD_TOOL_DEF,
)
```

In `ALL_TOOL_DEFS`, sostituisci `ADD_DASHBOARD_VIEW_TOOL_DEF` con le tre nuove voci:

```python
    CREATE_HA_CONFIG_TOOL_DEF,
    LIST_DASHBOARDS_TOOL_DEF,
    GET_DASHBOARD_CONFIG_TOOL_DEF,
    PROPOSE_DASHBOARD_TOOL_DEF,
```

In `EVALUATION_ONLY_TOOLS` aggiorna i commenti di esclusione:

```python
    # create_ha_config excluded: writes to HA (script/scene) — chat-only
    # propose_dashboard excluded: writes to the proposal store — chat-only
    # list_dashboards / get_dashboard_config excluded: chat-only per coerenza
```

- [ ] **Step 8: Run the full backend suite**

Run: `python -m pytest -q`
Expected: PASS. Se un test cita `add_dashboard_view` o il kind `dashboard` di `create_ha_config`, aggiornalo: la rimozione è voluta. **Non** rimuovere test che coprono `apply_ha_config` con kind `dashboard` (quel percorso resta vivo).

- [ ] **Step 9: Commit**

```bash
git add hiris/app/tools/ hiris/app/claude_runner.py tests/test_dashboard_tools.py
git commit -m "feat(dashboards): tool a proposta (list/get/propose) e stop alla scrittura diretta"
```

---

## Task 6: Endpoint di restore

**Files:**
- Create: `hiris/app/api/handlers_dashboards.py`
- Modify: `hiris/app/server.py` (registrazione rotta, vicino alle rotte `/api/proposals`, ~riga 2664)
- Test: `tests/test_dashboard_restore.py` (create)

**Interfaces:**
- Consumes: `latest_backup` (Task 2), `ha_client.save_dashboard_config` (Task 1).
- Produces: `POST /api/dashboards/{url_path}/restore` → `{"ok": true, "url_path": ...}` oppure `{"error": ...}` con 404/502/503.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_dashboard_restore.py`:

```python
import pytest
from hiris.app.api.handlers_dashboards import handle_restore_dashboard
from hiris.app.proxy.dashboard_backups import save_backup


class FakeHA:
    def __init__(self, result=None):
        self.result = result or {"ok": True, "url_path": "casa-mia"}
        self.saved = None

    async def save_dashboard_config(self, url_path, config):
        self.saved = (url_path, config)
        return self.result


class FakeRequest:
    def __init__(self, app, url_path="casa-mia"):
        self.app = app
        self.match_info = {"url_path": url_path}


@pytest.mark.asyncio
async def test_restore_reapplies_latest_snapshot(tmp_path):
    old = {"views": [{"title": "VECCHIA"}]}
    save_backup(str(tmp_path), "casa-mia", old)
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 200
    assert ha.saved == ("casa-mia", old)


@pytest.mark.asyncio
async def test_restore_without_backup_is_404(tmp_path):
    ha = FakeHA()
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 404
    assert ha.saved is None


@pytest.mark.asyncio
async def test_restore_reports_ha_failure(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": []})
    ha = FakeHA(result={"error": "boom"})
    resp = await handle_restore_dashboard(
        FakeRequest({"ha_client": ha, "data_dir": str(tmp_path)}))
    assert resp.status == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_restore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiris.app.api.handlers_dashboards'`

- [ ] **Step 3: Write minimal implementation**

Crea `hiris/app/api/handlers_dashboards.py`:

```python
"""Undo di una sostituzione di plancia: ri-applica l'ultimo snapshot."""
import logging

from aiohttp import web

from ..proxy.dashboard_backups import latest_backup

logger = logging.getLogger(__name__)


async def handle_restore_dashboard(request: web.Request) -> web.Response:
    ha = request.app.get("ha_client")
    data_dir = request.app.get("data_dir")
    if ha is None or not data_dir:
        return web.json_response({"error": "servizio non disponibile"}, status=503)
    url_path = request.match_info["url_path"]
    config = latest_backup(data_dir, url_path)
    if config is None:
        return web.json_response(
            {"error": "Nessuno snapshot disponibile per questa plancia"}, status=404)
    result = await ha.save_dashboard_config(url_path, config)
    if not isinstance(result, dict) or result.get("error"):
        msg = result.get("error") if isinstance(result, dict) else "errore sconosciuto"
        return web.json_response(
            {"error": f"Ripristino non riuscito: {msg}"}, status=502)
    return web.json_response({"ok": True, "url_path": url_path})
```

- [ ] **Step 4: Registra la rotta**

In `hiris/app/server.py`, accanto alle rotte `/api/proposals` (~riga 2664), aggiungi:

```python
    app.router.add_post("/api/dashboards/{url_path}/restore", handle_restore_dashboard)
```

e in cima, insieme agli altri import di handler:

```python
from .api.handlers_dashboards import handle_restore_dashboard
```

La rotta è sotto `/api/`, quindi eredita automaticamente auth e CSRF dal middleware globale (`csrf_middleware` richiede `X-Requested-With` sui POST).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_restore.py -v`
Expected: PASS (3 test)

- [ ] **Step 6: Verifica che l'app parta**

Run: `python -c "from hiris.app import server; print('import ok')"`
Expected: `import ok` (nessun ImportError dalla nuova rotta)

- [ ] **Step 7: Commit**

```bash
git add hiris/app/api/handlers_dashboards.py hiris/app/server.py tests/test_dashboard_restore.py
git commit -m "feat(dashboards): endpoint di ripristino dell'ultimo snapshot"
```

---

## Task 7: UI — intestazione create/replace e azione Annulla

**Files:**
- Modify: `hiris/app/static/config/proposals-core.js` (+`restoreDashboard`)
- Modify: `hiris/app/static/chat/proposals.js` (rendering card + Annulla)
- Modify: `hiris/app/static/config/proposals.js` (intestazione nella pagina config)
- Test: `tests/js/dashboard-proposal-ui.test.mjs` (create)

**Interfaces:**
- Consumes: `POST /api/dashboards/{url_path}/restore` (Task 6).
- Produces: `HirisProposalsCore.restoreDashboard(urlPath) -> Promise<{ok, error}>`

- [ ] **Step 1: Write the failing test**

Crea `tests/js/dashboard-proposal-ui.test.mjs`:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

function fixtureHtml() {
  return `<!doctype html><body>
    <a id="nav-proposals"><span id="proposals-badge" data-count="0"></span></a>
    <button id="mobile-proposals-btn"><span id="mobile-proposals-badge" data-count="0"></span></button>
    <div id="messages"></div><div id="input-area"></div>
    <div id="turn-counter"></div><div id="session-ended-msg"></div>
    <div id="task-panel"></div>
    <div id="proposals-panel"><div id="proposals-panel-header"></div>
      <div id="chat-proposals-list"></div></div>
  </body>`;
}

function dashProposal(mode) {
  return {
    id: 'p1', type: 'ha_dashboard', name: 'Casa Mia',
    description: 'x',
    config: { kind: 'dashboard', mode: mode, slug: 'casa-mia', ha_config: { views: [] } },
  };
}

test('la card di una sostituzione avvisa che sostituisce interamente', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async () => ({ ok: true, status: 200,
    json: async () => ({ proposals: [dashProposal('replace')] }) });

  await window.HirisChatProposals.load();

  const warn = document.querySelector('#chat-proposals-list .pp-warn');
  assert.ok(warn, 'una sostituzione deve mostrare un avviso');
  assert.match(warn.textContent, /[Ss]ostituisce interamente/);
});

test('la card di una creazione NON mostra l\'avviso di sostituzione', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async () => ({ ok: true, status: 200,
    json: async () => ({ proposals: [dashProposal('create')] }) });

  await window.HirisChatProposals.load();
  assert.equal(document.querySelector('#chat-proposals-list .pp-warn'), null);
});

test('dopo un replace applicato compare Annulla, che chiama il restore', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).indexOf('/apply') !== -1) return { ok: true, status: 200, json: async () => ({ ok: true }) };
    if (String(url).indexOf('/restore') !== -1) return { ok: true, status: 200, json: async () => ({ ok: true }) };
    return { ok: true, status: 200, json: async () => ({ proposals: [dashProposal('replace')] }) };
  };
  window.confirm = () => true;
  window.alert = () => {};

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatProposals.init();
  globalThis.setInterval = realSI;
  await tick(10);

  document.querySelector('.pp-apply').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const undo = document.querySelector('.pp-undo');
  assert.ok(undo, 'dopo un replace applicato deve comparire Annulla');
  undo.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const restore = calls.find((c) => c.url.indexOf('/restore') !== -1);
  assert.ok(restore, 'Annulla deve chiamare l\'endpoint di restore');
  assert.match(restore.url, /api\/dashboards\/casa-mia\/restore$/);
  assert.equal(restore.opts.method, 'POST');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/dashboard-proposal-ui.test.mjs`
Expected: FAIL — nessun elemento `.pp-warn`.

- [ ] **Step 3: Aggiungi `restoreDashboard` al core**

In `hiris/app/static/config/proposals-core.js`, dentro l'IIFE prima di `window.HirisProposalsCore = ...`:

```javascript
  function restoreDashboard(urlPath) {
    return fetch('api/dashboards/' + encodeURIComponent(urlPath) + '/restore', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(_result);
  }
```

e aggiungilo all'export:

```javascript
  window.HirisProposalsCore = {
    list: list, apply: apply, reject: reject, restoreDashboard: restoreDashboard
  };
```

- [ ] **Step 4: Rendering e Annulla nella chat**

In `hiris/app/static/chat/proposals.js`:

1. dentro `renderProposal(p)`, prima del `return`, calcola l'avviso:

```javascript
    var cfg = p.config || {};
    var isDashReplace = (p.type === 'ha_dashboard' && cfg.mode === 'replace');
    var warn = isDashReplace
      ? '<div class="pp-warn">Sostituisce interamente la plancia "' + esc(cfg.slug || '') + '".</div>'
      : '';
```

2. inserisci `+ warn` nella stringa restituita, subito dopo la riga `pp-desc`;

3. in `act()`, nel ramo di successo, dopo aver rimosso `.pp-actions`, aggiungi il pulsante Annulla quando ha senso:

```javascript
      if (card && !isReject) {
        var cfg2 = (card.dataset.ppMode === 'replace') ? card.dataset.ppSlug : '';
        if (cfg2) {
          var undo = document.createElement('button');
          undo.className = 'btn pp-undo';
          undo.type = 'button';
          undo.textContent = 'Annulla';
          undo.setAttribute('data-pp-undo', cfg2);
          card.appendChild(undo);
        }
      }
```

Perché `card.dataset` e non la proposta: dopo il reload la card viene ricostruita, quindi i dati servono sul nodo. Aggiungi gli attributi in `renderProposal`, sul div `pp-card`:

```javascript
      + ' data-pp-mode="' + esc(cfg.mode || '') + '" data-pp-slug="' + esc(cfg.slug || '') + '"'
```

4. estendi il click delegato in `init()` per gestire l'undo:

```javascript
    if (panel) panel.addEventListener('click', function(e) {
      var undoBtn = e.target.closest && e.target.closest('[data-pp-undo]');
      if (undoBtn) { undo(undoBtn.getAttribute('data-pp-undo')); return; }
      var btn = e.target.closest && e.target.closest('[data-pp-act]');
      if (btn) act(btn.dataset.pid, btn.dataset.ppAct);
    });
```

5. aggiungi la funzione `undo` accanto ad `act`:

```javascript
  function undo(urlPath) {
    if (!window.confirm('Ripristinare la versione precedente della plancia?')) return;
    HirisProposalsCore.restoreDashboard(urlPath).then(function(res) {
      if (!res.ok) { window.alert(res.error || 'Errore'); return; }
      load();
    }, function() { window.alert('Errore di rete'); });
  }
```

6. **Importante:** in `act()` il `setTimeout(load, 1000)` ricaricherebbe la lista facendo sparire il pulsante Annulla. Rimuovilo per il caso replace-applicato: ricarica solo i badge.

```javascript
      if (isReject || !isDashReplaceCard(card)) setTimeout(load, 1000);
```

con l'helper:

```javascript
  function isDashReplaceCard(card) {
    return !!(card && card.dataset && card.dataset.ppMode === 'replace' && card.dataset.ppSlug);
  }
```

- [ ] **Step 5: Stessa intestazione nella pagina config**

In `hiris/app/static/config/proposals.js`, dentro `renderProposals`, dopo la riga che costruisce `configPreview`, aggiungi:

```javascript
    var pcfg = p.config || {};
    var warn = (p.type === 'ha_dashboard' && pcfg.mode === 'replace')
      ? '<div class="pp-warn">Sostituisce interamente la plancia "' + escHtml(pcfg.slug || '') + '".</div>'
      : '';
```

e inseriscilo nella stringa subito dopo `proposal-desc`. (L'undo resta solo nella chat: è la superficie d'azione scelta.)

- [ ] **Step 6: CSS dell'avviso**

In `hiris/app/static/hiris-chat.css`, accanto alle regole `.pp-*` aggiunte in beta.10:

```css
    .pp-warn {
      font-size: 12px; color: var(--err, #c0392b);
      background: var(--err-tint, rgba(192,57,43,.08));
      border-radius: var(--r-sm); padding: 6px 10px; margin-bottom: 8px;
    }
    .pp-undo { margin-top: 8px; }
```

e la stessa regola `.pp-warn` in `hiris/app/static/hiris-config.css` per la pagina config.

- [ ] **Step 7: Run test to verify it passes**

Run: `node --test tests/js/dashboard-proposal-ui.test.mjs`
Expected: PASS (3 test)

- [ ] **Step 8: Run the full frontend suite**

Run: `npm test`
Expected: PASS — tutti i test, inclusi gli 85 esistenti.

- [ ] **Step 9: Commit**

```bash
git add hiris/app/static tests/js/dashboard-proposal-ui.test.mjs
git commit -m "feat(ui): avviso di sostituzione plancia e azione Annulla"
```

---

## Task 8: Documentazione, changelog e bump versione

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `hiris/config.yaml`
- Modify: `docs/` — cerca con `grep -rln "add_dashboard_view\|create_ha_config" docs/` e aggiorna i riferimenti

- [ ] **Step 1: Verifica la suite completa**

Run: `python -m pytest -q && npm test`
Expected: entrambe verdi. Annota i totali per il changelog.

- [ ] **Step 2: Aggiorna la documentazione**

Run: `grep -rln "add_dashboard_view" docs/ hiris/`
Per ogni file trovato, sostituisci il riferimento al tool rimosso con il nuovo flusso: `list_dashboards` → `get_dashboard_config` → `propose_dashboard` → approvazione nella sezione Proposte.

- [ ] **Step 3: Bump versione**

In `hiris/config.yaml`, porta `version` a `"1.1.0-beta.11"`.

- [ ] **Step 4: Voce di changelog**

In cima a `CHANGELOG.md`, sotto l'intestazione:

```markdown
## [1.1.0-beta.11] — Le plance si creano e si modificano per proposta (2026-08-01)

HIRIS puo' ora **creare una nuova plancia** (dashboard Lovelace) e **modificare
quelle esistenti**, ma non le scrive piu' di sua iniziativa: propone, e tu
approvi dalla sezione Proposte — esattamente come per le automazioni. Prima le
dashboard erano l'unico caso in cui la chat scriveva su Home Assistant senza
passare da una revisione.

Nuovi strumenti: `list_dashboards` ed `get_dashboard_config` per leggere le
plance esistenti, `propose_dashboard` per proporre una creazione o una
sostituzione. Le proposte di sostituzione lo dicono a chiare lettere, e prima
di sovrascrivere HIRIS salva uno **snapshot** della configurazione precedente:
se il risultato non convince, "Annulla" la ripristina con un click (ultimi 3
snapshot per plancia).

Rimossi gli strumenti di scrittura diretta delle dashboard
(`add_dashboard_view`, e il tipo `dashboard` da `create_ha_config`); script e
scene restano invariati.
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md hiris/config.yaml docs/
git commit -m "docs(release): 1.1.0-beta.11 — plance a proposta"
```

---

## Verifica finale (prima della review di branch)

- [ ] `python -m pytest -q` verde
- [ ] `npm test` verde
- [ ] `grep -rn "add_dashboard_view" hiris/app/` non restituisce nulla (il tool è rimosso ovunque)
- [ ] `grep -n "propose_dashboard\|list_dashboards\|get_dashboard_config" hiris/app/claude_runner.py` mostra i tre tool registrati
- [ ] Nessun tool nuovo compare in `EVALUATION_ONLY_TOOLS`
- [ ] La rotta di restore è registrata: `grep -n "dashboards/{url_path}/restore" hiris/app/server.py`

## Live-verify (utente, sull'addon)

1. Aggiorna l'addon e controlla che il build stamp in `/api/health` sia cambiato.
2. In chat: «quali plance ho?» → deve elencarle (`list_dashboards`).
3. «creami una plancia di prova con le luci del soggiorno» → deve comparire una **proposta**, non una dashboard già creata.
4. Attiva la proposta → la plancia compare nella sidebar di HA.
5. «aggiungi una vista con le temperature a quella plancia» → proposta di **sostituzione**, con l'avviso; attivala e verifica che le viste precedenti **ci siano ancora**.
6. Premi **Annulla** → la plancia torna alla versione precedente.
