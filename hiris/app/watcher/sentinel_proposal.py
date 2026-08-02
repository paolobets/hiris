"""Confezionamento della proposta che la Sentinella lascia all'utente quando il
semaforo non le permette di agire da sola (tier verde senza opt-in, o giallo).

Perche' uno script e non un'automazione. Cio' che la Sentinella ha in mano e'
UNA chiamata di servizio pertinente all'anomalia appena vista — il contratto di
SENTINEL_SYSTEM e' esattamente {domain, service, entity_id, data} — cioe' un
rimedio una-tantum, gia' deciso, per una situazione che sta accadendo ora.
Un'automazione Home Assistant e' invece una regola permanente e non esiste senza
un trigger: per confezionarla come automazione bisognerebbe inventare un trigger
che nessuno ha deciso (tipicamente "a ogni cambio di stato dell'entita'"),
consegnando all'utente una regola che scatta per sempre al posto del rimedio che
aveva approvato. Sarebbe una bugia peggiore di quella che stiamo togliendo.

Uno script HA e' invece la stessa identica cosa che la Sentinella ha in mano —
una sequenza di chiamate di servizio con un nome — e il ramo `ha_script`
dell'apply lo crea davvero in Home Assistant (`apply_ha_config` ->
`HAClient.create_script`), quindi l'approvazione produce un effetto reale e
verificabile invece di marcare "applicata" una proposta inerte.
"""
from __future__ import annotations

import re
from typing import Optional

from ..tools.config_tools import build_config_proposal, normalize_config_inputs
from .off_task import build_off_task

# Stesso identificatore accettato da HAClient.call_service: se dominio o
# servizio non lo rispettano l'azione non e' eseguibile, quindi non e' nemmeno
# confezionabile.
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")
_SLUG_UNSAFE_RE = re.compile(r"[^a-z0-9_]+")

# Lo slug e' l'object_id dello script in HA: tenerlo corto e leggibile.
_MAX_SLUG_LEN = 60


def _slug_part(text: object) -> str:
    return _SLUG_UNSAFE_RE.sub("_", str(text or "").strip().lower()).strip("_")


def build_sentinel_script_proposal(
    action: object, *, signal_kind: str, entity_id: str, message: str,
    routing_reason: str,
) -> Optional[dict]:
    """Il record ProposalStore per il rimedio proposto dalla Sentinella.

    Ritorna None se l'azione non e' confezionabile (manca il servizio, l'entita'
    non e' un entity_id canonico, i dati non sono un dizionario): in quel caso
    il chiamante NON deve salvare una proposta, perche' una proposta che non si
    puo' applicare e' esattamente il difetto che si sta eliminando.

    Lo slug e' deterministico su (segnale, entita'): una nuova proposta per lo
    stesso rimedio sovrascrive lo stesso script invece di riempire Home
    Assistant di copie quasi uguali.
    """
    if not isinstance(action, dict):
        return None
    eid = action.get("entity_id")
    if not isinstance(eid, str) or not _ENTITY_ID_RE.match(eid):
        return None
    service = action.get("service")
    if not isinstance(service, str) or not _IDENTIFIER_RE.match(service):
        return None
    domain = action.get("domain") or eid.split(".", 1)[0]
    if not isinstance(domain, str) or not _IDENTIFIER_RE.match(domain):
        return None
    data = action.get("data")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None

    sequence = [{"service": f"{domain}.{service}",
                 "target": {"entity_id": eid},
                 "data": dict(data)}]
    # Stessa fedelta' del percorso automatico (_act in server.py): se l'azione
    # prevede uno spegnimento ritardato, lo script lo contiene invece di
    # perderlo. build_off_task e' la sola fonte della regola (solo turn_on, solo
    # minuti positivi), qui non si duplica nessuna policy.
    off = build_off_task(action)
    if off is not None:
        minutes = int(off["trigger"]["minutes"])
        sequence.append({"delay": {"minutes": minutes}})
        sequence.append({"service": f"{domain}.turn_off",
                         "target": {"entity_id": eid}})

    name = f"Sentinella: {signal_kind} su {eid}"
    slug = f"hiris_sentinella_{_slug_part(signal_kind)}_{_slug_part(eid.split('.', 1)[1])}"
    slug = slug[:_MAX_SLUG_LEN].strip("_")
    try:
        normalized = normalize_config_inputs({
            "kind": "script", "name": name, "slug": slug,
            "config": {"alias": name, "sequence": sequence, "mode": "single"},
        })
    except ValueError:
        return None
    # Mai lasciare che un messaggio vuoto faccia ricadere build_config_proposal
    # sulla sua descrizione di default, che dichiara un'origine MCP: sarebbe una
    # riga falsa nella pagina Proposte.
    return build_config_proposal(
        normalized, description=str(message or "").strip() or name,
        routing_reason=routing_reason)
