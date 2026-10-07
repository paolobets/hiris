"""Il cancello al confine (spec 2026-09-27 §3; Tappa 7, F-01 e F-17): dove
entra chi, e con quale gesto.

**Ogni rotta dichiara il suo gesto** (`leggere`, `comandare`, `amministrare`,
il vocabolario di `soffitto.GESTI`) in `ADMISSION`, e il confine lo chiede al
soffitto di **chiunque** entri: una persona dall'ingress e un servizio firmato
con la stessa domanda (`soffitto.denies`). Fino al 07/10/2026 il gesto lo
decideva il codice della rotta -- `require_builder` in nove rotte,
`_solo_amministratori` in quattro, `ceiling["costruire"]` letto nudo -- e i
servizi firmati passavano da un controllo a parte, che guardava solo lettura
contro scrittura: un servizio approvato come `utente` scriveva la
configurazione dei modelli. Una rotta nuova nasceva senza gesto finche'
qualcuno non se ne ricordava; adesso nasce chiusa, a tutti.

**Chi non amministra, in piu', entra solo dove la riga lo dice**
(`Route.open_reason`), e solo se il proprietario ha acceso l'opzione
`non_admin_access`. Il principio e' quello di `soffitto.py`: HIRIS non concede
mai piu' di quanto il chiamante puo' gia' in Home Assistant, dove un non
amministratore usa le plance e comanda le entita' ma non entra in
Impostazioni. Qui: chatta, vede i suoi Impegni e le sue memorie, non
configura.

Ci passa anche la credenziale di turno del ponte, col ruolo che porta
(`credenziali.RUOLO_TURNO`). Non ci passa una strada sola: la presentazione
dentro la finestra d'accoppiamento (`handlers_servizi.ROTTA_APERTA`), l'unica
superficie che il prodotto non puo' autenticare, che esiste solo nei dieci
minuti in cui il proprietario l'apre.

Il cancello non conosce la voce di menu (`panel_visibility.py`): la voce e'
comodita', l'opzione e il ruolo sono il permesso.
"""
from __future__ import annotations

import json
import logging
from typing import NamedTuple

from aiohttp import web
from aiohttp.web_urldispatcher import StaticResource

from ..chat_thread import subject_key_for
from .boundary import error_body
from .soffitto import (
    _route_pattern,
    boundary_role,
    denies,
    is_admin_role,
    request_ceiling,
)

logger = logging.getLogger(__name__)

#: La cartella degli asset: ammessa come RISORSA STATICA, non come nome (vedi
#: `_resolved`).
STATIC_PREFIX = "/static"


class Route(NamedTuple):
    """Una riga della tabella delle rotte.

    - `method`, `canonical`: la rotta come il router l'ha registrata (il
      MODELLO, `/api/constructions/{id}`, mai un percorso);
    - `gesture`: il gesto del soffitto che la rotta chiede a chiunque;
    - `open_reason`: perche' una persona che non amministra ci entra -- la
      chiamata vera della pagina che la usa; `None` = non ci entra."""
    method: str
    canonical: str
    gesture: str
    open_reason: str | None = None


#: **La tabella delle rotte** -- metodo, modello, gesto, e per chi non
#: amministra la ragione per entrare. Scritta a mano perche' E' la decisione
#: (spec 2026-09-27 §3, D4 della Tappa 7), non una copia di niente: le rotte
#: si CHIEDONO al router nelle prove (`tests/test_admission.py`), il gesto e
#: la scelta di quali aprire no. Chiude per difetto: una rotta che qui non
#: c'e' e' negata a tutti, amministratore compreso.
#:
#: **I gesti.** `amministrare` per cio' che configura HIRIS o la casa, e per
#: le pagine che solo chi amministra apre (Costruzioni, Proposte, il sapere
#: corretto a mano, i servizi, i consumi azzerati); `leggere` per il resto,
#: comprese le scritture **nel proprio filo** (un turno di chat, una
#: conversazione, una promessa disdetta), che non toccano la casa ne' la
#: configurazione -- cosa si comanda dentro un turno lo decide il soffitto
#: nel dispatcher, strumento per strumento. Nessuna rotta chiede
#: `comandare`: nessuna comanda la casa da se'.
#:
#: Le ragioni delle righe aperte vengono da una chiamata vera delle pagine,
#: lette il 27/09/2026: `index.html` e `static/chat/*.js`,
#: `static/pending-badge.js`, `static/build-check.js`, `static/common.js`, e
#: nel guscio `/config` gli Impegni (`agenda-route.js`) e la Memoria in
#: lettura (`memory-route.js`). Niente prefissi: una rotta nuova nasce chiusa.
#: HEAD passa solo dove passa GET (ruling R-2.13), e non si scrive.
#:
#: **Chi aggiunge una rotta** aggiunge qui la sua riga col gesto; chi la apre
#: a chi non amministra le da' la ragione, e la sua prova -- mai un prefisso.
ADMISSION: tuple[Route, ...] = (
    # I due gusci e i loro asset.
    Route("GET", "/", "leggere",
          ("il guscio della chat: la pagina che una persona apre dal menu di "
           "Home Assistant")),
    Route("GET", "/config", "leggere",
          ("il guscio delle pagine: chi non amministra ci trova gli Impegni e "
           "la Memoria, il resto del menu gli e' chiuso")),
    Route("GET", STATIC_PREFIX, "leggere",
          ("fogli di stile, caratteri, icona e script dei due gusci: senza, "
           "nessuna delle due pagine si disegna")),
    # Cio' che ogni guscio chiama all'avvio.
    Route("GET", "/api/config", "leggere",
          ("il tema della pagina (`common.js::applyTheme`), chiamato da "
           "entrambi i gusci all'avvio")),
    Route("GET", "/api/health", "leggere",
          ("connesso o no (`chat/main.js::checkHealth`, `config/main.js`) e "
           "l'impronta del guscio (`build-check.js`); a chi non amministra "
           "arrivano solo stato, versione e impronta, che il guscio porta gia' "
           "scritta")),
    Route("GET", "/api/pending", "leggere",
          ("i pallini del menu (`pending-badge.js`): gli esiti non letti dei "
           "SUOI Impegni, e le proposte a zero per chi non amministra")),
    Route("GET", "/api/chat-settings", "leggere",
          ("nome dell'assistente e tetto dei turni "
           "(`chat/agents.js::loadSettings`), e solo quelli "
           "(`handlers_settings.CHAT_PAGE_FIELDS`): leggerle tutte e "
           "scriverle resta agli amministratori")),
    # La chat e le conversazioni, tutte nel filo di chi chiede.
    Route("POST", "/api/chat", "leggere",
          ("il turno di chat (`chat/send.js`): cosa si puo' fare dentro lo "
           "decide il soffitto nel dispatcher")),
    Route("GET", "/api/chat/reply/{job_id}", "leggere",
          ("la risposta di un turno servito dal ponte (`chat/send.js`), letta "
           "nel filo di chi l'ha chiesta")),
    Route("GET", "/api/chat/history", "leggere",
          ("la cronologia del SUO filo, riletta all'avvio "
           "(`chat/agents.js::restore`)")),
    Route("GET", "/api/chat/conversations", "leggere",
          "l'elenco delle SUE conversazioni (`chat/conversations.js`)"),
    Route("POST", "/api/chat/conversations", "leggere",
          "una conversazione nuova nel suo filo (`chat/conversations.js`)"),
    Route("POST", "/api/chat/conversations/{id}/resume", "leggere",
          "riprende una SUA conversazione; l'id di un altro filo e' un 404"),
    Route("DELETE", "/api/chat/conversations/{id}", "leggere",
          ("cancella una SUA conversazione: togliere le proprie parole non e' "
           "configurare")),
    # Gli Impegni (`config/agenda-route.js`), nel filo di chi chiede.
    Route("GET", "/api/agenda", "leggere", "le SUE promesse, la pagina Impegni"),
    Route("DELETE", "/api/agenda/{id}", "leggere",
          ("disdire una SUA promessa: vietarlo gli impedirebbe di fermare cio' "
           "che ha messo in moto")),
    Route("POST", "/api/agenda/read", "leggere",
          "segnare come letti gli esiti gia' mostrati dei SUOI Impegni"),
    Route("GET", "/api/executions/{id}", "leggere",
          ("l'esito di una SUA promessa eseguita; quello di un altro filo "
           "risponde come inesistente")),
    # La Memoria, in sola lettura (decisione 4 del proprietario).
    Route("GET", "/api/memories", "leggere",
          ("la pagina Memoria in sola lettura (`config/memory-route.js`); "
           "correggere e cancellare restano agli amministratori")),
    # -- Da qui in giu' le rotte che chi non amministra non apre. --
    # Le letture delle pagine di configurazione: per una persona e' il
    # menu chiuso; un servizio firmato le legge, come prima del 07/10/2026.
    # I corpi che Home Assistant riserva agli amministratori li copre la
    # rotta stessa (`handlers_home_space`, `privacy.cover_reserved_body`).
    Route("GET", "/api/briefing", "leggere"),
    Route("GET", "/api/home-space", "leggere"),
    Route("GET", "/api/misure", "leggere"),
    Route("GET", "/api/models", "leggere"),
    Route("GET", "/api/models/config", "leggere"),
    Route("GET", "/api/usage", "leggere"),
    Route("GET", "/api/usage/history", "leggere"),
    Route("GET", "/api/services", "leggere"),
    Route("GET", "/api/mind/watching", "leggere"),
    Route("GET", "/api/mind/report", "leggere"),
    Route("GET", "/api/mind/analysis", "leggere"),
    Route("GET", "/api/mind/knowledge", "leggere"),
    # Configurare HIRIS: le impostazioni, i modelli, la memoria corretta a
    # mano, i consumi azzerati, l'obiettivo del cervello.
    Route("PUT", "/api/chat-settings", "amministrare"),
    Route("PUT", "/api/models/config", "amministrare"),
    Route("PATCH", "/api/memories/{id}", "amministrare"),
    Route("DELETE", "/api/memories/{id}", "amministrare"),
    Route("POST", "/api/usage/reset", "amministrare"),
    Route("POST", "/api/mind/objective", "amministrare"),
    # Il sapere corretto a mano (spec 2026-09-26 §3, decisione 6).
    Route("POST", "/api/mind/judgment", "amministrare"),
    Route("POST", "/api/mind/scope", "amministrare"),
    # La pagina Costruzioni e le Proposte, letture comprese (spec 2026-09-26
    # §3, decisione 5): scrivono la configurazione di Home Assistant, che
    # Home Assistant nega a chi non amministra.
    Route("GET", "/api/constructions", "amministrare"),
    Route("GET", "/api/constructions/{id}", "amministrare"),
    Route("POST", "/api/constructions/{id}/confirm", "amministrare"),
    Route("POST", "/api/constructions/{id}/restore", "amministrare"),
    Route("POST", "/api/constructions/{id}/reject", "amministrare"),
    Route("POST", "/api/proposals/{id}/reject", "amministrare"),
    Route("POST", "/api/proposals/{id}/done", "amministrare"),
    Route("POST", "/api/proposals/{id}/redo", "amministrare"),
    Route("POST", "/api/proposals/{id}/automate", "amministrare"),
    # I servizi: dare a una macchina il diritto di comandare la casa non e'
    # meno che scriverci un'automazione. La presentazione dentro la finestra
    # aperta non passa da qui (`middleware_internal_auth`); fuori dalla
    # finestra la rotta risponde come le sue sorelle.
    Route("POST", "/api/services/present", "amministrare"),
    Route("POST", "/api/services/window/open", "amministrare"),
    Route("POST", "/api/services/window/close", "amministrare"),
    Route("POST", "/api/services/approve", "amministrare"),
    Route("POST", "/api/services/revoke", "amministrare"),
    # Gli strumenti al ponte: legge, col ruolo della credenziale di turno
    # (`credenziali.RUOLO_TURNO`); cosa si fa dentro un turno lo decide il
    # soffitto del dispatcher. La rotta stessa pretende quella credenziale, e
    # a chiunque altro -- un amministratore, un servizio firmato -- risponde
    # 401 (`handlers_mcp.handle_mcp`).
    Route("POST", "/api/mcp", "leggere"),
)

#: Le viste sulla tabella, derivate una volta.
_GESTURES = {(route.method, route.canonical): route.gesture for route in ADMISSION}
_ADMITTED = frozenset((route.method, route.canonical) for route in ADMISSION
                       if route.open_reason)

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


def _resolved(method: str, match_info) -> tuple[str, str] | None:
    """La rotta che aiohttp ha GIA' risolto (`match_info`, prima dei
    middleware), come chiave della tabella -- metodo e modello, mai il
    percorso, un prefisso o una regex. `None` per una rotta non risolta (404,
    405): arriva senza risorsa, e non c'e' niente da servire ne' da negare.
    HEAD vale come GET (ruling R-2.13). La cartella degli asset vale solo come
    RISORSA STATICA, non come nome."""
    resource = getattr(getattr(match_info, "route", None), "resource", None)
    if resource is None:
        return None
    if resource.canonical == STATIC_PREFIX and not isinstance(resource, StaticResource):
        return ("?", resource.canonical)
    return ("GET" if method == "HEAD" else method, resource.canonical)


def admitted(method: str, match_info) -> bool:
    """Questa richiesta sta fra le righe aperte a chi non amministra? Una
    rotta non risolta non ci sta: misurato con una mutazione, un controllo in
    piu' su `http_exception` non cambiava niente, ed e' uscito."""
    return _resolved(method, match_info) in _ADMITTED


def _refusal(request: web.Request, text: str) -> web.Response:
    """Il rifiuto nella forma di chi lo legge: JSON per le rotte `/api/`,
    pagina per i gusci. La forma si sceglie dal percorso e non dalla rotta:
    una rotta vietata e una che non esiste devono rispondere uguale (2.16).
    Una pagina porta solo i testi fissi: un altro testo diventa quello della
    parte riservata."""
    if request.path.startswith("/api/"):
        return web.Response(body=json.dumps(error_body(text)).encode("utf-8"),
                            status=403, content_type="application/json",
                            headers=_REFUSAL_HEADERS)
    return web.Response(body=_PAGES.get(text, _PAGES[NOT_ADMITTED]), status=403,
                        content_type="text/html", charset="utf-8",
                        headers={**_REFUSAL_HEADERS,
                                 "Content-Security-Policy": _PAGE_CSP})


def gesture_refusal(request: web.Request) -> web.Response | None:
    """`None` se il soffitto di chi chiede concede il gesto di questa rotta,
    altrimenti il 403. **Il cancello unico** (F-01, F-17; D4 della Tappa 7):
    lo chiedono il confine per ogni persona dall'ingress
    (`admission_refusal`), per ogni servizio firmato, per la credenziale di
    turno del ponte e per lo sviluppo (`middleware_internal_auth`), sempre
    prima del gestore -- cioe' prima di qualunque archivio.

    La domanda e' quella degli strumenti, `soffitto.denies`: lo sviluppo con
    l'interruttore acceso non si restringe, come non si restringeva nei turni
    di chat. Una rotta risolta che la tabella non nomina chiede un gesto che
    non esiste, e nessun soffitto lo concede.

    Il testo: per `amministrare` lo stesso delle pagine chiuse a chi non
    amministra (`NOT_ADMITTED`), per gli altri gesti il `perche` del soffitto.
    **Ogni rifiuto di un servizio firmato si scrive nel registro** dell'add-on,
    a `warning`, col nome del servizio e il modello della rotta: un'integrazione
    che si rompe per questo cancello si vede al primo tentativo, e si legge dal
    registro senza toccare niente (D4 della Tappa 7)."""
    key = _resolved(request.method, request.match_info)
    if key is None:
        return None
    gesture = _GESTURES.get(key)
    subject = request.get("soggetto")
    ceiling = request_ceiling(request)
    if not denies(ceiling, gesture, subject):
        return None
    if gesture is None:
        logger.error("cancello: la rotta %s %s non ha un gesto in "
                     "`admission.ADMISSION`: chiusa a tutti", request.method,
                     _route_pattern(request))
    text = NOT_ADMITTED if gesture in (None, "amministrare") else ceiling["perche"]
    if request.get("auth_via") == "canale":
        logger.warning(
            "cancello: %s %s negato al servizio %r (%s, ruolo «%s») — gesto «%s»",
            request.method, _route_pattern(request), (subject or {}).get("nome"),
            subject_key_for(subject), ceiling.get("ruolo"), gesture)
    elif not _is_static(request.match_info):
        _log_refusal(request, subject, f"gesto «{gesture}» negato al ruolo "
                                       f"«{ceiling.get('ruolo')}»")
    return _refusal(request, text)


async def admission_refusal(app, request: web.Request) -> web.Response | None:
    """`None` se questa persona dall'ingress entra qui, altrimenti il 403.

    Si chiama SOLO per le persone dall'ingress, dopo che il confine ha
    attaccato il soggetto: i servizi firmati, il ponte e lo sviluppo passano
    da `gesture_refusal` e basta, l'accoppiamento ha la sua regola, e nessuno
    di loro chiede niente a Home Assistant.

    Il ruolo si legge anche con l'opzione spenta: l'amministratore passa
    comunque. Ruoli illeggibili chiudono tutti, proprietario compreso, col
    loro testo (ruling R-2.8): nel dubbio si chiude, e si dice perche'. Chi
    supera queste domande risponde ancora a quella di tutti, il gesto della
    rotta (`gesture_refusal`).

    **Il ruolo letto resta sulla richiesta** (`request["ruolo"]`, fix
    round 1, I4): chi viene dopo -- il gesto, la salute, le pagine -- lo legge
    da qui invece di chiederlo di nuovo a Home Assistant.
    """
    subject = request.get("soggetto")
    seen = await boundary_role(app, subject)
    request["ruolo"] = seen.role
    if is_admin_role(seen.role):
        return gesture_refusal(request)
    if not seen.read:
        text, why = ROLES_UNREADABLE, "ruoli illeggibili"
    elif not app.get("non_admin_access"):
        text, why = OPTION_OFF, "opzione spenta"
    elif not seen.known:
        text, why = UNKNOWN_PERSON, "persona sconosciuta a Home Assistant"
    elif seen.role is None:
        text, why = NOT_ADMITTED, "senza gruppi in Home Assistant"
    elif admitted(request.method, request.match_info):
        return gesture_refusal(request)
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
