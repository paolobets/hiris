from __future__ import annotations
import json
import os
import threading
from datetime import date, datetime, timedelta

_URGENT_THRESHOLDS = ["overdue", "today", "tomorrow"]
_SEEN_FILE = "reminders_seen.json"


def urgency_of(due_date_str, today: date) -> str | None:
    """Classify `due_date_str` (ISO `%Y-%m-%d`) relative to `today`.

    Returns "overdue" if due < today, "today" if due == today, "tomorrow"
    if due == today + 1 day, else None. Missing/invalid input -> None,
    never raises.
    """
    if not due_date_str:
        return None
    try:
        due = datetime.strptime(str(due_date_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    if due < today:
        return "overdue"
    if due == today:
        return "today"
    if due == today + timedelta(days=1):
        return "tomorrow"
    return None


class ReminderSeen:
    """Persistent (key, threshold) dedup sidecar so urgent nudges fire once.

    Backed by a JSON file `reminders_seen.json` in `data_dir`, structured as
    `{key: [threshold, ...]}`. Writes are atomic (tmp file + os.replace).
    A missing or corrupt sidecar is treated as empty rather than raising.
    """

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._lock = threading.Lock()

    def _path(self) -> str:
        return os.path.join(self._data_dir, _SEEN_FILE)

    def _load(self) -> dict:
        try:
            with open(self._path(), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, ValueError, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}

    def _save(self, data: dict) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        tmp = self._path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path())

    def seen(self, key: str, threshold: str) -> bool:
        with self._lock:
            data = self._load()
        return threshold in data.get(key, [])

    def mark(self, key: str, threshold: str) -> None:
        with self._lock:
            data = self._load()
            thresholds = data.setdefault(key, [])
            if threshold not in thresholds:
                thresholds.append(threshold)
            self._save(data)


def due_nudges(store, *, today: date, seen: ReminderSeen, horizon_days: int = 2) -> list[dict]:
    """Not-yet-seen urgent nudges (overdue/today/tomorrow) for obligations
    due within `horizon_days` of `today`.

    Pure query + dedup lookup: does NOT call `seen.mark()` — the caller
    marks a (key, threshold) pair only after successfully notifying it.
    Ordered overdue -> today -> tomorrow.
    """
    before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    try:
        # Review C/#2: urgent nudges are also a home-wide broadcast (single
        # ha_push target, see server.py's _nudge_notify) -- scope to
        # owner="home" so a user's PRIVATE obligation is never nudged to the
        # whole household. See briefing.py's _collect_deadlines for the same
        # fix on the daily briefing path.
        items = store.upcoming_obligations(before=before, owner="home")
    except Exception:
        items = []

    order = {threshold: i for i, threshold in enumerate(_URGENT_THRESHOLDS)}
    out = []
    for item in items:
        threshold = urgency_of(item.get("due_date"), today)
        if threshold is None:
            continue
        key = item.get("source_ref") or str(item.get("id"))
        if seen.seen(key, threshold):
            continue
        out.append({"item": item, "threshold": threshold, "key": key})

    out.sort(key=lambda n: order.get(n["threshold"], len(order)))
    return out


