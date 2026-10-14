"""`GET /api/health` -- stato, versione, impronta del guscio e diagnostica.

Uscito da `server.py` per solo spostamento (Tappa 7, Task 11).
"""
from aiohttp import web

from ..conservazione import declarations
from ..mind.day_report import LAST_REPAIR_KEY
from ..mind.judgments import TYPE_JUDGMENTS_STATUS_KEY
from ..version import read_version
from .shell import BUILD_STAMP_KEY
from .soffitto import restricted_person


async def handle_health(request: web.Request) -> web.Response:
    # `ponte` porta i due fatti che nessun file del repository puo' dire: quale
    # CLI e' arrivata DAVVERO nel container (il `Dockerfile` dice cosa e' stato
    # chiesto, non cosa gira) e se il ponte parli con l'abbonamento invece che
    # con una chiave a consumo (`apiKeySource: none` = abbonamento). Finche'
    # nessun turno e' passato `stato` e' `non_visto`: «non ancora visto» non e'
    # «assente» (C-30).
    from ..agent.runner import last_bridge_init
    # `riparazione` porta l'esito della riaggregazione d'avvio: se e' saltata,
    # PERCHE', e quali resoconti ha scritto lo stesso. E' `null` finche' non e'
    # girata. Nasce da un difetto rimasto invisibile per due rilasci
    # (14/09/2026): le uscite anticipate scrivevano nel log dell'add-on, che da
    # fuori non si legge, e la casa poteva solo dire «nessun resoconto» senza
    # dire perche'. Stessa legge di `ponte` qui sopra -- un fatto che nessun
    # file del repository puo' dire.
    # `istantanea` dice da dove viene l'istantanea dei giudizi sui tipi -- il
    # sapere o il solo seme -- e, se dal seme, perche' (spec 2026-09-16 §8).
    # **Si chiamava `giudizi`, e quella parola qui era doppia** (giro di
    # correzioni 1, punto 3): in `/api/mind/knowledge` `giudizi` e' l'ELENCO
    # delle righe, qui era lo STATO dell'istantanea. Due cose diverse dette con
    # una parola sola si separano alla fonte, non a valle.
    #
    # **A una persona che non amministra, solo stato, versione e impronta del
    # guscio** (spec 2026-09-27, ruling R-2.23 e fix round 1, I1): il resto e'
    # diagnostica dell'add-on, che Home Assistant a lei non mostrerebbe;
    # l'impronta no -- il guscio la porta gia' scritta, e senza `build-check.js`
    # non saprebbe dirle che la sua pagina e' vecchia. Il ruolo e' quello che
    # il cancello ha letto e lasciato sulla richiesta: nessuna seconda domanda
    # a Home Assistant (`restricted_person`). Servizi, ponte e sviluppo invariati.
    #
    # `conservazione` dice per quanto tempo HIRIS ricorda ogni cosa (D7 della
    # Tappa 8): per ogni tabella di ogni archivio la finestra in giorni (`null`
    # = per sempre) e la ragione, chieste alle dichiarazioni degli archivi
    # (`conservazione.declarations`). In sola lettura: una finestra e' una
    # decisione scritta accanto allo schema, non una manopola.
    if restricted_person(request):
        return web.json_response({"status": "ok", "version": read_version(),
                                  "build": request.app.get(BUILD_STAMP_KEY, "")})
    return web.json_response({"status": "ok", "version": read_version(),
                              "build": request.app.get(BUILD_STAMP_KEY, ""),
                              "ponte": last_bridge_init(),
                              "riparazione": request.app.get(LAST_REPAIR_KEY),
                              "istantanea": request.app.get(TYPE_JUDGMENTS_STATUS_KEY),
                              "conservazione": declarations(request.app)})
