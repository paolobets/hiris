import json
import os
from datetime import datetime, timezone, timedelta

HISTORY_RETENTION_DAYS = 30
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _path(agent_id: str, data_dir: str) -> str:
    return os.path.join(data_dir, f"chat_history_{agent_id}.json")


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime(_TS_FMT)


def _load_raw(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("messages", [])
    except Exception:
        return []


def load_history(agent_id: str, data_dir: str) -> list[dict]:
    """Return [{role, content}] for Claude API, filtered to last 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_RETENTION_DAYS)
    result = []
    for m in _load_raw(_path(agent_id, data_dir)):
        ts = m.get("timestamp", "")
        try:
            msg_dt = datetime.strptime(ts, _TS_FMT).replace(tzinfo=timezone.utc)
            if msg_dt < cutoff:
                continue
        except (ValueError, TypeError):
            pass
        result.append({"role": m["role"], "content": m["content"]})
    return result


def append_messages(agent_id: str, messages: list[dict], data_dir: str) -> None:
    """Append [{role, content}] with current timestamp and save atomically."""
    path = _path(agent_id, data_dir)
    raw = _load_raw(path)
    ts = _now_ts()
    for m in messages:
        raw.append({"role": m["role"], "content": m["content"], "timestamp": ts})
    _write(agent_id, raw, path, data_dir)


def clear_history(agent_id: str, data_dir: str) -> None:
    """Delete the history file for the given agent."""
    try:
        os.remove(_path(agent_id, data_dir))
    except FileNotFoundError:
        pass


def _write(agent_id: str, raw_messages: list[dict], path: str, data_dir: str) -> None:
    os.makedirs(data_dir, exist_ok=True)
    data = {"schema_version": 1, "agent_id": agent_id, "messages": raw_messages}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
