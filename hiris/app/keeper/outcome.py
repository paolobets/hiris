"""La riga di HIRIS nel filo di chi ha chiesto una promessa -- la sua casa sola.

Due chiamanti, una guardia (fix round 1, M2): l'orologio (`Sweeper._tell`,
col suo scrittore montato) e le due strade che chiudono una promessa FUORI
dall'orologio (ruling 3.8) -- la scadenza del turno sul ponte
(`reasoning/consegna.close_expired_promise`) e il turno del ponte finito senza
«conclude» (`reasoning/consegna.consegna`), che passano tutte e due da
`fail_unfinished`. Le regole sono le stesse per tutti:
solo se c'e' un filo, filtro dei veleni (anche sul testo del modello citato,
`quoted`), mai un'eccezione. E dalle due strade di fuori nessuna push: non
c'e' una risposta da portare al telefono, solo un fallimento da dichiarare.
"""
from __future__ import annotations

import logging

from ..chat_store import append_assistant_line
from ..providers import SUBSCRIPTION
from ..states import FAILED, TAKEN
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


def tell_failure(data_dir: str, promise: dict, reason, *,
                 quoted: str | None = None) -> bool:
    """La riga breve di una promessa fallita, per chi ha `data_dir` e non
    l'orologio. `data_dir` e' `app["data_dir"]`, letto senza ripiego (D-27,
    Tappa 8): fino all'08/10/2026 qui c'era una guardia per «un'app non
    montata del tutto», cioe' per le prove che costruivano un'app senza la
    cartella -- in produzione l'avvio la scrive sempre per prima."""

    def write(thread, content, *, quoted=None):
        return append_assistant_line(content, data_dir, thread=thread,
                                     quoted=quoted)

    return write_line(write, promise, failure_message(promise, reason),
                      quoted=quoted)


#: Come finisce `fail_unfinished`: la promessa non c'e', era gia' conclusa,
#: o l'ha chiusa lei. Parole di un esito interno, come quelle della consegna
#: (`reasoning/consegna`), che le riporta.
UNKNOWN = "sconosciuta"
ALREADY_CLOSED = "gia_conclusa"
CLOSED = "chiusa"


def fail_unfinished(app, ident: str, *, reason: str, now: float, family: str,
                    message: str, durata_s: float,
                    quoted: str | None = None) -> str:
    """Chiude `fallita` una promessa che il ponte ha lasciato `in_corso`.

    **La sua casa sola** (D-24, Tappa 8): fino all'08/10/2026 lo stesso
    giro -- rileggere la promessa, chiuderla solo se ancora presa in carico,
    dirlo nel filo, contarlo nel registro degli esiti -- era scritto due
    volte, nella scadenza del turno (`reasoning/consegna.close_expired_promise`)
    e nella consegna di un turno finito senza «conclude»
    (`reasoning/consegna`), con l'ordine dei controlli tenuto uguale a mano.

    Una promessa che non e' piu' presa in carico e' gia' stata conclusa
    (`conclude` e' arrivato mentre il turno finiva): non si riapre, ne' si
    conta. Riaprirla cancellerebbe un testo che chi l'ha chiesta puo' gia'
    aver letto, o farebbe partire una seconda notifica.

    Ruling 3.8: chi l'ha chiesta lo legge anche nella sua chat -- una riga,
    solo se la promessa ha un filo, e nessuna push. `concludi` e' guardato
    sullo stato: se nel frattempo e' arrivato `conclude`, niente riga.
    `quoted` e' la risposta del modello citata nel motivo, che passa dal
    filtro dei veleni da sola.

    Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`: il
    registro degli esiti conta anche le promesse del ponte, con la `family`
    che dice cosa e' successo (`scaduto` per chi non ha risposto, `altro` per
    chi ha risposto senza seguire il protocollo).
    """
    store = app.get("agenda")
    row = store.read(ident) if (store is not None and ident) else None
    if row is None:
        return UNKNOWN
    if row.get("stato") != TAKEN:
        return ALREADY_CLOSED
    if store.concludi(ident, state=FAILED, now=now, reason=reason):
        tell_failure(app["data_dir"], row, reason, quoted=quoted)
    registry = app.get("occurrence_registry")
    if registry is not None:
        registry.fallimento(SUBSCRIPTION.id, family=family, code=None,
                            message=message, durata_s=durata_s)
    return CLOSED

