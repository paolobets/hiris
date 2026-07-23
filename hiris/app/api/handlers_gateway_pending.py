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

import hmac
import json
import logging
import os
import secrets
import time

from aiohttp import web

logger = logging.getLogger(__name__)

PENDING_TTL_S = 300                    # a pending command expires after 5 minutes
_ACTION_PREFIX = "HIRIS_GW"           # mobile_app notification action namespace
MAX_OTP_ATTEMPTS = 3                   # lockout threshold for chat step-up OTP


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
                   origin: str, label: str, user: str | None = None,
                   with_otp: bool = False) -> dict:
    """Create and persist a pending command; returns the new entry.

    ``user`` and ``with_otp`` are optional and keyword-only so existing
    gateway callers (which never pass them) keep working unchanged. When
    ``with_otp`` is set, a single-use 6-digit OTP is attached for the chat
    step-up flow (see ``verify_otp``); it reuses the same ``expires`` TTL.
    """
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
        "user": user,
    }
    if with_otp:
        entry["otp"] = f"{secrets.randbelow(1000000):06d}"
        entry["otp_attempts"] = 0
    data[nonce] = entry
    _save(data_dir, data)
    return entry


def list_pending(data_dir: str) -> list[dict]:
    """Return sanitized copies of pending entries (never the raw store).

    Security: this feeds ``GET /api/gateway/pending``, which is reachable
    with the same ``X-HIRIS-Internal-Token`` the MCP gateway (Claude) holds.
    The OTP is a step-up secret meant to prove a *human* typed it in chat —
    if it leaked back out over this endpoint, the very principal being
    checked could read it. So ``otp``/``otp_attempts`` are stripped from the
    copies handed out here; the stored entries themselves are untouched.
    """
    now = time.time()
    data = _load(data_dir)
    out = [{k: v for k, v in entry.items() if k not in ("otp", "otp_attempts")}
           for entry in data.values()
           if entry.get("status") == "pending" and entry.get("expires", 0) > now]
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


def verify_otp(data_dir: str, user: str, code: str) -> dict | None:
    """Validate an OTP typed in chat (step-up confirmation).

    Single-use, scoped to the same ``user`` who owns the pending, with a
    lockout after ``MAX_OTP_ATTEMPTS`` mismatches (the pending is then
    invalidated: status -> "rejected"). On match the pending is consumed
    exactly like ``take_pending`` and a sanitized copy of the entry (with
    ``otp``/``otp_attempts`` stripped, so the code never travels further
    downstream than this check) is returned; otherwise returns None (wrong
    user, no OTP, expired, or mismatch).
    """
    now = time.time()
    data = _load(data_dir)
    for entry in data.values():
        if (entry.get("status") == "pending" and entry.get("user") == user
                and entry.get("otp") and entry.get("expires", 0) > now):
            if hmac.compare_digest(str(code).encode(), str(entry["otp"]).encode()):
                entry["status"] = "consumed"
                _save(data_dir, data)
                return {k: v for k, v in entry.items()
                        if k not in ("otp", "otp_attempts")}
            entry["otp_attempts"] = int(entry.get("otp_attempts", 0)) + 1
            if entry["otp_attempts"] >= MAX_OTP_ATTEMPTS:
                entry["status"] = "rejected"
            _save(data_dir, data)
            return None
    return None


def resolve_pending(data_dir: str, nonce: str, status: str) -> None:
    data = _load(data_dir)
    if nonce in data:
        data[nonce]["status"] = status
        _save(data_dir, data)


def invalidate_user_otp_pendings(data_dir: str, user: str | None) -> None:
    """Reject any still-live chat-OTP pending belonging to ``user``.

    Called right before issuing a new one (see ``create_pending(...,
    with_otp=True)`` call sites) so at most ONE OTP pending exists per user
    at a time. ``verify_otp`` resolves a typed code by scanning for the
    first pending entry matching ``user`` that carries an ``otp`` — with two
    live OTP pendings for the same user, that scan could match the wrong one
    (e.g. reject a code meant for a different, still-open confirmation, or
    worse, confirm a stale action). Keeping the invariant at creation time
    avoids that ambiguity entirely.
    """
    if not user:
        return
    now = time.time()
    data = _load(data_dir)
    changed = False
    for entry in data.values():
        if (entry.get("status") == "pending" and entry.get("user") == user
                and entry.get("otp") and entry.get("expires", 0) > now):
            entry["status"] = "rejected"
            changed = True
    if changed:
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


async def notify(app: web.Application, *, message: str, actionable: bool, nonce: str,
                 service: str | None = None) -> bool:
    """Send a notification via the configured notify service (default
    notify.iphone_bet). Actionable (yellow) adds Approva/Nega buttons.

    ``service`` is optional and keyword-only: when passed (e.g. resolved via
    ``notify_service_for_user`` for the chatting user), it is used verbatim
    instead of the global ``gateway_settings.notify_service`` — existing
    callers that omit it keep the previous behaviour unchanged.

    Returns ``True`` iff ``ha.call_service`` actually completed, ``False`` on
    any failure (no ``ha_client``, invalid ``service`` string, or an
    exception from the call). Callers that need to know whether the push
    really reached HA (e.g. the chat step-up flow's ``otp_sent`` flag) can
    rely on this; callers that don't care may keep ignoring the return
    value, as before."""
    ha = app.get("ha_client")
    if ha is None:
        logger.warning("no ha_client — cannot send approval notification")
        return False
    service = (service or (app.get("gateway_settings") or {}).get("notify_service")
               or "notify.iphone_bet").strip()
    if "." not in service:
        logger.error("invalid notify service %r", service)
        return False
    domain, svc = service.split(".", 1)
    data: dict = {"message": message, "title": "HIRIS · richiesta da Claude"}
    if actionable:
        data["data"] = {"actions": build_actions(nonce), "tag": f"hiris-gw-{nonce}"}
    try:
        await ha.call_service(domain, svc, data)
        return True
    except Exception as exc:
        logger.error("approval notification failed: %s", exc)
        return False


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
        tier_confirmed=True,
    )
