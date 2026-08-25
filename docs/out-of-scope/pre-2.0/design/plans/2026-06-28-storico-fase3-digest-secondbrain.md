# Storico — Fase 3: digest notturno → second brain (regole) — Piano

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development o executing-plans. Step in checkbox (`- [ ]`).

**Goal:** Un job notturno che distilla lo `HistoryStore` in **insight testuali** (regole deterministiche, zero token) salvati nel `KnowledgeStore` (second brain), ricercabili via embedding — un riepilogo settimanale per entità storicizzata, aggiornato (superseded) ad ogni run.

**Architecture:** Funzioni pure `compute_insights` (delta settimana-su-settimana + summary, in italiano templated) + `_sensitivity_for` (presenza/sicurezza → "sensitive"). Un orchestratore async `run_history_digest` enumera le entità nello store, le interroga (14gg), calcola un insight per entità, supersede il precedente (per `source_ref`) e lo persiste con embedding. Schedulato in `server.py` a notte fonda dopo il compact. Niente LLM (scelta utente: regole).

**Tech Stack:** Python 3, sqlite3, pytest, APScheduler.
**Dipende da:** Fase 2a (`HistoryStore.query/has_entity`), `KnowledgeStore.add_item/list_items/delete_item`, embedder `await embedder.embed(text)`.
**Fuori scope:** generazione LLM (eventuale evoluzione ibrida futura); UI per visualizzare gli insight (sono già interrogabili via `recall_knowledge`).

---

### Task 1: `HistoryStore.list_entities()`

**Files:**
- Modify: `hiris/app/history/store.py`
- Test: `tests/test_history_store.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_list_entities_from_both_tables(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    s.append("sensor.a", "2026-06-20T10:00:00+00:00", "1.0")
    s.append("climate.b", "2026-06-20T10:00:00+00:00", "2.0")
    s.rollup_day("climate.b", "2026-06-20")
    s.compact(today="2026-06-21", retention_days=0)   # prune raw, keep daily for climate.b
    ents = s.list_entities()
    assert "climate.b" in ents          # survives via history_daily
    assert isinstance(ents, list)
```

- [ ] **Step 2: Run, confirm FAIL.**
Run: `python -m pytest tests/test_history_store.py -k list_entities -v`

- [ ] **Step 3: Implement** — add to `HistoryStore`:

```python
    def list_entities(self) -> list[str]:
        """Distinct entity ids known to the store (raw events or daily rollups)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT entity_id FROM history_events "
                "UNION SELECT entity_id FROM history_daily")
            return [r["entity_id"] for r in cur.fetchall()]
```

- [ ] **Step 4: Run, confirm PASS + full file.**
Run: `python -m pytest tests/test_history_store.py -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/history/store.py tests/test_history_store.py
git commit -m "feat(history-store): list_entities()"
```

---

### Task 2: `history_digest` — regole pure (compute_insights + sensitivity)

**Files:**
- Create: `hiris/app/brain/history_digest.py`
- Test: `tests/test_history_digest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_digest.py
from hiris.app.brain.history_digest import (
    compute_insights, _sensitivity_for, _pct_delta,
)


def _numeric_buckets(start_day, vals):
    # vals: list of daily means, oldest first; days are consecutive
    out = []
    for i, v in enumerate(vals):
        d = "2026-06-%02d" % (start_day + i)
        out.append({"t": d, "min": v - 1, "max": v + 1, "mean": v, "n": 24})
    return out


def test_pct_delta():
    assert _pct_delta(112.0, 100.0) == 12.0
    assert _pct_delta(100.0, 0.0) is None       # no baseline
    assert _pct_delta(90.0, 100.0) == -10.0


def test_sensitivity_for():
    assert _sensitivity_for("binary_sensor.porta") == "sensitive"
    assert _sensitivity_for("device_tracker.paolo") == "sensitive"
    assert _sensitivity_for("sensor.temp") == "normal"
    assert _sensitivity_for("climate.salotto") == "normal"


def test_compute_insights_numeric_delta():
    # 14 days: prev 7 mean ~20, last 7 mean ~24 -> +20%
    buckets = _numeric_buckets(7, [20, 20, 20, 20, 20, 20, 20, 24, 24, 24, 24, 24, 24, 24])
    ins = compute_insights("sensor.temp_salotto", buckets, today="2026-06-21")
    assert len(ins) == 1
    i = ins[0]
    assert i["entity_id"] == "sensor.temp_salotto"
    assert i["source_ref"] == "history-digest:sensor.temp_salotto:weekly"
    assert i["sensitivity"] == "normal"
    assert "20%" in i["text"] or "+20" in i["text"]
    assert "sensor.temp_salotto" in i["text"]


def test_compute_insights_onoff_summary():
    # on/off buckets: ~1h/day on for 7 recent days, none before
    buckets = []
    for d in range(14, 21):
        buckets.append({"t": "2026-06-%02d" % d, "on_seconds": 3600, "transitions": 4})
    ins = compute_insights("binary_sensor.movimento", buckets, today="2026-06-21")
    assert len(ins) == 1
    i = ins[0]
    assert i["sensitivity"] == "sensitive"
    assert "ore" in i["text"].lower()


def test_compute_insights_insufficient_data_returns_none():
    buckets = [{"t": "2026-06-20", "mean": 20.0, "min": 19, "max": 21, "n": 5}]
    assert compute_insights("sensor.x", buckets, today="2026-06-21") == []
```

- [ ] **Step 2: Run, confirm FAIL.**
Run: `python -m pytest tests/test_history_digest.py -v`

- [ ] **Step 3: Implement `hiris/app/brain/history_digest.py`**

```python
"""History digest (rule-based): turn HistoryStore daily buckets into one weekly
summary insight per entity, in Italian. Deterministic, no LLM, no tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

_MIN_DAYS = 3            # need at least this many days per window to summarize
_DELTA_PCT = 10.0        # |Δ%| at/above this is called out explicitly
_SENSITIVE_DOMAINS = {
    "binary_sensor", "device_tracker", "person", "alarm_control_panel", "lock",
}


def _sensitivity_for(entity_id: str) -> str:
    dom = entity_id.split(".", 1)[0] if "." in entity_id else ""
    return "sensitive" if dom in _SENSITIVE_DOMAINS else "normal"


def _pct_delta(cur: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100.0, 1)


def _day_str(today: str, offset: int) -> str:
    d = datetime.fromisoformat(today + "T00:00:00+00:00") + timedelta(days=offset)
    return d.strftime("%Y-%m-%d")


def _split_windows(buckets: list[dict], today: str) -> tuple[list[dict], list[dict]]:
    """Return (last7, prev7) bucket lists by day window relative to today."""
    last_lo = _day_str(today, -7)      # [today-7, today)  -> last 7 complete-ish days
    prev_lo = _day_str(today, -14)
    last7 = [b for b in buckets if last_lo <= b["t"] < today]
    prev7 = [b for b in buckets if prev_lo <= b["t"] < last_lo]
    return last7, prev7


def _avg(vals: list[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _fmt_delta(pct: Optional[float]) -> str:
    if pct is None or abs(pct) < _DELTA_PCT:
        return "in linea con la settimana precedente"
    sign = "+" if pct > 0 else ""
    return "%s%.0f%% rispetto alla settimana precedente" % (sign, pct)


def compute_insights(entity_id: str, buckets: list[dict], today: str) -> list[dict]:
    """One weekly-summary insight per entity, or [] if not enough data.

    Numeric entities (buckets carry 'mean') summarize the 7-day average vs the
    prior week. On/off entities (buckets carry 'on_seconds') summarize active
    hours vs the prior week."""
    last7, prev7 = _split_windows(buckets, today)
    if len(last7) < _MIN_DAYS:
        return []
    numeric = any(b.get("mean") is not None for b in last7)
    if numeric:
        cur = _avg([b.get("mean") for b in last7])
        prev = _avg([b.get("mean") for b in prev7]) if len(prev7) >= _MIN_DAYS else None
        if cur is None:
            return []
        pct = _pct_delta(cur, prev) if prev is not None else None
        text = ("Negli ultimi 7 giorni %s ha una media di %.1f (%s)."
                % (entity_id, cur, _fmt_delta(pct)))
    else:
        cur_h = sum(b.get("on_seconds") or 0.0 for b in last7) / 3600.0
        prev_h = (sum(b.get("on_seconds") or 0.0 for b in prev7) / 3600.0
                  if len(prev7) >= _MIN_DAYS else None)
        pct = _pct_delta(cur_h, prev_h) if prev_h is not None else None
        text = ("Negli ultimi 7 giorni %s è risultato attivo per circa %.0f ore (%s)."
                % (entity_id, cur_h, _fmt_delta(pct)))
    return [{
        "entity_id": entity_id,
        "metric": "weekly",
        "text": text,
        "sensitivity": _sensitivity_for(entity_id),
        "source_ref": "history-digest:%s:weekly" % entity_id,
    }]
```

- [ ] **Step 4: Run, confirm PASS.**
Run: `python -m pytest tests/test_history_digest.py -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/brain/history_digest.py tests/test_history_digest.py
git commit -m "feat(history-digest): rule-based weekly insight computation"
```

---

### Task 3: `run_history_digest` orchestrator (supersede + persist)

**Files:**
- Modify: `hiris/app/brain/history_digest.py` (add async orchestrator)
- Test: `tests/test_history_digest.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_history_digest.py
import pytest


class _FakeStore:
    def __init__(self, ents, buckets):
        self._ents = ents
        self._buckets = buckets
    def list_entities(self):
        return list(self._ents)
    def query(self, eid, days, today):
        b = self._buckets.get(eid)
        return {"id": eid, "source": "store", "buckets": b} if b else None


class _FakeKnowledge:
    def __init__(self):
        self.items = []      # list of dicts with id/kind/source_ref/content/sensitivity
        self._id = 0
    def list_items(self, *, kind=None, limit=100, **kw):
        return [dict(it) for it in self.items if kind is None or it["kind"] == kind]
    def delete_item(self, item_id):
        self.items = [it for it in self.items if it["id"] != item_id]
    def add_item(self, *, kind, content, source_ref=None, sensitivity="normal",
                 embedding=None, **kw):
        self._id += 1
        self.items.append({"id": self._id, "kind": kind, "content": content,
                           "source_ref": source_ref, "sensitivity": sensitivity,
                           "has_emb": embedding is not None})
        return self._id


class _FakeEmbedder:
    async def embed(self, text):
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_run_history_digest_persists_and_supersedes():
    from hiris.app.brain.history_digest import run_history_digest
    buckets = {"sensor.temp": _numeric_buckets(7, [20] * 7 + [24] * 7)}
    store = _FakeStore(["sensor.temp"], buckets)
    kb = _FakeKnowledge()
    emb = _FakeEmbedder()
    # first run -> 1 insight added, embedded
    n1 = await run_history_digest(store, kb, emb, today="2026-06-21")
    assert n1 == 1
    assert len(kb.items) == 1
    assert kb.items[0]["kind"] == "insight"
    assert kb.items[0]["source_ref"] == "history-digest:sensor.temp:weekly"
    assert kb.items[0]["has_emb"] is True
    # second run -> supersedes the prior one (still exactly 1 item for that ref)
    n2 = await run_history_digest(store, kb, emb, today="2026-06-21")
    assert n2 == 1
    refs = [it for it in kb.items if it["source_ref"] == "history-digest:sensor.temp:weekly"]
    assert len(refs) == 1


@pytest.mark.asyncio
async def test_run_history_digest_handles_no_embedder():
    from hiris.app.brain.history_digest import run_history_digest
    buckets = {"sensor.temp": _numeric_buckets(7, [20] * 7 + [24] * 7)}
    store = _FakeStore(["sensor.temp"], buckets)
    kb = _FakeKnowledge()
    n = await run_history_digest(store, kb, None, today="2026-06-21")
    assert n == 1 and kb.items[0]["has_emb"] is False
```

- [ ] **Step 2: Run, confirm FAIL.**
Run: `python -m pytest tests/test_history_digest.py -k run_history_digest -v`

- [ ] **Step 3: Implement** — append to `hiris/app/brain/history_digest.py`:

```python
import logging

logger = logging.getLogger(__name__)


async def run_history_digest(store, knowledge_store, embedder, today: str,
                             owner: str = "home") -> int:
    """For each entity in the store, compute its weekly insight, supersede the
    prior digest item with the same source_ref, and persist the new one
    (embedded when an embedder is available). Returns the number written."""
    written = 0
    try:
        existing = knowledge_store.list_items(kind="insight", limit=1000)
    except Exception as exc:
        logger.error("history digest: cannot list existing insights: %s", exc)
        existing = []
    by_ref = {}
    for it in existing:
        ref = it.get("source_ref")
        if ref:
            by_ref.setdefault(ref, []).append(it.get("id"))

    for eid in store.list_entities():
        try:
            res = store.query(eid, days=14, today=today)
            if not res or not res.get("buckets"):
                continue
            for ins in compute_insights(eid, res["buckets"], today):
                ref = ins["source_ref"]
                for old_id in by_ref.get(ref, []):
                    try:
                        knowledge_store.delete_item(old_id)
                    except Exception:
                        pass
                by_ref[ref] = []
                emb = None
                if embedder is not None:
                    try:
                        emb = await embedder.embed(ins["text"])
                    except Exception as exc:
                        logger.debug("history digest: embed failed for %s: %s", eid, exc)
                knowledge_store.add_item(
                    kind="insight", content=ins["text"], owner=owner,
                    title="Storico: %s" % eid, embedding=emb,
                    sensitivity=ins["sensitivity"], source="history-digest",
                    source_ref=ref, confidence=1.0, status="approved",
                    valid_from=today,
                )
                written += 1
        except Exception as exc:
            logger.error("history digest: entity %s failed: %s", eid, exc)
    if written:
        logger.info("history digest: wrote %d insight(s)", written)
    return written
```

- [ ] **Step 4: Run, confirm PASS + full digest file.**
Run: `python -m pytest tests/test_history_digest.py -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/brain/history_digest.py tests/test_history_digest.py
git commit -m "feat(history-digest): run_history_digest orchestrator (supersede + embed + persist)"
```

---

### Task 4: Wiring notturno in `server.py` + release v0.17.0

**Files:**
- Modify: `hiris/app/server.py`
- Modify: `hiris/config.yaml`, `CHANGELOG.md`

- [ ] **Step 1: Wire the nightly digest job in `create_app`**

Next to the history compaction job (which runs at 03:30), add a digest job at 04:00 (after compaction). `history_store`, `knowledge_store`, `embedder`, `data_dir`, `engine`, `logger` are all in scope there.

```python
    async def _run_history_digest_job() -> None:
        from datetime import datetime, timezone
        from .brain.history_digest import run_history_digest
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            await run_history_digest(history_store, knowledge_store, embedder, today=today)
        except Exception as exc:
            logger.error("History digest failed: %s", exc, exc_info=True)

    engine._scheduler.add_job(
        _run_history_digest_job,
        trigger="cron", hour=4, minute=0,
        id="hiris_history_digest", replace_existing=True, misfire_grace_time=3600,
    )
```

(Place it immediately after the `engine._scheduler.add_job(_run_history_compact, ...)` block added in Phase 2b. `embedder` is the variable used elsewhere for `embedding_provider`; confirm its name in scope — it is `embedder` per the dispatcher construction. If it is named differently at this point, use the in-scope name and report.)

- [ ] **Step 2: Verify import + suite**

Run: `python -c "import hiris.app.server"`   (no exception)
Run: `python -m pytest -q`   (all pass)

- [ ] **Step 3: Bump version + changelog**

`hiris/config.yaml`: `version: "0.17.0"`.
`CHANGELOG.md` new top section:

```markdown
## v0.17.0 — Storico → second brain: digest notturno di insight (2026-06-28)

- Nuovo job notturno (04:00) che distilla lo storico (`HistoryStore`) in **insight
  testuali** salvati nel second brain (`KnowledgeStore`), ricercabili via
  `recall_knowledge`. Un riepilogo settimanale per entità storicizzata
  (media/ore attive + Δ% settimana-su-settimana), aggiornato (superseded) ogni notte.
- **Regole deterministiche, zero token** (nessuna chiamata LLM). Dati di
  presenza/sicurezza marcati `sensitive` (rispettano l'egress privacy del brain).
- Completa la Fase 3 dello storico ([[storico]] 2a/2b/2c già in v0.16.0).
```

- [ ] **Step 4: Commit (LOCAL ONLY — push solo dopo conferma utente)**

```bash
git add hiris/app/server.py hiris/config.yaml CHANGELOG.md
git commit -m "release: v0.17.0 — digest notturno storico -> second brain"
```

---

## Self-Review (compilata)

**Spec coverage:** job notturno regole→KnowledgeStore (Task 3/4); insight testuali non grezzi, un summary settimanale per entità con Δ WoW (Task 2); sensitivity presenza/sicurezza (Task 2); supersede per evitare accumulo (Task 3); enumerazione entità (Task 1); embedding per ricercabilità + fallback senza embedder (Task 3).

**Placeholder scan:** nessun TBD; codice/comandi concreti ovunque. Task 4 Step 1 chiede di confermare il nome in-scope di `embedder` (istruzione esplicita).

**Type consistency:** `compute_insights(entity_id, buckets, today)->list[{entity_id,metric,text,sensitivity,source_ref}]` usato da `run_history_digest`; `_sensitivity_for`/`_pct_delta`/`_split_windows` coerenti; `run_history_digest(store, knowledge_store, embedder, today, owner)` usa `store.list_entities/query`, `knowledge_store.list_items(kind=)/delete_item/add_item(...)` (firme reali verificate), `await embedder.embed(text)`; `HistoryStore.list_entities()->list[str]` (Task 1). Job schedulato via `engine._scheduler.add_job` come compact/retention.

**Nota:** gli insight diventano subito interrogabili da Claude via `recall_knowledge` (già esposto). Nessuna UI necessaria. Bounded: 1 item per entità (supersede), quindi nessuna crescita illimitata del brain.
