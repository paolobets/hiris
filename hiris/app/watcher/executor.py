from __future__ import annotations
from typing import Awaitable, Callable
from .signals import Decision
from ..security.semaphore import DANGEROUS_DOMAINS as _DANGEROUS_DOMAINS, effective_tier

async def execute(decision: Decision, wake, *, tiers: dict, entity_tiers: dict,
                  notify: Callable[..., Awaitable], act: Callable[[dict], Awaitable],
                  propose: Callable[..., Awaitable], allow_green_auto: bool) -> str:
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
    if tier == "green" and allow_green_auto:
        await act(action)
        await notify(f"{decision.message} (fatto)", title=title)
        return "act"
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
