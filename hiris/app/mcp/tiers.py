from __future__ import annotations

import enum
from dataclasses import dataclass


class Tier(str, enum.Enum):
    READ = "read"
    SCHEDULE = "schedule"
    ACTION = "action"


@dataclass(frozen=True)
class ToolDef:
    name: str            # MCP tool name exposed to Claude
    tier: Tier
    hiris_tool: str      # tool name passed to HIRIS execute-API
    description: str


TOOLS: list[ToolDef] = [
    # --- READ ---
    ToolDef("get_home_status", Tier.READ, "get_home_status",
            "Snapshot delle entita' di casa e dei loro stati. Parti da qui per scoprire gli entity id e lo stato generale."),
    ToolDef("get_area_entities", Tier.READ, "get_area_entities",
            "Entita' raggruppate per area/stanza. Utile per mappare le stanze ai dispositivi."),
    ToolDef("get_entity_states", Tier.READ, "get_entity_states",
            "Stati correnti di una lista di entity id. Usalo dopo aver scoperto gli id."),
    ToolDef("get_history", Tier.READ, "get_history",
            "Dati storici/temporali delle entita' (trend, min/max/media, durate on/off). Sola lettura, output compresso. "
            "Es: andamento temperatura salotto ultimi 7 giorni; consumo energia ultimo mese."),
    ToolDef("get_automation_config", Tier.READ, "get_automation_config",
            "Read the full configuration (YAML-equivalent) of a Home Assistant "
            "automation created via the UI. Pass its entity_id, object_id or numeric "
            "id (use get_ha_automations to list them). READ-only."),
    ToolDef("get_advisories", Tier.READ, "get_advisories",
            "Segnalazioni di salute aperte rilevate dal Brain di HIRIS (batterie scariche, "
            "entita' non disponibili, automazioni rotte, domini pericolosi abilitati). "
            "Filtro opzionale per gravita' ('high'/'warn'/'info'). Sola lettura: non chiude "
            "ne' modifica una segnalazione."),
    # I due tool di diagnosi (get_logbook, render_template) NON sono esposti al
    # gateway. Il gateway e' una superficie remota e concede i tool di lettura
    # in blocco: derive_execute_policy include SEMPRE i READ_TOOLS, senza opt-in
    # per singolo tool, e le letture partono senza whitelist di entita'
    # (handlers_execute: "reads see the whole home").
    #   - render_template leggerebbe qualunque stato: un template non ha un
    #     entity_id da filtrare, quindi nessun perimetro potrebbe contenerlo.
    #   - get_logbook renderebbe enumerabile in blocco, dall'esterno, la
    #     cronologia dell'intera casa — serrature, allarme, presenze,
    #     chi-ha-fatto-cosa. Non e' un dato nuovo rispetto a get_history, ma e'
    #     enumerazione massiva invece che interrogazione mirata su entita' gia'
    #     note: una differenza di natura, non di grado.
    # E' una scelta di contenimento della superficie remota, non un limite
    # tecnico: entrambi funzionano gia' qui, e riabilitarli richiede una riga
    # (piu' il conteggio in tests/test_mcp_server_build.py e le asserzioni di
    # assenza in tests/test_diagnostics_tools.py). In chat e agli agenti locali
    # restano pienamente disponibili — vedi claude_runner.py.
    ToolDef("recall_knowledge", Tier.READ, "recall_knowledge",
            "Cerca nella knowledge base HIRIS e negli insight storici settimanali (non sensibili). "
            "Es: tendenze o variazioni recenti."),
    # --- SCHEDULE / PROPOSE ---
    ToolDef("create_task", Tier.SCHEDULE, "create_task",
            "Pianifica un task HIRIS (trigger + azioni). Le azioni possono includere "
            "send_notification (anche notifiche persistenti nel dashboard HA, channel "
            "'ha_persistent') e call_ha_service (solo su entita' verdi nel semaforo). "
            "Richiede conferma (gate di sicurezza)."),
    ToolDef("list_tasks", Tier.SCHEDULE, "list_tasks",
            "Elenca i task HIRIS pianificati."),
    ToolDef("cancel_task", Tier.SCHEDULE, "cancel_task",
            "Annulla un task HIRIS pianificato. Richiede sempre conferma."),
    ToolDef("create_automation_proposal", Tier.SCHEDULE, "create_automation_proposal",
            "Propone un'automazione HA per revisione umana (NON applicata automaticamente)."),
    ToolDef("send_notification", Tier.SCHEDULE, "send_notification",
            "Invia una notifica all'utente (informativa, non controlla dispositivi). "
            "channel: 'ha_persistent' = notifica persistente nel dashboard Home Assistant "
            "(title + message; per rimuoverla passa notification_id con message vuoto); "
            "'ha_push' = push sul telefono (title + message); 'apprise' = Telegram/WhatsApp/ntfy; "
            "'retropanel' = toast kiosk. Per le notifiche usa SEMPRE questo tool, mai call_service."),
    ToolDef("save_knowledge", Tier.SCHEDULE, "save_knowledge",
            "Salva un elemento di conoscenza (in attesa di approvazione umana in HIRIS)."),
    # --- ACTION (confirmation required, gated dal semaforo HIRIS) ---
    ToolDef("call_service", Tier.ACTION, "call_ha_service",
            "Esegue un servizio HA whitelisted su un'entita' whitelisted. Azione gated dal semaforo: "
            "puo' tornare 'pending_approval' (verde = esegue, giallo = approvazione su iPhone, "
            "rosso = conferma manuale in HIRIS)."),
]

_BY_NAME = {t.name: t for t in TOOLS}


def get_tool(name: str) -> ToolDef:
    return _BY_NAME[name]
