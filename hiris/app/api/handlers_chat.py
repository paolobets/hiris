# hiris/app/api/handlers_chat.py
from aiohttp import web


async def handle_chat(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)

    history = body.get("history", [])
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "Claude runner not configured — set CLAUDE_API_KEY"}, status=503)

    response = await runner.chat(
        user_message=message,
        conversation_history=history,
    )
    return web.json_response({"response": response})
