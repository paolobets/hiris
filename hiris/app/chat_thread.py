"""Il filo: la conversazione di UN soggetto da UN ingresso.

Spec `docs/design/2026-09-25-le-chat-divise.md` §2. Un modulo solo perche'
cinque punti devono calcolarlo nello stesso modo -- la chat, il poll, la coda,
la rotta MCP, l'officina -- e due calcoli dello stesso filo sono due fili.

«Ingresso» e non «canale»: canale in questo codice e' gia' il servizio
firmato (`api/canali.py`) e la strada del modello (`misura_turno`).
"""
from __future__ import annotations

import logging
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ENTRY_POINT_BY_AUTH = {"ingress": "pannello", "canale": "firma", "no_token": "sviluppo"}


@dataclass(frozen=True)
class ChatThread:
    subject_key: str
    entry_point: str


class SyncTurnsInFlight:
    """I fili con un turno SINCRONO in volo (la catena, JSON o SSE).

    Il turno del ponte ha la sua guardia nella coda (`has_pending_chat`); il
    turno sincrono no: dura quanto la chiamata al modello, e per tutto quel
    tempo nessuna riga dice che la risposta sta per essere scritta nella
    conversazione attiva. Senza questo segno «nuova», «riprendi» e «cancella»
    rispondevano 200 a meta' turno e la risposta atterrava nella conversazione
    ripresa (fetta «il seguito delle chat divise», review di sicurezza Low-1).

    Un contatore e non un insieme: due turni dello stesso filo possono
    sovrapporsi, e il primo che finisce non deve liberare il filo al secondo.
    In memoria, come la chiamata che protegge: muore col processo.
    """

    def __init__(self) -> None:
        self._counts: Counter[ChatThread] = Counter()

    @contextmanager
    def turn(self, thread: ChatThread):
        self._counts[thread] += 1
        try:
            yield
        finally:
            self._counts[thread] -= 1
            if self._counts[thread] <= 0:
                del self._counts[thread]

    def busy(self, thread: ChatThread) -> bool:
        return self._counts.get(thread, 0) > 0


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
    """La forma JSON del filo, per la risposta della rotta di claim.

    Non c'e' la funzione inversa perche' nessuno la rilegge: il runner non usa
    il filo del claim, e dentro il processo il filo si prende dalle colonne
    della coda (`job["thread"]`), mai da un dizionario.
    """
    return {"subject_key": thread.subject_key, "entry_point": thread.entry_point}


def subject_from_thread(thread: ChatThread | None) -> dict | None:
    """Il soggetto di un filo, per chi ha solo il filo: `{"specie", "id"}`.

    Serve all'orologio, che al risveglio di una promessa non ha la richiesta
    di chi l'ha chiesta -- ha la riga, e la riga ha il filo. Niente nome:
    cambia, e chi legge questo soggetto (la cronaca, il recapito) si regge
    sull'id. `-` torna `None`, com'era prima di diventare chiave.
    """
    if thread is None:
        return None
    specie, _sep, ident = thread.subject_key.partition(":")
    return {"specie": specie, "id": None if ident in ("", "-") else ident}


def without_thread(row: dict) -> dict:
    """La riga senza il filo, per chi risponde fuori dal processo.

    Il filo serve dentro (chi vede, chi riceve l'esito); fuori non si mostra,
    e un `ChatThread` `json_response` non saprebbe nemmeno serializzarlo. Una
    funzione sola per le rotte e per gli strumenti che rispondono con righe
    che lo portano.
    """
    return {k: v for k, v in row.items() if k != "thread"}


async def adopt_if_owner(app, request, thread: ChatThread) -> None:
    """Cio' che c'era prima delle chat divise va al proprietario (spec §3).

    Alla prima richiesta di una persona che Home Assistant dice proprietaria,
    dall'ingresso `pannello`, le sessioni orfane diventano sue -- e, dalla
    fetta «il seguito delle chat divise» (spec 2026-09-26 §2), anche le
    promesse orfane: nello stesso momento e con la stessa regola, perche' due
    regole per lo stesso passaggio di proprieta' sarebbero due proprietari
    possibili. Non all'avvio: li' Home Assistant puo' non rispondere ancora, e
    un proprietario sbagliato non si ripara. Import locali: `chat_store` e le
    rotte di `api/` importano da qui, e questo modulo deve restare una foglia.
    """
    from . import chat_store
    from .api.soffitto import is_owner

    data_dir = app.get("data_dir", "/data")
    agenda = app.get("agenda")
    soggetto = request.get("soggetto") or {}
    if thread.entry_point != "pannello" or soggetto.get("specie") != "persona":
        return
    chat_orphans = chat_store.has_orphans(data_dir)
    promise_orphans = agenda is not None and agenda.has_orphans()
    if not (chat_orphans or promise_orphans):
        return
    if not await is_owner(app, soggetto):
        return
    if chat_orphans:
        n = chat_store.adopt_orphans(data_dir, thread=thread)
        logger.info("cronologia di prima: %d sessioni passano al proprietario (%s)",
                    n, thread.subject_key)
    if promise_orphans:
        n = agenda.adopt_orphans(thread)
        logger.info("promesse di prima: %d passano al proprietario (%s)",
                    n, thread.subject_key)
