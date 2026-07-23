"""Semaforo unificato: gate UNICO per ogni azione verso la casa.

Centralizza (a) la denylist dei domini pericolosi — prima duplicata nella sola
Sentinella — e (b) la logica dei tier (green/yellow/red/off) in un'unica funzione
pura ``gate_action``, applicata da OGNI superficie che esegue un ``call_ha_service``
autorizzato da LLM/agenti: dispatcher (chat/agenti/gateway) e task differiti.
Le letture non passano mai di qui.
"""
from __future__ import annotations

from collections import namedtuple

from ..api.handlers_gateway_policy import effective_tier  # re-export, unica fonte

# Domini che non vanno MAI auto-attuati, qualunque sia il tier configurato.
# Difesa in profondità: batte il semaforo e la whitelist per-agente.
DANGEROUS_DOMAINS = frozenset(
    {"lock", "alarm_control_panel", "cover", "siren", "garage_door"}
)

# decision ∈ {"allow", "deny_dangerous", "deny_off", "confirm"}
GateVerdict = namedtuple("GateVerdict", ["decision", "tier", "reason"])


def _domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if "." in entity_id else ""


def gate_action(
    *,
    domain: str,
    service: str,
    entity_ids: list[str],
    tiers: dict,
    entity_tiers: dict,
) -> GateVerdict:
    """Decide il destino di un'azione ``domain.service`` sui ``entity_ids``.

    Ordine: (1) denylist domini pericolosi — dominio fornito O derivato da una
    qualsiasi entità target; (2) tier effettivo — off/mancante = deny_off,
    green = allow, yellow/red = confirm (il peggiore fra i target vince).
    Senza entity target si usa il tier del dominio.
    """
    tiers = tiers or {}
    entity_tiers = entity_tiers or {}
    # (1) denylist — batte tutto
    dangerous = domain in DANGEROUS_DOMAINS or any(
        _domain_of(e) in DANGEROUS_DOMAINS for e in entity_ids
    )
    if dangerous:
        return GateVerdict("deny_dangerous", None,
                           "Dominio pericoloso bloccato dalla denylist.")
    # (2) tier effettivo (peggiore fra i target)
    if entity_ids:
        levels = [effective_tier(e, tiers, entity_tiers) for e in entity_ids]
    else:
        levels = [tiers.get(domain, "off")]
    if any(lv == "off" for lv in levels):
        return GateVerdict("deny_off", "off", "Azione bloccata dal semaforo (off).")
    if "red" in levels:
        return GateVerdict("confirm", "red", "Azione ad alto rischio: richiede conferma.")
    if "yellow" in levels:
        return GateVerdict("confirm", "yellow", "Azione a rischio: richiede conferma.")
    if all(lv == "green" for lv in levels):
        return GateVerdict("allow", "green", "")
    return GateVerdict("deny_off", "off", "Tier non riconosciuto: bloccato per sicurezza.")
