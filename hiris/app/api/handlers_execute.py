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

# Provenance tag is client-supplied (the gateway); validate strictly before it
# is stored on tasks/audit. Default to "mcp-gateway" when missing/invalid.
_ORIGIN_RE = re.compile(r"^[A-Za-z0-9_:.\-]{1,64}$")


def _origin(body: dict) -> str:
    o = body.get("origin")
    if isinstance(o, str) and _ORIGIN_RE.match(o):
        return o
    return "mcp-gateway"


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

    policy = request.app.get("execute_policy") or {"tools": []}
    if tool not in policy.get("tools", []):
        logger.warning("execute-API rejected tool %r (not in allowlist)", tool)
        return web.json_response(
            {"error": f"tool {tool!r} not exposed by execute-API policy"}, status=403
        )

    result = await dispatcher.dispatch(
        tool,
        inputs,
        allowed_entities=policy.get("allowed_entities"),
        allowed_services=policy.get("allowed_services"),
        agent_id=_origin(body),
        cloud=True,
    )
    return web.json_response({"result": result})
