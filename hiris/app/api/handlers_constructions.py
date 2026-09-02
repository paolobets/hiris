"""Le cinque rotte della pagina Costruzioni.

Non serializzano niente per conto proprio: la forma di una costruzione e' UNA
e vive in `action/construction/revisions.py::_row`, gia' usata dall'archivio.
Una seconda forma costruita qui renderebbe la pagina e la chat due racconti
diversi dello stesso atto il primo giorno in cui qualcuno aggiunge un campo da
una parte sola (fondamenta 3).

**Confermare dalla pagina non passa dalla guardia del turno**, e non e' una
scappatoia: la guardia esiste per impedire a un MODELLO di darsi il permesso
da solo (spec §7). Un clic sulla pagina e' gia' l'umano. L'origine lo dice
esplicitamente -- `pagina` -- e finisce nella cronaca, cosi' resta scritto chi
ha deciso.

I codici portano la distinzione che conta: 404 «non esiste», 409 «esiste ma
non e' piu' in attesa», 503 «non disponibile» (l'archivio per le due GET e
per il rifiuto, l'archivio o l'officina per conferma e ripristino -- vedi i
messaggi qui sotto, che sono testo VERO e non una parafrasi). Un 400 unico
avrebbe costretto la pagina a leggere il testo dell'errore per sapere quale
dei tre mostrare.

**Il rifiuto non passa dall'officina.** Le altre due POST scrivono su Home
Assistant; questa no -- il «no» del proprietario si scrive nell'archivio e
basta, e farlo passare dall'officina gli darebbe la stessa superficie di
rischio di una conferma. Non e' una quinta rotta uguale alle altre: e'
un'assenza deliberata.
"""
from __future__ import annotations

import time

from aiohttp import web

from .boundary import occurrence_out

# Un solo testo per «quell'id non esiste», usato sia da chi legge sia da chi
# agisce: due frasi diverse per lo stesso fatto sarebbero una piccola
# incoerenza da mantenere sincronizzata a mano per sempre.
_NOT_FOUND = "non ho nessuna costruzione con quell'identificatore."


def _store(request):
    return request.app.get("costruzioni")


async def handle_get_constructions(request: web.Request) -> web.Response:
    store = _store(request)
    if store is None:
        return web.json_response(
            {"constructions": [], "error": "archivio non disponibile"}, status=503)
    # Le scadute si segnano PRIMA di elencare, o la pagina mostrerebbe come
    # «da approvare» proposte che l'officina rifiuterebbe di applicare -- e il
    # bottone mentirebbe.
    store.scadi(time.time())
    pending_only = request.query.get("pending_only") in ("1", "true", "si")
    return web.json_response(
        {"constructions": store.list(pending_only=pending_only, limit=200)})


async def handle_get_construction(request: web.Request) -> web.Response:
    store = _store(request)
    if store is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    row = store.read(request.match_info["id"])
    if row is None:
        return web.json_response({"error": _NOT_FOUND}, status=404)
    return web.json_response({"construction": row})


async def _act(request: web.Request, verb: str) -> web.Response:
    store = _store(request)
    workshop = request.app.get("officina")
    if store is None or workshop is None:
        return web.json_response({"error": "officina non disponibile"}, status=503)
    ident = request.match_info["id"]
    if store.read(ident) is None:
        return web.json_response({"error": _NOT_FOUND}, status=404)
    method = getattr(workshop, verb)
    occurrence = await method(ident, actor="pagina", exchange=None, now=time.time())
    if "errore" in occurrence:
        # Un guasto di TRASPORTO verso Home Assistant (ondata finale, punto
        # 7, terza pulizia) non e' «la proposta non e' piu' in attesa»: e' la
        # stessa indisponibilita' che le due GET, qui sopra, dichiarano con
        # 503. Prima questo ramo appiattiva ogni errore dell'officina su 409,
        # anche quando la causa era Home Assistant irraggiungibile. Il flag
        # e' interno (`Workshop._fallita`/`_rete`): non deve uscire nel corpo
        # della risposta.
        status = 503 if occurrence.pop("guasto_rete", False) else 409
        return web.json_response(occurrence_out(occurrence), status=status)
    return web.json_response(occurrence_out(occurrence))


async def handle_confirm_construction(request: web.Request) -> web.Response:
    return await _act(request, "apply")


async def handle_restore_construction(request: web.Request) -> web.Response:
    return await _act(request, "restore")


async def handle_reject_construction(request: web.Request) -> web.Response:
    """Il «no»: si scrive nell'archivio e basta.

    Non passa dall'officina, e non e' una svista: non c'e' niente da scrivere
    su Home Assistant, e farlo passare da li' darebbe a un rifiuto la stessa
    superficie di rischio di una conferma.
    """
    store = _store(request)
    if store is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    ident = request.match_info["id"]
    if store.read(ident) is None:
        return web.json_response({"error": _NOT_FOUND}, status=404)
    occurrence = store.mark_cancelled(ident, now=time.time())
    if "errore" in occurrence:
        return web.json_response(occurrence_out(occurrence), status=409)
    return web.json_response(occurrence_out(occurrence))
