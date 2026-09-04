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


async def handle_get_pending(request: web.Request) -> web.Response:
    agenda = request.app.get("agenda")
    constructions = request.app.get("constructions")
    # Un archivio solo che manca basta a rendere la risposta parziale, e una
    # risposta parziale qui e' indistinguibile da una completa: il guscio
    # riceverebbe un numero e un buco, e il buco diventerebbe un pallino
    # spento -- cioe' di nuovo «non c'e' niente» al posto di «non lo so».
    if agenda is None or constructions is None:
        return web.json_response({"error": "archivio non disponibile"}, status=503)
    return web.json_response({
        "agenda_unread": agenda.count_unread(),
        "constructions_pending": constructions.count_pending(now=time.time()),
    })
