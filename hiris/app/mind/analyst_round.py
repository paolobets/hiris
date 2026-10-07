"""Il giro dell'**analista**, la parte che vive fuori da `server.py`.

Oggi ci sta solo la scrittura dell'analisi (`write_analysis`), spostata da
`server.py` senza una riga di logica cambiata (N65-2, 07/10/2026): la scrittura
e' il punto in cui il «rimetti» dell'analista si confronta con la casa, e la
regola del proprietario del 06/10/2026 vieta codice nuovo dentro `server.py`.
Il resto del giro (`analyst_round`, il raccoglitore del ponte) ci arriva alla
Chiusura dello sprint, quando `server.py` si spezza in commit di solo
spostamento (`analisi/2026-10-06-file-monolitici-proposta.md`, passo 2).
"""
from __future__ import annotations

import logging

from ..home_space.house import House
from . import analyst, analyst_turn

logger = logging.getLogger(__name__)

#: Quanti giorni di misure si consegnano all'analista. Trenta e' il numero
#: della spec §9 -- «trenta giorni di misure stanno in un prompt» -- e
#: misurato sulla casa vera sono ~35.000 token.
ANALYST_DAYS = 30


def write_analysis(app, store, day: str, occurrence: dict) -> None:
    """Scrive l'analisi, o dice perche' non l'ha scritta.

    **Una risposta rifiutata non si archivia**: un'analisi con dentro dei
    problemi non e' un'analisi, e scriverla direbbe che quel giorno e' stato
    analizzato. Il giro dopo riprova, perche' `analysis(giorno)` resta `None`.

    **Il «rimetti» si confronta con la casa di adesso** (N65-2): `app` serve
    solo a leggerla, dagli stessi archivi vivi da cui la legge l'osservatore.
    """
    analysis = occurrence.get("analisi")
    if analysis is None:
        if occurrence.get("problemi"):
            logger.warning("analista: risposta rifiutata per %s -- %s",
                           day, " \u00b7 ".join(occurrence["problemi"]))
        return
    # **Il fondamento si legge QUI**, non da chi chiama: e' lo stato dei
    # resoconti nel momento in cui l'analisi viene scritta, e le due strade --
    # il turno diretto e la risposta raccolta dal ponte -- devono registrarlo
    # allo stesso modo. Il ponte rilegge le serie adesso (vedi
    # `_collect_analyst_turn`), quindi «adesso» e' il fondamento giusto per
    # entrambe.
    analysis = {**analysis,
                "fondamento": analyst_turn.fondamento(
                    store.report_stamps(limit=ANALYST_DAYS))}
    house = House.read(app.get("home_space_store"), app.get("entity_cache"))
    store.replace_analysis(day, analyst.bring_back(store, analysis, house))
    logger.info("analista: analisi di %s scritta (%d osservazioni)",
                day, len(analysis.get("osservazioni") or []))
