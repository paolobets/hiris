import logging

from aiohttp import web

from ..chat_store import load_history, append_messages

logger = logging.getLogger(__name__)


async def handle_chat(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)
    if len(message) > 4000:
        return web.json_response({"error": "message too long (max 4000 chars)"}, status=413)

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
        allowed_tools = agent.allowed_tools or None
        allowed_entities = agent.allowed_entities or None
        allowed_services = agent.allowed_services or None
    else:
        logger.warning("No agent found (requested: %s). BASE_SYSTEM_PROMPT will be used.", agent_id)
        allowed_tools = None
        allowed_entities = None
        allowed_services = None

    # Assemble agent-specific prompt parts in order; BASE_SYSTEM_PROMPT is
    # prepended by claude_runner.py at runtime so it is not included here.
    prompt_parts = []
    if agent and agent.strategic_context:
        prompt_parts.append(agent.strategic_context.strip())
    if agent and agent.system_prompt:
        prompt_parts.append(agent.system_prompt.strip())

    context_map = request.app.get("context_map")
    entity_cache = request.app.get("entity_cache")
    knowledge_db = request.app.get("knowledge_db")
    visible_ids: frozenset[str] = frozenset()
    if context_map and entity_cache:
        ctx_str, visible_ids = context_map.get_context(
            query=message,
            entity_cache=entity_cache,
            allowed_entities=allowed_entities,
            knowledge_db=knowledge_db,
        )
        if ctx_str:
            prompt_parts.append(ctx_str.strip())

    system_prompt = "\n\n---\n\n".join(prompt_parts)

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
        visible_entity_ids=visible_ids,
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
