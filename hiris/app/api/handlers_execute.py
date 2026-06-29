"""Non-LLM execute-API: lets the MCP gateway drive curated HIRIS tools.

This endpoint is the *only* HIRIS change required by the MCP gateway. It is gated
by ``internal_token`` (LAN-only secret), exposes a server-side allowlist of tools,
and re-applies the per-tool entity/service whitelists before dispatching. HIRIS
remains the single source of safety: the gateway can never widen these privileges.
"""
from __future__ import annotations

import hmac
import logging
import re

from aiohttp import web

logger = logging.getLogger(__name__)

# Hard server-side ceiling: tools the execute-API may EVER dispatch, regardless
# of what the env CSV or the saved policy lists. Prevents a misconfigured
# EXECUTE_API_TOOLS from exposing unconstrained tools (http_request, set_input_helper, …).
from .handlers_gateway_policy import READ_TOOLS as _RT, PROPOSE_TOOLS as _PT
_HARD_EXECUTE_ALLOWED = frozenset(_RT) | frozenset(_PT) | {"call_ha_service", "create_task"}

# Provenance tag is client-supplied (the gateway); validate strictly before it
# is stored on tasks/audit. Default to "mcp-gateway" when missing/invalid.
_ORIGIN_RE = re.compile(r"^[A-Za-z0-9_:.\-]{1,64}$")


def _origin(body: dict) -> str:
    o = body.get("origin")
    if isinstance(o, str) and _ORIGIN_RE.match(o):
        return o
    return "mcp-gateway"


def _target_entities(inputs: dict) -> list[str]:
    data = inputs.get("data") if isinstance(inputs.get("data"), dict) else {}
    target = inputs.get("target") if isinstance(inputs.get("target"), dict) else {}
    raw = (data.get("entity_id") if isinstance(data, dict) else None) or target.get("entity_id")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, str)]
    return []


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def parse_execute_policy(tools: str, entities: str, services: str) -> dict:
    """Build the server-side execute-API policy from raw config strings.

    - tools: CSV allowlist of tool names this API may dispatch (empty => none,
      i.e. fail-closed — nothing is exposed unless explicitly listed).
    - entities / services: CSV glob whitelists handed to the dispatcher
      (empty => None, i.e. the dispatcher applies no extra entity/service filter
      beyond the tool's own checks; set them to constrain the gateway tightly).
    """
    ent = _csv(entities)
    svc = _csv(services)
    return {
        "tools": _csv(tools),
        "allowed_entities": ent or None,
        "allowed_services": svc or None,
    }


def _check_token(request: web.Request) -> bool:
    """Independent token check for /api/execute (defense-in-depth).

    Uses the same X-HIRIS-Internal-Token header as the rest of HIRIS so a single
    credential works through the global middleware and here. This handler-level
    check is deliberately independent of the X-Ingress-Path branch: even if a
    forged ingress header slipped past the global middleware, /api/execute still
    requires the internal_token.
    """
    expected = request.app.get("internal_token") or ""
    if not expected:                       # fail closed when unset
        return False
    presented = request.headers.get("X-HIRIS-Internal-Token", "")
    if not presented:
        return False
    return hmac.compare_digest(presented, expected)


async def handle_execute(request: web.Request) -> web.Response:
    if not _check_token(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    dispatcher = request.app.get("tool_dispatcher")
    if dispatcher is None:
        return web.json_response({"error": "dispatcher unavailable"}, status=503)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)

    tool = body.get("tool")
    inputs = body.get("input", {})
    if not isinstance(tool, str) or not tool:
        return web.json_response({"error": "tool required"}, status=400)
    if not isinstance(inputs, dict):
        return web.json_response({"error": "input must be an object"}, status=400)

    if tool not in _HARD_EXECUTE_ALLOWED:
        logger.warning("execute-API hard-rejected tool %r (outside server allowlist)", tool)
        return web.json_response({"error": f"tool {tool!r} not permitted by execute-API"}, status=403)

    policy = request.app.get("execute_policy") or {"tools": []}
    if tool not in policy.get("tools", []):
        logger.warning("execute-API rejected tool %r (not in allowlist)", tool)
        return web.json_response(
            {"error": f"tool {tool!r} not exposed by execute-API policy"}, status=403
        )

    # Tier routing for actions: green executes directly; yellow/red are held for
    # approval (notification) and not dispatched here. Per-entity overrides beat
    # the domain level (off entity inside green domain is BLOCKED, never dispatched).
    if tool == "call_ha_service":
        from .handlers_gateway_policy import effective_tier
        domain = inputs.get("domain")
        tiers = policy.get("tiers") or {}
        entity_tiers = policy.get("entity_tiers") or {}
        targets = _target_entities(inputs)
        if targets:
            levels = [effective_tier(e, tiers, entity_tiers) for e in targets]
            if any(lv == "off" for lv in levels):
                return web.json_response(
                    {"result": {"error": "Entità bloccata dal semaforo (off)."}})
            tier = "red" if "red" in levels else ("yellow" if "yellow" in levels else None)
        else:
            dom_tier = tiers.get(domain, "off")
            tier = dom_tier if dom_tier in ("yellow", "red") else None
        if tier in ("yellow", "red"):
            from .handlers_gateway_pending import create_pending, notify
            label = f"{domain}.{inputs.get('service', '')}"
            entry = create_pending(
                request.app.get("data_dir") or "/data",
                tool=tool, inputs=inputs, tier=tier, origin=_origin(body), label=label,
            )
            msg = (f"Claude chiede: {label}. "
                   + ("Approva o nega dalla notifica." if tier == "yellow"
                      else "Conferma manualmente in HIRIS (Approvazioni)."))
            await notify(request.app, message=msg,
                         actionable=(tier == "yellow"), nonce=entry["id"])
            return web.json_response({"result": {
                "status": "pending_approval", "id": entry["id"], "tier": tier,
                "message": ("Azione in attesa di approvazione"
                            + (" — notifica inviata." if tier == "yellow"
                               else " manuale in HIRIS.")),
            }})

    # Reads are non-destructive and must NOT be constrained by the action
    # whitelist (allowed_entities/allowed_services are derived from the *green
    # action domains*; applying them to reads hides every entity outside those
    # domains — e.g. all sensors/temperatures — once any category is enabled).
    # Only mutating tools carry the whitelist; reads see the whole home.
    from .handlers_gateway_policy import READ_TOOLS
    is_read = tool in READ_TOOLS
    result = await dispatcher.dispatch(
        tool,
        inputs,
        allowed_entities=None if is_read else policy.get("allowed_entities"),
        allowed_services=None if is_read else policy.get("allowed_services"),
        agent_id=_origin(body),
        cloud=True,
    )
    return web.json_response({"result": result})
