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
