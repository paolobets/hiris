from __future__ import annotations
from typing import Awaitable, Callable
from .signals import Decision
from ..api.handlers_gateway_policy import effective_tier

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
    tier = effective_tier(action["entity_id"], tiers or {}, entity_tiers or {})
    if tier == "green" and allow_green_auto:
        await act(action)
        await notify(f"{decision.message} (fatto)", title=title)
        return "act"
    if tier in ("green", "yellow"):
        await propose(decision, wake)
        return "propose"
    # red / off → solo allerta
    await notify(decision.message, title=title)
    return "alert"
