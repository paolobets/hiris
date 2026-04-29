# hiris/app/api/handlers_agents.py
import re
from dataclasses import asdict
from aiohttp import web
from ..config import EUR_RATE as _EUR_RATE

_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_VALID_AGENT_TYPES = frozenset({"chat", "agent", "monitor", "reactive", "preventive"})
_VALID_TRIGGER_TYPES = frozenset({"schedule", "state_changed", "manual", "cron", "preventive"})
_VALID_ACTION_MODES = frozenset({"automatic", "configured"})


def _check_agent_id(agent_id: str) -> web.Response | None:
    if not _AGENT_ID_RE.match(agent_id):
        return web.json_response({"error": "invalid agent_id"}, status=400)
    return None


def _validate_agent_payload(body: dict) -> str | None:
    """Return an error message string if the payload is invalid, else None."""
    name = body.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            return "name must be a non-empty string"
        if len(name) > 256:
            return "name too long (max 256 chars)"

    agent_type = body.get("type")
    if agent_type is not None and agent_type not in _VALID_AGENT_TYPES:
        return f"type must be one of {sorted(_VALID_AGENT_TYPES)}"

    # Legacy single-trigger (still accepted; engine migrates it to triggers list)
    trigger = body.get("trigger")
    if trigger is not None:
        if not isinstance(trigger, dict):
            return "trigger must be an object"
        if "type" not in trigger:
            return "trigger.type is required"

    # New-style triggers list
    triggers = body.get("triggers")
    if triggers is not None:
        if not isinstance(triggers, list):
            return "triggers must be a list"
        for i, t in enumerate(triggers):
            if not isinstance(t, dict):
                return f"triggers[{i}] must be an object"
            if "type" not in t:
                return f"triggers[{i}].type is required"
            if t["type"] not in _VALID_TRIGGER_TYPES:
                return f"triggers[{i}].type must be one of {sorted(_VALID_TRIGGER_TYPES)}"

    action_mode = body.get("action_mode")
    if action_mode is not None and action_mode not in _VALID_ACTION_MODES:
        return f"action_mode must be one of {sorted(_VALID_ACTION_MODES)}"

    rules = body.get("rules")
    if rules is not None:
        if not isinstance(rules, list):
            return "rules must be a list"
        for i, r in enumerate(rules):
            if not isinstance(r, dict):
                return f"rules[{i}] must be an object"
            if "states" not in r or "actions" not in r:
                return f"rules[{i}] must have 'states' and 'actions' fields"
            if not isinstance(r["states"], list):
                return f"rules[{i}].states must be a list"
            if not isinstance(r["actions"], list):
                return f"rules[{i}].actions must be a list"

    budget = body.get("budget_eur_limit")
    if budget is not None:
        try:
            if float(budget) < 0:
                return "budget_eur_limit must be >= 0"
        except (TypeError, ValueError):
            return "budget_eur_limit must be a number"

    for list_field in ("allowed_tools", "allowed_entities", "allowed_services"):
        val = body.get(list_field)
        if val is not None and not isinstance(val, list):
            return f"{list_field} must be a list"

    response_mode = body.get("response_mode")
    if response_mode is not None and response_mode not in ("auto", "compact", "minimal"):
        return "response_mode must be one of: auto, compact, minimal"

    states = body.get("states")
    if states is not None:
        if not isinstance(states, list) or not states:
            return "states must be a non-empty list of strings"
        if not all(isinstance(s, str) and s.strip() for s in states):
            return "states must be a list of non-empty strings"

    return None


async def handle_list_agents(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    result = []
    for agent_id, agent_data in engine.list_agents().items():
        entry = dict(agent_data)
        entry["status"] = engine.get_agent_status(agent_id)
        budget_eur = 0.0
        if runner:
            try:
                usage = runner.get_agent_usage(agent_id)
                cost_usd = usage.get("cost_usd", 0.0)
                budget_eur = round(float(cost_usd) * _EUR_RATE, 4)
            except Exception:
                budget_eur = 0.0
        entry["budget_eur"] = budget_eur
        entry["budget_limit_eur"] = float(entry.get("budget_eur_limit", 0.0))
        result.append(entry)
    return web.json_response(result)


async def handle_create_agent(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    required = {"name", "type"}
    missing = required - set(body.keys())
    if missing:
        return web.json_response({"error": f"Missing required fields: {missing}"}, status=400)

    if err := _validate_agent_payload(body):
        return web.json_response({"error": err}, status=400)

    engine = request.app["engine"]
    agent = engine.create_agent(body)
    return web.json_response(asdict(agent), status=201)


async def handle_get_agent(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_agent(agent_id)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(agent))


async def handle_update_agent(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    if err := _validate_agent_payload(body):
        return web.json_response({"error": err}, status=400)

    engine = request.app["engine"]
    agent = engine.update_agent(agent_id, body)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(agent))


async def handle_delete_agent(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_agent(agent_id)
    if agent is not None and agent.is_default:
        return web.json_response({"error": "Cannot delete default agent"}, status=409)
    deleted = engine.delete_agent(agent_id)
    if not deleted:
        return web.json_response({"error": "Not found"}, status=404)
    return web.Response(status=204)


async def handle_run_agent(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_agent(agent_id)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    result = await engine.run_agent(agent)
    return web.json_response({"result": result})


async def handle_list_entities(request: web.Request) -> web.Response:
    cache = request.app["entity_cache"]
    q = request.rel_url.query.get("q", "").lower().strip()
    _MAX_Q_LEN = 100
    if len(q) > _MAX_Q_LEN:
        return web.json_response({"error": "Query too long"}, status=400)
    entities = []
    for e in cache.get_all():
        domain = e["id"].split(".")[0]
        entities.append({
            "id": e["id"],
            "name": e.get("name", ""),
            "state": e.get("state", ""),
            "domain": domain,
        })
    if q:
        entities = [
            e for e in entities
            if q in e["id"].lower() or q in e["name"].lower() or q in e["domain"].lower()
        ]
    entities.sort(key=lambda e: e["id"])
    return web.json_response(entities)


async def handle_get_agent_usage(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    engine = request.app["engine"]
    if not engine.get_agent(agent_id):
        return web.json_response({"error": "Not found"}, status=404)
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    usage = runner.get_agent_usage(agent_id)
    cost_usd = usage.get("cost_usd", 0.0)
    return web.json_response({
        "agent_id": agent_id,
        "requests": usage.get("requests", 0),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_usd * _EUR_RATE, 6),
        "last_run": usage.get("last_run"),
    })


async def handle_reset_agent_usage(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    engine = request.app["engine"]
    if not engine.get_agent(agent_id):
        return web.json_response({"error": "Not found"}, status=404)
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    runner.reset_agent_usage(agent_id)
    return web.json_response({"reset": True, "agent_id": agent_id})


async def handle_context_preview(request: web.Request) -> web.Response:
    """Return SemanticContextMap output for this agent (empty-string query = all relevant entities)."""
    agent_id = request.match_info["agent_id"]
    if err := _check_agent_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_agent(agent_id)
    if agent is None:
        return web.json_response({"error": "Not found"}, status=404)

    context_map = request.app.get("context_map")
    entity_cache = request.app.get("entity_cache")
    if not context_map or not entity_cache:
        return web.json_response({"context_str": "", "entity_count": 0, "token_estimate": 0})

    allowed_entities = agent.allowed_entities or None
    ctx_str, visible_ids = context_map.get_context(
        query="",
        entity_cache=entity_cache,
        allowed_entities=allowed_entities,
        knowledge_db=request.app.get("knowledge_db"),
    )
    context_str = ctx_str.strip() if ctx_str else ""
    return web.json_response({
        "context_str": context_str,
        "entity_count": len(visible_ids),
        "token_estimate": len(context_str) // 4,
    })
