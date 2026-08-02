from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..brain.knowledge_store import KnowledgeStore
    from ..backends.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# Same timestamp format used by KnowledgeStore (see brain/knowledge_store.py).
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# I tre messaggi che il modello legge -- e che quindi arrivano all'utente.
# Dicono cosa NON e' successo e perche' conta, mai il dettaglio tecnico:
# l'eccezione resta nel log del server (regola del repo, mai echo di str(exc)).
# Gemelli di _ERRORE_SENZA_EMBEDDING in tools/knowledge_tools.py: stesso
# difetto, stessa risposta.
_ERRORE_SALVATAGGIO_SENZA_EMBEDDING = (
    "Non sono riuscito a salvare questo ricordo: la memoria semantica non è "
    "disponibile e non sarebbe più richiamabile. Riprova più tardi."
)
_ERRORE_SALVATAGGIO = (
    "Non sono riuscito a salvare questo ricordo. Riprova più tardi."
)
_ERRORE_RICERCA = (
    "Non sono riuscito a cercare nella memoria: la memoria semantica non è "
    "disponibile in questo momento. Non posso dire che non ci sia nulla, solo "
    "che non ho potuto controllare."
)

RECALL_MEMORY_TOOL_DEF = {
    "name": "recall_memory",
    "description": (
        "Cerca nella memoria persistente dell'agente informazioni rilevanti da sessioni precedenti. "
        "Usa questo strumento prima di rispondere a domande dove il contesto passato potrebbe aiutare."
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
    embedder: "EmbeddingProvider",
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

    Senza embedding il ricordo NON e' richiamabile: `knowledge_store.search`
    filtra su `status='approved' AND embedding IS NOT NULL`. Scriverlo comunque
    e rispondere `saved: True` e' un successo dichiarato che non esiste --
    l'utente dice "ricordati che..." e il ricordo non tornera' mai. Quindi qui,
    se l'embedding non c'e', si fallisce apertamente e non si scrive nulla. E'
    la stessa scelta gia' fatta per il tool gemello save_knowledge
    (tools/knowledge_tools.py).
    """
    content = tool_input["content"]
    if len(content) > 1000:
        return {"error": "content exceeds 1000 character limit"}
    tags = tool_input.get("tags") or []
    try:
        embedding = await embedder.embed(content) if embedder is not None else None
    except Exception:
        logger.exception("save_memory: embedding non calcolato, nulla da salvare")
        embedding = None
    if not embedding:
        logger.warning("save_memory rifiutato: nessun embedding disponibile")
        return {"error": _ERRORE_SALVATAGGIO_SENZA_EMBEDDING}

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
                embedding=embedding,
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
    embedder: "EmbeddingProvider",
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
    # Senza vettore di ricerca non si e' guardato da nessuna parte: rispondere
    # `{"memories": [], "count": 0}` farebbe dire al modello "non ricordo
    # nulla" quando la frase vera e' "non ho potuto controllare". I due casi
    # devono restare distinguibili, quindi il guasto NON porta un elenco: solo
    # l'errore.
    try:
        query_vec = await embedder.embed(tool_input["query"]) if embedder is not None else None
    except Exception:
        logger.exception("recall_memory: vettore di ricerca non calcolato")
        query_vec = None
    if not query_vec:
        logger.warning("recall_memory non eseguita: nessun vettore di ricerca")
        return {"error": _ERRORE_RICERCA}

    loop = asyncio.get_running_loop()

    def _search() -> list[dict]:
        # Over-fetch when a tag filter is active so post-filtering doesn't
        # starve the result set below k.
        search_k = k * 4 if tags else k
        rows = store.search(
            query_vec=query_vec, k=search_k, owner=owner, chatbot_id=chatbot_id,
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
    return {"memories": memories, "count": len(memories)}
