"""CSRF middleware: require X-Requested-With on state-changing requests.

Browsers will not let cross-origin pages set arbitrary headers without a CORS
preflight, so a malicious site cannot replay a state-changing request with a
custom header against a logged-in HA user. This is the same defense used in
several JS frameworks for free, no token roundtrip needed.

Applies only to /api/* with POST/PUT/PATCH/DELETE. Same-origin fetch from our
UI must always set X-Requested-With: 'fetch' (any non-empty value works).

Server-to-server clients are exempt: CSRF is a browser-only attack class, and a
request that has already proved it is a machine -- a channel signature, a turn
credential, or the shared secret while it still exists -- is by definition not
a forged cross-site request.

**The exemption reads the verdict the auth middleware left** (`auth_via`)
instead of comparing the secret a second time. One place decides who is
authenticated, not two -- and the second one would have gone stale the day the
bridge moved to ephemeral credentials, asking a bridge turn for a CSRF header
the boundary had already cleared. That makes the ORDER of the two middlewares
load-bearing, and a gate pins it
(`test_security.py::test_il_csrf_gira_DOPO_l_autenticazione_e_non_prima`).
"""
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _allow_no_csrf() -> bool:
    """Re-read env var per request so tests can patch it without import-order issues."""
    return os.environ.get("HIRIS_ALLOW_NO_CSRF", "").strip() == "1"


@web.middleware
async def csrf_middleware(request: web.Request, handler) -> web.Response:
    if request.method in _SAFE_METHODS:
        return await handler(request)
    if not request.path.startswith("/api/"):
        return await handler(request)
    if request.headers.get("X-Requested-With"):
        return await handler(request)
    # **L'esenzione si tiene sull'esito del confine, non su un secondo
    # confronto del segreto** (22/09/2026). Prima questo modulo ricopiava il
    # confronto del token: un secondo posto in cui si decide chi e'
    # autenticato, e che col ponte passato alle credenziali effimere sarebbe
    # diventato subito falso -- avrebbe chiesto il CSRF a un turno del ponte
    # che il confine aveva gia' riconosciuto.
    #
    # Il CSRF e' un attacco del BROWSER: una richiesta che ha gia' provato di
    # essere una macchina -- firma di canale, credenziale di turno, o il
    # segreto condiviso finche' esiste -- non e', per definizione, una
    # richiesta forgiata cross-site.
    if request.get("auth_via") in ("canale", "turno", "accoppiamento"):
        return await handler(request)
    if _allow_no_csrf():
        return await handler(request)
    logger.warning(
        "CSRF blocked: %s %s missing X-Requested-With (origin=%s)",
        request.method, request.path,
        request.headers.get("Origin", ""),
    )
    return web.json_response({"error": "csrf_required"}, status=403)
