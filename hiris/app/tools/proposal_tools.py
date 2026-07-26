from __future__ import annotations
from typing import Any

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
                "description": "HA automation YAML dict or HIRIS agent config dict",
            },
            "routing_reason": {
                "type": "string",
                "description": "Why this level was chosen over the alternative",
            },
            "automation_id": {
                "type": "string",
                "description": (
                    "ONLY when MODIFYING an existing HA automation: its numeric "
                    "unique id (from get_automation_config / get_ha_automations). "
                    "When set, approving the proposal OVERWRITES that automation "
                    "instead of creating a new one. Omit for a brand-new automation."
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
    # Modify-in-place: carry the target automation's id INSIDE the config (which
    # is persisted as-is), so create_automation reuses it at apply time and HA
    # overwrites the existing automation instead of creating a duplicate.
    cfg = config
    if automation_id and isinstance(cfg, dict):
        cfg = {**cfg, "id": str(automation_id)}
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
        return {"error": str(exc)}
