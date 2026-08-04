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
    "description": (
        "Cerca nel second brain di casa fatti/preferenze rilevanti. Se la memoria "
        "semantica non è disponibile (nessun embedder configurato, o il calcolo del "
        "vettore fallisce), il risultato porta `degraded: true` e restituisce gli "
        "elementi più recenti invece dei più pertinenti: in quel caso vanno presentati "
        "come 'i più recenti', non come 'i più pertinenti', perché il confronto dei "
        "significati non è avvenuto. In quella modalità l'archivio documenti non viene "
        "affatto consultato (nessuna ricerca sui documenti caricati): i risultati "
        "riguardano solo fatti/preferenze/scadenze/spese, mai i documenti, e questo va "
        "detto invece di lasciar intendere che l'archivio sia stato controllato."
    ),
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
    """Propone un elemento di conoscenza (stato `pending`, approvato dall'utente).

    Senza embedding l'elemento resta comunque scritto: `KnowledgeStore.search`
    degrada a `recent()` (piu' recenti prima, stessi filtri di riservatezza)
    quando non c'e' un vettore di query, quindi un elemento senza embedding e'
    comunque ritrovabile -- non e' piu' un successo apparente rifiutare qui
    avrebbe solo spostato il difetto vero, che e' a monte: il default di
    fabbrica (NullEmbedder) non calcola MAI un vettore, quindi rifiutare
    significava non salvare nulla su un'installazione stock. Se un embedder
    c'e' e funziona, il vettore si calcola e si salva esattamente come prima;
    se l'embedder non c'e', non risponde, o solleva, si salva comunque senza
    vettore invece di fingere che il ricordo non sia mai stato detto."""
    content = tool_input["content"]
    try:
        emb = await embedder.embed(content) if embedder is not None else None
    except Exception:
        logger.exception("save_knowledge: embedding non calcolato, salvo senza vettore")
        emb = None
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
    chatbot_id: str | None = None,
    allow_sensitive: bool = False,
    kinds: list[str] | str | None = None,
    pseudonymizer: Any = None,
    cloud: bool = True,
    pseudonym_map: dict[str, str] | None = None,
) -> dict:
    # Senza vettore di ricerca non si e' potuto confrontare i significati.
    # `KnowledgeStore.search` degrada da se' a `recent()` quando riceve un
    # vettore vuoto (stessi filtri di riservatezza, ordine per recenza), quindi
    # qui non serve piu' un ramo: si passa il vettore per quel che e' -- vuoto
    # o pieno -- e il segnale di degradazione arriva nel ritorno.
    # `search_chunks` invece non ha un percorso degradato equivalente (nessuna
    # nozione di "chunk piu' recenti"): senza vettore i chunk vengono
    # semplicemente saltati, invece di restituirli in un ordine arbitrario che
    # sembrerebbe un confronto di significati senza esserlo.
    try:
        qv = await embedder.embed(tool_input["query"]) if embedder is not None else None
    except Exception:
        logger.exception("recall_knowledge: vettore di ricerca non calcolato")
        qv = None
    k = int(tool_input.get("k", 5))
    loop = asyncio.get_running_loop()

    def _search_and_merge() -> list[dict]:
        items = store.search(
            query_vec=qv or [],
            k=k,
            owner=owner,
            chatbot_id=chatbot_id,
            allow_sensitive=allow_sensitive,
            kinds=kinds,
        )
        chunks = store.search_chunks(
            query_vec=qv,
            k=k,
            owner=owner,
            allow_sensitive=allow_sensitive,
        ) if qv else []
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
            # Review C/#5: mirror the store's own semantics (knowledge_store.
            # search/search_chunks gate on `sensitivity='normal'` -- i.e. ANY
            # non-'normal' value is treated as sensitive there), not an exact
            # match on the literal string "sensitive". An exact match let a
            # third sensitivity value reach the cloud LLM verbatim even though
            # the store itself already treats it as sensitive.
            is_sensitive = (sens or "normal") != "normal"
            if is_sensitive and cloud:
                if pseudonymizer is not None:
                    # Record token->value into the caller's per-request
                    # mapping (review B/#7) so ONLY this exchange's own
                    # detokenize call can ever expand these tokens back.
                    content = pseudonymizer.pseudonymize(content, pseudonym_map)
                else:
                    content = "[contenuto sensibile non disponibile]"
            out.append({"id": _id, "kind": kind, "content": content})
        return out

    out = await loop.run_in_executor(None, _search_and_merge)
    return {"results": out, "degraded": not qv}


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
