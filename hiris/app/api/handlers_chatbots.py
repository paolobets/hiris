# hiris/app/api/handlers_chatbots.py
import logging
import re
from dataclasses import asdict
from aiohttp import web
from ..config import EUR_RATE as _EUR_RATE

logger = logging.getLogger(__name__)

_CHATBOT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _check_chatbot_id(agent_id: str) -> web.Response | None:
    if not _CHATBOT_ID_RE.match(agent_id):
        return web.json_response({"error": "invalid agent_id"}, status=400)
    return None


def _validate_chatbot_payload(body: dict) -> str | None:
    """Return an error message string if the payload is invalid, else None."""
    name = body.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            return "name must be a non-empty string"
        if len(name) > 256:
            return "name too long (max 256 chars)"

    for list_field in ("allowed_tools", "allowed_entities", "allowed_services"):
        val = body.get(list_field)
        if val is not None and not isinstance(val, list):
            return f"{list_field} must be a list"

    response_mode = body.get("response_mode")
    if response_mode is not None and response_mode not in ("auto", "compact", "minimal"):
        return "response_mode must be one of: auto, compact, minimal"

    # Extended Thinking budget. 0 disables; otherwise Anthropic requires
    # 1024 ≤ budget < max_tokens. We enforce the lower bound and the
    # cross-field upper bound here so the runner can pass it through cleanly.
    tb = body.get("thinking_budget")
    if tb is not None:
        try:
            tb_int = int(tb)
        except (TypeError, ValueError):
            return "thinking_budget must be an integer"
        if tb_int < 0:
            return "thinking_budget must be >= 0"
        if 0 < tb_int < 1024:
            return "thinking_budget must be 0 (disabled) or >= 1024"
        max_t = body.get("max_tokens")
        if max_t is not None:
            try:
                if tb_int >= int(max_t):
                    return "thinking_budget must be < max_tokens"
            except (TypeError, ValueError):
                pass

    allowed_endpoints = body.get("allowed_endpoints")
    if allowed_endpoints is not None:
        if not isinstance(allowed_endpoints, list):
            return "allowed_endpoints must be a list"
        for i, ep in enumerate(allowed_endpoints):
            if not isinstance(ep, dict):
                return f"allowed_endpoints[{i}] must be an object"
            url = ep.get("url")
            if not isinstance(url, str) or not url.startswith("http"):
                return f"allowed_endpoints[{i}].url must be a string starting with 'http'"

    return None


async def handle_list_chatbots(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    result = []
    for agent_id, agent_data in engine.list_chatbots().items():
        entry = dict(agent_data)
        entry["status"] = engine.get_chatbot_status(agent_id)
        budget_eur = 0.0
        usage_payload: dict = {}
        if runner:
            try:
                usage = runner.get_agent_usage(agent_id) or {}
                cost_usd = usage.get("cost_usd", 0.0)
                budget_eur = round(float(cost_usd) * _EUR_RATE, 4)
                usage_payload = {
                    "requests": int(usage.get("requests", 0)),
                    "input_tokens": int(usage.get("input_tokens", 0)),
                    "output_tokens": int(usage.get("output_tokens", 0)),
                    "cost_eur": budget_eur,
                    "last_run": usage.get("last_run"),
                }
            except Exception as exc:
                logger.warning("get_agent_usage(%s) failed: %s", agent_id, exc)
                budget_eur = 0.0
        entry["budget_eur"] = budget_eur
        entry["usage"] = usage_payload
        result.append(entry)
    return web.json_response(result)


async def _validate_openrouter_model(request: web.Request, body: dict) -> str | None:
    """Reject save when the agent's model is an OpenRouter id that does not
    advertise tool support (e.g. the broken hermes-3-llama-3.1-405b:free).
    Returns an error message string, or None if the model is OK / not OpenRouter.
    """
    model = body.get("model")
    if not isinstance(model, str):
        return None
    if not (model.startswith("openrouter:") or model.startswith("openrouter/")):
        return None
    api_key = request.app.get("openrouter_api_key", "")
    from .handlers_models import is_openrouter_model_tool_capable
    capable = await is_openrouter_model_tool_capable(model, api_key)
    if capable is False:
        return (
            f"Modello OpenRouter '{model}' non supporta i tool: HIRIS richiede "
            "tool use per ogni agente. Scegli un altro modello (Claude, GPT-4o, "
            "Mistral Large, Llama 3.3 70B free, Qwen 2.5 72B free, …)."
        )
    return None


async def handle_create_chatbot(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    required = {"name"}
    missing = required - set(body.keys())
    if missing:
        return web.json_response({"error": f"Missing required fields: {missing}"}, status=400)

    if err := _validate_chatbot_payload(body):
        return web.json_response({"error": err}, status=400)

    if err := await _validate_openrouter_model(request, body):
        return web.json_response({"error": err}, status=400)

    engine = request.app["engine"]
    agent = engine.create_chatbot(body)
    return web.json_response(asdict(agent), status=201)


async def handle_get_chatbot(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_chatbot(agent_id)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(agent))


async def handle_update_chatbot(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    if err := _validate_chatbot_payload(body):
        return web.json_response({"error": err}, status=400)

    if err := await _validate_openrouter_model(request, body):
        return web.json_response({"error": err}, status=400)

    engine = request.app["engine"]
    agent = engine.update_chatbot(agent_id, body)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(agent))


async def handle_delete_chatbot(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_chatbot(agent_id)
    if agent is not None and agent.is_default:
        return web.json_response({"error": "Cannot delete default agent"}, status=409)
    deleted = engine.delete_chatbot(agent_id)
    if not deleted:
        return web.json_response({"error": "Not found"}, status=404)
    # Clean up orphaned data: long-term memories (chatbot_id-scoped
    # KnowledgeStore rows, Slice 3) and persisted chat history.
    knowledge_store = request.app.get("knowledge_store")
    if knowledge_store is not None:
        try:
            knowledge_store.delete_by_chatbot(agent_id)
        except Exception as exc:
            logger.warning("knowledge_store.delete_by_chatbot(%s) failed: %s", agent_id, exc)
    data_dir = request.app.get("data_dir")
    if data_dir:
        try:
            from ..chat_store import clear_history
            clear_history(agent_id, data_dir)
        except Exception as exc:
            logger.warning("clear_history(%s) failed: %s", agent_id, exc)
    return web.Response(status=204)


async def handle_run_chatbot(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_chatbot(agent_id)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    result = await engine.run_chatbot(agent)
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


async def handle_get_chatbot_usage(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    engine = request.app["engine"]
    if not engine.get_chatbot(agent_id):
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


async def handle_reset_chatbot_usage(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    engine = request.app["engine"]
    if not engine.get_chatbot(agent_id):
        return web.json_response({"error": "Not found"}, status=404)
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    runner.reset_agent_usage(agent_id)
    return web.json_response({"reset": True, "agent_id": agent_id})


async def handle_context_preview(request: web.Request) -> web.Response:
    """Return SemanticContextMap output for this agent (empty-string query = all relevant entities)."""
    agent_id = request.match_info["agent_id"]
    if err := _check_chatbot_id(agent_id):
        return err
    engine = request.app["engine"]
    agent = engine.get_chatbot(agent_id)
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
