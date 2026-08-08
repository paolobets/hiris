from __future__ import annotations
import logging
import re
from typing import Any

from .dashboard_backups import save_backup

logger = logging.getLogger(__name__)

VALID_KINDS = frozenset({"dashboard", "script", "scene"})
VALID_DASHBOARD_MODES = frozenset({"create", "replace"})

_KIND_PROPOSAL_TYPE = {
    "dashboard": "ha_dashboard",
    "script": "ha_script",
    "scene": "ha_scene",
}
_KIND_LABEL = {"dashboard": "Dashboard", "script": "Script", "scene": "Scena"}

_SLUG_RE = re.compile(r"^[a-z0-9_]+$")                 # script/scene object_id
_URL_PATH_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")  # dashboard: HA richiede un trattino

_MAX_CONFIG_BYTES = 256 * 1024  # cap difensivo sulla dimensione del config


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


async def apply_ha_config(ha_client: Any, normalized: dict,
                          data_dir: str | None = None) -> dict:
    """Materializza una config normalizzata su HA. Condivisa dal percorso chat e
    dall'apply di una proposta pending.

    Difensivo: `normalized` puo' arrivare da una proposta costruita fuori da
    `normalize_config_inputs` (es. dal gateway MCP), quindi le chiavi non sono
    garantite. Mai sollevare KeyError: si ritorna sempre un dict {"error": ...}.

    `mode` (solo dashboard): 'create' (default, retro-compatibile con le
    proposte gia' salvate) crea una nuova plancia; 'replace' sovrascrive la
    config di una plancia esistente, salvando prima uno snapshot in data_dir."""
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
    ha_config = normalized.get("ha_config")
    mode = normalized.get("mode") or "create"
    if mode not in VALID_DASHBOARD_MODES:
        # Messaggio fisso: il valore arriva da una proposta e stampare il repr
        # di un oggetto arbitrario non aggiunge nulla di utile al chiamante.
        return {"error": "mode dashboard non valido: usa 'create' oppure 'replace'"}
    if not slug or not isinstance(ha_config, dict):
        return {"error": "config non valida: kind mancante o non supportato"}

    if mode == "replace":
        # Leggere PRIMA di scrivere: se la config attuale non e' leggibile
        # (plancia inesistente o in modalita' YAML) si annulla tutto, cosi' non
        # si sovrascrive mai senza aver messo al sicuro lo stato precedente.
        current = await ha_client.get_lovelace_config(slug)
        if not isinstance(current, dict) or current.get("error"):
            msg = current.get("error") if isinstance(current, dict) else "errore sconosciuto"
            return {"error": f"plancia non leggibile, sostituzione annullata: {msg}"}
        if data_dir:
            if not save_backup(data_dir, slug, current):
                return {
                    "error": (
                        "non e' stato possibile salvare la copia di sicurezza della "
                        "configurazione attuale della plancia: la sostituzione e' stata "
                        "annullata e la plancia non e' stata modificata"
                    )
                }
        else:
            logger.warning(
                "apply dashboard replace su %s senza data_dir: nessuno snapshot salvato", slug)
        return await ha_client.save_dashboard_config(slug, ha_config)

    name = normalized.get("name")
    if not name:
        return {"error": "config non valida: kind mancante o non supportato"}
    return await ha_client.create_dashboard(
        slug, name, ha_config,
        icon=normalized.get("icon"),
        show_in_sidebar=normalized.get("show_in_sidebar", True),
    )


def build_config_proposal(normalized: dict, *, description: str | None = None,
                          routing_reason: str | None = None) -> dict:
    """Build the ProposalStore record for a pending HA-config creation.

    I default descrivono l'origine MCP (il primo chiamante). `description` e
    `routing_reason` permettono a un altro percorso autonomo — oggi la
    Sentinella, che propone il proprio rimedio come script — di riusare la
    stessa costruzione del record senza dichiarare un'origine che non e' la sua.
    """
    kind = normalized["kind"]
    label = _KIND_LABEL[kind]
    return {
        "type": _KIND_PROPOSAL_TYPE[kind],
        "name": normalized["name"],
        "description": description if description else (
            f"{label} '{normalized['name']}' generata via MCP — in attesa di approvazione."
        ),
        "config": normalized,
        "routing_reason": routing_reason if routing_reason else (
            "Richiesta via gateway MCP: la creazione di config HA richiede "
            "l'approvazione dell'operatore nella pagina Proposte di HIRIS."
        ),
    }
