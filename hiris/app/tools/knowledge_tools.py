from __future__ import annotations
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

SAVE_KNOWLEDGE_TOOL_DEF = {
    "name": "save_knowledge",
    "description": (
        "Proponi di salvare un fatto/preferenza/scadenza/spesa nel "
        "second brain di casa. Crea una proposta che l'utente approva."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["fact", "preference", "obligation", "expense", "note"],
            },
            "content": {"type": "string", "description": "Il testo da ricordare"},
            "title": {"type": "string"},
            "amount": {"type": "number"},
            "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            "category": {"type": "string"},
            "sensitivity": {"type": "string", "enum": ["normal", "sensitive"]},
        },
        "required": ["kind", "content"],
    },
}

RECALL_KNOWLEDGE_TOOL_DEF = {
    "name": "recall_knowledge",
    "description": "Cerca nel second brain di casa fatti/preferenze rilevanti.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "Quanti risultati (default 5)"},
        },
        "required": ["query"],
    },
}

LINK_KNOWLEDGE_TOOL_DEF = {
    "name": "link_knowledge",
    "description": "Collega due item del second brain (proposta).",
    "input_schema": {
        "type": "object",
        "properties": {
            "src_id": {"type": "integer"},
            "dst_id": {"type": "integer"},
            "relation": {"type": "string"},
        },
        "required": ["src_id", "dst_id", "relation"],
    },
}


async def handle_save_knowledge(
    store: Any, embedder: Any, tool_input: dict, *, owner: str
) -> dict:
    content = tool_input["content"]
    try:
        emb = await embedder.embed(content)
    except Exception:
        emb = []
    loop = asyncio.get_running_loop()
    item_id = await loop.run_in_executor(
        None,
        lambda: store.add_item(
            kind=tool_input["kind"],
            content=content,
            owner=owner,
            title=tool_input.get("title", ""),
            amount=tool_input.get("amount"),
            due_date=tool_input.get("due_date"),
            category=tool_input.get("category"),
            embedding=emb or None,
            sensitivity=tool_input.get("sensitivity", "normal"),
            source="chat",
            status="pending",
        ),
    )
    return {"id": item_id, "status": "pending"}


async def handle_recall_knowledge(
    store: Any,
    embedder: Any,
    tool_input: dict,
    *,
    owner: str,
    allow_sensitive: bool = False,
    pseudonymizer: Any = None,
    cloud: bool = True,
) -> dict:
    try:
        qv = await embedder.embed(tool_input["query"])
    except Exception:
        qv = []
    if not qv:
        return {"results": []}
    k = int(tool_input.get("k", 5))
    loop = asyncio.get_running_loop()

    def _search_and_merge() -> list[dict]:
        items = store.search(
            query_vec=qv,
            k=k,
            owner=owner,
            allow_sensitive=allow_sensitive,
        )
        chunks = store.search_chunks(
            query_vec=qv,
            k=k,
            owner=owner,
            allow_sensitive=allow_sensitive,
        )
        # Merge: items carry their own "kind"; chunks use kind="document_chunk"
        merged: list[tuple[float, int, str, str, str | None]] = []
        for r in items:
            merged.append((r.get("score", 0.0), r["id"], r["kind"],
                           r["content"], r.get("sensitivity")))
        for c in chunks:
            merged.append((c.get("score", 0.0), c["id"], "document_chunk",
                           c["content"], c.get("sensitivity")))
        merged.sort(key=lambda x: x[0], reverse=True)
        out = []
        for _score, _id, kind, content, sens in merged[:k]:
            is_sensitive = sens == "sensitive"
            if is_sensitive and cloud:
                if pseudonymizer is not None:
                    content = pseudonymizer.pseudonymize(content)
                else:
                    content = "[contenuto sensibile non disponibile]"
            out.append({"id": _id, "kind": kind, "content": content})
        return out

    out = await loop.run_in_executor(None, _search_and_merge)
    return {"results": out}


async def handle_link_knowledge(store: Any, tool_input: dict) -> dict:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: store.add_link(
            src_id=int(tool_input["src_id"]),
            dst_id=int(tool_input["dst_id"]),
            relation=tool_input["relation"],
            source="inferred",
        ),
    )
    return {"ok": True}
