from aiohttp import web


async def handle_config(request: web.Request) -> web.Response:
    return web.json_response({"theme": request.app.get("theme", "auto")})
