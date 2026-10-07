"""`GET /api/pending`: i due numeri dei pallini, in una richiesta sola.

Sta in un file suo e non dentro `handlers_agenda.py` o
`handlers_constructions.py` perche' legge DUE archivi e non appartiene a
nessuno dei due.

Esiste per non far leggere quattrocento righe serializzate a chi vuole due
interi: `GET /api/agenda` serve fino a 200 promesse, `GET /api/constructions`
altrettanto. Questa rotta la chiamano tutti e
due i gusci a ogni apertura, a ogni risposta della chat e al ritorno del
fuoco sulla finestra. Oggi costa due `count(*)` (`count_unread`,
`count_pending`) piu' una lettura intera: le proposte dell'attuatore si
contano leggendole (`_proposals_pending`), perche' il loro archivio non ha un
conteggio.

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
from .admission import NOT_ADMITTED
from .boundary import error_response
from .soffitto import denies, request_ceiling


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
        return error_response(503, "archivio non disponibile")
    # **Le Proposte e le pagine di configurazione sono di chi amministra**
    # (spec 2026-09-26 §3, decisione 5; spec 2026-09-27 §4): a chi non puo'
    # deciderle il pallino conta zero, e `can_build` e `can_configure` dicono
    # al guscio se mostrare le voci -- lo decide il server a ogni risposta,
    # non un ruolo indovinato dal browser. Nascondere una voce non e' la
    # difesa: la difesa e' il gesto `amministrare` delle rotte
    # (`admission.ADMISSION`), che il confine chiede prima del gestore.
    # Il soffitto qui si LEGGE e basta: gli Impegni restano del filo di chi
    # guarda, amministratore compreso.
    #
    # **Una domanda sola** (F-01, F-03, Tappa 7): fino al 07/10/2026
    # `can_build` leggeva `ceiling["costruire"]` nudo e `can_configure`
    # chiedeva `denies(..., "amministrare")`, e in sviluppo dicevano due cose
    # diverse (BACKLOG, «In sviluppo `can_configure` e' vero mentre
    # `can_build` e' falso»). Le due chiavi restano perche' il guscio le legge
    # entrambe: portano lo stesso fatto.
    #
    # Il soffitto viene dal ruolo che il cancello ha GIA' letto
    # (`request_ceiling`): una lettura dei ruoli per richiesta, non due.
    ceiling = request_ceiling(request)
    can_configure = not denies(ceiling, "amministrare", request.get("soggetto"))
    can_build = can_configure
    answer = {
        # Il pallino degli Impegni e' di chi guarda (spec 2026-09-26 §2): gli
        # esiti non letti del SUO filo, dal confine -- come la pagina.
        "agenda_unread": agenda.count_unread(request_thread(request)),
        # **Le due code, sommate** (spec 2026-09-21 §3): un pallino che ne
        # contasse una sola direbbe un numero piu' piccolo di quello che ti
        # aspetta -- ed e' peggio di nessun pallino, perche' sembra un conto.
        "constructions_pending": (constructions.count_pending(now=time.time())
                                  + _proposals_pending(request.app)) if can_build else 0,
        "can_build": can_build,
        "can_configure": can_configure,
    }
    # **Il testo del rifiuto viaggia qui** (fix round 1 del Task 4): il
    # guscio `/config` lo scrive su una pagina di configurazione aperta per
    # indirizzo, invece di chiederlo a una rotta negata -- che lasciava nel
    # registro del cancello una riga falsa sulla pagina. E' la costante del
    # cancello, non una copia. All'amministratore non arriva: la sua
    # risposta resta quella di prima.
    if not can_configure:
        answer["configure_refusal"] = NOT_ADMITTED
    return web.json_response(answer)
