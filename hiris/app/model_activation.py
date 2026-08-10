"""Derivazione dei provider AI attivi (SP-2).

Un provider è ATTIVO solo se il suo toggle `provider_*` è true E la sua
credenziale è presente. Migrazione retro-compat: se TUTTI i toggle sono al
default false (install pre-SP-2), l'attivazione è derivata dalla presenza
credenziale — così un install esistente continua a funzionare identico senza
riscrivere config.yaml.
"""
from __future__ import annotations

_PROVIDERS = ("subscription", "claude", "openai", "openrouter", "ollama")


def derive_active_providers(cfg: dict, creds: dict) -> dict[str, bool]:
    toggles = {
        "subscription": bool(cfg.get("provider_subscription", False)),
        "claude": bool(cfg.get("provider_claude", False)),
        "openai": bool(cfg.get("provider_openai", False)),
        "openrouter": bool(cfg.get("provider_openrouter", False)),
        "ollama": bool(cfg.get("provider_ollama", False)),
    }
    legacy = not any(toggles.values())
    active: dict[str, bool] = {}
    for p in _PROVIDERS:
        has_cred = bool(creds.get(p, False))
        if legacy:
            # migrazione: attivo = credenziale presente (+ flag legacy abbonamento)
            if p == "subscription":
                active[p] = has_cred and bool(cfg.get("chat_via_subscription", False))
            else:
                active[p] = has_cred
        else:
            active[p] = toggles[p] and has_cred
    return active


def reconcile_chain(
    strategy_order: list[str],
    manual: list[str] | None,
    active_providers: dict,
) -> list[str]:
    """Build the effective boot-time model chain (SP-2 final review fix).

    ``strategy_order`` is the provider order for the current strategy (e.g.
    ``_STRATEGY_ORDER["balanced"]``); ``manual`` is the persisted
    ``chain_order`` override (``None``/empty when the user never saved one);
    ``active_providers`` maps provider name -> bool (Task 1 activation).

    Behaviour:
      - No manual override: the chain is simply the active providers in
        strategy order.
      - Manual override present: it is filtered to active providers
        (inactive/unknown names dropped), THEN any active provider from
        ``strategy_order`` that is missing from that filtered list is
        APPENDED, in strategy order. This mirrors the frontend's
        ``buildDisplayChain`` (models-route.js) and closes a fail-open seam:
        a partial persisted ``chain_order`` (saved back when fewer providers
        were active) must never silently drop a provider that becomes active
        later — that provider's runner is built and reachable via explicit
        model selection regardless, so leaving it out of the chain would only
        make the chat fallback order look more restricted than it actually is.
      - If the result is empty either way (e.g. all overrides invalid AND no
        active strategy providers), it falls back to ``strategy_order``
        filtered to active providers -- callers still get an explicit,
        non-empty-when-possible chain rather than an empty one degrading to
        undefined router behavior.
    """
    strategy_active = [n for n in strategy_order if active_providers.get(n)]
    if manual:
        chain = [n for n in manual if active_providers.get(n)]
        for n in strategy_active:
            if n not in chain:
                chain.append(n)
    else:
        chain = list(strategy_active)
    if not chain:
        chain = list(strategy_active)
    return chain
