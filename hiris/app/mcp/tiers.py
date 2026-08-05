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
    ToolDef("get_logbook", Tier.READ, "get_logbook",
            "Cronologia degli eventi di Home Assistant (chi ha fatto cosa e quando). "
            "Senza entity_id elenca tutti gli eventi delle ultime ore; con entity_id "
            "si restringe a una sola entita'. Sola lettura."),
    # render_template NON e' esposto al gateway. Il gateway e' una superficie
    # remota e concede i tool di lettura in blocco: derive_execute_policy include
    # SEMPRE i READ_TOOLS, senza opt-in per singolo tool, e le letture partono
    # senza whitelist di entita' (handlers_execute: "reads see the whole home").
    # Il perimetro delle letture remote e' ora la denylist di lettura
    # (api/read_denylist.py), che rifiuta le richieste che nominano un'entita'
    # coperta e POTA le risposte -- copre quindi anche il parametro omesso.
    # get_logbook e' rientrato proprio per questo: la sua enumerazione in blocco
    # della cronologia (serrature, allarme, presenze) non e' piu' illimitata.
    # render_template invece la denylist non lo coprirebbe: un template legge
    # qualunque stato e non ha un entity_id da filtrare, quindi nessun perimetro
    # potrebbe contenerlo. Contenimento della superficie remota, non limite
    # tecnico: funziona gia' qui, e riabilitarlo richiederebbe una riga (piu' il
    # conteggio in tests/test_mcp_server_build.py e le asserzioni di assenza in
    # tests/test_diagnostics_tools.py). In chat e agli agenti locali resta
    # pienamente disponibile — vedi claude_runner.py.
    ToolDef("recall_memory", Tier.READ, "recall_memory",
            "Cerca in cio' che HIRIS ricorda (preferenze, fatti, scadenze, spese, appunti) "
            "e negli insight storici settimanali (non sensibili). Es: tendenze o variazioni recenti."),
    # --- SCHEDULE / PROPOSE ---
    # Il gate di conferma qui NON esiste e non e' un'omissione: api/
    # handlers_execute.py dispaccia create_task direttamente. Il limite reale e'
    # un altro e vale gia' alla creazione -- ogni azione call_ha_service deve
    # avere entity_id espliciti (niente area/dispositivo/label) e tier VERDE
    # per-entita', altrimenti il task viene rifiutato subito.
    #
    # Fix wave 1 -- quel filtro pero' vale sulle azioni di PRIMO LIVELLO. Un
    # task puo' contenere a sua volta un create_task (tools/dispatcher.py::
    # _ALLOWED_TASK_ACTIONS, attuato da task_engine 513-521) e le azioni del
    # figlio non sono ispezionate da handlers_execute. Fra due strade --
    # estendere il filtro all'annidamento o correggere la descrizione -- si e'
    # scelta la seconda, per tre ragioni:
    #   1. l'annidamento non ha un fondo: create_task e' un'azione ammessa
    #      dentro un task e nessun contatore di profondita' esiste, quindi
    #      estendere il filtro vorrebbe dire una visita ricorsiva con un tetto
    #      di profondita' inventato qui, sul percorso remoto;
    #   2. sarebbe un SECONDO punto di enforcement dello stesso confine, il
    #      duplicato che tools/dispatcher.py (465-482) ha gia' rifiutato per
    #      allowed_entities proprio perche' i due punti divergono;
    #   3. non e' un varco sul semaforo: allo scatto task_engine 477-505 valuta
    #      OGNI azione, e cio' che non e' verde diventa step-up all'owner o
    #      viene saltato. Il costo residuo e' un messaggio d'errore peggiore
    #      (il task nasce e non attua), non un confine piu' debole.
    # Percio' e' la PROMESSA a essere sbagliata, non il codice a essere
    # incompleto -- e una rete dichiarata e assente e' peggio di nessuna rete,
    # perche' il modello agisce con meno cautela. Vedi
    # tests/test_coerenza_conferma.py (perimetro del filtro pinnato) e
    # tests/test_execute_api.py (rifiuti off/giallo/rosso).
    ToolDef("create_task", Tier.SCHEDULE, "create_task",
            "Pianifica un task HIRIS (trigger + azioni). Le azioni possono includere "
            "send_notification (anche notifiche persistenti nel dashboard HA, channel "
            "'ha_persistent') e call_ha_service. Il filtro alla creazione vale sulle "
            "azioni di primo livello: li' una call_ha_service e' accettata solo con "
            "entity_id espliciti e su entita' verdi nel semaforo, altrimenti il task "
            "viene rifiutato subito. Le azioni di un task annidato non passano da quel "
            "filtro, ma allo scatto ogni azione ripassa dal semaforo: cio' che e' verde "
            "parte da solo, il resto viene fermato o messo in attesa di una conferma "
            "umana. Un task non allarga il semaforo e non lo scavalca."),
    ToolDef("list_tasks", Tier.SCHEDULE, "list_tasks",
            "Elenca i task HIRIS pianificati."),
    # Anche qui nessun gate, e qui nemmeno serviva: annullare TOGLIE un'azione
    # futura, non ne esegue una. Resta un residuo noto e volutamente non
    # chiuso in questo giro: cancel_task non filtra per agent_id, quindi da
    # qui si annulla anche un task creato dall'utente in HIRIS -- un
    # impedimento, non un'attuazione.
    ToolDef("cancel_task", Tier.SCHEDULE, "cancel_task",
            "Annulla un task HIRIS pianificato: rimuove un'azione futura, non ne "
            "esegue una. Immediato e non reversibile -- il task va ricreato. "
            "Usa prima list_tasks per prendere l'id giusto."),
    ToolDef("create_automation_proposal", Tier.SCHEDULE, "create_automation_proposal",
            "Propone un'automazione HA per revisione umana (NON applicata automaticamente)."),
    ToolDef("send_notification", Tier.SCHEDULE, "send_notification",
            "Invia una notifica all'utente (informativa, non controlla dispositivi). "
            "channel: 'ha_persistent' = notifica persistente nel dashboard Home Assistant "
            "(title + message; per rimuoverla passa notification_id con message vuoto); "
            "'ha_push' = push sul telefono (title + message); 'apprise' = Telegram/WhatsApp/ntfy; "
            "'retropanel' = toast kiosk. Per le notifiche usa SEMPRE questo tool, mai call_service."),
    ToolDef("save_memory", Tier.SCHEDULE, "save_memory",
            "Salva subito qualcosa da ricordare (preferenza, fatto, scadenza, spesa, appunto): "
            "nessuna approvazione, nessuna coda."),
    # --- ACTION (confirmation required, gated dal semaforo HIRIS) ---
    ToolDef("call_service", Tier.ACTION, "call_ha_service",
            "Esegue un servizio HA whitelisted su un'entita' whitelisted. Azione gated dal semaforo: "
            "puo' tornare 'pending_approval' (verde = esegue, giallo = approvazione su iPhone, "
            "rosso = conferma manuale in HIRIS)."),
]

_BY_NAME = {t.name: t for t in TOOLS}


def get_tool(name: str) -> ToolDef:
    return _BY_NAME[name]
