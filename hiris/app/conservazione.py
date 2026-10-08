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

**I residui** (`RESIDUI_DISMESSI`, `cancella_residui`, `decidi_vault`,
`announce_chatbots_json`): gli archivi dismessi che l'avvio cancella, e
l'annuncio di `chatbots.json`, che invece resta.

Spostati da `server.py` l'08/10/2026; `server.py` li iscrive allo
schedulatore, o li chiama all'avvio, e basta.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from collections.abc import Iterable

from .mind.observer import SCOPE_TURN_KIND
from .mind.store import ATTEMPT_EXPIRED
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


#: **Gli archivi dismessi che si cancellano** (23/09/2026).
#:
#: Erano undici, dichiarati morti nel codice e annunciati a ogni avvio, e
#: restavano per sempre per una regola scritta: «mai dati utente in /data».
#: Ma quella regola era gia' stata contraddetta lo stesso giorno da noi --
#: `vault.db`, cancellato con la fetta 7 -- e il criterio vero non era mai
#: stato scritto.
#:
#: Eccolo: **un archivio che nessun codice legge piu' non e' un dato
#: dell'utente, e' un residuo.** E un residuo entra nei backup di Home
#: Assistant, che non sono cifrati se il proprietario non ci mette una
#: password: il reperto C-4 ne ha escluso il solo `claude`, e il C-6 ha
#: dichiarato la conservazione delle sette tabelle VIVE -- questi file non
#: sono tabelle di nessun archivio vivo, quindi non avevano ne' una
#: dichiarazione ne' un cancellatore.
#:
#: **`chatbots.json` NON e' in questo elenco**, per decisione del
#: proprietario: contiene il prompt personalizzato che aveva salvato sul bot
#: di default, e va guardato prima. Un residuo si cancella quando e' morto
#: **e** quando qualcuno ha deciso -- non per la sola prima meta'. Lo dice
#: all'avvio `announce_chatbots_json`, e la Tappa 8 (D6) lo lascia com'e'
#: finche' il proprietario non lo ha guardato.
#:
#: Entrati l'08/10/2026 (Tappa 8, Task 7, D6):
#: - `agents.json`, il predecessore di `chatbots.json` (prima della rinomina
#:   SP-4): il prompt da guardare sta nel successore, e di lui nessun codice
#:   legge niente dalla fetta E4;
#: - `casa.db` col suo diario (`-wal`) e la sua memoria condivisa (`-shm`):
#:   la copia impoverita dei registri di Home Assistant che l'anagrafe dal
#:   vivo ha sostituito, e che nessun codice apre piu' (M-40). Un `-wal` senza
#:   il suo archivio non e' leggibile da nessuno.
#:
#: L'elenco e' NOMINATO, mai un'euristica sul nome: un archivio vivo che
#: somigliasse a un residuo, o uno che nascera' domani, non deve poter
#: sparire per assonanza.
RESIDUI_DISMESSI = (
    "advisory.db",
    "agents.json",
    "casa.db",
    "casa.db-shm",
    "casa.db-wal",
    "dashboard_backups.json",
    "ha_health.json",
    "history.db",
    "history_policy.json",
    "hiris_memory.db",
    "knowledge.db",
    "portrait.db",
    "proposals.db",
    "sentinel.db",
    "tasks.json",
)


#: Perche' un residuo se ne va: la frase che il registro dice accanto al nome.
_DISMESSO = ("nessun codice lo leggeva piu', e un archivio dismesso entra nei "
             "backup di Home Assistant come tutto il resto di /data.")
_IMPORTATO = ("il suo totale e' gia' nell'archivio dei consumi "
              "(`legacy_importati`), e nessun codice lo legge piu'.")


def cancella_residui(data_dir: str, imported: Iterable[str] = ()) -> None:
    """Cancella gli archivi dismessi, **dicendo quali e quanto erano grandi**.

    `imported` sono i contatori di prima (`usage*.json`) che l'archivio dei
    consumi ha gia' registrato come importati (`UsageStore.legacy_imported`,
    D6 della Tappa 8): da li' in poi sono un residuo come gli altri. Uno che
    non si e' potuto importare -- illeggibile -- non e' fra questi, e resta.

    Cancellare dati di un utente in silenzio e' proibito dalle fondamenta di
    questo progetto: si dice il nome e la dimensione, non «ho fatto pulizia».

    **Un file che non c'e' non fa rumore.** La casa di chi installa oggi non
    ne ha nessuno, e una riga per ognuno a ogni avvio sarebbe rumore sano che
    seppellisce quello vero.

    Non solleva mai: e' igiene, non una condizione di funzionamento. Un
    permesso negato o un disco pieno non devono impedire a HIRIS di partire --
    stessa disciplina di `decidi_vault`.
    """
    residues = [(os.path.join(data_dir, nome), _DISMESSO) for nome in RESIDUI_DISMESSI]
    residues += [(percorso, _IMPORTATO) for percorso in imported]
    for percorso, ragione in residues:
        nome = os.path.basename(percorso)
        try:
            if not os.path.exists(percorso):
                continue
            quanto = os.path.getsize(percorso)
            os.remove(percorso)
        except OSError as errore:
            logger.warning(
                "%s non si e' potuto cancellare (%s: %s): resta su disco",
                nome, type(errore).__name__, errore)
            continue
        logger.info("%s cancellato (%d byte): %s", nome, quanto, ragione)


def decidi_vault(data_dir: str) -> None:
    """Cancella `vault.db`, e dice cosa conteneva (reperto C-6, 23/09/2026).

    **Prima lo ANNUNCIAVA.** Una riga informativa all'avvio diceva che il file
    conteneva «DATI PERSONALI IN CHIARO» -- la mappa PII<->token della
    pseudonimizzazione, la cui cifratura a riposo fu rinviata e mai fatta --
    che nessun codice lo legge piu', e che cancellarlo era «una decisione
    tua». Ma una riga fra centinaia di righe di avvio non e' un modo di dire
    una cosa a una persona, e quella persona per decidere avrebbe dovuto
    aprire un file SQLite dentro il contenitore dell'add-on.

    Quindi decide HIRIS, ed e' la decisione facile: un file che nessuno legge,
    che nessuna interfaccia svuota e che contiene dati personali in chiaro e'
    solo un rischio -- tanto piu' da quando si sa che entrava nei backup.

    **Si dice cosa e' stato cancellato**, non «ho fatto pulizia»: cancellare
    dati di un utente in silenzio e' proibito dalle fondamenta di questo
    progetto. Un file vuoto se ne va senza avvisi: non c'era niente da
    raccontare, e il rumore sano seppellisce quello vero.

    Non solleva mai: e' igiene, non una condizione di funzionamento.
    """
    percorso = os.path.join(data_dir, "vault.db")
    if not os.path.exists(percorso):
        return
    righe = None
    try:
        conn = sqlite3.connect(percorso)
        try:
            righe = conn.execute("SELECT COUNT(*) FROM pii").fetchone()[0]
        finally:
            conn.close()
    except Exception as errore:
        # Corrotto, o senza la tabella che ci si aspetta: si cancella lo
        # stesso -- nessuno lo legge -- e si dice che non lo si e' potuto
        # contare, invece di affermare uno zero che nessuno ha misurato.
        logger.info("vault.db non si e' potuto leggere prima di cancellarlo "
                    "(%s: %s)", type(errore).__name__, errore)
    try:
        os.remove(percorso)
    except OSError as errore:
        logger.warning("vault.db non si e' potuto cancellare (%s: %s): resta "
                       "su disco, e contiene dati personali in chiaro",
                       type(errore).__name__, errore)
        return
    if righe:
        logger.warning(
            "vault.db cancellato: conteneva %d righe della mappa PII<->token "
            "della pseudonimizzazione, con la colonna `value` IN CHIARO (la "
            "cifratura a riposo fu rinviata e mai fatta). Nessun codice lo "
            "leggeva piu' da quando brain/privacy.py e' uscito, e nessuna "
            "interfaccia lo svuotava: restava solo a farsi copiare nei backup.",
            righe)


def announce_chatbots_json(data_dir: str) -> None:
    """L'annuncio di `chatbots.json` all'avvio (uscito da `server.py` nella
    Tappa 8, Task 7).

    Un `chatbots.json` di un'installazione precedente non ha piu' nessun
    lettore ne' scrittore: l'entita' Chatbot e la sua migrazione sono uscite
    con la fetta E4. Il prompt personalizzato eventualmente salvato sul bot di
    default NON viene migrato nelle impostazioni della chat, e il file **resta
    su disco finche' il proprietario non lo ha guardato** (D6 della Tappa 8):
    per lui e solo per lui la frase «resta, intatto» e' vera. Il predecessore
    `agents.json` e' invece un residuo, e lo cancella `cancella_residui`.
    """
    if os.path.exists(os.path.join(data_dir, "chatbots.json")):
        logger.info(
            "chatbots.json presente in %s da un'installazione precedente: da "
            "fetta E4 Task 4 nessun codice lo legge ne' lo scrive piu' "
            "(l'entita' Chatbot e' uscita, sostituita dalle impostazioni della "
            "chat). Il prompt personalizzato eventualmente salvato sul bot di "
            "default non viene migrato -- si riparte con i default nel codice. "
            "Il file resta su disco, intatto, finche' non lo guardi.",
            data_dir,
        )


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
                    outcome=ATTEMPT_EXPIRED,
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
