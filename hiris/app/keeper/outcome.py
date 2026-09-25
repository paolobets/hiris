"""La riga breve di una promessa fallita FUORI dall'orologio (ruling 3.8).

Due strade chiudono una promessa senza passare da `Sweeper`: la scadenza del
turno sul ponte (`server._close_expired_promise`) e il turno del ponte finito
senza «conclude» (`api/handlers_reasoning`). Anche li' chi l'ha chiesta deve
trovarlo nella sua chat -- una riga sola, con le stesse regole dell'orologio
(solo se c'e' un filo, filtro dei veleni) e SENZA push: non c'e' una
risposta da portare al telefono, solo un fallimento da dichiarare.

La forma della riga e' `promise.failure_message`, la stessa dell'orologio; la
scrittura e' `chat_store.append_assistant_line`, la stessa dell'orologio.
Qui c'e' solo la cucitura fra le due per chi ha `data_dir` e non l'orologio.
"""
from __future__ import annotations

import logging

from ..chat_store import append_assistant_line
from .promise import failure_message

logger = logging.getLogger(__name__)


def tell_failure(data_dir: str | None, promise: dict, reason) -> bool:
    """Scrive la riga del fallimento nel filo della promessa; `True` se e'
    entrata. Non solleva mai: chi chiama ha gia' chiuso la promessa, e una
    chat che non si scrive non deve riaprirla ne' far cadere la rotta.

    Senza `data_dir` (un'app non montata del tutto) non si scrive: la
    cartella di ripiego `/data` e' quella di produzione, e scriverci da un
    contesto che non la conosce sarebbe scrivere nel posto sbagliato."""
    if not data_dir or promise.get("thread") is None:
        return False
    try:
        return append_assistant_line(failure_message(promise, reason), data_dir,
                                     thread=promise["thread"])
    except Exception as error:
        logger.warning("promessa %s: fallimento non scritto nel filo (%s)",
                       promise.get("id"), type(error).__name__)
        return False
