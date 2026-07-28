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
from ..security.semaphore import normalize_target
_HARD_EXECUTE_ALLOWED = frozenset(_RT) | frozenset(_PT) | {"call_ha_service", "create_task", "send_notification"}

# Tools always exposed regardless of the saved EXECUTE_API_TOOLS policy. Notifications
# are informational — they never actuate a device — so per the "notifiche sempre
# permesse" decision the gateway can always reach the user without extra config.
# (Still bounded by _HARD_EXECUTE_ALLOWED and the internal_token.)
_ALWAYS_EXPOSED = frozenset({"send_notification"})

# Provenance tag is client-supplied (the gateway); validate strictly before it
# is stored on tasks/audit. Default to "mcp-gateway" when missing/invalid.
_ORIGIN_RE = re.compile(r"^[A-Za-z0-9_:.\-]{1,64}$")


def _origin(body: dict) -> str:
    o = body.get("origin")
    if isinstance(o, str) and _ORIGIN_RE.match(o):
        return o
    return "mcp-gateway"


def _target_entities(inputs: dict) -> list[str]:
    # Delegate to the shared normalizer so the tiers PRE-SCREENED here are the
    # UNION of data+target entity_ids -- the exact set the dispatcher executes
    # after confirmation (review A/#5 C1). First-wins here would let a smuggled
    # `target` entity ride an approval evaluated only on the `data` entity.
    return normalize_target(inputs.get("data"), inputs.get("target")).entity_ids


def _has_group_target(inputs: dict) -> bool:
    """True if data/target carries area_id/device_id/label_id/floor_id.

    A group target is never resolvable to a per-entity tier: HA actuates the
    whole area/device/label/floor server-side, bypassing per-entity overrides
    even when an explicit (green) entity_id rides along. Fail-closed regardless
    of accompanying entity_ids. Delegated to normalize_target so the key set
    stays in one place (review A/#5 I2/M3).
    """
    return normalize_target(inputs.get("data"), inputs.get("target")).has_group_target


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
    if tool not in _ALWAYS_EXPOSED and tool not in policy.get("tools", []):
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
        if _has_group_target(inputs):
            logger.warning("execute-API gated: area/device/label target present (%s.%s)",
                          domain, inputs.get("service"))
            return web.json_response({"result": {"ok": False, "error":
                "Azione su area/dispositivo/label non consentita: specifica le entità target."}})
        targets = _target_entities(inputs)
        if targets:
            levels = [effective_tier(e, tiers, entity_tiers) for e in targets]
            if any(lv == "off" for lv in levels):
                return web.json_response(
                    {"result": {"ok": False, "error": "Entità bloccata dal semaforo (off)."}})
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

    # create_task is dispatched without per-fire approval, so any call_ha_service
    # action it schedules must target ONLY green-effective entities. off/yellow/red
    # (or a broadcast with no entity target) are rejected here — otherwise a task
    # would let the gateway bypass the per-entity semaforo at fire time.
    if tool == "create_task":
        from .handlers_gateway_policy import effective_tier
        tiers = policy.get("tiers") or {}
        entity_tiers = policy.get("entity_tiers") or {}
        for action in (inputs.get("actions") or []):
            if not isinstance(action, dict) or action.get("type") != "call_ha_service":
                continue
            if _has_group_target(action):
                return web.json_response({"result": {"ok": False, "error":
                    "Task rifiutato: azione call_ha_service con target area/dispositivo/label. "
                    "Specifica le entità esplicite (i task possono contenere solo azioni verdi "
                    "per-entità)."}})
            targets = _target_entities(action)
            if not targets:
                return web.json_response({"result": {"ok": False, "error":
                    "Task rifiutato: azione call_ha_service senza entity target esplicito. "
                    "Per inviare una notifica usa un'azione send_notification "
                    "(channel ha_persistent/ha_push), non call_ha_service."}})
            for e in targets:
                if effective_tier(e, tiers, entity_tiers) != "green":
                    return web.json_response({"result": {"ok": False, "error":
                        f"Task rifiutato: l'azione su {e!r} non e' verde nel semaforo "
                        "(i task possono contenere solo azioni verdi)."}})

    # create_ha_config from the gateway is NEVER executed directly. It is held as a
    # pending proposal the operator reviews+approves in HIRIS (spec: MCP = convalida).
    if tool == "create_ha_config":
        from ..tools.config_tools import normalize_config_inputs, build_config_proposal
        store = request.app.get("proposal_store")
        if store is None:
            return web.json_response({"error": "ProposalStore non disponibile"}, status=503)
        try:
            normalized = normalize_config_inputs(inputs)
        except ValueError as exc:
            return web.json_response({"result": {"ok": False, "error": str(exc)}})
        pid = await store.save(build_config_proposal(normalized))
        return web.json_response({"result": {
            "status": "pending_approval", "proposal_id": pid,
            "message": (f"Creazione '{normalized['name']}' in attesa di approvazione "
                        "dell'operatore in HIRIS (pagina Proposte)."),
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
        # dispatcher.dispatch's kwarg is chatbot_id (Task 6 rename) but the
        # VALUE here is a request-origin label ("mcp-gateway"/"unknown"), not
        # a Chatbot id -- intentionally frozen, see _origin().
        chatbot_id=_origin(body),
        cloud=True,
    )
    return web.json_response({"result": result})
