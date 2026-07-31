from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tipi che handle_apply_proposal sa APPLICARE davvero. Un tipo fuori da questo
# set cadrebbe nel ramo "status-only" (marca applied senza toccare HA) -> lo
# rifiutiamo alla creazione invece di salvarlo e perderlo in silenzio (bug #2).
_VALID_PROPOSAL_TYPES = frozenset(
    {"ha_automation", "hiris_agent", "ha_dashboard", "ha_script", "ha_scene"})
# Alias comuni che gli LLM usano al posto dei valori canonici (root cause bug #2:
# il Chatbot ha proposto type='automation').
_PROPOSAL_TYPE_ALIASES = {"automation": "ha_automation", "agent": "hiris_agent"}

CREATE_AUTOMATION_PROPOSAL_TOOL_DEF = {
    "name": "create_automation_proposal",
    "description": (
        "Propose a new automation to the user. Use this after explaining your "
        "routing choice (HA native vs HIRIS agent). The proposal is saved as "
        "disabled/pending — the user must explicitly activate it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["ha_automation", "hiris_agent"]},
            "name": {"type": "string"},
            "description": {
                "type": "string",
                "description": "Human-readable explanation of what this does",
            },
            "config": {
                "type": "object",
                "description": (
                    "HA automation YAML dict (trigger/condition/action/mode/alias) "
                    "or HIRIS agent config dict. To MODIFY an existing automation, "
                    "INCLUDE its numeric 'id' (as returned by get_automation_config) "
                    "in this config so approval OVERWRITES it. To create a NEW "
                    "automation, OMIT 'id'."
                ),
            },
            "routing_reason": {
                "type": "string",
                "description": "Why this level was chosen over the alternative",
            },
            "automation_id": {
                "type": "string",
                "description": (
                    "Optional. The numeric unique id of an existing HA automation "
                    "to MODIFY. Alternative to putting 'id' inside config (this "
                    "param wins if both are given). Omit for a brand-new automation."
                ),
            },
        },
        "required": ["type", "name", "description", "config", "routing_reason"],
    },
}


async def create_automation_proposal(
    proposal_store: Any,
    proposal_type: str,
    name: str,
    description: str,
    config: dict,
    routing_reason: str,
    automation_id: str | None = None,
) -> dict:
    if proposal_store is None:
        return {"error": "ProposalStore not available"}
    # Bug #2: normalizza gli alias di tipo e rifiuta i tipi sconosciuti. Il
    # Chatbot aveva proposto type='automation' (non 'ha_automation') -> l'apply
    # cadeva nel ramo status-only che NON scrive in HA (l'automazione "sembrava
    # applicata" ma non cambiava). Meglio fallire forte alla creazione.
    proposal_type = (proposal_type or "").strip()
    proposal_type = _PROPOSAL_TYPE_ALIASES.get(proposal_type, proposal_type)
    if proposal_type not in _VALID_PROPOSAL_TYPES:
        return {"error": (f"Tipo proposta non valido: {proposal_type!r}. "
                          f"Usa uno di: {', '.join(sorted(_VALID_PROPOSAL_TYPES))}")}
    # Bug #2 (overwrite vs duplicato): l'id nel config e' load-bearing all'apply
    # (create_automation vi sovrascrive l'automazione con quell'id). Precedenza:
    # automation_id esplicito > id gia' presente nel config (che l'LLM copia
    # leggendo l'automazione con get_automation_config). Se NESSUNO dei due c'e'
    # -> automazione NUOVA (nessun id, apply ne conia uno). Contratto invertito
    # rispetto a prima (che strippava l'id senza automation_id, rompendo il caso
    # "modifica"): ORA per creare una NUOVA automazione l'LLM deve OMETTERE l'id.
    cfg = config
    if proposal_type == "ha_automation" and isinstance(cfg, dict):
        _id = automation_id or cfg.get("id")
        if _id:
            cfg = {**cfg, "id": str(_id)}
    try:
        pid = await proposal_store.save(
            {
                "type": proposal_type,
                "name": name,
                "description": description,
                "config": cfg,
                "routing_reason": routing_reason,
            }
        )
        return {
            "proposal_id": pid,
            "status": "pending",
            "message": (
                f"Proposta '{name}' salvata. "
                "L'utente può attivarla dalla sezione Proposte."
            ),
        }
    except Exception as exc:
        # Never echo str(exc) back to the caller (same policy as the
        # dispatcher's own catch-all, dispatcher.py's bottom except): it can
        # leak internal detail (e.g. a raw sqlite3.OperationalError with a
        # file path). Log server-side, return a generic-but-useful message.
        logger.exception("create_automation_proposal: save failed")
        return {"error": "Impossibile salvare la proposta. Riprova più tardi."}
