"""Le tre rotte delle promesse: guardare, disdire, e guardare cosa e' cambiato.

Non serializzano niente per conto proprio. La forma di una promessa e' UNA, e
vive in `keeper/promise.py::serializza` (gia' usata dall'archivio): se
questa rotta ne costruisse una sua, la pagina e la chat mostrerebbero due
cose diverse della stessa promessa il primo giorno in cui qualcuno aggiunge
un campo da una parte sola.

I codici HTTP portano la distinzione che conta: 404 «non esiste», 409
«esiste ma non e' piu' disdicibile». Un 400 unico avrebbe costretto la
pagina a leggere il testo dell'errore per sapere quale dei due mostrare.

**`GET /api/executions/{id}`** vive qui e non in un file suo (review finale
della fetta, rilievo ①): non serializza niente di suo neppure lei --
`Journal.read` gia' lo fa (`action/journal.py::_row`) -- ed e' la sorella
delle due sopra per lo stesso motivo per cui loro sono insieme: la pagina
Promesse le chiama tutte e tre. La promessa NON ricopia i fatti
dell'esecuzione (spec §8): si collega per `esecuzione_id`, e chi vuole
sapere cosa e' cambiato chiede qui -- a parte, per identificatore, mai
appiattito dentro `serializza()`. E' una rotta di lettura: nessun
`csrf_middleware` da rispettare (e' un metodo "safe", stessa esenzione di
`GET /api/agenda`), ma passa comunque dagli stessi middleware di ogni
altra rotta -- non ne salta nessuno.

**Ogni rotta lavora sul filo di chi chiede** (fetta «il seguito delle chat
divise», spec 2026-09-26 §2): il filo lo dice il confine
(`chat_thread.request_thread`), mai la query o il corpo. Un id di un altro
filo risponde ESATTAMENTE come uno inesistente -- stesso status, stesso corpo:
un 403 o un 409 direbbero a Marta che Paolo ha qualcosa in programma. Gli
amministratori non sono esenti: una promessa e' di chi l'ha chiesta, non di
chi puo' costruire.
"""
from __future__ import annotations

import time

from aiohttp import web

from ..chat_thread import adopt_if_owner, request_thread, without_thread
from .boundary import occurrence_out

# Vedi `handle_mark_read`: sta qui e non in `keeper/`, perche' e' un limite
# della PORTA HTTP (quanto accetto in una richiesta), non una regola
# dell'archivio.
_MAX_IDS = 500

# Il corpo del 404, uno solo per «non esiste» e «non e' tuo».
_PROMISE_NOT_FOUND = {"error": "non ho nessuna promessa con quell’identificatore."}
_EXECUTION_NOT_FOUND = {"error": "non ho nessuna esecuzione con quell’identificatore."}


async def handle_get_agenda(request: web.Request) -> web.Response:
    store = request.app.get("agenda")
    if store is None:
        return web.json_response({"agenda": [], "error": "archivio non disponibile"},
                                 status=503)
    thread = request_thread(request)
    # Le promesse di prima vanno al proprietario alla sua prima lettura, con
    # la stessa regola e nello stesso gesto della cronologia. Solo qui, fra
    # le rotte degli Impegni: una DELETE o un «letto» su un'orfana non
    # adottano prima di agire -- rispondono come per un id che non esiste.
    await adopt_if_owner(request.app, request, thread)
    show_all = request.query.get("all") in ("1", "true", "si")
    rows = store.list(thread=thread, solo_in_sospeso=not show_all, limit=200)
    return web.json_response({"agenda": [without_thread(r) for r in rows]})


async def handle_delete_promise(request: web.Request) -> web.Response:
    store = request.app.get("agenda")
    if store is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    ident = request.match_info["id"]
    thread = request_thread(request)
    if store.read_in_thread(ident, thread) is None:
        return web.json_response(_PROMISE_NOT_FOUND, status=404)
    occurrence = store.cancel(ident, thread=thread, now=time.time())
    if "errore" in occurrence:
        return web.json_response(occurrence_out(occurrence), status=409)
    return web.json_response(occurrence_out(
        {**occurrence, "promessa": without_thread(occurrence["promessa"])}))


async def handle_mark_read(request: web.Request) -> web.Response:
    """Segna letti gli esiti che la pagina ha appena mostrato.

    Prende gli identificatori e non «tutti i non letti»: la pagina segna cio'
    che ha messo sullo schermo, e cio' che non ha disegnato deve restare
    acceso.

    Un id sconosciuto, o di una promessa ancora in sospeso, NON e' un errore:
    non viene contato, e basta. La pagina manda cio' che ha disegnato e non
    deve conoscere le regole dell'archivio -- che sono in
    `AgendaStore.mark_read`, l'unico posto in cui vivono. Il numero che torna
    dice quante righe ha toccato davvero, che e' l'unica risposta onesta a
    una richiesta di questa forma.
    """
    store = request.app.get("agenda")
    if store is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "corpo non leggibile"}, status=400)
    ids = body.get("ids") if isinstance(body, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return web.json_response({"error": "serve una lista `ids` di stringhe."},
                                 status=400)
    # Un tetto, perche' `mark_read` genera un segnaposto SQL per id: oltre
    # `SQLITE_MAX_VARIABLE_NUMBER` (32766) SQLite solleva, e un errore
    # d'ingresso uscirebbe come 500. Il tetto del corpo di aiohttp (1 MB)
    # lascerebbe passare decine di migliaia di identificatori. Non e' una
    # difesa da attacco -- questa rotta sta dietro CSRF e in rete locale --
    # e' che un 400 dice la verita' e un 500 no. `MAX_IN_SOSPESO` e' 50 e
    # lo storico e' potato a 90 giorni: la pagina non ne disegnera' mai
    # tanti, quindi il tetto non puo' tagliare una richiesta legittima.
    if len(ids) > _MAX_IDS:
        return web.json_response(
            {"error": f"troppi identificatori in una volta (il tetto e' {_MAX_IDS})."},
            status=400)
    return web.json_response({"marked": store.mark_read(
        ids, thread=request_thread(request), now=time.time())})


async def handle_get_execution(request: web.Request) -> web.Response:
    """La riga di cronaca di un'esecuzione -- cosi' com'e', da `Journal.read`.

    404 «non ne ho piu' il dettaglio» copre sia l'id sbagliato sia la riga
    potata dopo 90 giorni (`journal.py::EXECUTIONS_RETENTION_S`): dal
    lato della pagina sono la stessa cosa -- non c'e' piu' niente da mostrare
    -- e nessuna delle due merita un errore che sembri un guasto.

    **Un'esecuzione prodotta da una promessa e' di chi l'ha chiesta**: per
    un altro filo -- e per una promessa orfana, finche' nessuno l'ha adottata
    -- risponde lo stesso 404 di un id inesistente. Un'esecuzione che nessuna
    promessa ha prodotto resta com'era: la spec tocca solo le promesse.
    """
    journal = request.app.get("journal")
    if journal is None:
        return web.json_response({"error": "cronaca non disponibile"}, status=503)
    ident = request.match_info["id"]
    row = journal.read(ident)
    if row is None:
        return web.json_response(_EXECUTION_NOT_FOUND, status=404)
    agenda = request.app.get("agenda")
    if agenda is None:
        # Senza l'archivio delle promesse non si sa di chi sia: nel dubbio non
        # si mostra, come le altre rotte di questo file senza archivio.
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    promise = agenda.read_by_execution(ident)
    if promise is not None and promise["thread"] != request_thread(request):
        return web.json_response(_EXECUTION_NOT_FOUND, status=404)
    return web.json_response({"execution": row})
