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

    runner = request.app.get("claude_runner")
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

    agent_model = getattr(agent, "model", "auto") if agent else "auto"
    agent_max_tokens = getattr(agent, "max_tokens", 4096) if agent else 4096
    agent_type = getattr(agent, "type", "chat") if agent else "chat"
    agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False
    agent_require_confirmation = getattr(agent, "require_confirmation", False) if agent else False

    response = await runner.chat(
        user_message=message,
        system_prompt=system_prompt,
        conversation_history=history,
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
