"""Yellow/Red approval flow for gateway actions.

When the gateway requests an action whose category is yellow or red, HIRIS does
NOT execute it. It holds it as a *pending command* (single-use nonce + expiry)
and notifies the user:
  - yellow: an actionable iPhone notification (Approva / Nega) — the button tap
    fires ``mobile_app_notification_action`` which we map back to the nonce.
  - red:   an informational notification; approval is only possible by hand from
    the HIRIS "Approvazioni" page (deliberate high friction for alarm/locks).

Security: the nonce is single-use, time-limited, and bound to the exact held
command; an approval can never execute anything other than the command it was
issued for. The notify service is configurable (default notify.iphone_bet).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time

from aiohttp import web

logger = logging.getLogger(__name__)

PENDING_TTL_S = 300                    # a pending command expires after 5 minutes
_ACTION_PREFIX = "HIRIS_GW"           # mobile_app notification action namespace


def _pending_path(data_dir: str) -> str:
    return os.path.join(data_dir, "gateway_pending.json")


def _load(data_dir: str) -> dict:
    try:
        with open(_pending_path(data_dir), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("gateway_pending.json unreadable (%s)", exc)
        return {}


def _save(data_dir: str, data: dict) -> None:
    path = _pending_path(data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def create_pending(data_dir: str, *, tool: str, inputs: dict, tier: str,
                   origin: str, label: str) -> dict:
    """Create and persist a pending command; returns the new entry."""
    data = _load(data_dir)
    now = time.time()
    # opportunistic GC of expired/resolved entries
    data = {k: v for k, v in data.items()
            if v.get("status") == "pending" and v.get("expires", 0) > now}
    nonce = secrets.token_urlsafe(18)
    entry = {
        "id": nonce, "tool": tool, "inputs": inputs, "tier": tier,
        "origin": origin, "label": label, "ts": now,
        "expires": now + PENDING_TTL_S, "status": "pending",
    }
    data[nonce] = entry
    _save(data_dir, data)
    return entry


def list_pending(data_dir: str) -> list[dict]:
    now = time.time()
    data = _load(data_dir)
    out = [v for v in data.values()
           if v.get("status") == "pending" and v.get("expires", 0) > now]
    out.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return out


def take_pending(data_dir: str, nonce: str) -> dict | None:
    """Fetch a still-valid pending entry and atomically mark it consumed.
    Single-use: a second take of the same nonce returns None."""
    data = _load(data_dir)
    entry = data.get(nonce)
    now = time.time()
    if not entry or entry.get("status") != "pending" or entry.get("expires", 0) <= now:
        return None
    entry["status"] = "consumed"
    _save(data_dir, data)
    return entry


def resolve_pending(data_dir: str, nonce: str, status: str) -> None:
    data = _load(data_dir)
    if nonce in data:
        data[nonce]["status"] = status
        _save(data_dir, data)


def parse_action(action: str) -> tuple[str, str] | None:
    """Parse a mobile_app notification action string 'HIRIS_GW:approve:<nonce>'."""
    parts = (action or "").split(":")
    if len(parts) == 3 and parts[0] == _ACTION_PREFIX and parts[1] in ("approve", "reject"):
        return parts[1], parts[2]
    return None


def build_actions(nonce: str) -> list[dict]:
    return [
        {"action": f"{_ACTION_PREFIX}:approve:{nonce}", "title": "Approva"},
        {"action": f"{_ACTION_PREFIX}:reject:{nonce}", "title": "Nega"},
        {"action": "URI", "title": "Apri HIRIS", "uri": "/hassio_ingress"},
    ]


async def notify(app: web.Application, *, message: str, actionable: bool, nonce: str) -> None:
    """Send a notification via the configured notify service (default
    notify.iphone_bet). Actionable (yellow) adds Approva/Nega buttons."""
    ha = app.get("ha_client")
    if ha is None:
        logger.warning("no ha_client — cannot send approval notification")
        return
    service = ((app.get("gateway_settings") or {}).get("notify_service")
               or "notify.iphone_bet").strip()
    if "." not in service:
        logger.error("invalid notify service %r", service)
        return
    domain, svc = service.split(".", 1)
    data: dict = {"message": message, "title": "HIRIS · richiesta da Claude"}
    if actionable:
        data["data"] = {"actions": build_actions(nonce), "tag": f"hiris-gw-{nonce}"}
    try:
        await ha.call_service(domain, svc, data)
    except Exception as exc:
        logger.error("approval notification failed: %s", exc)


async def approve(app: web.Application, nonce: str) -> dict:
    """Atomically consume the nonce and execute the held command (single-use)."""
    data_dir = app.get("data_dir") or "/data"
    entry = take_pending(data_dir, nonce)
    if entry is None:
        return {"ok": False, "error": "richiesta non trovata, scaduta o già gestita"}
    result = await execute_pending(app, entry)
    resolve_pending(data_dir, nonce, "approved")
    logger.info("gateway pending %s approved (%s)", nonce, entry.get("label"))
    return {"ok": True, "result": result}


def reject(app: web.Application, nonce: str) -> dict:
    data_dir = app.get("data_dir") or "/data"
    entry = take_pending(data_dir, nonce)
    if entry is None:
        return {"ok": False, "error": "richiesta non trovata, scaduta o già gestita"}
    resolve_pending(data_dir, nonce, "rejected")
    return {"ok": True}


async def on_notification_action(app: web.Application, event_data: dict) -> None:
    """HA fired mobile_app_notification_action: map the action back to a nonce
    and approve/reject. This is what makes the iPhone 'Approva' button work."""
    parsed = parse_action(event_data.get("action", ""))
    if not parsed:
        return
    verb, nonce = parsed
    if verb == "approve":
        await approve(app, nonce)
    else:
        reject(app, nonce)


# --- HTTP endpoints (used by the HIRIS "Approvazioni" page) ---
async def handle_list_pending(request: web.Request) -> web.Response:
    return web.json_response({"pending": list_pending(request.app.get("data_dir") or "/data")})


async def handle_approve_pending(request: web.Request) -> web.Response:
    nonce = request.match_info.get("nonce", "")
    return web.json_response(await approve(request.app, nonce))


async def handle_reject_pending(request: web.Request) -> web.Response:
    nonce = request.match_info.get("nonce", "")
    return web.json_response(reject(request.app, nonce))


async def execute_pending(app: web.Application, entry: dict) -> object:
    """Dispatch a previously-held command. The approval authorises exactly this
    command, so it runs with a whitelist scoped to its own action."""
    dispatcher = app.get("tool_dispatcher")
    if dispatcher is None:
        return {"error": "dispatcher unavailable"}
    inputs = entry.get("inputs", {})
    # Scope the whitelist to the approved action's own domain/entity so approval
    # can only run THIS command, nothing wider.
    domain = inputs.get("domain")
    allowed_services = [f"{domain}.*"] if domain else None
    return await dispatcher.dispatch(
        entry["tool"], inputs,
        allowed_services=allowed_services, allowed_entities=None,
        agent_id=entry.get("origin", "mcp-gateway"), cloud=True,
    )
