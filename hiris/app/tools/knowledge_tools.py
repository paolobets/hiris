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


# Messaggio unico per il fallimento "senza embedding": lo legge il modello e
# arriva all'utente, quindi dice cosa NON e' successo (non e' stato salvato) e
# perche' contava (non sarebbe stato ritrovabile). Nessun dettaglio tecnico:
# l'eccezione resta nel log del server.
_ERRORE_SENZA_EMBEDDING = (
    "Non sono riuscito a salvare questo ricordo: la memoria semantica non è "
    "disponibile e l'elemento non sarebbe più richiamabile. Riprova più tardi."
)

# Gemello in lettura: un guasto della ricerca non deve arrivare all'utente
# travestito da "non c'e' nulla". Stesse regole di sopra sul dettaglio tecnico.
_ERRORE_RICERCA_SENZA_EMBEDDING = (
    "Non sono riuscito a cercare nella memoria di casa: la memoria semantica "
    "non è disponibile in questo momento. Non posso dire che non ci sia nulla, "
    "solo che non ho potuto controllare."
)


async def handle_save_knowledge(
    store: Any, embedder: Any, tool_input: dict, *, owner: str
) -> dict:
    """Propone un elemento di conoscenza (stato `pending`, approvato dall'utente).

    Senza embedding l'elemento NON e' richiamabile: knowledge_store.search
    filtra su `status='approved' AND embedding IS NOT NULL`. Salvarlo comunque
    riaprirebbe -- spostato di un passo -- lo stesso fallimento silenzioso che
    la coda di approvazione ha chiuso: il modello dice "salvato", l'elemento
    compare nella coda, l'utente lo approva, e resta irraggiungibile. Quindi
    qui, se l'embedding non c'e', si fallisce apertamente e non si scrive
    nulla. Il presupposto e' verificato in questo punto solo, non nella lista
    dei tool esposti, perche' e' l'unico attraversato da TUTTI i percorsi
    (chat, agenti, gateway MCP) e perche' un embedder configurato puo'
    comunque fallire sulla singola chiamata."""
    content = tool_input["content"]
    try:
        emb = await embedder.embed(content) if embedder is not None else None
    except Exception:
        logger.exception("save_knowledge: embedding non calcolato, nulla da salvare")
        emb = None
    if not emb:
        logger.warning("save_knowledge rifiutato: nessun embedding disponibile")
        return {"error": _ERRORE_SENZA_EMBEDDING}
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
            embedding=emb,
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
    # Senza vettore di ricerca non si e' guardato da nessuna parte. Rispondere
    # `{"results": []}` fa dire al modello "non ho trovato nulla" quando la
    # frase vera e' "non ho potuto controllare", e l'utente resta convinto che
    # il ricordo non esista. Il guasto NON porta un elenco: solo l'errore, cosi'
    # resta distinguibile da una ricerca riuscita e senza esiti.
    try:
        qv = await embedder.embed(tool_input["query"]) if embedder is not None else None
    except Exception:
        logger.exception("recall_knowledge: vettore di ricerca non calcolato")
        qv = None
    if not qv:
        logger.warning("recall_knowledge non eseguita: nessun vettore di ricerca")
        return {"error": _ERRORE_RICERCA_SENZA_EMBEDDING}
    k = int(tool_input.get("k", 5))
    loop = asyncio.get_running_loop()

    def _search_and_merge() -> list[dict]:
        items = store.search(
            query_vec=qv,
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
