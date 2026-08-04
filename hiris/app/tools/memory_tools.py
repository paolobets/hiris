from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..brain.knowledge_store import confronta_significati

if TYPE_CHECKING:
    from ..brain.knowledge_store import KnowledgeStore
    from ..backends.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# Same timestamp format used by KnowledgeStore (see brain/knowledge_store.py).
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Il messaggio che il modello legge -- e che quindi arriva all'utente. Dice
# cosa NON e' successo e perche' conta, mai il dettaglio tecnico: l'eccezione
# resta nel log del server (regola del repo, mai echo di str(exc)).
_ERRORE_SALVATAGGIO = (
    "Non sono riuscito a salvare questo ricordo. Riprova più tardi."
)

RECALL_MEMORY_TOOL_DEF = {
    "name": "recall_memory",
    "description": (
        "Cerca nella memoria persistente dell'agente informazioni rilevanti da sessioni precedenti. "
        "Usa questo strumento prima di rispondere a domande dove il contesto passato potrebbe aiutare. "
        "Se la memoria semantica non è disponibile (nessun embedder configurato, o il calcolo del "
        "vettore fallisce), il risultato porta `degraded: true` e restituisce i ricordi più recenti "
        "invece dei più pertinenti: in quel caso vanno presentati come 'i più recenti', non come 'i più "
        "pertinenti', perché il confronto dei significati non è avvenuto."
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
                "description": "Numero massimo di ricordi da restituire (default 5, max 20)",
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

SAVE_MEMORY_TOOL_DEF = {
    "name": "save_memory",
    "description": (
        "Salva un'informazione nella memoria persistente di questo agente. "
        "Usa per preferenze utente, fatti importanti, pattern ricorrenti o decisioni prese. "
        "I ricordi restano disponibili nelle conversazioni successive fino alla "
        "loro scadenza, configurabile dall'utente (90 giorni per impostazione "
        "predefinita, illimitata se impostata a 0)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Testo del ricordo da salvare (max 1000 caratteri)",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tag per categorizzare il ricordo, "
                    "es. ['preferenza', 'utente', 'orario']"
                ),
            },
        },
        "required": ["content"],
    },
}


async def handle_save_memory(
    store: "KnowledgeStore",
    # `None` e' un valore previsto, non una svista: il dispatcher passa
    # l'embedder cablato, che puo' non esserci (provider non configurato). Il
    # codice qui sotto lo controlla gia'; l'annotazione lo dichiara.
    embedder: "EmbeddingProvider | None",
    tool_input: dict,
    *,
    owner: str,
    chatbot_id: str,
    retention_days: int | None = None,
) -> dict:
    """Save agent working-memory (chatbot-scoped memory) into the unified KnowledgeStore.

    kind='memory', status='approved' (no human-in-the-loop gate like
    save_knowledge — this is the agent's own scratch memory), scoped by
    owner (who it belongs to) AND chatbot_id (which agent wrote it).

    Senza embedding il ricordo resta comunque scritto: `KnowledgeStore.search`
    degrada a `recent()` (piu' recenti prima, stessi filtri di riservatezza)
    quando non c'e' un vettore di query, quindi resta comunque ritrovabile.
    Rifiutare qui spostava il difetto vero a monte: il default di fabbrica
    (NullEmbedder) non calcola MAI un vettore, quindi su un'installazione
    stock "ricordati che..." non veniva mai salvato. Se un embedder c'e' e
    funziona, il vettore si calcola e si salva esattamente come prima; se non
    c'e', non risponde, o solleva, si salva comunque senza vettore.
    """
    content = tool_input["content"]
    if len(content) > 1000:
        return {"error": "content exceeds 1000 character limit"}
    tags = tool_input.get("tags") or []
    try:
        embedding = await embedder.embed(content) if embedder is not None else None
    except Exception:
        logger.exception("save_memory: embedding non calcolato, salvo senza vettore")
        embedding = None

    valid_until: str | None = None
    if retention_days and retention_days > 0:
        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=retention_days)
        ).strftime(_TS_FMT)

    loop = asyncio.get_running_loop()
    try:
        item_id = await loop.run_in_executor(
            None,
            lambda: store.add_item(
                kind="memory",
                content=content,
                owner=owner,
                chatbot_id=chatbot_id,
                data={"tags": tags},
                embedding=embedding or None,
                sensitivity="normal",
                source="chat",
                status="approved",
                valid_until=valid_until,
            ),
        )
    except Exception:
        # Il dettaglio (percorsi, host, stringhe di connessione) resta nel log
        # del server: al modello va il fatto, non il messaggio dell'eccezione.
        logger.exception("save_memory: scrittura fallita")
        return {"error": _ERRORE_SALVATAGGIO}
    return {"saved": True, "id": item_id}


async def handle_recall_memory(
    store: "KnowledgeStore",
    embedder: "EmbeddingProvider | None",   # None previsto: vedi handle_save_memory
    tool_input: dict,
    *,
    owner: str,
    chatbot_id: str,
) -> dict:
    """Recall from the unified KnowledgeStore, restricted to kind='memory'
    rows scoped to this owner's chatbot_id (this agent's own memory only).
    The kinds=['memory'] filter is required: the unified scope WHERE also
    matches unscoped knowledge rows (facts, expenses, obligations...) owned
    by this owner, and without it recall_memory would let an agent read
    knowledge outside its configured kinds egress filter."""
    k = min(max(1, int(tool_input.get("k", 5))), 20)
    tags = tool_input.get("tags") or None
    # Senza vettore di ricerca non si e' potuto confrontare i significati.
    # `KnowledgeStore.search` degrada da se' a `recent()` quando riceve un
    # vettore vuoto (stessi filtri di riservatezza, ordine per recenza), quindi
    # qui non serve piu' un ramo: si passa il vettore per quel che e' -- vuoto
    # o pieno -- e il segnale di degradazione arriva nel ritorno.
    try:
        query_vec = await embedder.embed(tool_input["query"]) if embedder is not None else None
    except Exception:
        logger.exception("recall_memory: vettore di ricerca non calcolato")
        query_vec = None

    loop = asyncio.get_running_loop()

    def _search() -> list[dict]:
        # Over-fetch when a tag filter is active so post-filtering doesn't
        # starve the result set below k.
        search_k = k * 4 if tags else k
        rows = store.search(
            query_vec=query_vec or [], k=search_k, owner=owner, chatbot_id=chatbot_id,
            kinds=["memory"],
        )
        if tags:
            tag_set = set(tags)
            rows = [
                r for r in rows
                if tag_set.intersection((r.get("data") or {}).get("tags") or [])
            ]
        return rows[:k]

    rows = await loop.run_in_executor(None, _search)
    memories = [
        {
            "id": r["id"],
            "content": r["content"],
            "tags": (r.get("data") or {}).get("tags") or [],
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]
    return {"memories": memories, "count": len(memories), "degraded": not confronta_significati(query_vec)}
