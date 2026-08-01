"""Tool di diagnosi: cronologia degli eventi e valutazione di un template.

Lo snapshot di salute e' una fotografia periodica: dice com'e' la casa adesso.
Questi due tool rispondono invece a domande puntuali, che senza parametri non
avrebbero senso -- "cosa e' successo ieri sera in salotto?" e "questa
condizione e' vera adesso?" -- e per questo sono tool a se' e non sezioni dello
snapshot.

Sono anche gli unici tool di questo filone che colpiscono Home Assistant a ogni
chiamata dell'LLM: tutto il resto passa dalla cache del HealthMonitor. Da qui
due conseguenze:
  - la validazione degli input avviene PRIMA della chiamata, cosi' una
    tool-call malformata non diventa traffico verso HA;
  - i limiti sono quelli dichiarati da `proxy/ha_client.py`, importati e non
    ricopiati: due numeri per lo stesso limite divergono al primo cambio.

Sola lettura: nessuno dei due puo' modificare alcunche'. `render_template` fa
una POST ma HA si limita a renderizzare.
"""
from __future__ import annotations

import fnmatch
import logging
import re
from typing import Any

# Unica fonte dei limiti: chi conosce il costo reale della chiamata e' il
# client che la esegue.
from ..proxy.ha_client import (
    DEFAULT_LOGBOOK_HOURS,
    MAX_LOGBOOK_ENTRIES,
    MAX_LOGBOOK_HOURS,
    MAX_TEMPLATE_LEN,
)

logger = logging.getLogger(__name__)

# entity_id canonico (dominio.oggetto), come in history_tools e ha_client.
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

__all__ = [
    "DEFAULT_LOGBOOK_HOURS", "MAX_LOGBOOK_ENTRIES", "MAX_LOGBOOK_HOURS",
    "MAX_TEMPLATE_LEN", "GET_LOGBOOK_TOOL_DEF", "RENDER_TEMPLATE_TOOL_DEF",
    "get_logbook", "render_template", "validate_logbook_inputs",
    "validate_template",
]

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

RENDER_TEMPLATE_TOOL_DEF = {
    "name": "render_template",
    "description": (
        "Valuta un template Jinja di Home Assistant e ne restituisce il testo. "
        "Serve alla diagnosi: verificare se una condizione e' vera ADESSO "
        "(\"{{ is_state('binary_sensor.porta','on') }}\"), contare entita' in "
        "uno stato, leggere un attributo che gli altri tool non espongono. "
        "Sola lettura: Home Assistant si limita a renderizzare, il template "
        "non puo' chiamare servizi ne' modificare stati. Ritorna "
        "{'result': '<testo>'} oppure {'error': '<messaggio>'}: il messaggio e' "
        "quello di Home Assistant, leggilo per correggere il template e "
        f"riprovare. Massimo {MAX_TEMPLATE_LEN} caratteri; anche la risposta e' "
        "troncata se molto lunga."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "template": {
                "type": "string",
                "description": "Template Jinja di Home Assistant da valutare.",
            },
        },
        "required": ["template"],
    },
}


def validate_logbook_inputs(entity_id: Any, hours: Any) -> str | None:
    """Ritorna il messaggio d'errore, oppure None se gli input sono buoni.

    Separata e sincrona apposta: e' la parte che decide se HA viene chiamato o
    no, quindi deve essere verificabile senza un client finto.

    Volutamente severa: qui `hours=None` e' un errore. La traduzione di "non
    l'ho specificato" nel default e' un fatto del CONTRATTO del tool e vive in
    `get_logbook`, prima della validazione; questa funzione giudica un valore
    gia' deciso.
    """
    if entity_id is not None and not (
        isinstance(entity_id, str) and _ENTITY_ID_RE.match(entity_id)
    ):
        return ("entity_id deve avere la forma 'dominio.oggetto' in minuscolo "
                "(es. 'light.salotto'), oppure essere omesso per tutta la casa")
    # `isinstance(True, int)` e' vero in Python: un booleano passerebbe per una
    # finestra di 1 ora. Una tool-call dell'LLM puo' portare qualunque tipo.
    if isinstance(hours, bool) or not isinstance(hours, int):
        return f"hours deve essere un intero fra 1 e {MAX_LOGBOOK_HOURS}"
    if not (1 <= hours <= MAX_LOGBOOK_HOURS):
        return (f"hours deve essere fra 1 e {MAX_LOGBOOK_HOURS} "
                f"(ricevuto {hours})")
    return None


def validate_template(template: Any) -> str | None:
    """Ritorna il messaggio d'errore, oppure None se il template e' accettabile.

    Non giudica il CONTENUTO del template -- e' Home Assistant a valutarlo --
    ma solo che sia una stringa non vuota entro il limite di lunghezza: oltre
    quella soglia non e' piu' una domanda, e' un payload.
    """
    if not isinstance(template, str) or not template.strip():
        return "template vuoto o non valido"
    if len(template) > MAX_TEMPLATE_LEN:
        return f"template troppo lungo (max {MAX_TEMPLATE_LEN} caratteri)"
    return None


def _nel_perimetro(entity_id: Any, allowed_entities: list[str] | None) -> bool:
    """Vero se la voce e' attribuibile a un'entita' concessa.

    `None` -> nessuna restrizione; `[]` -> nulla passa (stessa semantica di
    tutto il dispatcher: una whitelist vuota e' una decisione, non
    un'omissione). Una voce senza entity_id -- avvio di Home Assistant, script,
    eventi di sistema -- non e' verificabile contro il perimetro: sotto
    perimetro attivo si scarta, fail-closed.
    """
    if allowed_entities is None:
        return True
    if not isinstance(entity_id, str):
        return False
    return any(fnmatch.fnmatch(entity_id, pat) for pat in allowed_entities)


async def get_logbook(
    ha: Any,
    entity_id: str | None = None,
    hours: int | None = None,
    allowed_entities: list[str] | None = None,
) -> dict:
    """Eventi recenti di Home Assistant, filtrati sul perimetro del chiamante.

    `allowed_entities` arriva dal dispatcher e viene applicato QUI, alle voci
    restituite, non solo all'entita' richiesta: `entity_id` e' facoltativo, e
    un perimetro che valesse soltanto quando l'LLM specifica un'entita' si
    aggirerebbe semplicemente omettendola.

    `hours` assente o `None` vale il default: e' l'intera intenzione "non l'ho
    specificato", ed e' parte del contratto del TOOL, non del suo instradamento.
    Tenerla qui significa che un secondo chiamante non deve ricordarsi di
    replicarla. `0` invece resta un errore: e' un input sbagliato, e tradurlo
    nel default lo nasconderebbe al modello invece di respingerlo.
    """
    if ha is None:
        return {"error": "Home Assistant non raggiungibile — controlla i log di avvio"}
    if hours is None:
        hours = DEFAULT_LOGBOOK_HOURS
    err = validate_logbook_inputs(entity_id, hours)
    if err:
        return {"error": err}

    # ha_client.get_logbook non solleva mai e tronca gia' a MAX_LOGBOOK_ENTRIES
    # tenendo le voci PIU' RECENTI.
    voci = await ha.get_logbook(entity_id, hours)
    lette = len(voci)
    # Il taglio si riconosce solo dalla lunghezza: il tipo di ritorno di
    # ha_client (una lista) non ospita un flag, e il suo docstring impone al
    # chiamante di dichiararlo. Senza dichiarazione il modello conclude "non e'
    # successo altro". Il totale reale degli eventi nella finestra NON e'
    # conoscibile da qui: si dichiara cio' che si sa (c'e' stato un taglio, e
    # qual e' la finestra coperta).
    troncato = lette >= MAX_LOGBOOK_ENTRIES

    if allowed_entities is not None:
        voci = [v for v in voci if _nel_perimetro(v.get("entity_id"), allowed_entities)]

    risultato: dict = {
        "entries": voci,
        "count": len(voci),
        "hours": hours,
        "entity_id": entity_id,
    }
    if troncato:
        risultato["truncated"] = {
            # Voci LETTE dalla finestra, non voci mostrate: le due dichiarazioni
            # descrivono tagli diversi e devono restare indipendenti. Contare
            # qui le voci sopravvissute al perimetro farebbe coincidere questo
            # numero con 'filtered.shown' quando compaiono insieme, e 'shown'
            # smetterebbe di significare "N delle voci massime lette". Quante
            # voci si stanno effettivamente vedendo lo dice 'count'.
            "shown": lette,
            "window_hours": hours,
            # Quali voci mancano, non solo quante: ha_client tiene le piu'
            # recenti, quindi il buco sta all'inizio della finestra.
            "oldest_dropped": True,
        }
    if allowed_entities is not None and len(voci) != lette:
        # Secondo taglio, di natura diversa dal primo: qui il totale letto lo
        # conosciamo, quindi si dichiara {shown, total} come fa get_advisories.
        risultato["filtered"] = {"shown": len(voci), "total": lette}
    return risultato


async def render_template(ha: Any, template: Any) -> dict:
    """Valuta un template Jinja tramite Home Assistant e ne restituisce l'esito.

    Pass-through deliberato: `ha_client.render_template` ritorna gia'
    {"result": ...} oppure {"error": ...}, con la risposta troncata e senza mai
    fare eco di str(exc). Reinterpretare qui il messaggio d'errore di HA
    toglierebbe al modello proprio l'informazione che gli serve per correggere
    il template.
    """
    if ha is None:
        return {"error": "Home Assistant non raggiungibile — controlla i log di avvio"}
    err = validate_template(template)
    if err:
        return {"error": err}
    return await ha.render_template(template)
