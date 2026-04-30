from __future__ import annotations

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
        },
        "required": ["type", "name", "description", "config", "routing_reason"],
    },
}


async def create_automation_proposal(
    proposal_store,
    type: str,
    name: str,
    description: str,
    config: dict,
    routing_reason: str,
) -> dict:
    if proposal_store is None:
        return {"error": "ProposalStore not available"}
    try:
        pid = await proposal_store.save(
            {
                "type": type,
                "name": name,
                "description": description,
                "config": config,
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
