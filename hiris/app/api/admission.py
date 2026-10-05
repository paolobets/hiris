"""Il cancello al confine (spec 2026-09-27 §3): dove entra chi non amministra.

**Tutto e' riservato agli amministratori per difetto.** Una persona arrivata
dall'ingress che Home Assistant non dice amministratrice passa solo sulle rotte
di `ADMISSION`, e solo se il proprietario ha acceso l'opzione
`non_admin_access`. Il principio e' quello di `soffitto.py`: HIRIS non concede
mai piu' di quanto il chiamante puo' gia' in Home Assistant, dove un non
amministratore usa le plance e comanda le entita' ma non entra in
Impostazioni. Qui: chatta, vede i suoi Impegni e le sue memorie, non configura.

La lista dice **dove** si entra; i cancelli di dentro (`require_builder`, il
soffitto su `confirm` e sulle `fai`, i fili) dicono **cosa** si fa li'.

Il cancello non conosce la voce di menu (`panel_visibility.py`): la voce e'
comodita', l'opzione e il ruolo sono il permesso.
"""
from __future__ import annotations

import json
import logging

from aiohttp import web
from aiohttp.web_urldispatcher import StaticResource

from ..chat_thread import subject_key_for
from .boundary import error_body
from .soffitto import _route_pattern, boundary_role, is_admin_role

logger = logging.getLogger(__name__)

#: La cartella degli asset: ammessa come RISORSA STATICA, non come nome (vedi
#: `admitted`).
STATIC_PREFIX = "/static"

#: **La lista di ammissione** -- metodo, modello della rotta del router,
#: ragione. Scritta a mano perche' E' la decisione (spec §3), non una copia di
#: niente: le rotte si CHIEDONO al router nelle prove, la scelta di quali
#: aprire no. Ogni voce viene da una chiamata vera delle pagine, lette il
#: 27/09/2026: `index.html` e `static/chat/*.js`, `static/pending-badge.js`,
#: `static/build-check.js`, `static/common.js`, e nel guscio `/config` gli
#: Impegni (`agenda-route.js`) e la Memoria in lettura (`memory-route.js`).
#: Niente prefissi: una rotta nuova nasce chiusa. HEAD passa solo dove passa
#: GET (ruling R-2.13), e non si scrive.
#:
#: **Chi aggiunge una pagina per chi non amministra** aggiunge qui le sue
#: rotte, una per una, con la ragione e la sua prova -- mai un prefisso.
ADMISSION: tuple[tuple[str, str, str], ...] = (
    # I due gusci e i loro asset.
    ("GET", "/",
     ("il guscio della chat: la pagina che una persona apre dal menu di Home "
      "Assistant")),
    ("GET", "/config",
     ("il guscio delle pagine: chi non amministra ci trova gli Impegni e la "
      "Memoria, il resto del menu gli e' chiuso")),
    ("GET", STATIC_PREFIX,
     ("fogli di stile, caratteri, icona e script dei due gusci: senza, nessuna "
      "delle due pagine si disegna")),
    # Cio' che ogni guscio chiama all'avvio.
    ("GET", "/api/config",
     ("il tema della pagina (`common.js::applyTheme`), chiamato da "
      "entrambi i gusci all'avvio")),
    ("GET", "/api/health",
     ("connesso o no (`chat/main.js::checkHealth`, `config/main.js`) e "
      "l'impronta del guscio (`build-check.js`); a chi non amministra arrivano "
      "solo stato, versione e impronta, che il guscio porta gia' scritta")),
    ("GET", "/api/pending",
     ("i pallini del menu (`pending-badge.js`): gli esiti non letti dei SUOI "
      "Impegni, e le proposte a zero per chi non costruisce")),
    ("GET", "/api/chat-settings",
     ("nome dell'assistente e tetto dei turni (`chat/agents.js::loadSettings`), "
      "e solo quelli (`handlers_settings.CHAT_PAGE_FIELDS`): leggerle tutte e "
      "scriverle resta agli amministratori")),
    # La chat e le conversazioni, tutte nel filo di chi chiede.
    ("POST", "/api/chat",
     ("il turno di chat (`chat/send.js`): cosa si puo' fare dentro lo decide il "
      "soffitto nel dispatcher")),
    ("GET", "/api/chat/reply/{job_id}",
     ("la risposta di un turno servito dal ponte (`chat/send.js`), letta nel "
      "filo di chi l'ha chiesta")),
    ("GET", "/api/chat/history",
     ("la cronologia del SUO filo, riletta all'avvio "
      "(`chat/agents.js::restore`)")),
    ("GET", "/api/chat/conversations",
     "l'elenco delle SUE conversazioni (`chat/conversations.js`)"),
    ("POST", "/api/chat/conversations",
     "una conversazione nuova nel suo filo (`chat/conversations.js`)"),
    ("POST", "/api/chat/conversations/{id}/resume",
     "riprende una SUA conversazione; l'id di un altro filo e' un 404"),
    ("DELETE", "/api/chat/conversations/{id}",
     ("cancella una SUA conversazione: togliere le proprie parole non e' "
      "configurare")),
    # Gli Impegni (`config/agenda-route.js`), nel filo di chi chiede.
    ("GET", "/api/agenda",
     "le SUE promesse, la pagina Impegni"),
    ("DELETE", "/api/agenda/{id}",
     ("disdire una SUA promessa: vietarlo gli impedirebbe di fermare cio' che "
      "ha messo in moto")),
    ("POST", "/api/agenda/read",
     "segnare come letti gli esiti gia' mostrati dei SUOI Impegni"),
    ("GET", "/api/executions/{id}",
     ("l'esito di una SUA promessa eseguita; quello di un altro filo risponde "
      "come inesistente")),
    # La Memoria, in sola lettura (decisione 4 del proprietario).
    ("GET", "/api/memories",
     ("la pagina Memoria in sola lettura (`config/memory-route.js`); "
      "correggere e cancellare restano agli amministratori")),
)

_ADMITTED = frozenset((method, canonical) for method, canonical, _ in ADMISSION)

#: I testi dei rifiuti, decisi dal coordinatore il 27/09/2026 (decisione 7 e
#: fix round 1, punto 11). Solo questi quattro distinguono qualcosa: opzione
#: spenta, rotta non concessa, ruoli illeggibili, persona che Home Assistant
#: non riconosce. Niente rotta, ruolo o soggetto nel testo.
OPTION_OFF = ("HIRIS in questa casa è riservato agli amministratori: chiedi a "
              "chi lo gestisce di attivarlo per tutti.")
NOT_ADMITTED = "Questa parte di HIRIS è riservata agli amministratori."
ROLES_UNREADABLE = "Non ho potuto leggere i ruoli da Home Assistant: riprova tra poco."
UNKNOWN_PERSON = ("Home Assistant non mi ha detto chi sei: HIRIS risponde solo "
                  "agli utenti di Home Assistant che riconosce. Se sei appena "
                  "stato aggiunto, riprova tra un minuto.")

#: Le intestazioni che il rifiuto si mette da se': esce dal primo middleware e
#: non passa da `_security_headers` (security-constraints 2.4). La pagina non
#: ha niente da caricare, quindi `default-src 'none'`.
_REFUSAL_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
_PAGE_CSP = "default-src 'none'"


def _page(text: str) -> bytes:
    # Solo il guasto dei ruoli si risolve da se': la sua pagina si ricarica,
    # le altre direbbero lo stesso rifiuto ogni sei secondi.
    refresh = ('<meta http-equiv="refresh" content="6">'
               if text == ROLES_UNREADABLE else "")
    return ("<!DOCTYPE html>\n<html lang=\"it\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"{refresh}<title>HIRIS</title></head><body><p>{text}</p></body></html>\n"
            ).encode()


#: Le pagine si compongono una volta, all'import, dai testi fissi: niente che
#: venga dalla richiesta ci finisce dentro.
_PAGES = {text: _page(text)
          for text in (OPTION_OFF, NOT_ADMITTED, ROLES_UNREADABLE, UNKNOWN_PERSON)}


def admitted(method: str, match_info) -> bool:
    """Questa richiesta sta nella lista? Si guarda la rotta che aiohttp ha
    GIA' risolto (`match_info`, prima dei middleware) -- metodo e modello,
    uguali, mai il percorso, un prefisso o una regex. Una rotta non risolta
    (404, 405) arriva senza risorsa, e non sta nella lista: misurato con una
    mutazione, un controllo in piu' su `http_exception` non cambiava niente,
    ed e' uscito."""
    resource = getattr(getattr(match_info, "route", None), "resource", None)
    if resource is None:
        return False
    method = "GET" if method == "HEAD" else method
    if (method, resource.canonical) not in _ADMITTED:
        return False
    if resource.canonical == STATIC_PREFIX:
        return isinstance(resource, StaticResource)
    return True


def _refusal(request: web.Request, text: str) -> web.Response:
    """Il rifiuto nella forma di chi lo legge: JSON per le rotte `/api/`,
    pagina per i gusci. La forma si sceglie dal percorso e non dalla rotta:
    una rotta vietata e una che non esiste devono rispondere uguale (2.16)."""
    if request.path.startswith("/api/"):
        return web.Response(body=json.dumps(error_body(text)).encode("utf-8"),
                            status=403, content_type="application/json",
                            headers=_REFUSAL_HEADERS)
    return web.Response(body=_PAGES[text], status=403, content_type="text/html",
                        charset="utf-8",
                        headers={**_REFUSAL_HEADERS,
                                 "Content-Security-Policy": _PAGE_CSP})


async def admission_refusal(app, request: web.Request) -> web.Response | None:
    """`None` se questa persona dall'ingress entra qui, altrimenti il 403.

    Si chiama SOLO per le persone dall'ingress, dopo che il confine ha
    attaccato il soggetto: servizi firmati, ponte, accoppiamento e sviluppo
    hanno le loro regole e non chiedono niente a Home Assistant.

    Il ruolo si legge anche con l'opzione spenta: l'amministratore passa
    comunque. Ruoli illeggibili chiudono tutti, proprietario compreso, col
    loro testo (ruling R-2.8): nel dubbio si chiude, e si dice perche'.

    **Il ruolo letto resta sulla richiesta** (`request["ruolo"]`, fix
    round 1, I4): chi viene dopo -- la salute, le pagine dei task successivi
    -- lo legge da qui invece di chiederlo di nuovo a Home Assistant.
    """
    subject = request.get("soggetto")
    seen = await boundary_role(app, subject)
    request["ruolo"] = seen.role
    if is_admin_role(seen.role):
        return None
    if not seen.read:
        text, why = ROLES_UNREADABLE, "ruoli illeggibili"
    elif not app.get("non_admin_access"):
        text, why = OPTION_OFF, "opzione spenta"
    elif not seen.known:
        text, why = UNKNOWN_PERSON, "persona sconosciuta a Home Assistant"
    elif seen.role is None:
        text, why = NOT_ADMITTED, "senza gruppi in Home Assistant"
    elif admitted(request.method, request.match_info):
        return None
    else:
        text, why = NOT_ADMITTED, "rotta fuori dalla lista"
    if not _is_static(request.match_info):
        _log_refusal(request, subject, why)
    return _refusal(request, text)


def _is_static(match_info) -> bool:
    resource = getattr(getattr(match_info, "route", None), "resource", None)
    return isinstance(resource, StaticResource)


def _log_refusal(request: web.Request, subject, why: str) -> None:
    # A `info`: una persona che apre per indirizzo una pagina che non e' sua e'
    # un caso normale. Non per ogni file della pagina: un guscio rifiutato
    # si porta dietro i suoi asset, e venti righe uguali non dicono niente
    # in piu' della prima (fix round 1, punto 12). Il MODELLO della rotta, mai
    # il percorso decodificato; la chiave del soggetto, mai il nome
    # (security-constraints 2.18).
    logger.info("cancello: %s %s negato a %s — %s", request.method,
                _route_pattern(request), subject_key_for(subject), why)
