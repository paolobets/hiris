from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..proxy.memory_store import MemoryStore
    from ..backends.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

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
        "I ricordi persistono tra le conversazioni."
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


async def recall_memory(
    memory_store: "MemoryStore",
    embedder: "EmbeddingProvider",
    agent_id: str,
    query: str,
    k: int = 5,
    tags: list[str] | None = None,
) -> dict:
    k = min(max(1, k), 20)
    try:
        results = await memory_store.search(agent_id, query, k, tags, embedder)
    except Exception as exc:
        logger.warning("recall_memory failed: %s", exc)
        return {"memories": [], "count": 0, "error": str(exc)}
    return {"memories": results, "count": len(results)}


async def save_memory(
    memory_store: "MemoryStore",
    embedder: "EmbeddingProvider",
    agent_id: str,
    content: str,
    tags: list[str] | None = None,
    retention_days: int | None = None,
) -> dict:
    if len(content) > 1000:
        return {"error": "content exceeds 1000 character limit"}
    try:
        mem_id = await memory_store.save(
            agent_id, content, tags or [], embedder, retention_days
        )
    except Exception as exc:
        logger.warning("save_memory failed: %s", exc)
        return {"error": str(exc)}
    return {"saved": True, "id": mem_id}
