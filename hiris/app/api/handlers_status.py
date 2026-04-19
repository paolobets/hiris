# hiris/app/api/handlers_status.py
from aiohttp import web


async def handle_status(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    agents = engine.list_agents()
    return web.json_response({
        "version": "0.0.6",
        "agents": {
            "total": len(agents),
            "enabled": sum(1 for a in agents.values() if a["enabled"]),
        },
    })
