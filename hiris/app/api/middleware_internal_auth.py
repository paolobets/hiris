import hmac
import ipaddress
import logging
import os
import re
import time

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
#: Le intestazioni con cui un CANALE si presenta (spec 2026-09-21 §6). La
#: `X-HIRIS-Canale` viaggia anche senza firma durante la convivenza: li' non
#: autentica niente e serve solo a MISURARE chi non firma ancora.
_CANALE = "X-HIRIS-Canale"
_MOMENTO = "X-HIRIS-Momento"
_UNICO = "X-HIRIS-Unico"
_FIRMA = "X-HIRIS-Firma"

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


async def _canale(request: web.Request):
    """Il canale che ha firmato questa richiesta — o `None` se non ci prova.

    **Chi prova a firmare e sbaglia non scivola sul ripiego del token**: sarebbe
    una porta aperta da qualunque firma storta, cioe' il contrario di una
    difesa. Per questo la funzione distingue tre esiti e non due: non ci prova
    (`None`), ci prova e regge (il canale), ci prova e non regge (il motivo).
    """
    from . import canali

    # **A dire «sto firmando» e' la FIRMA, non il nome del canale.** Durante la
    # convivenza (spec §8) chi usa ancora il token dichiara `X-HIRIS-Canale`
    # per farsi misurare: trattare quella dichiarazione come un tentativo di
    # firma lo rifiuterebbe, cioe' spegnerebbe l'integrazione che stiamo
    # cercando di contare. Misurato scrivendo la prova, non supposto.
    if not request.headers.get(_FIRMA):
        return None, None
    return canali.riconosci(
        canale=request.headers.get(_CANALE, ""),
        momento=request.headers.get(_MOMENTO, ""),
        unico=request.headers.get(_UNICO, ""),
        firma=request.headers.get(_FIRMA, ""),
        metodo=request.method, percorso=request.path,
        corpo=await request.read(),
        registrate=request.app.get("canali_registrati") or {},
        visti=request.app.get("canali_visti"),
        adesso=time.time())


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    """Validate X-HIRIS-Internal-Token for non-Ingress requests.

    Genuine HA Supervisor Ingress requests (X-Ingress-Path matches the
    Supervisor pattern AND the source IP is a trusted Supervisor address) always
    pass. Every other request requires a matching X-HIRIS-Internal-Token; when no
    token is configured they are denied by default (set HIRIS_ALLOW_NO_TOKEN=1 to
    disable this during local development).
    """
    from .canali import consente_metodo

    firmato, motivo = await _canale(request)
    if motivo is not None:
        logger.warning("canale: richiesta rifiutata da %s — %s",
                       request.remote, motivo)
        return web.json_response({"errore": motivo}, status=401)
    if firmato is not None:
        if not consente_metodo(firmato["ruolo"], request.method):
            logger.warning(
                "canale: «%s» ha ruolo «%s» e ha chiesto %s %s — negato",
                firmato["canale"], firmato["ruolo"], request.method, request.path)
            return web.json_response(
                {"errore": f"il canale «{firmato['canale']}» ha il ruolo "
                           f"«{firmato['ruolo']}»: legge e non scrive"},
                status=403)
        request["auth_via"] = "canale"
        request["soggetto"] = {"specie": firmato["specie"],
                               "id": firmato["canale"],
                               "nome": firmato["canale"],
                               "utente": None,
                               "ruolo": firmato["ruolo"]}
        return await handler(request)

    if _is_supervisor_ingress(request):
        request["auth_via"] = "ingress"
        request["soggetto"] = _soggetto(request, "persona")
        return await handler(request)

    # **La credenziale EFFIMERA del ponte** (spec §5, ingresso 7), e si guarda
    # PRIMA del segreto condiviso per la stessa ragione per cui la firma si
    # guarda prima di entrambi: finche' il segreto lungo vince, chi ce l'ha non
    # ha nessun motivo di passare a una credenziale che scade, e il ripiego non
    # finisce mai.
    #
    # Il ponte non e' una persona e non e' un'integrazione registrata: e' HIRIS
    # che lavora per conto suo, per il tempo di un turno. Da cui `specie:
    # nessuno`, che e' cio' che la cronaca deve scrivere.
    from .credenziali import riconosci

    turno = riconosci(request.app.get("credenziali") or {},
                      request.headers.get("X-HIRIS-Internal-Token"),
                      adesso=time.time())
    if turno is not None:
        request["auth_via"] = "turno"
        request["soggetto"] = {"specie": "nessuno", "id": turno["mestiere"],
                               "nome": turno["mestiere"], "utente": None,
                               "ruolo": None}
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

    # La CONVIVENZA (spec §8): il token resta per una fetta, perche' il gateway
    # e il proxy di Retro Panel vivono in due repository separati e un taglio
    # netto li spegnerebbe. Ma chi lo usa **si misura**, o la fine della
    # convivenza la deciderebbe una speranza invece di un dato.
    logger.info(
        "convivenza: richiesta col token condiviso da %s (canale dichiarato: "
        "%s) su %s %s — questo ripiego esce quando questa riga tace",
        request.remote, request.headers.get(_CANALE) or "IGNOTO",
        request.method, request.path)
    request["auth_via"] = "token"
    request["soggetto"] = _soggetto(request, "integrazione")
    return await handler(request)
