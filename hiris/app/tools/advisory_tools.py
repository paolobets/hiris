"""Definizione dello strumento di lettura sulle segnalazioni del Brain.

fetta E2 Task 8: `get_advisories` e tutte le funzioni di supporto
(troncamento dell'evidenza, filtro di perimetro) sono uscite -- orfane dal
Task 7 (il `ToolDispatcher` che le chiamava e' uscito), nessun chiamante di
produzione le invocava piu'. La definizione resta: e' nominata da
`EVALUATION_ONLY_TOOLS` (claude_runner.py, sola lettura -- un sorvegliante
proattivo deve poter vedere le segnalazioni gia' note), l'unico catalogo
rimasto in piedi -- lo usa la Sentinella.
"""
from __future__ import annotations

# Severita' emesse dai controlli (brain/health_checks.py), dalla piu' grave.
SEVERITA = ("high", "warn", "info")

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
        "i dettagli mancanti non esistano. Se la risposta contiene 'filtered', "
        "alcune segnalazioni riguardano entita' fuori dal tuo perimetro e non "
        "ti vengono mostrate ('shown' su 'total'): dillo all'utente invece di "
        "concludere che non ci sia altro. Sola lettura: questo tool non puo' "
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
