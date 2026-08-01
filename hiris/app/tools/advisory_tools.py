"""Tool di sola lettura sulle segnalazioni del Brain.

Il Brain esegue periodicamente i controlli di salute della casa e ne archivia
gli esiti in `AdvisoryStore`. Senza questo tool quelle segnalazioni vivono solo
nella dashboard di configurazione: in chat HIRIS non le vede, e alla domanda
"ci sono problemi in casa?" risponde a vuoto. Qui si limita a leggerle.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cap sulle voci restituite. Protegge il PROMPT dell'LLM: in una casa messa
# male le segnalazioni possono essere decine e finirebbero tutte nel contesto.
# Il taglio avviene solo qui in lettura -- l'archivio e la dashboard di
# configurazione restano completi -- e viene sempre dichiarato in `truncated`,
# come gia' fa lo snapshot di salute (proxy/health_monitor.py).
MAX_ADVISORIES = 20

# Solo le segnalazioni ancora attive arrivano al modello:
# - `open`         il problema c'e' e nessuno l'ha ancora guardato;
# - `acknowledged` l'utente ne ha preso atto ma il problema non e' rientrato
#                  (`reconcile` continua ad aggiornarla come una aperta);
# - `resolved`     rientrata da sola, non c'e' piu' nulla da dire;
# - `dismissed`    messa a tacere DALL'UTENTE per sempre: riproporla in chat
#                  vanificherebbe la sua scelta.
# Stessa coppia usata dal feed del Brain (brain/feed.py): una sola nozione di
# "segnalazione attiva" in tutto il prodotto.
STATI_ATTIVI = ("open", "acknowledged")

# Severita' emesse dai controlli (brain/health_checks.py), dalla piu' grave.
SEVERITA = ("high", "warn", "info")

# Campi passati al modello. Tutto il resto (`id`, `source_ref`, `fix_kind`,
# `check_id`, i timestamp, `resolved_auto`) e' contabilita' interna dello
# store: non aiuta a rispondere all'utente e costa token a ogni chiamata.
# `status` resta perche' distingue "da guardare" da "gia' presa in carico".
_CAMPI_ESPOSTI = ("severity", "title", "evidence", "suggested_fix", "status")

GET_ADVISORIES_TOOL_DEF = {
    "name": "get_advisories",
    "description": (
        "Elenca le segnalazioni di salute aperte rilevate dal Brain di HIRIS: "
        "batterie scariche, entita' non disponibili da giorni, automazioni "
        "rotte, domini pericolosi lasciati abilitati, entita' senza area. "
        "Usalo quando l'utente chiede se ci sono problemi in casa, se qualcosa "
        "non funziona, o cosa andrebbe sistemato. Ogni voce riporta gravita' "
        "('severity': 'high' grave, 'warn' avviso, 'info' informativa), titolo, "
        "evidenza e rimedio suggerito; 'status' vale 'open' (da guardare) o "
        "'acknowledged' (l'utente ne ha gia' preso atto). Le segnalazioni "
        "archiviate o messe a tacere dall'utente non compaiono. Filtra con "
        "'severity' se ti serve solo il livello piu' grave. L'elenco e' "
        "limitato: se la risposta contiene 'truncated', riferisci sempre "
        "all'utente il totale reale indicato li' ('shown' su 'total'), "
        "altrimenti gli faresti credere che i problemi siano meno di quanti "
        "sono. Sola lettura: questo tool non puo' chiudere, archiviare o "
        "modificare una segnalazione."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": list(SEVERITA),
                "description": (
                    "Mostra solo le segnalazioni di questa gravita'. "
                    "Omesso: tutte."
                ),
            }
        },
        "required": [],
    },
}


def _rango(riga: dict) -> int:
    """Posizione della gravita' nell'ordine di taglio; ignote in fondo."""
    sev = riga.get("severity")
    return SEVERITA.index(sev) if sev in SEVERITA else len(SEVERITA)


def _voce(riga: dict) -> dict:
    """Proietta una riga dello store sui soli campi destinati al modello."""
    voce = {c: riga.get(c) for c in _CAMPI_ESPOSTI}
    # `_row` dello store deserializza sempre l'evidenza, ma una riga malformata
    # la lascerebbe a None: il modello si aspetta un oggetto.
    voce["evidence"] = riga.get("evidence") or {}
    return voce


def get_advisories(advisory_store: Any, severity: str | None = None) -> dict:
    """Segnalazioni attive del Brain, filtrate e limitate per il prompt."""
    if advisory_store is None:
        return {"error": "AdvisoryStore non disponibile — controlla i log di avvio"}
    if severity is not None and severity not in SEVERITA:
        return {"error": f"severity non valida: attesa una fra {', '.join(SEVERITA)}"}

    try:
        # Una sola lettura senza filtro: `AdvisoryStore.list` accetta un solo
        # stato per volta, e ne servono due.
        righe = advisory_store.list()
    except Exception:
        # Il dettaglio dell'errore resta nei log: rimandarlo al chiamante
        # significherebbe metterlo nel prompt dell'LLM.
        logger.exception("Lettura delle segnalazioni non riuscita")
        return {"error": "Lettura delle segnalazioni non riuscita"}

    attive = [
        r for r in righe or []
        if r.get("status") in STATI_ATTIVI
        and (severity is None or r.get("severity") == severity)
    ]
    totale = len(attive)

    # Lo store ordina per data di aggiornamento decrescente. Tagliare in
    # quell'ordine nasconderebbe una segnalazione grave ma vecchia dietro
    # venti informative appena riviste: ordiniamo prima per gravita' e, a
    # parita', il sort stabile conserva la recenza dello store.
    attive.sort(key=_rango)

    mostrate = [_voce(r) for r in attive[:MAX_ADVISORIES]]
    risultato: dict = {"advisories": mostrate, "count": len(mostrate)}
    if totale > MAX_ADVISORIES:
        risultato["truncated"] = {
            "shown": MAX_ADVISORIES,
            "total": totale,
            # Senza questo il modello sa quante ne mancano ma non QUALI vede.
            "order": "severity_first",
        }
    return risultato
