import hmac
import logging
import os
import re
from aiohttp import web

logger = logging.getLogger(__name__)

# Supervisor adds X-Ingress-Path = "/api/hassio_ingress/<token>/..." to every
# proxied request. Validate the pattern so an attacker forwarded through a
# different proxy cannot just attach the header with an arbitrary value.
_INGRESS_PATH_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]+(/.*)?$")


def _allow_no_token() -> bool:
    """Re-read env var at each request so tests can patch it without import-order issues."""
    return os.environ.get("HIRIS_ALLOW_NO_TOKEN", "").strip() == "1"


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    """Validate X-HIRIS-Internal-Token for non-Ingress requests.

    Requests via HA Supervisor Ingress (X-Ingress-Path matches the Supervisor
    pattern) always pass. Non-ingress requests require a matching
    X-HIRIS-Internal-Token; when no token is configured they are denied by
    default (set HIRIS_ALLOW_NO_TOKEN=1 to disable this during local development).
    """
    ingress_path = request.headers.get("X-Ingress-Path", "")
    if ingress_path and _INGRESS_PATH_RE.match(ingress_path):
        return await handler(request)

    token = request.app.get("internal_token", "")
    if not token:
        if _allow_no_token():
            logger.critical("SECURITY: HIRIS_ALLOW_NO_TOKEN=1 is set — authentication is DISABLED")
            return await handler(request)
        logger.warning(
            "Blocked unauthenticated non-ingress request from %s "
            "(no internal_token configured; set HIRIS_ALLOW_NO_TOKEN=1 for dev)",
            request.remote,
        )
        return web.json_response({"error": "unauthorized"}, status=401)

    if not hmac.compare_digest(request.headers.get("X-HIRIS-Internal-Token", ""), token):
        logger.warning("Unauthorized inter-addon request from %s", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)

    return await handler(request)
