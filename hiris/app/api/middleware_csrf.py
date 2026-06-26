"""CSRF middleware: require X-Requested-With on state-changing requests.

Browsers will not let cross-origin pages set arbitrary headers without a CORS
preflight, so a malicious site cannot replay a state-changing request with a
custom header against a logged-in HA user. This is the same defense used in
several JS frameworks for free, no token roundtrip needed.

Applies only to /api/* with POST/PUT/PATCH/DELETE. Same-origin fetch from our
UI must always set X-Requested-With: 'fetch' (any non-empty value works).

Server-to-server clients authenticated by a valid X-HIRIS-Internal-Token (the
MCP gateway, the Retro Panel proxy) are exempt: CSRF is a browser-only attack
class, and a request that already proves knowledge of the shared secret is by
definition not a forged cross-site request.
"""
import hmac
import logging
import os
from aiohttp import web

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _allow_no_csrf() -> bool:
    """Re-read env var per request so tests can patch it without import-order issues."""
    return os.environ.get("HIRIS_ALLOW_NO_CSRF", "").strip() == "1"


def _has_valid_internal_token(request: web.Request) -> bool:
    token = request.app.get("internal_token", "")
    if not token:
        return False
    return hmac.compare_digest(request.headers.get("X-HIRIS-Internal-Token", ""), token)


@web.middleware
async def csrf_middleware(request: web.Request, handler) -> web.Response:
    if request.method in _SAFE_METHODS:
        return await handler(request)
    if not request.path.startswith("/api/"):
        return await handler(request)
    if request.headers.get("X-Requested-With"):
        return await handler(request)
    if _has_valid_internal_token(request):
        return await handler(request)
    if _allow_no_csrf():
        return await handler(request)
    logger.warning(
        "CSRF blocked: %s %s missing X-Requested-With (origin=%s)",
        request.method, request.path,
        request.headers.get("Origin", ""),
    )
    return web.json_response({"error": "csrf_required"}, status=403)
