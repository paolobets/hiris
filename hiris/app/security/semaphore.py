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

# review A/#5 (CONFIRMED HIGH, target-vs-data split): HA's call_service only
# reads `data` — `target` is a distinct dict the LLM/agent may use to scope a
# call (entity_id/area_id/device_id/label_id). If a caller gates on
# data.entity_id OR target.entity_id but forwards only `data` to HA, a call
# scoped via `target` to a single green entity arrives at HA with NO
# entity_id filter at all -> HA executes it domain-wide, actuating sibling
# entities that were never gated. NormalizedTarget/normalize_target is the
# ONE place that merges target into data and derives the entity_id set, so
# gated entities == executed entities on every call site.
NormalizedTarget = namedtuple("NormalizedTarget", ["data", "entity_ids", "has_group_target"])


def _as_entity_list(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, str)]
    return []


def normalize_target(data: dict | None, target: dict | None) -> NormalizedTarget:
    """Merge ``target`` into ``data`` for HA service execution and derive the
    entity_id set used for BOTH gating and execution (review A/#5).

    Call this ONCE, immediately after tier gating decides the action may
    proceed, and use its ``.data`` for the actual ``ha.call_service`` /
    persisted-task data — never the caller's raw ``data`` dict — so the
    entities that were gated are exactly the entities HA acts on:

    - ``entity_ids``: union of data.entity_id and target.entity_id (as a
      flat list of strings). Pass this to ``gate_action``.
    - ``data``: a NEW dict — the caller's ``data`` with ``entity_id`` set to
      the merged union (string if exactly one entity, else a list; omitted
      entirely if the union is empty, so a genuine domain-wide call with
      neither data nor target entity_id keeps working unchanged).
    - ``has_group_target``: True if area_id/device_id/label_id appears in
      EITHER data or target. A group target isn't resolvable to a per-entity
      tier — callers MUST fail-closed reject before gating when this is set
      (on every path: dispatcher AND task_engine — Fix #2/#8's guard must
      not be dispatcher-only).
    """
    merged_data = dict(data) if isinstance(data, dict) else {}
    target = target if isinstance(target, dict) else {}

    # HA honors area_id/device_id/label_id/floor_id as group targets (in target
    # AND inside service data). None resolves to a per-entity tier, so any of
    # them must fail-closed reject on unconfirmed paths — floor_id included
    # (HA >=2024.4, same era as label_id), else data={"floor_id":...} broadcasts
    # a whole floor while gated on a single green entity.
    _GROUP_KEYS = ("area_id", "device_id", "label_id", "floor_id")
    has_group_target = any(merged_data.get(k) or target.get(k) for k in _GROUP_KEYS)

    entity_ids = _as_entity_list(merged_data.get("entity_id"))
    for eid in _as_entity_list(target.get("entity_id")):
        if eid not in entity_ids:
            entity_ids.append(eid)

    if entity_ids:
        merged_data["entity_id"] = entity_ids[0] if len(entity_ids) == 1 else list(entity_ids)

    return NormalizedTarget(data=merged_data, entity_ids=entity_ids, has_group_target=has_group_target)

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
