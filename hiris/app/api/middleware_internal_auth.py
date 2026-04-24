import hmac
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    """Validate X-HIRIS-Internal-Token for non-Ingress requests.

    Requests via HA Supervisor Ingress (X-Ingress-Path present) always pass.
    When internal_token is empty, all requests pass (auth disabled).
    """
    # X-Ingress-Path is set by HA Supervisor's reverse proxy on all ingress traffic.
    # In the HA add-on threat model, this is a trusted signal: port 8099 is only
    # exposed externally via HA Ingress, and other add-ons communicating via Docker
    # internal network would use X-HIRIS-Internal-Token instead.
    if request.headers.get("X-Ingress-Path"):
        return await handler(request)
    token = request.app.get("internal_token", "")
    if token and not hmac.compare_digest(
        request.headers.get("X-HIRIS-Internal-Token", ""), token
    ):
        logger.warning("Unauthorized inter-addon request from %s", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)
