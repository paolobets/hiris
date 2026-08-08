"""Definizione dello strumento di richiamo della memoria.

fetta E2 Task 8: `handle_save_memory` e `handle_recall_memory` (le funzioni
esecutrici) e `SAVE_MEMORY_TOOL_DEF` sono usciti -- orfani dal Task 7 (il
`ToolDispatcher` che li chiamava e' uscito), nessun chiamante di produzione li
invocava piu'. `RECALL_MEMORY_TOOL_DEF` resta: e' l'unico dei due nominato da
`EVALUATION_ONLY_TOOLS` (claude_runner.py, sola lettura -- `save_memory` ne e'
escluso di proposito, rischio di scrittura per un agente reattivo), l'unico
catalogo rimasto in piedi -- lo usa la Sentinella.
"""
from __future__ import annotations

# `LEGACY_TOOL_ALIASES` e `normalize_tool_names` sono state spostate in
# chatbot_engine.py: non sono uno strumento, sono una normalizzazione di
# alias legacy dei nomi di tool, usata anche da api/handlers_execute.py.

RECALL_MEMORY_TOOL_DEF = {
    "name": "recall_memory",
    "description": (
        "Cerca in ciò che HIRIS ricorda: preferenze, fatti, scadenze, spese, "
        "appunti e ricordi di conversazioni passate -- un unico archivio, non uno "
        "per ogni tipo. Usa questo strumento prima di rispondere a domande dove "
        "il contesto passato potrebbe aiutare. Se la memoria semantica non è "
        "disponibile (nessun embedder configurato, o il calcolo del vettore "
        "fallisce), il risultato porta `degraded: true` e restituisce i ricordi "
        "più recenti invece dei più pertinenti: in quel caso vanno presentati "
        "come 'i più recenti', non come 'i più pertinenti', perché il confronto "
        "dei significati non è avvenuto. In quella modalità l'archivio documenti "
        "non viene affatto consultato: i risultati riguardano solo ciò che è "
        "stato scritto come testo (mai i documenti caricati), e questo va detto "
        "invece di lasciar intendere che l'archivio sia stato controllato."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query in linguaggio naturale per la ricerca semantica",
            },
            "k": {
                "type": "integer",
                "description": "Numero massimo di risultati da restituire (default 5, max 20)",
                "default": 5,
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Filtro opzionale per tag — restituisce solo ricordi "
                    "con almeno uno di questi tag"
                ),
            },
        },
        "required": ["query"],
    },
}
