from __future__ import annotations
import re
from typing import Any

VALID_KINDS = frozenset({"dashboard", "script", "scene"})

_KIND_PROPOSAL_TYPE = {
    "dashboard": "ha_dashboard",
    "script": "ha_script",
    "scene": "ha_scene",
}
_KIND_LABEL = {"dashboard": "Dashboard", "script": "Script", "scene": "Scena"}

_SLUG_RE = re.compile(r"^[a-z0-9_]+$")                 # script/scene object_id
_URL_PATH_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")  # dashboard: HA richiede un trattino

_MAX_CONFIG_BYTES = 256 * 1024  # cap difensivo sulla dimensione del config

CREATE_HA_CONFIG_TOOL_DEF = {
    "name": "create_ha_config",
    "description": (
        "Crea un artefatto di configurazione Home Assistant: una dashboard Lovelace "
        "('plancia'), uno script o una scena. Dalla chat viene creato subito su HA. "
        "Le dashboard sono additive (nuova voce in sidebar). Fornisci un config HA valido."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["dashboard", "script", "scene"]},
            "name": {"type": "string", "description": "Titolo leggibile dell'artefatto"},
            "slug": {
                "type": "string",
                "description": ("id tecnico. script/scene: a-z 0-9 _ . "
                               "dashboard: url_path con almeno un trattino (es. 'casa-mia')."),
            },
            "config": {
                "type": "object",
                "description": ("Config HA. script: {sequence:[...]}. scene: {entities:{...}}. "
                               "dashboard: {views:[...]} (config Lovelace)."),
            },
            "icon": {"type": "string", "description": "Solo dashboard: icona mdi (opzionale)"},
            "show_in_sidebar": {"type": "boolean", "description": "Solo dashboard (default true)"},
        },
        "required": ["kind", "name", "slug", "config"],
    },
}


def normalize_config_inputs(inputs: dict) -> dict:
    """Validate + normalize the tool inputs. Raises ValueError on any problem.

    Returned dict shape (re-used verbatim as the pending proposal's `config`):
    {"kind","slug","name","icon","show_in_sidebar","ha_config"}
    """
    kind = inputs.get("kind")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind non valido: {kind!r} (usa dashboard|script|scene)")
    name = inputs.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name mancante o vuoto")
    slug = inputs.get("slug")
    if not isinstance(slug, str):
        raise ValueError("slug mancante")
    config = inputs.get("config")
    if not isinstance(config, dict) or not config:
        raise ValueError("config vuoto o non valido")
    if len(str(config).encode("utf-8", "ignore")) > _MAX_CONFIG_BYTES:
        raise ValueError("config troppo grande")

    if kind == "dashboard":
        if not _URL_PATH_RE.match(slug):
            raise ValueError("slug dashboard non valido: serve un url_path con un trattino (es. 'casa-mia')")
        if "views" not in config or not isinstance(config.get("views"), list):
            raise ValueError("config dashboard non valida: manca la lista 'views'")
    else:
        if not _SLUG_RE.match(slug):
            raise ValueError(f"slug {kind} non valido: usa solo a-z 0-9 _")

    return {
        "kind": kind,
        "slug": slug,
        "name": name.strip(),
        "icon": inputs.get("icon") if kind == "dashboard" else None,
        "show_in_sidebar": bool(inputs.get("show_in_sidebar", True)) if kind == "dashboard" else None,
        "ha_config": config,
    }


async def apply_ha_config(ha_client: Any, normalized: dict) -> dict:
    """Materialize a normalized config on HA. Shared by the chat dispatch path and
    the pending-proposal apply path.

    Defensive: `normalized` may originate from a proposal built outside
    `normalize_config_inputs` (e.g. `create_automation_proposal` via MCP), so required
    keys are not guaranteed to be present. Never raise KeyError — always return an
    {"error": ...} dict instead, so callers can turn it into a clean HTTP error."""
    kind = normalized.get("kind")
    if kind not in VALID_KINDS:
        return {"error": "config non valida: kind mancante o non supportato"}
    if kind in ("script", "scene"):
        slug = normalized.get("slug")
        ha_config = normalized.get("ha_config")
        if not slug or not isinstance(ha_config, dict):
            return {"error": "config non valida: kind mancante o non supportato"}
        if kind == "script":
            return await ha_client.create_script(slug, ha_config)
        return await ha_client.create_scene(slug, ha_config)
    # kind == "dashboard"
    slug = normalized.get("slug")
    name = normalized.get("name")
    ha_config = normalized.get("ha_config")
    if not slug or not name or not isinstance(ha_config, dict):
        return {"error": "config non valida: kind mancante o non supportato"}
    return await ha_client.create_dashboard(
        slug, name, ha_config,
        icon=normalized.get("icon"),
        show_in_sidebar=normalized.get("show_in_sidebar", True),
    )


def build_config_proposal(normalized: dict) -> dict:
    """Build the ProposalStore record for an MCP-originated creation (pending)."""
    kind = normalized["kind"]
    label = _KIND_LABEL[kind]
    return {
        "type": _KIND_PROPOSAL_TYPE[kind],
        "name": normalized["name"],
        "description": f"{label} '{normalized['name']}' generata via MCP — in attesa di approvazione.",
        "config": normalized,
        "routing_reason": (
            "Richiesta via gateway MCP: la creazione di config HA richiede "
            "l'approvazione dell'operatore nella pagina Proposte di HIRIS."
        ),
    }
