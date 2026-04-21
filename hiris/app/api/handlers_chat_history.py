import logging
from aiohttp import web
from ..chat_store import load_history, clear_history

logger = logging.getLogger(__name__)


async def handle_get_chat_history(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    data_dir = request.app["data_dir"]
    messages = load_history(agent_id, data_dir)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    data_dir = request.app["data_dir"]
    clear_history(agent_id, data_dir)
    return web.json_response({"ok": True})
