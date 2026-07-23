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


async def handle_save_memory(
    store: "KnowledgeStore",
    embedder: "EmbeddingProvider",
    tool_input: dict,
    *,
    owner: str,
    lens: str,
    retention_days: int | None = None,
) -> dict:
    """Save agent working-memory ("lens" memory) into the unified KnowledgeStore.

    kind='memory', status='approved' (no human-in-the-loop gate like
    save_knowledge — this is the agent's own scratch memory), scoped by
    owner (who it belongs to) AND lens (which agent wrote it).
    """
    content = tool_input["content"]
    if len(content) > 1000:
        return {"error": "content exceeds 1000 character limit"}
    tags = tool_input.get("tags") or []
    try:
        embedding = await embedder.embed(content)
    except Exception as exc:
        logger.warning("save_memory: embedding failed, saving without vector: %s", exc)
        embedding = []

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
                lens=lens,
                data={"tags": tags},
                embedding=embedding or None,
                sensitivity="normal",
                source="chat",
                status="approved",
                valid_until=valid_until,
            ),
        )
    except Exception as exc:
        logger.warning("save_memory failed: %s", exc)
        return {"error": str(exc)}
    return {"saved": True, "id": item_id}


async def handle_recall_memory(
    store: "KnowledgeStore",
    embedder: "EmbeddingProvider",
    tool_input: dict,
    *,
    owner: str,
    lens: str,
) -> dict:
    """Recall from the unified KnowledgeStore, scoped to this owner's lens
    (own agent memory) plus any un-lensed knowledge shared with this owner."""
    k = min(max(1, int(tool_input.get("k", 5))), 20)
    tags = tool_input.get("tags") or None
    try:
        query_vec = await embedder.embed(tool_input["query"])
    except Exception as exc:
        logger.warning("recall_memory: embedding failed: %s", exc)
        return {"memories": [], "count": 0, "error": str(exc)}
    if not query_vec:
        return {"memories": [], "count": 0}

    loop = asyncio.get_running_loop()

    def _search() -> list[dict]:
        # Over-fetch when a tag filter is active so post-filtering doesn't
        # starve the result set below k.
        search_k = k * 4 if tags else k
        rows = store.search(query_vec=query_vec, k=search_k, owner=owner, lens=lens)
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
