"""Le due rotte delle promesse: guardare, e disdire.

Non serializzano niente per conto proprio. La forma di una promessa e' UNA, e
vive in `schedulatore/promessa.py::serializza` (gia' usata dall'archivio): se
questa rotta ne costruisse una sua, la pagina e la chat mostrerebbero due
cose diverse della stessa promessa il primo giorno in cui qualcuno aggiunge
un campo da una parte sola.

I codici HTTP portano la distinzione che conta: 404 «non esiste», 409
«esiste ma non e' piu' disdicibile». Un 400 unico avrebbe costretto la
pagina a leggere il testo dell'errore per sapere quale dei due mostrare.
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
    return web.json_response({"promesse": archivio.elenca(solo_in_sospeso=not tutte,
                                                          limite=200)})


async def handle_delete_promessa(request: web.Request) -> web.Response:
    archivio = request.app.get("promesse")
    if archivio is None:
        return web.json_response({"errore": "archivio non disponibile"}, status=503)
    ident = request.match_info["id"]
    if archivio.leggi(ident) is None:
        return web.json_response({"errore": "non ho nessuna promessa con quell'identificatore."},
                                 status=404)
    esito = archivio.disdici(ident, adesso=time.time())
    if "errore" in esito:
        return web.json_response(esito, status=409)
    return web.json_response(esito)
