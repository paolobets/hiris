from __future__ import annotations


def reasoning_items(rows) -> list[dict]:
    out = []
    for r in rows or []:
        out.append({
            "type": "reasoning", "ts": r.get("ts", ""),
            "title": "Ragionamento del Brain",
            "body": r.get("text", ""),
            "refs": {"id": r.get("id"), "mode": r.get("mode")},
            "actions": [], "status": None,
        })
    return out


def advisory_items(rows) -> list[dict]:
    out = []
    for r in rows or []:
        if r.get("status") not in ("open", "acknowledged"):
            continue
        out.append({
            "type": "advisory", "ts": r.get("ts_updated", ""),
            "title": r.get("title", ""),
            "body": r.get("suggested_fix", ""),
            "refs": {"id": r.get("id"), "check_id": r.get("check_id"),
                     "fix_kind": r.get("fix_kind"), "severity": r.get("severity"),
                     "evidence": r.get("evidence") or {}},
            "actions": [{"type": "ack"}, {"type": "dismiss"}],
            "status": r.get("status"),
        })
    return out


def proposal_items(rows) -> list[dict]:
    out = []
    for r in rows or []:
        out.append({
            "type": "proposal", "ts": r.get("created_at", ""),
            "title": r.get("name", ""),
            "body": r.get("description", ""),
            "refs": {"id": r.get("id"), "proposal_type": r.get("type")},
            "actions": [{"type": "apply"}, {"type": "reject"}],
            "status": r.get("status"),
        })
    return out


def brain_action_items(rows) -> list[dict]:
    out = []
    for r in rows or []:
        out.append({
            "type": "brain_action", "ts": r.get("created_at", ""),
            "title": "Azione del Brain",
            "body": r.get("content", ""),
            "refs": {"id": r.get("id"), "source_ref": r.get("source_ref")},
            "actions": [], "status": r.get("status"),
        })
    return out


def merge_feed(*item_lists, limit: int = 50, type_filter: str | None = None) -> list[dict]:
    items = [i for lst in item_lists for i in (lst or [])]
    if type_filter:
        wanted = {t.strip() for t in type_filter.split(",") if t.strip()}
        items = [i for i in items if i.get("type") in wanted]
    items.sort(key=lambda i: i.get("ts", ""), reverse=True)
    return items[: int(limit)]
