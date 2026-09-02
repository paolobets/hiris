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
"""
from __future__ import annotations

import time

from aiohttp import web

from .boundary import occurrence_out


async def handle_get_agenda(request: web.Request) -> web.Response:
    store = request.app.get("agenda")
    if store is None:
        return web.json_response({"agenda": [], "error": "archivio non disponibile"},
                                 status=503)
    show_all = request.query.get("all") in ("1", "true", "si")
    return web.json_response({"agenda": store.list(solo_in_sospeso=not show_all,
                                                    limit=200)})


async def handle_delete_promise(request: web.Request) -> web.Response:
    store = request.app.get("agenda")
    if store is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    ident = request.match_info["id"]
    if store.read(ident) is None:
        return web.json_response({"error": "non ho nessuna promessa con quell'identificatore."},
                                 status=404)
    occurrence = store.cancel(ident, now=time.time())
    if "errore" in occurrence:
        return web.json_response(occurrence_out(occurrence), status=409)
    return web.json_response(occurrence_out(occurrence))


async def handle_get_execution(request: web.Request) -> web.Response:
    """La riga di cronaca di un'esecuzione -- cosi' com'e', da `Journal.read`.

    404 «non ne ho piu' il dettaglio» copre sia l'id sbagliato sia la riga
    potata dopo 90 giorni (`journal.py::EXECUTIONS_RETENTION_S`): dal
    lato della pagina sono la stessa cosa -- non c'e' piu' niente da mostrare
    -- e nessuna delle due merita un errore che sembri un guasto.
    """
    journal = request.app.get("journal")
    if journal is None:
        return web.json_response({"error": "cronaca non disponibile"}, status=503)
    ident = request.match_info["id"]
    row = journal.read(ident)
    if row is None:
        return web.json_response(
            {"error": "non ho nessuna esecuzione con quell'identificatore."},
            status=404)
    return web.json_response({"execution": row})
