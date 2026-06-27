"""Storicizzazione policy — UI/file-managed, per-domain + explicit allow/exclude.

Decides which entities the HistoryStore captures. Default empty => capture nothing
(opt-in). Mirrors the gateway-policy pattern (handlers_gateway_policy.py)."""
from __future__ import annotations

import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90
_MIN_RETENTION, _MAX_RETENTION = 1, 365

HISTORY_CATEGORIES = [
    {"id": "sensor", "label": "Sensori (temperatura, umidità, …)"},
    {"id": "binary_sensor", "label": "Sensori on/off (presenza, porte, …)"},
    {"id": "climate", "label": "Climatizzazione"},
    {"id": "switch", "label": "Interruttori / Prese"},
    {"id": "light", "label": "Luci"},
    {"id": "valve", "label": "Valvole / Irrigazione"},
    {"id": "cover", "label": "Tapparelle / Tende"},
    {"id": "lock", "label": "Serrature"},
    {"id": "fan", "label": "Ventilazione"},
    {"id": "media_player", "label": "Media / TV"},
    {"id": "device_tracker", "label": "Presenza persone"},
    {"id": "person", "label": "Persone"},
    {"id": "alarm_control_panel", "label": "Allarme"},
]
_VALID_DOMAINS = {c["id"] for c in HISTORY_CATEGORIES}


def _path(data_dir: str) -> str:
    return os.path.join(data_dir, "history_policy.json")


def load_policy(data_dir: str) -> dict:
    try:
        with open(_path(data_dir), encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raw = {}
    except Exception as exc:
        logger.warning("history_policy.json unreadable (%s) — using empty", exc)
        raw = {}
    domains = raw.get("domains") if isinstance(raw.get("domains"), dict) else {}
    domains = {k: bool(v) for k, v in domains.items() if k in _VALID_DOMAINS}
    entities = [e for e in raw.get("entities", []) if isinstance(e, str)]
    exclude = [e for e in raw.get("exclude", []) if isinstance(e, str)]
    ret = raw.get("retention_days", DEFAULT_RETENTION_DAYS)
    if not isinstance(ret, int) or isinstance(ret, bool):
        ret = DEFAULT_RETENTION_DAYS
    ret = max(_MIN_RETENTION, min(_MAX_RETENTION, ret))
    return {"domains": domains, "entities": entities, "exclude": exclude,
            "retention_days": ret}


def save_policy(data_dir: str, data: dict) -> dict:
    clean = {
        "domains": {k: bool(v) for k, v in (data.get("domains") or {}).items()
                    if k in _VALID_DOMAINS},
        "entities": [e for e in (data.get("entities") or []) if isinstance(e, str)],
        "exclude": [e for e in (data.get("exclude") or []) if isinstance(e, str)],
        "retention_days": data.get("retention_days", DEFAULT_RETENTION_DAYS),
    }
    if not isinstance(clean["retention_days"], int) or isinstance(clean["retention_days"], bool):
        clean["retention_days"] = DEFAULT_RETENTION_DAYS
    clean["retention_days"] = max(_MIN_RETENTION, min(_MAX_RETENTION, clean["retention_days"]))
    path = _path(data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh)
    os.replace(tmp, path)
    return clean


def should_capture(entity_id: str, policy: dict) -> bool:
    """True if this entity should be recorded into the HistoryStore."""
    if entity_id in (policy.get("exclude") or []):
        return False
    if entity_id in (policy.get("entities") or []):
        return True
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    return bool((policy.get("domains") or {}).get(domain, False))


async def handle_get_history_policy(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    return web.json_response(dict(load_policy(data_dir), categories=HISTORY_CATEGORIES))


async def handle_save_history_policy(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_policy(data_dir, body if isinstance(body, dict) else {})
    cap = request.app.get("history_capture")
    if cap is not None:
        cap.set_policy(clean)
    return web.json_response({"ok": True, **clean})
