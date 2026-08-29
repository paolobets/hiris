"""Le cinque rotte della pagina Costruzioni.

Non serializzano niente per conto proprio: la forma di una costruzione e' UNA
e vive in `azione/costruzione/versioni.py::_row`, gia' usata dall'archivio.
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

# Un solo testo per «quell'id non esiste», usato sia da chi legge sia da chi
# agisce: due frasi diverse per lo stesso fatto sarebbero una piccola
# incoerenza da mantenere sincronizzata a mano per sempre.
_NON_TROVATA = "non ho nessuna costruzione con quell'identificatore."


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
        {"costruzioni": archivio.list(pending_only=solo_aperte, limit=200)})


async def handle_get_costruzione(request: web.Request) -> web.Response:
    archivio = _archivio(request)
    if archivio is None:
        return web.json_response({"errore": "archivio non disponibile"}, status=503)
    riga = archivio.read(request.match_info["id"])
    if riga is None:
        return web.json_response({"errore": _NON_TROVATA}, status=404)
    return web.json_response({"costruzione": riga})


async def _agisci(request: web.Request, verbo: str) -> web.Response:
    archivio = _archivio(request)
    officina = request.app.get("officina")
    if archivio is None or officina is None:
        return web.json_response({"errore": "officina non disponibile"}, status=503)
    ident = request.match_info["id"]
    if archivio.read(ident) is None:
        return web.json_response({"errore": _NON_TROVATA}, status=404)
    metodo = getattr(officina, verbo)
    esito = await metodo(ident, actor="pagina", exchange=None, now=time.time())
    if "errore" in esito:
        # Un guasto di TRASPORTO verso Home Assistant (ondata finale, punto
        # 7, terza pulizia) non e' «la proposta non e' piu' in attesa»: e' la
        # stessa indisponibilita' che le due GET, qui sopra, dichiarano con
        # 503. Prima questo ramo appiattiva ogni errore dell'officina su 409,
        # anche quando la causa era Home Assistant irraggiungibile. Il flag
        # e' interno (`Workshop._fallita`/`_rete`): non deve uscire nel corpo
        # della risposta.
        status = 503 if esito.pop("guasto_rete", False) else 409
        return web.json_response(esito, status=status)
    return web.json_response(esito)


async def handle_conferma_costruzione(request: web.Request) -> web.Response:
    return await _agisci(request, "applica")


async def handle_ripristina_costruzione(request: web.Request) -> web.Response:
    return await _agisci(request, "ripristina")


async def handle_rifiuta_costruzione(request: web.Request) -> web.Response:
    """Il «no»: si scrive nell'archivio e basta.

    Non passa dall'officina, e non e' una svista: non c'e' niente da scrivere
    su Home Assistant, e farlo passare da li' darebbe a un rifiuto la stessa
    superficie di rischio di una conferma.
    """
    archivio = _archivio(request)
    if archivio is None:
        return web.json_response({"errore": "archivio non disponibile"}, status=503)
    ident = request.match_info["id"]
    if archivio.read(ident) is None:
        return web.json_response({"errore": _NON_TROVATA}, status=404)
    esito = archivio.mark_cancelled(ident, now=time.time())
    if "errore" in esito:
        return web.json_response(esito, status=409)
    return web.json_response(esito)
