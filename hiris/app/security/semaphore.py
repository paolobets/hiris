"""Semaforo unificato: autorita' unica per il tier (green/yellow/red/off) di
un'entita' o di un dominio.

Centralizzava (a) la denylist dei domini pericolosi — prima duplicata nella
sola Sentinella — e (b) la logica dei tier in un'unica funzione pura
``gate_action``, applicata da OGNI superficie che eseguiva un
``call_ha_service`` autorizzato da LLM/agenti: dispatcher (chat/agenti/
gateway) e task differiti. Le letture non passano mai di qui.

Review finale fetta E2, I-1 (cascata verificata): ``gate_action``,
``normalize_target``/``NormalizedTarget`` e ``GateVerdict`` sono uscite --
`task_engine.py` (`_run_action`) era il loro ULTIMO chiamante di produzione
(il dispatcher che le chiamava anche lui e' uscito nel Task 7); rimosso il
ramo `call_ha_service` da `_run_action` per I-1, non restava nessuna
superficie che eseguisse ancora un `call_ha_service` da gate-are. Restano
``DANGEROUS_DOMAINS``, ``effective_tier`` (re-export) e
``summarize_autonomy``: servono ancora la Sentinella (``watcher/executor.py``,
propone/nega secondo il tier) e il riepilogo Autonomia dell'editor Chatbot.
"""
from __future__ import annotations

from ..api.handlers_gateway_policy import effective_tier  # re-export, unica fonte

# Domini che non vanno MAI auto-attuati, qualunque sia il tier configurato.
# Difesa in profondità: batte il semaforo e la whitelist per-agente.
DANGEROUS_DOMAINS = frozenset(
    {"lock", "alarm_control_panel", "cover", "siren", "garage_door"}
)


def _domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if "." in entity_id else ""


def summarize_autonomy(entities: list[str], tiers: dict, entity_tiers: dict) -> dict:
    """Per-entity/pattern tier counts for DISPLAY (Chatbot editor's Autonomia
    summary):

    - a pattern whose domain is in ``DANGEROUS_DOMAINS`` is counted under
      ``"dangerous"``, never under a tier, denylist-first exactly like the
      Sentinel's own gate (``watcher/executor.py``) orders its checks.
    - everything else uses ``effective_tier`` (per-entity override beats the
      domain tier, unconfigured domain fails closed to 'off').

    ``entities`` accepts both concrete entity ids (``cover.living``) and the
    domain-glob patterns the Scope picker's pills add (``cover.*``): both
    resolve through the same domain-prefix logic ``effective_tier`` already
    uses internally, so no separate glob-handling branch is needed here.
    """
    counts = {"green": 0, "yellow": 0, "red": 0, "off": 0, "dangerous": 0}
    tiers = tiers or {}
    entity_tiers = entity_tiers or {}
    for pattern in entities or []:
        if not isinstance(pattern, str):
            continue
        if _domain_of(pattern) in DANGEROUS_DOMAINS:
            counts["dangerous"] += 1
            continue
        level = effective_tier(pattern, tiers, entity_tiers)
        counts[level if level in counts else "off"] += 1
    return counts
