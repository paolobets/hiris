"""La conservazione: per quanto la casa ricorda, e chi pota.

Spostato da `server.py` l'08/10/2026 (Tappa 8, Task 6), senza cambiare una
riga di logica: la potatura del grezzo e quella della chat, che giravano alle
03:00 nello stesso secondo, e la spazzata della coda del ponte. `server.py`
le iscrive allo schedulatore e basta.
"""
from __future__ import annotations

import logging
import time

from .chat_store import delete_old_messages
from .mind.observer import SCOPE_TURN_KIND
from .mind.store import READING_RETENTION_S
from .models_store import bridge_deadline_min
from .reasoning.consegna import close_expired_promise
from .steering import JOB_SPECIES
from .version import read_version

logger = logging.getLogger(__name__)


# La potatura del grezzo: senza, l'archivio dei cambi cresce per sempre.
# Il numero di giorni non si scrive a mano -- si deriva dalla costante
# dell'archivio (`mind/store.READING_RETENTION_S`, 22 giorni: 21
# di promessa, il 22esimo la guardia che la rende vera al bordo), cosi'
# la riga di log non puo' mentire quando la costante cambia
# (task-5-correzioni.md, punto C).
#
# try/except proprio (task-5-fix-brief.md, punto 3): era l'unico dei tre
# lavori del cervello senza una rete sua -- un guasto di SQLite alle tre
# di notte finiva nel registro di apscheduler senza il prefisso
# «cervello:», mentre i due fratelli (le condizioni, l'aggregazione) ce
# l'hanno gia'.
async def prune_observations(app) -> None:
    try:
        count = app["observations"].prune(time.time())
        if count:
            days = READING_RETENTION_S // 86400
            logger.info("cervello: %s cambi oltre i %s giorni sono usciti",
                        count, days)
    except Exception as error:
        logger.warning("cervello: potatura fallita (%s: %s)",
                       type(error).__name__, error)


# Daily retention job (chat messages only -- knowledge/memory items no
# longer expire, Task 6 "la memoria non evapora": handle_save_memory
# stopped computing a valid_until, so purge_expired_chatbot had no more
# work fed to it and was removed).
#
# Task 12: la fonte del numero di giorni non e' piu' il globale di modulo
# `chat_store.HISTORY_RETENTION_DAYS` (uscito dal modulo) ma
# `app["chat_settings"].retention_days` -- letto AD OGNI GIRO
# dentro la chiusura, non catturato una volta sola all'avvio: un PUT su
# /api/chat-settings riassegna quella chiave a caldo
# (`handlers_settings.handle_save_settings`), e la potatura di
# stanotte deve vedere il valore che l'utente ha scelto oggi, non quello
# con cui l'add-on e' partito.
def run_retention(app) -> None:
    days = app["chat_settings"].retention_days
    if days > 0:
        n = delete_old_messages(app["data_dir"], days)
        if n:
            logger.info("Retention: deleted %d old chat messages", n)


# ── Ponte push (Piano A): spazzata dei job scaduti senza risposta dal
# runner remoto. Il ramo chat resta (Slice 4b): un job "chat" scaduto
# resta semplicemente 'expired', esposto alla sua stessa route di poll.
# fetta E3 Task 4: il ramo di fallback olistico (ragionava in locale via
# _run_decision) e' uscito con `_holistic_reason`, l'unico produttore di
# job kind="holistic" -- nessun job di quel tipo viene piu' accodato.
# Silenzio dichiarato: un job kind="holistic" qui puo' arrivare SOLO da
# un reasoning.db lasciato da un'installazione precedente questo
# deploy -- nessun fallback locale lo ragiona piu', quindi non e' un
# pass silenzioso: un log esplicito lo dichiara prima di lasciarlo
# scadere (sweep_expired lo ha gia' marcato 'expired' sopra).
async def reasoning_sweep(app) -> None:
    reasoning_queue = app["reasoning_queue"]
    # Lo STESSO VALORE dell'instradamento, non la stessa espressione: fino
    # alla 2.5.0 i due gate chiamavano `_bridge_active` ciascuno per conto
    # suo sugli stessi due ingressi, e il fail-safe «mai accodare in una
    # coda che nessuno spazza» reggeva sul fatto che le due chiamate
    # restassero identiche. Adesso il valore e' derivato UNA volta
    # (`_recompute_chain`) e qui si LEGGE: due letture dello stesso slot
    # non possono divergere nemmeno per distrazione. Ed e' anche cio' che
    # rende la spazzata sensibile al ponte spento dalla pagina, senza un
    # riavvio.
    if not app.get("bridge_active"):
        return
    for job in reasoning_queue.sweep_expired(time.time()):
        if job.get("kind") == "promessa":
            # Fetta «le promesse seguono la catena» (22/08/2026): il turno
            # e' scaduto senza che il piano rispondesse. La promessa non
            # puo' restare `in_corso` -- sarebbe invisibile, e peggio di
            # una fallita: `risana()` la chiuderebbe solo al prossimo
            # riavvio, cioe' forse mai.
            close_expired_promise(app, job)
            continue
        if job.get("kind") == SCOPE_TURN_KIND:
            # **Un turno dell'osservatore scaduto deve lasciare traccia**
            # (correzione della review indipendente, 11/09/2026). Senza,
            # l'ultimo tentativo resta «accodata» per sempre e la pagina
            # dice «in corso da N minuti» mentre il piano non rispondera'
            # mai: un worker fermo con un token buono diventa
            # indistinguibile da un'attesa legittima -- lo stesso guasto
            # appiattito su un'assenza che questa fetta esiste per togliere.
            # E' il gemello di `close_expired_promise` (`reasoning/consegna`).
            store = app.get("observations")
            if store is not None:
                attesa = max(0.0, job.get("deadline_ts", 0) - job.get("created_ts", 0))
                store.record_attempt(
                    outcome="scaduta",
                    detail=f"il piano non ha risposto entro {attesa / 60:.0f} minuti",
                    version=read_version())
            logger.warning(
                "osservatore: il turno %s e' scaduto senza risposta dal piano",
                job.get("job_id"))
            continue
        if job.get("kind") == "chat":
            continue
        # Una specie dichiarata (`steering.JOB_SPECIES`) e' un turno che il
        # piano non ha fatto in tempo a servire, non un orfano: fino al
        # 06/10/2026 analisi, ricette e attuazione scadute finivano nel
        # registro come «orfano (ponte olistico rimosso)» (rapporto T0-T2
        # della Tappa 6). Orfano resta solo un tipo che nessuno dichiara
        # piu', come l'olistico di un archivio di prima della fetta E3.
        if job.get("kind") in JOB_SPECIES:
            logger.warning(
                "reasoning sweep: il turno %s (%s) e' scaduto senza risposta "
                "dal piano", job.get("job_id"), job.get("kind"))
        else:
            logger.warning(
                "reasoning sweep: job %s di tipo %r orfano (ponte olistico rimosso, "
                "fetta E3 Task 4), scartato",
                job.get("job_id"), job.get("kind"))
    # fetta «la catena diventa l'unica verita'», Task 14. Lo sweep NON ruba
    # il lavoro al poll: `sweep_expired` guarda solo 'pending'/'claimed' e
    # non tocca i job in 'ripiego' -- e' cio' che rende sicura la
    # convivenza fra i due, visto che il ripiego vive nella rotta di poll
    # (ogni 3,5 s) e non qui (ogni 2 minuti).
    #
    # Ma un job rimasto in 'ripiego' oltre il DOPPIO della scadenza e' un
    # ripiego che si e' schiantato: il processo e' caduto mentre chiedeva
    # alla catena, e nessuno chiudera' piu' quel job. Non puo' restare in
    # volo per sempre -- `prune` cancella 'decided', 'expired' e 'failed',
    # mai 'ripiego' -- e finche' resta li' tiene anche la conversazione
    # bloccata sul 409 (`has_pending_chat` conta i ripieghi come in volo).
    # Il doppio, e non la scadenza secca, perche' il ripiego COMINCIA alla
    # scadenza: il margine e' il tempo che la catena ha per rispondere.
    reasoning_queue.fail_stuck_downgrades(
        time.time() - 2 * 60 * bridge_deadline_min(app.get("models_config")))
    # **Le risposte consegnate si dimenticano** (reperto C-6,
    # 23/09/2026). La domanda si azzera alla consegna da sempre
    # (`submit`); la risposta restava fino alla potatura a sette giorni,
    # anche dopo che il proprietario aveva cancellato la conversazione.
    #
    # Un quarto d'ora di margine, e non zero: un ricaricamento della
    # pagina rifa' il poll sullo stesso lavoro, e una risposta svuotata
    # all'istante gli tornerebbe come «non e' arrivata in tempo». La
    # spazzata gira ogni due minuti, quindi il ritardo vero e' il margine.
    dimenticate = reasoning_queue.forget_delivered(
        before_ts=time.time() - 15 * 60)
    if dimenticate:
        logger.info("coda del ragionamento: dimenticate %d risposte gia' "
                    "consegnate", dimenticate)
    reasoning_queue.prune(time.time() - 7 * 86400)
