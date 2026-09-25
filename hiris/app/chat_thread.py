"""Il filo: la conversazione di UN soggetto da UN ingresso.

Spec `docs/design/2026-09-25-le-chat-divise.md` §2. Un modulo solo perche'
cinque punti devono calcolarlo nello stesso modo -- la chat, il poll, la coda,
la rotta MCP, l'officina -- e due calcoli dello stesso filo sono due fili.

«Ingresso» e non «canale»: canale in questo codice e' gia' il servizio
firmato (`api/canali.py`) e la strada del modello (`misura_turno`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ENTRY_POINT_BY_AUTH = {"ingress": "pannello", "canale": "firma", "no_token": "sviluppo"}


@dataclass(frozen=True)
class ChatThread:
    subject_key: str
    entry_point: str


def subject_key_for(soggetto: dict | None) -> str:
    """`specie:id` -- mai il nome, che cambia. `-` quando l'id non c'e'."""
    s = soggetto or {}
    return f"{s.get('specie') or 'nessuno'}:{s.get('id') or '-'}"


def entry_point_for(auth_via: str | None) -> str:
    return _ENTRY_POINT_BY_AUTH.get(auth_via or "", "interno")


def thread_for(soggetto: dict | None, auth_via: str | None) -> ChatThread:
    return ChatThread(subject_key_for(soggetto), entry_point_for(auth_via))


def request_thread(request) -> ChatThread:
    return thread_for(request.get("soggetto"), request.get("auth_via"))


def thread_to_context(thread: ChatThread) -> dict:
    return {"subject_key": thread.subject_key, "entry_point": thread.entry_point}


def thread_from_context(d: dict | None) -> ChatThread | None:
    if not d or not d.get("subject_key") or not d.get("entry_point"):
        return None
    return ChatThread(d["subject_key"], d["entry_point"])


async def adopt_if_owner(app, request, thread: ChatThread) -> None:
    """La cronologia di prima delle chat divise va al proprietario (spec §3).

    Alla prima richiesta di una persona che Home Assistant dice proprietaria,
    dall'ingresso `pannello`, le sessioni orfane diventano sue. Non all'avvio:
    li' Home Assistant puo' non rispondere ancora, e un proprietario sbagliato
    non si ripara. Import locali: `chat_store` e le rotte di `api/` importano da
    qui, e questo modulo deve restare una foglia.
    """
    from . import chat_store
    from .api.soffitto import is_owner

    data_dir = app.get("data_dir", "/data")
    soggetto = request.get("soggetto") or {}
    if (thread.entry_point != "pannello" or soggetto.get("specie") != "persona"
            or not chat_store.has_orphans(data_dir)):
        return
    if not await is_owner(app, soggetto):
        return
    n = chat_store.adopt_orphans(data_dir, thread=thread)
    logger.info("cronologia di prima: %d sessioni passano al proprietario (%s)",
                n, thread.subject_key)
