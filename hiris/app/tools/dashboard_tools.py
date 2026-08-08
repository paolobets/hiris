"""Tool plance (dashboard Lovelace) per il Chatbot.

L'LLM legge le plance esistenti e PROPONE una creazione o una sostituzione:
non scrive mai direttamente su HA. Il gate umano e' la review della proposta,
come per le automazioni; la rete di sicurezza sulle sostituzioni e' lo
snapshot/undo (proxy/dashboard_backups.py)."""
from __future__ import annotations

import logging
from typing import Any

from ..proxy.proposta_config import _URL_PATH_RE, _MAX_CONFIG_BYTES

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({"create", "replace"})

LIST_DASHBOARDS_TOOL_DEF = {
    "name": "list_dashboards",
    "description": (
        "Elenca le plance (dashboard Lovelace) esistenti su Home Assistant, "
        "con url_path e titolo. Usalo prima di proporre una modifica, per "
        "sapere quale plancia esiste e come si chiama."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

GET_DASHBOARD_CONFIG_TOOL_DEF = {
    "name": "get_dashboard_config",
    "description": (
        "Legge la configurazione completa (viste e card) di una plancia "
        "esistente. Usalo PRIMA di proporre una sostituzione, cosi' la nuova "
        "configurazione parte da quella attuale e non perdi contenuti."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url_path": {"type": "string", "description": "url_path della plancia (es. 'casa-mia')"},
        },
        "required": ["url_path"],
    },
}

PROPOSE_DASHBOARD_TOOL_DEF = {
    "name": "propose_dashboard",
    "description": (
        "Propone di creare una nuova plancia oppure di sostituire quella "
        "esistente. NON scrive su Home Assistant: salva una proposta che "
        "l'utente attiva dalla sezione Proposte. "
        "mode='create': nuova plancia, servono url_path (con almeno un "
        "trattino, es. 'casa-mia') e title. "
        "mode='replace': sostituisce INTERAMENTE la configurazione della "
        "plancia indicata — leggi prima get_dashboard_config e includi anche "
        "le viste da conservare, altrimenti spariscono. "
        "Per plance molto grandi proponi poche viste per volta."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["create", "replace"]},
            "url_path": {"type": "string", "description": "url_path della plancia"},
            "title": {"type": "string", "description": "Titolo in sidebar (obbligatorio con mode='create')"},
            "config": {"type": "object", "description": "Config Lovelace completa: {views:[...]}"},
            "reason": {"type": "string", "description": "Perche' proponi questa plancia"},
        },
        "required": ["mode", "url_path", "config", "reason"],
    },
}


async def propose_dashboard(proposal_store: Any, mode: str, url_path: str,
                            config: dict, reason: str,
                            title: str | None = None) -> dict:
    """Valida e salva una proposta ha_dashboard. Non tocca mai HA.

    Fail-closed come validate_agentbot: una proposta malformata viene
    RIFIUTATA, non salvata — la lezione del bug #2 era che le proposte non
    canoniche venivano marcate applied senza alcun effetto."""
    if proposal_store is None:
        return {"error": "ProposalStore non disponibile"}
    # isinstance esplicito: gli input arrivano da una tool call del modello e
    # non sono garantiti stringhe. `(mode or "").strip()` solleverebbe
    # AttributeError su un non-stringa (es. un numero), finendo nella except
    # generica del dispatcher invece di essere rifiutato qui: fail-closed.
    mode = mode.strip() if isinstance(mode, str) else ""
    if mode not in VALID_MODES:
        return {"error": f"mode non valido: {mode!r} (usa create|replace)"}
    if not isinstance(url_path, str) or not _URL_PATH_RE.match(url_path):
        return {"error": "url_path non valido: serve un url_path con almeno un trattino (es. 'casa-mia')"}
    # Volutamente PIU' STRETTO di HAClient.save_dashboard_config, che accetta
    # anche la forma a strategia ({"strategy": {...}}, senza 'views') perche'
    # HA la accetta e il ripristino di uno snapshot deve poterla riscrivere.
    # Qui il contenuto lo scrive un LLM: il tool accetta solo cio' che il
    # modello puo' legittimamente proporre, cioe' viste esplicite. Una
    # "strategia" proposta dal modello non sarebbe una plancia che ha davvero
    # composto, quindi resta fuori.
    if not isinstance(config, dict) or not isinstance(config.get("views"), list):
        return {"error": "config non valida: serve un dict Lovelace con la lista 'views'"}
    if len(str(config).encode("utf-8", "ignore")) > _MAX_CONFIG_BYTES:
        return {"error": "config troppo grande: proponi meno viste per volta"}
    if mode == "create":
        if not isinstance(title, str) or not title.strip():
            return {"error": "title obbligatorio con mode='create'"}
        title = title.strip()

    label = title or url_path
    descr = (f"Crea la nuova plancia '{label}'." if mode == "create"
             else f"Sostituisce interamente la configurazione della plancia '{label}'.")
    record = {
        "type": "ha_dashboard",
        "name": label,
        "description": descr,
        "config": {
            "kind": "dashboard",
            "mode": mode,
            "slug": url_path,
            "name": title,
            "ha_config": config,
        },
        "routing_reason": reason,
    }
    try:
        pid = await proposal_store.save(record)
    except Exception:
        # Mai fare echo di str(exc) verso il chiamante: puo' contenere dettagli
        # interni (percorsi su disco, errori sqlite). Log lato server, messaggio
        # generico ma azionabile verso l'LLM/utente.
        logger.exception("propose_dashboard: salvataggio proposta fallito")
        return {"error": "Impossibile salvare la proposta. Riprova piu' tardi."}
    return {
        "proposal_id": pid,
        "status": "pending",
        "message": (f"Proposta plancia '{label}' salvata. "
                    "L'utente puo' attivarla dalla sezione Proposte."),
    }
