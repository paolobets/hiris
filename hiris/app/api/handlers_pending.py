"""`GET /api/pending`: i due numeri dei pallini, in una richiesta sola.

Sta in un file suo e non dentro `handlers_agenda.py` o
`handlers_constructions.py` perche' legge DUE archivi e non appartiene a
nessuno dei due.

Esiste per non far leggere quattrocento righe serializzate a chi vuole due
interi: `GET /api/agenda` serve fino a 200 promesse, `GET /api/constructions`
altrettanto e prima SCRIVE (`store.scadi`). Questa rotta la chiamano tutti e
due i gusci a ogni apertura, a ogni risposta della chat e al ritorno del
fuoco sulla finestra: deve costare due `count(*)`.

**Le chiavi dicono cosa contano, non dove stanno.** `agenda_unread` e
`constructions_pending` sono asimmetriche apposta, perche' i due numeri
contano due cose diverse: sugli Impegni gli esiti che nessuno ha ancora
letto, sulle Proposte quelle in attesa di una risposta. Chiamarle `agenda` e
`constructions` -- simmetriche, come le rotte -- avrebbe nascosto proprio
questo al primo che legge il JSON, che avrebbe creduto di vedere due volte lo
stesso fatto.

**503 e non uno zero** quando un archivio manca. Il pallino che questa rotta
serve nasce per sostituirne uno morto: quello contava le segnalazioni del
Brain leggendo una rotta uscita con la fetta E3, e mostrava `0` quando quella
rotta rispondeva 404 (la lapide sta in `hiris-config.css`, dove vivevano le
sue quattro regole `.nav-badge`). Non era inutile: era peggio -- diceva «non
c'e' niente da guardare» quando la verita' era «non lo so». Chi consuma
questa rotta puo' distinguere le due cose solo se gliele distingue il codice
HTTP.

E' un metodo "safe": nessun `csrf_middleware` da rispettare, ma passa
comunque dagli stessi middleware di ogni altra rotta -- non ne salta nessuno.
"""
from __future__ import annotations

import time

from aiohttp import web

from ..chat_thread import request_thread
from .soffitto import per_richiesta


def _proposals_pending(app) -> int:
    """Quante proposte da fare a mano aspettano una tua decisione."""
    observations = app.get("observations")
    if observations is None:
        return 0
    return len(observations.proposals(pending_only=True))


async def handle_get_pending(request: web.Request) -> web.Response:
    agenda = request.app.get("agenda")
    constructions = request.app.get("constructions")
    # Un archivio solo che manca basta a rendere la risposta parziale, e una
    # risposta parziale qui e' indistinguibile da una completa: il guscio
    # riceverebbe un numero e un buco, e il buco diventerebbe un pallino
    # spento -- cioe' di nuovo «non c'e' niente» al posto di «non lo so».
    if agenda is None or constructions is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    # **Le Proposte sono di chi costruisce** (spec 2026-09-26 §3, decisione
    # 5): a chi non puo' deciderle il pallino conta zero, e `can_build` dice
    # al guscio se mostrare la voce -- lo decide il server a ogni risposta,
    # non un ruolo indovinato dal browser. Nascondere la voce non e' la
    # difesa: la difesa e' il 403 di `soffitto.require_builder` sulla pagina.
    # Il soffitto qui si LEGGE e basta: gli Impegni restano del filo di chi
    # guarda, amministratore compreso.
    can_build = (await per_richiesta(request.app, request))["costruire"]
    return web.json_response({
        # Il pallino degli Impegni e' di chi guarda (spec 2026-09-26 §2): gli
        # esiti non letti del SUO filo, dal confine -- come la pagina.
        "agenda_unread": agenda.count_unread(request_thread(request)),
        # **Le due code, sommate** (spec 2026-09-21 §3): un pallino che ne
        # contasse una sola direbbe un numero piu' piccolo di quello che ti
        # aspetta -- ed e' peggio di nessun pallino, perche' sembra un conto.
        "constructions_pending": (constructions.count_pending(now=time.time())
                                  + _proposals_pending(request.app)) if can_build else 0,
        "can_build": can_build,
    })
