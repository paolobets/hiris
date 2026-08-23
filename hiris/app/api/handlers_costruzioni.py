"""Le quattro rotte della pagina Costruzioni.

Non serializzano niente per conto proprio: la forma di una costruzione e' UNA
e vive in `azione/costruzione/versioni.py::_riga`, gia' usata dall'archivio.
Una seconda forma costruita qui renderebbe la pagina e la chat due racconti
diversi dello stesso atto il primo giorno in cui qualcuno aggiunge un campo da
una parte sola (fondamenta 3).

**Confermare dalla pagina non passa dalla guardia del turno**, e non e' una
scappatoia: la guardia esiste per impedire a un MODELLO di darsi il permesso
da solo (spec §7). Un clic sulla pagina e' gia' l'umano. L'origine lo dice
esplicitamente -- `pagina` -- e finisce nella cronaca, cosi' resta scritto chi
ha deciso.

I codici portano la distinzione che conta: 404 «non esiste», 409 «esiste ma
non e' piu' in attesa», 503 «archivio non disponibile». Un 400 unico avrebbe
costretto la pagina a leggere il testo dell'errore per sapere quale dei tre
mostrare.
"""
from __future__ import annotations

import time

from aiohttp import web


def _archivio(request):
    return request.app.get("costruzioni")


async def handle_get_costruzioni(request: web.Request) -> web.Response:
    archivio = _archivio(request)
    if archivio is None:
        return web.json_response(
            {"costruzioni": [], "errore": "archivio non disponibile"}, status=503)
    # Le scadute si segnano PRIMA di elencare, o la pagina mostrerebbe come
    # «da approvare» proposte che l'officina rifiuterebbe di applicare -- e il
    # bottone mentirebbe.
    archivio.scadi(time.time())
    solo_aperte = request.query.get("in_attesa") in ("1", "true", "si")
    return web.json_response(
        {"costruzioni": archivio.elenca(solo_in_attesa=solo_aperte, limite=200)})


async def handle_get_costruzione(request: web.Request) -> web.Response:
    archivio = _archivio(request)
    if archivio is None:
        return web.json_response({"errore": "archivio non disponibile"}, status=503)
    riga = archivio.leggi(request.match_info["id"])
    if riga is None:
        return web.json_response(
            {"errore": "non ho nessuna costruzione con quell'identificatore."},
            status=404)
    return web.json_response({"costruzione": riga})


async def _agisci(request: web.Request, verbo: str) -> web.Response:
    archivio = _archivio(request)
    officina = request.app.get("officina")
    if archivio is None or officina is None:
        return web.json_response({"errore": "officina non disponibile"}, status=503)
    ident = request.match_info["id"]
    if archivio.leggi(ident) is None:
        return web.json_response(
            {"errore": "non ho nessuna costruzione con quell'identificatore."},
            status=404)
    metodo = getattr(officina, verbo)
    esito = await metodo(ident, origine="pagina", turno=None, adesso=time.time())
    if "errore" in esito:
        return web.json_response(esito, status=409)
    return web.json_response(esito)


async def handle_conferma_costruzione(request: web.Request) -> web.Response:
    return await _agisci(request, "applica")


async def handle_ripristina_costruzione(request: web.Request) -> web.Response:
    return await _agisci(request, "ripristina")
