from aiohttp import web

from ..chat_store import (
    delete_conversation,
    list_conversations,
    load_history,
    new_conversation,
    resume_conversation,
)
from ..chat_thread import adopt_if_owner, request_thread
from .handlers_chat import PENDING_REPLY_ERROR

# fetta E5 Task 4 ("il frontend"): la rotta e' `GET /api/chat/history`
# (server.py), senza identificatori nel percorso. Fetta «le chat divise»: nel
# percorso non serve niente, perche' CHI legge lo dice il confine
# (`request["soggetto"]`/`["auth_via"]`, scritti da `middleware_internal_auth`)
# e da li' si calcola il filo. Un id nel percorso sarebbe un secondo modo --
# falsificabile -- di dire di chi e' la cronologia.
#
# Fetta «il seguito delle chat divise» (spec 2026-09-26 §4): nel filo ci sono
# piu' conversazioni, e le loro rotte un id nel percorso lo portano -- quello
# della conversazione, mai quello del filo. Il filo resta del confine, e
# l'archivio lega l'id al filo in ogni istruzione: l'id di un altro e' un id
# che non esiste. `DELETE /api/chat/history` («cancella tutto») e' uscita:
# si cancella una conversazione per volta (decisione 9).

# Il corpo del 404, uno solo per «non esiste» e «non e' tuo» (security 6.3):
# due corpi diversi direbbero a chi prova gli id quali sono di qualcun altro.
_CONVERSATION_NOT_FOUND = {"error": "non ho nessuna conversazione con quell’identificatore."}


def _reply_in_flight(request: web.Request, thread) -> web.Response | None:
    """Il 409 delle tre scritture sulle conversazioni, o `None`.

    Una risposta in volo verra' scritta nella conversazione attiva del filo:
    chiuderla, sostituirla o cancellarla adesso la farebbe atterrare altrove.
    Due strade, una frase (quella di `handle_chat`): il turno del ponte, che
    la coda conosce (`has_pending_chat`, ripieghi compresi), e il turno
    sincrono della catena, che dura quanto la chiamata al modello e lascia il
    suo segno in `app["sync_turns"]` (`handlers_chat._sync_turn`)."""
    queue = request.app.get("reasoning_queue")
    sync_turns = request.app.get("sync_turns")
    if ((queue is not None and queue.has_pending_chat(thread))
            or (sync_turns is not None and sync_turns.busy(thread))):
        return web.json_response({"error": PENDING_REPLY_ERROR}, status=409)
    return None


async def handle_get_chat_history(request: web.Request) -> web.Response:
    data_dir = request.app["data_dir"]
    thread = request_thread(request)
    # La cronologia di prima va al proprietario alla sua prima lettura: e' la
    # pagina che apre per prima, e senza questa riga la vedrebbe vuota finche'
    # non scrive un messaggio (spec §3).
    await adopt_if_owner(request.app, request, thread)
    # Task 12: prima di questo task `load_history` leggeva sempre il globale
    # `chat_store.HISTORY_RETENTION_DAYS` -- questa pagina era GIA' filtrata
    # dallo stesso numero, per accidente di implementazione condivisa, non
    # per scelta dichiarata qui. Passare `giorni_conservazione` esplicitamente
    # mantiene lo stesso comportamento invece di farlo silenziosamente
    # ricadere sul default (90) del parametro qualunque cosa l'utente abbia
    # scelto in «Impostazioni chat».
    giorni = request.app["chat_settings"].retention_days
    # collaudo 3.22, C4: `include_timestamp=True` SOLO qui -- questa e' la
    # rotta che disegna le bolle, e disegnarle con `new Date()` "al momento
    # del disegno" (il client, prima di questa correzione) affermava un'ora
    # falsa per ogni messaggio ripristinato. Il chiamante che nutre il
    # modello (`handlers_chat.py`) non passa questo argomento: resta
    # `{role, content}`, il formato che l'API del modello si aspetta.
    messages = load_history(data_dir, thread=thread, days=giorni, include_timestamp=True)
    return web.json_response({"messages": messages})


async def handle_list_conversations(request: web.Request) -> web.Response:
    thread = request_thread(request)
    # Adotta come `GET /api/chat/history`: la barra laterale si apre insieme
    # alla cronologia, e il proprietario deve trovarci anche le conversazioni
    # di prima. Le tre scritture qui sotto NON adottano: su un'orfana
    # rispondono come per un id che non esiste.
    await adopt_if_owner(request.app, request, thread)
    rows = list_conversations(request.app["data_dir"], thread=thread,
                              days=request.app["chat_settings"].retention_days)
    return web.json_response({"conversations": rows})


async def handle_new_conversation(request: web.Request) -> web.Response:
    thread = request_thread(request)
    busy = _reply_in_flight(request, thread)
    if busy is not None:
        return busy
    new_conversation(request.app["data_dir"], thread=thread)
    return web.json_response({"ok": True})


async def handle_resume_conversation(request: web.Request) -> web.Response:
    thread = request_thread(request)
    busy = _reply_in_flight(request, thread)
    if busy is not None:
        return busy
    if not resume_conversation(request.app["data_dir"], thread=thread,
                               session_id=request.match_info["id"],
                               days=request.app["chat_settings"].retention_days):
        return web.json_response(_CONVERSATION_NOT_FOUND, status=404)
    return web.json_response({"ok": True})


async def handle_delete_conversation(request: web.Request) -> web.Response:
    thread = request_thread(request)
    busy = _reply_in_flight(request, thread)
    if busy is not None:
        return busy
    if not delete_conversation(request.app["data_dir"], thread=thread,
                               session_id=request.match_info["id"]):
        return web.json_response(_CONVERSATION_NOT_FOUND, status=404)
    return web.json_response({"ok": True})
