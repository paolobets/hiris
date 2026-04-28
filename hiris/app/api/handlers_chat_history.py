import logging
import re
from aiohttp import web
from ..chat_store import load_history, clear_history

logger = logging.getLogger(__name__)

_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def _validate_agent_id(agent_id: str) -> bool:
    return bool(_AGENT_ID_RE.match(agent_id))


async def handle_get_chat_history(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if not _validate_agent_id(agent_id):
        return web.json_response({"error": "invalid agent_id"}, status=400)
    data_dir = request.app["data_dir"]
    messages = load_history(agent_id, data_dir)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if not _validate_agent_id(agent_id):
        return web.json_response({"error": "invalid agent_id"}, status=400)
    data_dir = request.app["data_dir"]
    clear_history(agent_id, data_dir)
    return web.json_response({"ok": True})
