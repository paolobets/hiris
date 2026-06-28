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
    last_lo = _day_str(today, -7)
    prev_lo = _day_str(today, -14)
    last7 = [b for b in buckets if last_lo <= b["t"] < today]
    prev7 = [b for b in buckets if prev_lo <= b["t"] < last_lo]
    return last7, prev7


def _avg(vals: list) -> Optional[float]:
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
