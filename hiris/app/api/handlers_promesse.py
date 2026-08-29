"""Le tre rotte delle promesse: guardare, disdire, e guardare cosa e' cambiato.

Non serializzano niente per conto proprio. La forma di una promessa e' UNA, e
vive in `schedulatore/promessa.py::serializza` (gia' usata dall'archivio): se
questa rotta ne costruisse una sua, la pagina e la chat mostrerebbero due
cose diverse della stessa promessa il primo giorno in cui qualcuno aggiunge
un campo da una parte sola.

I codici HTTP portano la distinzione che conta: 404 «non esiste», 409
«esiste ma non e' piu' disdicibile». Un 400 unico avrebbe costretto la
pagina a leggere il testo dell'errore per sapere quale dei due mostrare.

**`GET /api/esecuzioni/{id}`** vive qui e non in un file suo (review finale
della fetta, rilievo ①): non serializza niente di suo neppure lei --
`Cronaca.leggi` gia' lo fa (`azione/cronaca.py::_riga`) -- ed e' la sorella
delle due sopra per lo stesso motivo per cui loro sono insieme: la pagina
Promesse le chiama tutte e tre. La promessa NON ricopia i fatti
dell'esecuzione (spec §8): si collega per `esecuzione_id`, e chi vuole
sapere cosa e' cambiato chiede qui -- a parte, per identificatore, mai
appiattito dentro `serializza()`. E' una rotta di lettura: nessun
`csrf_middleware` da rispettare (e' un metodo "safe", stessa esenzione di
`GET /api/promesse`), ma passa comunque dagli stessi middleware di ogni
altra rotta -- non ne salta nessuno.
"""
from __future__ import annotations

import time

from aiohttp import web


async def handle_get_promesse(request: web.Request) -> web.Response:
    archivio = request.app.get("promesse")
    if archivio is None:
        return web.json_response({"promesse": [], "errore": "archivio non disponibile"},
                                 status=503)
    tutte = request.query.get("tutte") in ("1", "true", "si")
    return web.json_response({"promesse": archivio.list(solo_in_sospeso=not tutte,
                                                       limit=200)})


async def handle_delete_promessa(request: web.Request) -> web.Response:
    archivio = request.app.get("promesse")
    if archivio is None:
        return web.json_response({"errore": "archivio non disponibile"}, status=503)
    ident = request.match_info["id"]
    if archivio.read(ident) is None:
        return web.json_response({"errore": "non ho nessuna promessa con quell'identificatore."},
                                 status=404)
    esito = archivio.cancel(ident, now=time.time())
    if "errore" in esito:
        return web.json_response(esito, status=409)
    return web.json_response(esito)


async def handle_get_esecuzione(request: web.Request) -> web.Response:
    """La riga di cronaca di un'esecuzione -- cosi' com'e', da `Cronaca.leggi`.

    404 «non ne ho piu' il dettaglio» copre sia l'id sbagliato sia la riga
    potata dopo 90 giorni (`cronaca.py::CONSERVAZIONE_ESECUZIONI_S`): dal
    lato della pagina sono la stessa cosa -- non c'e' piu' niente da mostrare
    -- e nessuna delle due merita un errore che sembri un guasto.
    """
    cronaca = request.app.get("cronaca")
    if cronaca is None:
        return web.json_response({"errore": "cronaca non disponibile"}, status=503)
    ident = request.match_info["id"]
    riga = cronaca.leggi(ident)
    if riga is None:
        return web.json_response(
            {"errore": "non ho nessuna esecuzione con quell'identificatore."},
            status=404)
    return web.json_response({"esecuzione": riga})
