from aiohttp import web


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

    history = body.get("history", [])
    agent_id = body.get("agent_id")
    engine = request.app["engine"]

    agent = None
    if agent_id:
        agent = engine.get_agent(agent_id)
    if agent is None:
        agent = engine.get_default_agent()

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
        system_prompt = "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
        allowed_tools = None
        allowed_entities = None
        allowed_services = None

    response = await runner.chat(
        user_message=message,
        system_prompt=system_prompt,
        conversation_history=history,
        allowed_tools=allowed_tools,
        allowed_entities=allowed_entities,
        allowed_services=allowed_services,
    )
    return web.json_response({"response": response})
