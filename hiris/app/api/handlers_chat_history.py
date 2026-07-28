import logging
import re
from aiohttp import web
from ..chat_store import load_history, clear_history

logger = logging.getLogger(__name__)

_CHATBOT_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def _validate_chatbot_id(chatbot_id: str) -> bool:
    return bool(_CHATBOT_ID_RE.match(chatbot_id))


async def handle_get_chat_history(request: web.Request) -> web.Response:
    # Route placeholder is still named {agent_id} (server.py) -- out of this
    # task's scope, unchanged. Only the internal identifier is renamed here.
    chatbot_id = request.match_info["agent_id"]
    if not _validate_chatbot_id(chatbot_id):
        return web.json_response({"error": "invalid agent_id"}, status=400)
    data_dir = request.app["data_dir"]
    messages = load_history(chatbot_id, data_dir)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    chatbot_id = request.match_info["agent_id"]
    if not _validate_chatbot_id(chatbot_id):
        return web.json_response({"error": "invalid agent_id"}, status=400)
    data_dir = request.app["data_dir"]
    clear_history(chatbot_id, data_dir)
    return web.json_response({"ok": True})
