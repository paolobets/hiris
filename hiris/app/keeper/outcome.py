"""La riga di HIRIS nel filo di chi ha chiesto una promessa -- la sua casa sola.

Due chiamanti, una guardia (fix round 1, M2): l'orologio (`Sweeper._tell`,
col suo scrittore montato) e le due strade che chiudono una promessa FUORI
dall'orologio (ruling 3.8) -- la scadenza del turno sul ponte
(`server._close_expired_promise`) e il turno del ponte finito senza
«conclude» (`api/handlers_reasoning`). Le regole sono le stesse per tutti:
solo se c'e' un filo, filtro dei veleni (anche sul testo del modello citato,
`quoted`), mai un'eccezione. E dalle due strade di fuori nessuna push: non
c'e' una risposta da portare al telefono, solo un fallimento da dichiarare.
"""
from __future__ import annotations

import logging

from ..chat_store import append_assistant_line
from .promise import failure_message

logger = logging.getLogger(__name__)


def write_line(write, promise: dict, content: str, *,
               quoted: str | None = None) -> bool:
    """Scrive `content` nel filo della promessa con `write(thread, content,
    quoted=...)`; `True` se e' entrata. Non solleva MAI: chi chiama ha gia'
    chiuso la promessa, e una chat che non si scrive non deve riaprirla, ne'
    rompere il battito, ne' far cadere una rotta."""
    thread = promise.get("thread")
    if thread is None:
        return False
    try:
        written = bool(write(thread, content, quoted=quoted))
    except Exception as error:
        logger.warning("promessa %s: riga non scritta nel filo (%s)",
                       promise.get("id"), type(error).__name__)
        return False
    if not written:
        logger.info("promessa %s: riga non scritta nel filo (filtrata)",
                    promise.get("id"))
    return written


def tell_failure(data_dir: str | None, promise: dict, reason, *,
                 quoted: str | None = None) -> bool:
    """La riga breve di una promessa fallita, per chi ha `data_dir` e non
    l'orologio. Senza `data_dir` (un'app non montata del tutto) non si
    scrive: la cartella di ripiego `/data` e' quella di produzione, e
    scriverci da un contesto che non la conosce sarebbe scrivere nel posto
    sbagliato."""
    if not data_dir:
        return False

    def write(thread, content, *, quoted=None):
        return append_assistant_line(content, data_dir, thread=thread,
                                     quoted=quoted)

    return write_line(write, promise, failure_message(promise, reason),
                      quoted=quoted)
