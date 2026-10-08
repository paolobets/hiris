"""La ricostruzione dell'anagrafe quando la casa cambia: l'antirimbalzo.

Spostato da `server.py` l'08/10/2026 (Tappa 8, Task 1), senza cambiare una
riga di logica: il seguito della ricostruzione -- le parole degli stati, e la
riconciliazione degli archivi -- cresce fuori da `server.py`, che tiene solo
l'iscrizione.
"""
from __future__ import annotations

import asyncio
import logging

from ..background import spawn as _spawn
from .topology import rebuild

logger = logging.getLogger(__name__)


def schedule_registry_rebuild(client, store, delay: float = 3.0, *,
                              then=None):
    """Restituisce `trigger(event_type)`: ricostruisce l'anagrafe, una volta sola.

    `then`, se c'e', si attende DOPO ogni ricostruzione riuscita: e' cio' che
    dipende dalla cornice appena letta. In produzione sono le parole degli
    stati (`prime_state_translations`, A-14): un cambio di lingua arriva come
    `core_config_updated`, e le parole si rileggono nella lingua nuova invece
    di aspettare il giro dei cinque minuti. Dopo ogni ricostruzione e non solo
    dopo quell'evento, perche' `read` risponde dalla cache finche' versione e
    lingua non cambiano: chiederla in piu' non costa una lettura.

    Riorganizzare la casa in Home Assistant produce una raffica di eventi —
    spostare dieci entita' ne emette dieci. Ricostruire a ogni evento
    significherebbe dieci letture di tutti i registri per un unico gesto
    dell'utente: si aspetta che la raffica finisca, e si rilegge una volta.

    Un guasto viene registrato e basta: l'ascoltatore deve sopravvivere a un
    Home Assistant che si riavvia, o dopo il primo intoppo l'anagrafe resta
    ferma per sempre senza che nessuno lo sappia.
    """
    state: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(delay)
            await rebuild(client, store)
            if then is not None:
                await then()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("ricostruzione dell'anagrafe fallita: %s", exc)

    def trigger(event_type: str) -> None:
        pending = state["attesa"]
        if pending is not None and not pending.done():
            pending.cancel()
        # _spawn(), non un asyncio.create_task(...) nudo: tiene un riferimento
        # forte finche' la ricostruzione non finisce (review C/#15) -- vedi il
        # commento in cima a `background.py`.
        state["attesa"] = _spawn(_fra_poco(), name="ricostruzione_anagrafe")

    return trigger
