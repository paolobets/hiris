from __future__ import annotations

# `normalize_config_inputs`, `apply_ha_config` e `build_config_proposal` sono
# state spostate in ..proxy.proposta_config: non sono strumenti, sono "la
# forma di una proposta" e "l'applicazione di una proposta approvata", usate
# anche da moduli fuori da tools/ (watcher/sentinel_proposal.py,
# api/handlers_execute.py, api/handlers_proposals.py). Qui resta solo la
# definizione del tool per l'LLM.

CREATE_HA_CONFIG_TOOL_DEF = {
    "name": "create_ha_config",
    "description": (
        "Crea uno script o una scena Home Assistant. Dalla chat viene creato "
        "subito su HA. Fornisci un config HA valido. "
        "Per le plance (dashboard Lovelace) NON usare questo strumento: usa "
        "propose_dashboard, che passa dall'approvazione dell'utente."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["script", "scene"]},
            "name": {"type": "string", "description": "Titolo leggibile dell'artefatto"},
            "slug": {"type": "string", "description": "id tecnico: a-z 0-9 _"},
            "config": {
                "type": "object",
                "description": "Config HA. script: {sequence:[...]}. scene: {entities:{...}}.",
            },
        },
        "required": ["kind", "name", "slug", "config"],
    },
}
