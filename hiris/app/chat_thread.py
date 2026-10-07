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


# -- Il filo negli archivi (B-52, Tappa 6 Task 2) -----------------------------
#
# Quattro archivi portano il filo nelle stesse due colonne: `chat_sessions`,
# `promesse`, `costruzioni`, `reasoning_jobs`. Fino al 05/10/2026 la condizione
# «di questo filo» era scritta a mano in dodici righe di tre file (dieci in
# `chat_store.py`, la costante di `keeper/store.py`, la coda), e il filo si
# ricostruiva dalla riga in tre: qui vivono una volta sola. I due valori
# viaggiano sempre come parametri (`?`), mai incollati nel testo della query.


def thread_condition(alias: str = "") -> str:
    """La condizione SQL «di questo filo», per `thread_params` come parametri.

    `alias` e' il nome della tabella nella query (`"s"` per `... AS s`), vuoto
    quando la query ne ha una sola."""
    prefix = f"{alias}." if alias else ""
    return f"{prefix}subject_key = ? AND {prefix}entry_point = ?"


def thread_params(thread: ChatThread | None) -> tuple[str | None, str | None]:
    """I due valori del filo nell'ordine delle colonne; `(None, None)` per una
    riga che non ne porta uno -- non se ne inventa uno."""
    if thread is None:
        return (None, None)
    return (thread.subject_key, thread.entry_point)


def thread_from_columns(subject_key: str | None,
                        entry_point: str | None) -> ChatThread | None:
    """Il filo di una riga letta da un archivio; `None` per una riga scritta
    prima che il filo esistesse (le colonne NULL)."""
    if not subject_key:
        return None
    return ChatThread(subject_key, entry_point)


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


def new_subject(specie: str, *, ident: str | None = None, nome: str | None = None,
                utente: str | None = None, ruolo: str | None = None) -> dict:
    """**Il soggetto, in una forma sola** (F-19, Tappa 7): chi chiede, con le
    stesse cinque chiavi da ogni porta -- il confine (`middleware_internal_auth`),
    la firma (`canali.riconosci`), il soffitto (`sole_owner`, `administrators`,
    `ceiling_at_wake`) e il filo (`subject_from_thread`). Fino al 07/10/2026 lo
    costruivano otto punti in quattro forme (5, 4, 2 e 1 chiave), e chi lo
    leggeva non poteva distinguere un campo assente da un campo vuoto.

    - `specie`: `persona`, una specie di servizio (`canali.SERVICE_SPECIES`), `nessuno`
      (il ponte, un turno interno) o `sviluppo`;
    - `id`: la chiave stabile (l'utente di Home Assistant, l'impronta di un
      servizio, il mestiere di un turno) -- `None` quando non c'e';
    - `nome`: l'etichetta da mostrare, mai un'identita';
    - `utente`: il nome utente di Home Assistant, solo per una persona;
    - `ruolo`: il ruolo che viaggia con la credenziale (un servizio), `None`
      per una persona -- il suo lo legge il cancello da Home Assistant."""
    return {"specie": specie, "id": ident or None, "nome": nome or None,
            "utente": utente or None, "ruolo": ruolo or None}


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


def subject_from_thread(thread: ChatThread | None) -> dict | None:
    """Il soggetto di un filo, per chi ha solo il filo: nella forma di
    `new_subject`, con specie e id.

    Serve all'orologio, che al risveglio di una promessa non ha la richiesta
    di chi l'ha chiesta -- ha la riga, e la riga ha il filo. Niente nome:
    cambia, e chi legge questo soggetto (la cronaca, il recapito) si regge
    sull'id. `-` torna `None`, com'era prima di diventare chiave.
    """
    if thread is None:
        return None
    specie, _sep, ident = thread.subject_key.partition(":")
    return new_subject(specie, ident=None if ident in ("", "-") else ident)


def unknown_id_text(nothing: str, by: str = "quell’identificatore") -> str:
    """«Non ho nessuna X con quell'identificatore»: il rifiuto di un id che non c'e'.

    Vive qui perche' e' la frase della regola del filo: un id che non esiste e
    un id di qualcun altro rispondono con **la stessa frase**, o chi prova gli
    id saprebbe quali sono altrui (security 6.3, spec 2026-09-25 §5). Era
    scritta a mano in nove punti, rotte e archivi (C-07, Tappa 4): una sola
    funzione, cosi' i nove non possono divergere.

    `nothing` porta l'accordo che solo chi chiama conosce («nessuna promessa»,
    «nessun servizio»); `by` e' cio' con cui si e' cercato.
    """
    return f"non ho {nothing} con {by}."


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
    un proprietario sbagliato non si ripara. Le promesse hanno una seconda
    porta, il loro risveglio (`keeper/sweeper.py::_adopt_orphan`): una
    promessa che matura prima di questa lettura va al proprietario che Home
    Assistant dice unico, con la stessa funzione dell'archivio; la
    cronologia resta a questa lettura. Import locali: `chat_store` e le
    rotte di `api/` importano da qui, e questo modulo deve restare una foglia.
    """
    from . import chat_store
    from .api.soffitto import is_owner

    data_dir = app["data_dir"]
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
