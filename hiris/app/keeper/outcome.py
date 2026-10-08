"""La riga di HIRIS nel filo di chi ha chiesto una promessa -- la sua casa sola.

Due chiamanti, una guardia (fix round 1, M2): l'orologio (`Sweeper._tell`,
col suo scrittore montato) e le due strade che chiudono una promessa FUORI
dall'orologio (ruling 3.8) -- la scadenza del turno sul ponte
(`close_expired_promise`, qui sotto) e il turno del ponte finito senza
«conclude» (`reasoning/consegna`). Le regole sono le stesse per tutti:
solo se c'e' un filo, filtro dei veleni (anche sul testo del modello citato,
`quoted`), mai un'eccezione. E dalle due strade di fuori nessuna push: non
c'e' una risposta da portare al telefono, solo un fallimento da dichiarare.
"""
from __future__ import annotations

import logging
import time

from ..chat_store import append_assistant_line
from ..providers import SUBSCRIPTION
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


def close_expired_promise(app, job: dict) -> None:
    """Il turno del piano e' scaduto: la promessa fallisce dichiarando l'attesa.

    Estratta invece che scritta in linea dentro lo sweep perche' ha una
    ragione sua e va provata da sola: e' l'unico punto che impedisce a una
    promessa servita dal ponte di restare `in_corso` per sempre quando il
    piano non risponde. `risana()` la chiuderebbe soltanto al prossimo
    riavvio -- cioe' forse mai.

    L'id viene da `wake`: `sweep_expired` azzera `context_json` come fa
    `submit`, e `wake` e' la sola parte del job che sopravvive.
    """
    ident = (job.get("wake") or {}).get("promessa_id") or ""
    store = app.get("agenda")
    riga = store.read(ident) if (store is not None and ident) else None
    if riga is None or riga.get("stato") != "in_corso":
        # Gia' conclusa da `concludi` mentre il turno finiva: non si
        # riapre. E' lo stesso ordine di controlli della consegna
        # (`reasoning/consegna`), per la stessa ragione.
        return
    # **L'attesa e' quella del turno** (S-02, Tappa 6 Task 2): la scadenza
    # viaggia col job, e la `scadenza_min` di ADESSO puo' essere un'altra --
    # l'utente puo' averla cambiata mentre il turno era in coda. Stessa durata
    # che il registro degli esiti riceve qui sotto: una sola, letta una volta.
    durata_s = (float(job.get("deadline_ts", 0.0))
                - float(job.get("created_ts", 0.0)))
    minuti = round(durata_s / 60)
    reason = (f"ho aspettato il {SUBSCRIPTION.name} per {minuti} minuti e non ha "
              "risposto: non so cosa dirti.")
    # Ruling 3.8: chi l'ha chiesta lo legge anche nella sua chat -- una riga,
    # solo se la promessa ha un filo, e nessuna push. `concludi` e' guardato
    # sullo stato: se nel frattempo e' arrivato `conclude`, niente riga.
    if store.concludi(ident, state="fallita", now=time.time(), reason=reason):
        tell_failure(app.get("data_dir"), riga, reason)
    # Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`:
    # terza strada delle promesse sul ponte, dopo il successo (`api/
    # handlers_mcp`) e il turno finito senza «conclude» (`reasoning/
    # consegna`). Stessa famiglia `scaduto` del ramo chat
    # (`api/handlers_chat`): il piano non ha rifiutato, non ha risposto.
    registry = app.get("occurrence_registry")
    if registry is not None:
        registry.fallimento(
            SUBSCRIPTION.id, family="scaduto", code=None,
            message="nessuna conclusione entro la scadenza del ponte (promessa)",
            durata_s=durata_s)
    logger.warning(
        "promessa %s: il turno sul piano e' scaduto dopo %d minuti",
        ident, minuti)
