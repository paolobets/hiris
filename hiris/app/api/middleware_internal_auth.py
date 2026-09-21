import hmac
import ipaddress
import logging
import os
import re

from aiohttp import web

logger = logging.getLogger(__name__)

# Supervisor adds X-Ingress-Path = "/api/hassio_ingress/<token>/..." to every
# proxied request. Validate the pattern so an attacker forwarded through a
# different proxy cannot just attach the header with an arbitrary value.
_INGRESS_PATH_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]+(/.*)?$")

# Default HA Supervisor Docker network. The ingress proxy always reaches the
# add-on from inside this range; a direct LAN/tunnel client never does.
_DEFAULT_SUPERVISOR_CIDRS = ["172.30.32.0/23"]


def _allow_no_token() -> bool:
    """Re-read env var at each request so tests can patch it without import-order issues."""
    return os.environ.get("HIRIS_ALLOW_NO_TOKEN", "").strip() == "1"


def _supervisor_cidrs(request: web.Request) -> list[str]:
    cidrs = request.app.get("supervisor_ingress_cidrs")
    return cidrs if cidrs else _DEFAULT_SUPERVISOR_CIDRS


def _is_supervisor_ingress(request: web.Request) -> bool:
    """Verify a request genuinely came from HA Supervisor Ingress.

    Dual check to prevent X-Ingress-Path spoofing (CR-1):
    1. ``X-Ingress-Path`` must be present AND match the Supervisor pattern.
    2. The TCP source IP must fall inside a trusted Supervisor CIDR.

    Without the IP check, any client that can reach the add-on port directly
    (LAN, or a tunnel from another host) could attach
    ``X-Ingress-Path: /api/hassio_ingress/x`` and bypass the internal_token on
    the entire API surface.
    """
    ingress_path = request.headers.get("X-Ingress-Path", "")
    if not ingress_path or not _INGRESS_PATH_RE.match(ingress_path):
        return False
    remote = request.remote
    if not remote:
        return False
    try:
        remote_ip = ipaddress.ip_address(remote)
    except (ValueError, TypeError):
        return False
    for cidr in _supervisor_cidrs(request):
        try:
            if remote_ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except (ValueError, TypeError):
            continue
    logger.warning(
        "CR-1: X-Ingress-Path present but source IP %s not in supervisor CIDRs "
        "%s — treating as direct request (internal_token required)",
        remote, _supervisor_cidrs(request),
    )
    return False


#: Le intestazioni con cui il Supervisor dice CHI sta chiamando. Verificato il
#: 21/09/2026 sul sorgente (`supervisor/api/ingress.py::_init_header`): le
#: compone da `session_data.user` e **filtra via le stesse in ingresso** prima
#: di aggiungere le proprie, quindi attraverso l'ingress non sono falsificabili.
#: Su ogni altra strada lo sono, ed e' il motivo per cui si leggono in un ramo
#: solo.
_CHI = "X-Remote-User-Id"
_NOME = "X-Remote-User-Display-Name"
_UTENTE = "X-Remote-User-Name"


def _soggetto(request: web.Request, specie: str) -> dict:
    """Chi sta chiamando — sempre un oggetto, mai `None`.

    **«Non so chi sei» non e' «sei il proprietario».** Un ingress senza identita'
    (i provider di autenticazione non nativi non la portano: l'intestazione non
    e' garantita) da' una PERSONA ANONIMA, non l'assenza di un soggetto: un
    campo mancante e un campo vuoto si confondono al primo lettore distratto,
    due parole diverse no.

    La `specie` c'e' sempre perche' e' il primo fatto che serve a decidere un
    soffitto: una persona di Home Assistant e una macchina che porta un token
    non si autenticano nello stesso modo e non possono valere lo stesso.
    """
    if specie != "persona":
        return {"specie": specie, "id": None, "nome": None, "utente": None}
    return {"specie": "persona",
            "id": request.headers.get(_CHI) or None,
            "nome": (request.headers.get(_NOME)
                     or request.headers.get(_UTENTE) or None),
            "utente": request.headers.get(_UTENTE) or None}


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    """Validate X-HIRIS-Internal-Token for non-Ingress requests.

    Genuine HA Supervisor Ingress requests (X-Ingress-Path matches the
    Supervisor pattern AND the source IP is a trusted Supervisor address) always
    pass. Every other request requires a matching X-HIRIS-Internal-Token; when no
    token is configured they are denied by default (set HIRIS_ALLOW_NO_TOKEN=1 to
    disable this during local development).
    """
    if _is_supervisor_ingress(request):
        request["auth_via"] = "ingress"
        request["soggetto"] = _soggetto(request, "persona")
        return await handler(request)

    token = request.app.get("internal_token", "")
    if not token:
        if _allow_no_token():
            logger.critical("SECURITY: HIRIS_ALLOW_NO_TOKEN=1 is set — authentication is DISABLED")
            request["auth_via"] = "no_token"
            request["soggetto"] = _soggetto(request, "sviluppo")
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

    request["auth_via"] = "token"
    request["soggetto"] = _soggetto(request, "integrazione")
    return await handler(request)
