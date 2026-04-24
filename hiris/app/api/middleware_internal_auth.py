import logging
from aiohttp import web

logger = logging.getLogger(__name__)


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    if request.headers.get("X-Ingress-Path"):
        return await handler(request)
    token = request.app.get("internal_token", "")
    if token and request.headers.get("X-HIRIS-Internal-Token") != token:
        logger.warning("Unauthorized inter-addon request from %s", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)
