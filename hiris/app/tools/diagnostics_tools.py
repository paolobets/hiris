"""Definizione dello strumento di lettura sulla cronologia degli eventi.

fetta E2 Task 8: `get_logbook`/`render_template` (le funzioni esecutrici),
`validate_logbook_inputs`/`validate_template` e `RENDER_TEMPLATE_TOOL_DEF`
sono usciti -- orfani dal Task 7 (il `ToolDispatcher` che li chiamava e'
uscito), nessun chiamante di produzione li invocava piu'. `render_template`
non sarebbe comunque entrato in `EVALUATION_ONLY_TOOLS`: legge QUALUNQUE stato
di Home Assistant senza un entity_id da filtrare, il vettore di prompt
injection perfetto per un agente reattivo che gira sullo stato di HA (vedi il
commento su `EVALUATION_ONLY_TOOLS` in claude_runner.py). `GET_LOGBOOK_TOOL_
DEF` resta: e' nominato da `EVALUATION_ONLY_TOOLS`, l'unico catalogo rimasto
in piedi -- lo usa la Sentinella.
"""
from __future__ import annotations

# Unica fonte dei limiti: chi conosce il costo reale della chiamata e' il
# client che la esegue.
from ..proxy.ha_client import DEFAULT_LOGBOOK_HOURS, MAX_LOGBOOK_HOURS

__all__ = ["DEFAULT_LOGBOOK_HOURS", "MAX_LOGBOOK_HOURS", "GET_LOGBOOK_TOOL_DEF"]

GET_LOGBOOK_TOOL_DEF = {
    "name": "get_logbook",
    "description": (
        "Cronologia degli eventi di Home Assistant: chi ha acceso cosa, quando "
        "e' cambiato uno stato, cosa e' successo in una stanza. Usalo per "
        "domande sul PASSATO RECENTE ('cosa e' successo ieri sera in salotto?', "
        "'chi ha acceso il riscaldamento?', 'quando si e' aperta la porta?'). "
        "Per andamenti numerici (temperature, consumi) usa invece get_history. "
        f"'entity_id' e' facoltativo: omesso significa tutta la casa. 'hours' e' "
        f"la finestra all'indietro da adesso, da 1 a {MAX_LOGBOOK_HOURS} "
        f"(default {DEFAULT_LOGBOOK_HOURS}). Sola lettura: non modifica nulla. "
        "Se la risposta contiene 'truncated' della finestra sono state lette "
        "SOLO le voci piu' recenti ('shown' voci lette nelle ultime "
        "'window_hours' ore): dillo all'utente e non concludere che prima non "
        "sia successo altro; per vedere piu' indietro restringi la finestra o "
        "filtra per entita'. Se contiene 'filtered' di quelle voci ti sono "
        "mostrate solo quelle delle entita' che ti sono concesse ('shown' su "
        "'total' lette): riferiscilo come parziale. I due numeri 'shown' "
        "contano cose diverse e possono comparire insieme: 'count' e' sempre "
        "quante voci stai effettivamente vedendo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": (
                    "Entita' su cui filtrare, forma 'dominio.oggetto'. "
                    "Omesso: eventi di tutta la casa."
                ),
            },
            "hours": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_LOGBOOK_HOURS,
                "description": (
                    f"Ore all'indietro da adesso (default {DEFAULT_LOGBOOK_HOURS})."
                ),
            },
        },
        "required": [],
    },
}
