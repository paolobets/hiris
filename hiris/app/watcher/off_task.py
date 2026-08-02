from __future__ import annotations
from typing import Optional


def _minuti(valore: object) -> Optional[int]:
    """I minuti di ritardo, o None se il valore non e' utilizzabile come tali.

    `off_after_min` non e' un campo scritto da noi: fa parte dell'azione decisa
    dal modello, che il numero lo puo' benissimo scrivere come testo ("30"). Il
    confronto diretto con zero alzava TypeError su quel testo, e il chiamante
    che confeziona la proposta della Sentinella chiama fuori dal blocco
    protetto: l'eccezione risaliva fino al gestore dell'evento, che registrava
    un errore e lasciava l'utente senza proposta E senza notifica. La regola sta
    qui, alla radice, cosi' vale anche per il chiamante storico (il percorso di
    esecuzione automatica).

    Un testo numerico vale come il numero che dichiara: e' cio' che il modello
    intendeva, e scartarlo perderebbe in silenzio lo spegnimento ritardato.
    Tutto il resto -- prosa, liste, dizionari, booleani (True e' un int per
    Python, ma non e' "fra un minuto") -- e' un valore non valido, e un valore
    non valido produce lo stesso esito di sempre: None, mai un'eccezione.
    """
    if isinstance(valore, bool):
        return None
    if isinstance(valore, (int, float)):
        numero = float(valore)
    elif isinstance(valore, str):
        try:
            numero = float(valore.strip())
        except ValueError:
            return None
    else:
        return None
    minuti = int(numero)
    return minuti if minuti > 0 else None


def build_off_task(action: dict) -> Optional[dict]:
    if not isinstance(action, dict):
        return None
    mins = _minuti(action.get("off_after_min"))
    eid = action.get("entity_id")
    if mins is None or not eid or action.get("service") != "turn_on":
        return None
    domain = action.get("domain") or eid.split(".", 1)[0]
    return {"label": f"sentinel-off:{eid}",
            "trigger": {"type": "delay", "minutes": mins},
            "actions": [{"type": "call_ha_service", "domain": domain,
                         "service": "turn_off", "data": {"entity_id": eid}}],
            "one_shot": True}
