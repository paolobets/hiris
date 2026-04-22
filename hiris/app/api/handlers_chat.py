import logging
import re

from aiohttp import web

from ..chat_store import load_history, append_messages

logger = logging.getLogger(__name__)

_RAG_TOP_K = 12  # entities to pre-fetch per request
_CTRL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def _sanitize(value: str, max_len: int = 128) -> str:
    return _CTRL_RE.sub('', str(value))[:max_len]


def _prefetch_context(message: str, app: web.Application) -> str:
    """Semantic search → fetch current states → return compact context block."""
    idx = app.get("embedding_index")
    cache = app.get("entity_cache")
    if not idx or not cache or not idx.ready:
        return ""
    ids = idx.search(message, top_k=_RAG_TOP_K)
    if not ids:
        return ""
    entities = cache.get_minimal(ids)
    if not entities:
        return ""
    lines = []
    for e in entities:
        name = _sanitize(e.get("name") or e["id"])
        state = _sanitize(e["state"])
        seg = f"- {name} [{e['id']}]: {state}"
        if e.get("unit"):
            seg += f" {_sanitize(e['unit'], 16)}"
        a = e.get("attributes") or {}
        curr = a.get("current_temperature")
        setp = a.get("temperature")
        action = a.get("hvac_action")
        if curr is not None:
            seg += f", corrente {curr}°C"
        if setp is not None:
            seg += f" → setpoint {setp}°C"
        if action:
            seg += f" ({_sanitize(action, 32)})"
        lines.append(seg)
    return "Entità rilevanti (dati in tempo reale):\n" + "\n".join(lines)


async def handle_chat(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)

    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response(
            {"error": "Claude runner not configured — set CLAUDE_API_KEY"}, status=503
        )

    agent_id = body.get("agent_id")
    data_dir = request.app.get("data_dir", "/data")
    engine = request.app["engine"]

    agent = None
    if agent_id:
        agent = engine.get_agent(agent_id)
    if agent is None:
        agent = engine.get_default_agent()

    effective_agent_id = getattr(agent, "id", None) if agent else None

    # Load server-side history (client-sent history field is ignored)
    history = load_history(effective_agent_id, data_dir) if effective_agent_id else []

    # Enforce max turns limit
    max_turns = getattr(agent, "max_chat_turns", 0) if agent else 0
    if max_turns > 0:
        turn_count = sum(1 for m in history if m["role"] == "user")
        if turn_count >= max_turns:
            return web.json_response({
                "error": "max_turns_reached",
                "turns": turn_count,
                "limit": max_turns,
            })

    # Send only the most recent messages to Claude to avoid stale-context issues
    # and keep token usage bounded. Full history is still persisted and counted.
    _MAX_CONTEXT = 30
    context_history = history[-_MAX_CONTEXT:] if len(history) > _MAX_CONTEXT else history

    if agent:
        if agent.strategic_context:
            system_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
        else:
            system_prompt = agent.system_prompt or (
                "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
            )
        allowed_tools = agent.allowed_tools or None
        allowed_entities = agent.allowed_entities or None
        allowed_services = agent.allowed_services or None
    else:
        logger.warning("No agent found (requested: %s). Using fallback prompt.", agent_id)
        system_prompt = "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
        allowed_tools = None
        allowed_entities = None
        allowed_services = None

    # Inject semantic map snippet (replaces home_profile — richer context)
    semantic_map = request.app.get("semantic_map")
    entity_cache = request.app.get("entity_cache")
    if semantic_map and entity_cache:
        map_snippet = semantic_map.get_prompt_snippet(entity_cache)
        if map_snippet:
            system_prompt = f"{system_prompt}\n\n---\n\n{map_snippet}"

    # RAG pre-fetch: inject relevant entity states before Claude reasons
    prefetched = _prefetch_context(message, request.app)
    if prefetched:
        system_prompt = f"{system_prompt}\n\n---\n\n{prefetched}"

    agent_model = getattr(agent, "model", "auto") if agent else "auto"
    agent_max_tokens = getattr(agent, "max_tokens", 4096) if agent else 4096
    agent_type = getattr(agent, "type", "chat") if agent else "chat"
    agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False
    agent_require_confirmation = getattr(agent, "require_confirmation", False) if agent else False

    response = await runner.chat(
        user_message=message,
        system_prompt=system_prompt,
        conversation_history=context_history,
        allowed_tools=allowed_tools,
        allowed_entities=allowed_entities,
        allowed_services=allowed_services,
        model=agent_model,
        max_tokens=agent_max_tokens,
        agent_type=agent_type,
        restrict_to_home=agent_restrict,
        require_confirmation=agent_require_confirmation,
        agent_id=effective_agent_id,
    )

    # Persist the new user+assistant exchange
    if effective_agent_id:
        append_messages(effective_agent_id, [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ], data_dir)

    raw = getattr(runner, "last_tool_calls", None)
    tools_called = raw if isinstance(raw, list) else []
    return web.json_response({"response": response, "debug": {"tools_called": tools_called}})
