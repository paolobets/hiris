"""La conservazione: per quanto la casa ricorda, e chi pota.

**Ogni archivio dichiara per quanto tiene** (Tappa 8, Task 6; G-10, D5, D7):
accanto al suo schema, nella forma che `mind/store.CONSERVAZIONE` ha dal
reperto C-6 (`storage.Retention`: per tabella giorni, ragione e
cancellazione), e con un `prune(now)` che la applica. Quali siano gli archivi
non lo dice un elenco: sono i valori dell'app che portano una dichiarazione
(`archives`), e `tests/test_conservazione_archivi.py` li confronta con chi
chiama `storage.init_schema`.

**Un lavoro notturno solo** (`nightly`, alle 03:00) li pota tutti. Fino
all'08/10/2026 le potature erano otto, con quattro inneschi: due lavori alle
03:00 nello stesso secondo, uno ogni due minuti (e solo a ponte acceso), e
quattro a ogni scrittura -- i consumi a ogni turno, le promesse a ogni
promessa, le costruzioni a ogni proposta, la cronaca a ogni comando. Nessun
posto sapeva rispondere a «per quanto tempo HIRIS ricorda questa cosa»: la
risposta adesso e' `declarations`, che `/api/health` mostra.

**La spazzata della coda del ponte** (`reasoning_sweep`) resta ogni due
minuti, perche' non pota: chiude i turni scaduti, raccoglie i ripieghi
schiantati e dimentica le risposte consegnate dopo un quarto d'ora. Gira
**acceso o spento che sia il ponte** (D5, G-11): spazzare cio' che e' gia' in
coda non accoda niente, e a ponte spento un ripiego schiantato teneva la
conversazione bloccata sul 409.

Spostati da `server.py` l'08/10/2026; `server.py` li iscrive allo
schedulatore e basta.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .mind.observer import SCOPE_TURN_KIND
from .models_store import bridge_deadline_min
from .reasoning.consegna import close_expired_promise
from .steering import JOB_SPECIES
from .storage import database_name
from .version import read_version

logger = logging.getLogger(__name__)


def archives(app) -> list[tuple[str, object]]:
    """Gli archivi dell'app, `(nome del file, archivio)`, nell'ordine in cui
    l'avvio li ha aperti: ogni valore che dichiara la sua conservazione e sa
    applicarla. Chiesti all'app, non elencati qui: un archivio nuovo entra da
    solo, e uno senza dichiarazione lo ferma la prova che confronta questo
    insieme coi chiamanti di `storage.init_schema`.

    Il nome e' quello del file, chiesto alla connessione dell'archivio
    (`storage.database_name`): e' il nome che si vede in `/data`."""
    found = []
    for value in app.values():
        kind = type(value)
        if hasattr(kind, "CONSERVAZIONE") and callable(getattr(kind, "prune", None)):
            found.append((database_name(value._conn), value))
    return found


def declarations(app) -> list[dict]:
    """**Per quanto tempo HIRIS ricorda ogni cosa** (D7): per ogni tabella di
    ogni archivio, la finestra in giorni (`None` = per sempre) e la ragione.
    In sola lettura: le finestre sono decisioni scritte accanto agli schemi,
    non manopole (la finestra della chat la sceglie il proprietario dalla sua
    pagina, e qui si vede com'e' adesso)."""
    return [{"archivio": name, "tabella": table, "giorni": days, "ragione": reason}
            for name, store in archives(app)
            for table, (days, reason, _deletion) in store.CONSERVAZIONE.items()]


async def nightly(app) -> None:
    """Il lavoro delle 03:00: ogni archivio applica la sua dichiarazione.

    **Un archivio che non si pota non ferma gli altri**: e' igiene, e un
    disco che non collabora su un archivio non deve lasciare crescere tutti
    gli altri. Si dice quale e perche'.

    Le potature girano fuori dal ciclo degli eventi (`asyncio.to_thread`):
    SQLite e' sincrono, e fino a qui la potatura del grezzo bloccava il ciclo
    dentro un lavoro `async`. Ogni archivio tiene il suo lucchetto.
    """
    now = time.time()
    for name, store in archives(app):
        try:
            removed = await asyncio.to_thread(store.prune, now)
        except Exception as error:
            logger.warning("conservazione: %s non si e' potato (%s: %s)",
                           name, type(error).__name__, error)
            continue
        if removed:
            logger.info("conservazione: %s, %d righe oltre la finestra sono "
                        "uscite", name, removed)


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
    # **Nessun interruttore** (D5, G-11, 08/10/2026). Fino a qui la spazzata
    # leggeva `app["bridge_active"]` e a ponte spento non faceva niente: i
    # turni rimasti in coda non scadevano, un ripiego schiantato teneva la
    # conversazione sul 409, e la coda non si potava mai. Spazzare cio' che e'
    # gia' in coda non accoda niente: il fail-safe «mai accodare in una coda
    # che nessuno spazza» resta dell'instradamento, che e' l'unico ad
    # accodare, e adesso la coda si spazza sempre.
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
    # volo per sempre -- la potatura notturna cancella 'decided', 'expired'
    # e 'failed', mai 'ripiego' -- e finche' resta li' tiene la conversazione
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
