"""Tool di sola lettura sulle segnalazioni del Brain.

Il Brain esegue periodicamente i controlli di salute della casa e ne archivia
gli esiti in `AdvisoryStore`. Senza questo tool quelle segnalazioni vivono solo
nella dashboard di configurazione: in chat HIRIS non le vede, e alla domanda
"ci sono problemi in casa?" risponde a vuoto. Qui si limita a leggerle.
"""
from __future__ import annotations

import json
import logging
from typing import Any

# Stati di una segnalazione ancora attiva, definiti accanto alla colonna
# `status` che li esprime (brain/advisory_store.py):
# - `open`         il problema c'e' e nessuno l'ha ancora guardato;
# - `acknowledged` l'utente ne ha preso atto ma il problema non e' rientrato
#                  (`reconcile` continua ad aggiornarla come una aperta);
# - `resolved`     rientrata da sola, non c'e' piu' nulla da dire;
# - `dismissed`    messa a tacere DALL'UTENTE per sempre: riproporla in chat
#                  vanificherebbe la sua scelta.
# Stessa coppia usata dal feed del Brain (brain/feed.py) e dal briefing
# quotidiano: una sola nozione di "segnalazione attiva" in tutto il prodotto.
from ..brain.advisory_store import STATI_ATTIVI  # noqa: F401  (ri-esportata)

logger = logging.getLogger(__name__)

# Cap sulle voci restituite. Protegge il PROMPT dell'LLM: in una casa messa
# male le segnalazioni possono essere decine e finirebbero tutte nel contesto.
# Il taglio avviene solo qui in lettura -- l'archivio e la dashboard di
# configurazione restano completi -- e viene sempre dichiarato in `truncated`,
# come gia' fa lo snapshot di salute (proxy/health_monitor.py).
MAX_ADVISORIES = 20

# Cap sull'EVIDENZA di ogni singola voce. Limitare il numero di segnalazioni
# non basta: `evidence` e' un dict di forma libera prodotto dal controllo che
# l'ha emessa, e nessuno garantisce che resti piccolo. Oggi i controlli
# esistenti (brain/health_checks.py) ne emettono due o tre chiavi e quello
# sulle entita' senza area tronca gia' da se' a 50 identificativi, ma il
# prossimo controllo che emette una lista -- gli aggiornamenti disponibili --
# entrerebbe intero nel contesto, moltiplicato per MAX_ADVISORIES voci.
# Due limiti, perche' servono a proteggere da due forme diverse di eccesso:
# molte chiavi piccole, oppure poche chiavi enormi.
MAX_EVIDENCE_KEYS = 8
# ~1200 caratteri per voce: sopra il costo di ogni evidenza emessa oggi dai
# controlli, e con un tetto complessivo (20 x 1200) che resta leggibile.
MAX_EVIDENCE_CHARS = 1200

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
        "sono. Anche l'evidenza di una singola voce e' limitata: se la voce "
        "contiene 'evidence_truncated', l'evidenza mostrata e' parziale ("
        "'shown' chiavi su 'total') e va riferita come tale, senza dedurne che "
        "i dettagli mancanti non esistano. Sola lettura: questo tool non puo' "
        "chiudere, archiviare o modificare una segnalazione."
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


def _evidenza_limitata(grezza: Any) -> tuple[dict, dict | None]:
    """Riduce l'evidenza ai limiti di prompt.

    Ritorna `(evidenza, taglio)`: `taglio` e' None se non si e' tolto nulla,
    altrimenti `{"shown": chiavi tenute, "total": chiavi originali}` -- stessa
    forma della dichiarazione di troncamento dello snapshot di salute
    (proxy/health_monitor.py), perche' serve alla stessa cosa: permettere al
    modello di dire all'utente che sta vedendo una parte.
    """
    # `_row` dello store deserializza sempre l'evidenza, ma una riga malformata
    # la lascerebbe a None: il modello si aspetta un oggetto.
    if not isinstance(grezza, dict):
        return {}, None

    totale = len(grezza)
    tenute: dict = {}
    spazio = MAX_EVIDENCE_CHARS
    for chiave, valore in list(grezza.items())[:MAX_EVIDENCE_KEYS]:
        try:
            costo = len(json.dumps({chiave: valore}, ensure_ascii=False))
        except (TypeError, ValueError):
            # Evidenza non serializzabile: saltare la chiave e dichiararlo e'
            # meglio che far fallire la lettura di tutte le segnalazioni.
            continue
        if costo > spazio:
            # Si salta la chiave smisurata e si prosegue invece di fermarsi:
            # una chiave sintetica che segue una enorme (es. `count` dopo
            # `entities`) e' proprio quella che serve al modello per riferire
            # il numero reale.
            continue
        tenute[chiave] = valore
        spazio -= costo

    if len(tenute) == totale:
        return tenute, None
    return tenute, {"shown": len(tenute), "total": totale}


def _voce(riga: dict) -> dict:
    """Proietta una riga dello store sui soli campi destinati al modello."""
    voce = {c: riga.get(c) for c in _CAMPI_ESPOSTI}
    voce["evidence"], taglio = _evidenza_limitata(riga.get("evidence"))
    if taglio is not None:
        voce["evidence_truncated"] = taglio
    return voce


def get_advisories(advisory_store: Any, severity: str | None = None) -> dict:
    """Segnalazioni attive del Brain, filtrate e limitate per il prompt."""
    if advisory_store is None:
        return {"error": "AdvisoryStore non disponibile — controlla i log di avvio"}
    if severity is not None and severity not in SEVERITA:
        return {"error": f"severity non valida: attesa una fra {', '.join(SEVERITA)}"}

    try:
        # Una lettura per stato, non una lettura totale. `AdvisoryStore.list()`
        # senza `status` fa una SELECT su TUTTE le righe -- comprese le risolte
        # e quelle messe a tacere, che si accumulano per sempre perche' lo store
        # non pota mai nulla -- e deserializza il JSON dell'evidenza di ognuna,
        # per poi buttarne via la maggior parte qui in Python. Costo che pesa
        # perche' questa funzione e' sincrona e gira sull'event loop.
        # Lo store ha gia' un indice su (status, ts_updated): due letture
        # mirate costano meno di una totale. L'unione perde l'ordine globale
        # per data, ma il riordino per gravita' qui sotto lo rifa' comunque.
        righe: list[dict] = []
        for stato in STATI_ATTIVI:
            righe.extend(advisory_store.list(status=stato) or [])
    except Exception:
        # Il dettaglio dell'errore resta nei log: rimandarlo al chiamante
        # significherebbe metterlo nel prompt dell'LLM.
        logger.exception("Lettura delle segnalazioni non riuscita")
        return {"error": "Lettura delle segnalazioni non riuscita"}

    # Il controllo su `status` e' ridondante con le letture mirate qui sopra e
    # resta apposta: e' l'unico punto che garantisce che una segnalazione messa
    # a tacere dall'utente non riemerga in chat, anche se un domani lo store
    # cambiasse il modo di filtrare.
    attive = [
        r for r in righe
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
