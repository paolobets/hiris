from __future__ import annotations
from typing import Awaitable, Callable
from .signals import Decision
from ..security.semaphore import DANGEROUS_DOMAINS as _DANGEROUS_DOMAINS, effective_tier

async def execute(decision: Decision, wake, *, tiers: dict, entity_tiers: dict,
                  notify: Callable[..., Awaitable],
                  propose: Callable[..., Awaitable]) -> str:
    # La 2.0 conosce e non agisce: qui non c'e' piu' un adattatore `act` --
    # nessun esito di questa funzione tocca mai HA. Un tempo il tier "green"
    # con l'opt-in `allow_green_auto` chiamava `act(action)` ed eseguiva
    # davvero il servizio; quel ramo e' uscito (fetta E2, Task 6) e "green"
    # ora prende esattamente la stessa strada di "yellow": una proposta che
    # l'utente deve approvare.
    title = "HIRIS Sentinella"
    if decision.verdict == "falso_positivo":
        return "skip"
    action = decision.action
    if not action or not action.get("entity_id"):
        await notify(decision.message, title=title)
        return "notify"
    eid = action["entity_id"]
    dom_supplied = action.get("domain")
    dom_entity = eid.split(".", 1)[0] if "." in eid else ""
    if dom_supplied in _DANGEROUS_DOMAINS or dom_entity in _DANGEROUS_DOMAINS:
        await notify(decision.message, title=title)
        return "alert"
    tier = effective_tier(eid, tiers or {}, entity_tiers or {})
    if tier in ("green", "yellow"):
        # L'esito vero lo conosce solo chi ha provato a proporre: se la proposta
        # non e' stata creata (azione non confezionabile, salvataggio fallito)
        # l'adattatore ripiega sulla notifica e lo dice qui, cosi' la timeline
        # non registra "propose" per un evento senza nessuna proposta. Un
        # adattatore che non ritorna nulla mantiene il comportamento storico.
        return await propose(decision, wake) or "propose"
    # red / off → solo allerta
    await notify(decision.message, title=title)
    return "alert"
