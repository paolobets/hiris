from __future__ import annotations

import json
import secrets
import threading
import time

from ..chat_thread import ChatThread, thread_condition, thread_from_columns, thread_params
from ..home_space.historian import day_boundaries, local_date
from ..storage import add_missing_columns, connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reasoning_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    wake_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    nonce TEXT,
    deadline_ts REAL NOT NULL,
    created_ts REAL NOT NULL,
    claimed_ts REAL, decided_ts REAL,
    decision_json TEXT,
    -- **Quando la risposta e' stata CONSEGNATA** (reperto C-6, 23/09/2026).
    -- Non `decided_ts`: fra decisa e consegnata c'e' il poll della pagina, e
    -- una risposta mai raccolta non va dimenticata -- sarebbe lavoro pagato e
    -- buttato. Colonna nuova, quindi in inglese.
    delivered_ts REAL,
    -- Il FILO (fetta «le chat divise», Task 2): CHI chiede e DA DOVE, stessi
    -- nomi di `chat_sessions`/`costruzioni` (spec §2). NULL per i job che non
    -- ne portano uno (le altre specie, o una riga scritta prima di questa
    -- versione) -- non se ne inventa uno.
    subject_key TEXT, entry_point TEXT,
    -- La PRECEDENZA (Tappa 6, Task 2, D4 approvata il 05/10/2026): chi ha il
    -- numero piu' alto si serve prima, a pari numero chi e' arrivato prima.
    -- Colonna nuova, quindi in inglese, come `delivered_ts`.
    priority INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reasoning_status ON reasoning_jobs(status, created_ts);
"""

# `CREATE INDEX ... (kind, subject_key, entry_point, status)`: usato da
# `has_pending_chat` per contare solo il filo di chi chiede. NON sta dentro
# `_SCHEMA` sopra: `init_schema` (storage.py) esegue quello script SEMPRE
# PRIMA di girare le migrazioni -- anche su un archivio vecchio (v1 o v2) che
# non ha ancora `subject_key`/`entry_point` -- e un `CREATE INDEX` su una
# colonna che non esiste ancora fa fallire l'apertura invece di migrare
# (verificato: prova diretta con sqlite3, "no such column"). Si crea invece
# dopo le migrazioni, con `init_schema(..., after_sql=...)` (G-13, Tappa 8):
# a quel punto le colonne esistono davvero SEMPRE, che l'archivio sia appena
# nato (le porta gia' `_SCHEMA`) o appena migrato da v1/v2 (le ha appena
# aggiunte `_migration_3`) -- e' idempotente (`IF NOT EXISTS`), quindi non
# importa se l'indice esisteva gia'.
_IDX_THREAD_SQL = ("CREATE INDEX IF NOT EXISTS idx_reasoning_thread "
                    "ON reasoning_jobs(kind, subject_key, entry_point, status)")

#: **La precedenza di un turno sul ponte** (Tappa 6, Task 2; D4 del piano,
#: approvata da Paolo il 05/10/2026). Il ponte e' una corsia sola: fino alla
#: Tappa 6 `claim` serviva chi era arrivato prima, e una domanda in chat
#: aspettava dietro ai turni del cervello. La chat ha la precedenza piu' alta;
#: tutti gli altri turni stanno sotto, fra loro nell'ordine d'arrivo.
#:
#: Due valori e non uno per specie: la sola decisione presa e' «la chat passa
#: avanti» (spec §4.3). Ogni accodamento la DICHIARA (`priority=`, provato da
#: `tests/test_reasoning_priority.py` sul sorgente); il Task 7 la fa leggere
#: dalla dichiarazione della specie di turno.
PRIORITY_CHAT = 1
PRIORITY_BACKGROUND = 0


def turn_answer(turn: dict | None) -> str:
    """La risposta che un turno ha dato, o `""` se non ne ha data una.

    **Un turno che il ponte dichiara fallito non ha risposto** (06/10/2026).
    Il ponte, quando la CLI manca, scade o esce male, consegna comunque un
    testo -- `[runner non disponibile]`, `[errore runner rc=...]` -- e lo
    accompagna con `outcome: "fallito"` (`agent/runner._reply`, lo stesso
    esito che scrive nel registro dei turni). Quel testo e' per la chat, che
    lo mostra; chi raccoglie un turno del cervello deve leggerlo come
    «nessuna risposta». Misurato nel registro dell'add-on dal 05/10 13:32 al
    06/10 14:05: l'analista rifiutava come «non JSON» lo stesso turno fallito
    ogni ora, fino a mezzanotte.

    Una decisione scritta prima di questa versione non porta l'esito, e si
    legge com'era. Fino a qui la stessa espressione era scritta in quattro
    raccoglitori di `server.py`.
    """
    decision = (turn or {}).get("decision") or {}
    if decision.get("outcome") == "fallito":
        return ""
    return decision.get("reply") or ""


def _row(r) -> dict:
    # `created_ts` viaggia dalla fetta «la catena diventa l'unica verita'»
    # (Task 14): chi ripiega alla scadenza registra nel registro degli esiti
    # QUANTO il piano ha avuto per rispondere, e quel numero e'
    # `deadline_ts - created_ts` -- misurato, non il valore corrente
    # dell'archivio, che l'utente puo' aver cambiato mentre il turno era in
    # volo. Additivo: nessun lettore esistente pinna l'insieme delle chiavi.
    return {"job_id": r["job_id"], "kind": r["kind"], "status": r["status"],
            "nonce": r["nonce"], "wake": json.loads(r["wake_json"]),
            "context": json.loads(r["context_json"]),
            "deadline_ts": r["deadline_ts"], "created_ts": r["created_ts"],
            "priority": r["priority"],
            "thread": thread_from_columns(r["subject_key"], r["entry_point"])}

def _migration_2(conn) -> None:
    """Versione 2 (23/09/2026, reperto C-6): la colonna della consegna.

    Un archivio gia' esistente ha righe senza `delivered_ts`, e restano a
    `NULL`: per loro non si sa se la risposta sia stata consegnata, e nel
    dubbio NON si dimentica. Le pota la potatura a sette giorni, come prima.
    """
    add_missing_columns(conn, "reasoning_jobs", {"delivered_ts": "REAL"})


def _migration_3(conn) -> None:
    """Versione 3 (fetta «le chat divise», Task 2): il filo del job.

    Stesso pattern di `_migration_2`: `ALTER TABLE ADD COLUMN` solo se manca,
    cosi' una seconda apertura dello stesso archivio non fallisce. L'indice
    NON si crea qui: lo crea `init_schema` dopo le migrazioni (`after_sql`,
    vedi il commento su `_IDX_THREAD_SQL`)."""
    add_missing_columns(conn, "reasoning_jobs",
                        {"subject_key": "TEXT", "entry_point": "TEXT"})


def _migration_4(conn) -> None:
    """Versione 4 (Tappa 6, Task 2): la precedenza del turno.

    Stesso schema di `_migration_2` e `_migration_3`: la colonna si aggiunge
    solo se manca. Le righe di prima prendono `PRIORITY_BACKGROUND` (il
    `DEFAULT 0`): un turno accodato prima di questa versione si serve
    nell'ordine d'arrivo, com'era quando e' stato accodato."""
    add_missing_columns(conn, "reasoning_jobs",
                        {"priority": "INTEGER NOT NULL DEFAULT 0"})


class ReasoningQueue:
    def __init__(self, db_path: str, *, read_timezone=None) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        # L'indice del filo dopo le migrazioni (`after_sql`): e' l'UNICO
        # punto in cui le colonne esistono sempre, qualunque sia stata la
        # strada per arrivarci. Vedi il commento su `_IDX_THREAD_SQL`.
        init_schema(self._conn, _SCHEMA, version=4,
                    migrations={2: _migration_2, 3: _migration_3,
                                4: _migration_4},
                    after_sql=_IDX_THREAD_SQL)
        # Una FUNZIONE e non un valore: all'avvio l'archivio della casa puo'
        # non esserci ancora, e il fuso va letto quando serve. Stesso pattern
        # gia' usato per UsageStore (server.py, costruzione di
        # `app["usage"]`).
        self._read_timezone = read_timezone or (lambda: None)
        # Chi aspetta un turno nuovo (A-23, 06/10/2026): il lavoratore del
        # ponte non interroga piu' la coda a intervalli, si fa svegliare da
        # `enqueue`. Uno solo, perche' il consumatore e' uno solo.
        self._on_enqueue = None

    def on_enqueue(self, listener, *, only_if=None) -> None:
        """Registra (o, con `None`, toglie) chi va svegliato a ogni turno
        accodato. Si chiama dopo il commit e fuori dal lucchetto: chi si
        sveglia trova il turno gia' scritto, e puo' prenderlo subito.

        Con `only_if` la sostituzione avviene solo se la sveglia in vigore e'
        ancora quella: un lavoratore che si ferma toglie la SUA, e non quella
        di un lavoratore nuovo che si fosse gia' registrato (G18-1 della
        revisione del 06/10/2026)."""
        if only_if is not None and self._on_enqueue is not only_if:
            return
        self._on_enqueue = listener

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def enqueue(self, kind: str, wake: dict, context: dict, deadline_ts: float,
                *, job_id: str | None = None, now: float,
                thread: ChatThread | None = None,
                priority: int = PRIORITY_BACKGROUND) -> str:
        jid = job_id or secrets.token_urlsafe(12)
        with self._lock:
            self._conn.execute(
                "INSERT INTO reasoning_jobs(job_id,kind,wake_json,context_json,"
                "status,deadline_ts,created_ts,subject_key,entry_point,priority) "
                "VALUES(?,?,?,?, 'pending', ?, ?, ?, ?, ?)",
                (jid, kind, json.dumps(wake), json.dumps(context), deadline_ts, now,
                 *thread_params(thread), int(priority)))
            self._conn.commit()
        listener = self._on_enqueue
        if listener is not None:
            listener()
        return jid

    def claim(self, now: float) -> dict | None:
        """Il prossimo turno da servire: la precedenza piu' alta, poi il
        piu' vecchio (D4 della Tappa 6). Uno scaduto non si serve mai: lo
        chiude `sweep_expired`, e servirlo vorrebbe dire pagare una risposta
        che `submit` rifiutera'."""
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE status='pending' AND deadline_ts > ? "
                "ORDER BY priority DESC, created_ts ASC, id ASC LIMIT 1",
                (now,)).fetchone()
            if r is None:
                return None
            nonce = secrets.token_urlsafe(16)
            self._conn.execute(
                "UPDATE reasoning_jobs SET status='claimed', nonce=?, claimed_ts=? WHERE job_id=?",
                (nonce, now, r["job_id"]))
            self._conn.commit()
        out = _row(r); out["nonce"] = nonce; out["status"] = "claimed"
        return out

    # Silenzio dichiarato (3) della fetta "il ponte riceve il nucleo" (parita'
    # A, Task 5, domanda aperta 7): sia qui in `submit()` sia in
    # `sweep_expired()` sotto, la stessa UPDATE che chiude il job azzera anche
    # `context_json` a '{}'. Il `context` di un job di chat porta il nucleo
    # per intero -- aree, dispositivi, entita', "cio' che le persone hanno
    # detto" (`home_space/briefing.py::compose`) -- e senza questo azzeramento resterebbe
    # nel file `reasoning.db` fino alla potatura a 7 giorni (`prune()`,
    # chiamata da `server.py` con `before_ts = now - 7*86400`), ben oltre il
    # tempo in cui serve a qualcuno. Verificato (non assunto) che nessun
    # lettore lo riapre dopo la risoluzione: `handle_chat_reply_poll` legge
    # solo `decision` dal job (`handlers_chat.py`, il ramo di poll), MAI
    # `context`; `consegna` chiama `q.get(job_id)` anche lui
    # DOPO il proprio submit, ma legge solo `kind`, `wake`, `thread` e
    # `created_ts` (`reasoning/consegna.py`); `has_pending_chat(thread, now=None)` e' una
    # SELECT indicizzata su `kind`/`subject_key`/`entry_point`/`status` (dal
    # Task 2 "la coda porta il filo": prima solo su `status`/`deadline_ts`,
    # senza filo) che non riapre mai `context_json` (il metodo e' piu' sotto
    # in questo stesso file: si cerca per NOME, perche' un
    # rinvio al numero di riga invecchia al primo commit che sposta il
    # metodo -- ed e' gia' successo: quando questo commento e' stato
    # scritto citava `:96-125`, e il metodo era gia' altrove). Il record --
    # riga, `status`, `decision_json`,
    # timestamp -- resta: serve alla contabilita' (conteggio giornaliero,
    # log dello sweep) e alla potatura, che continua a rimuovere le righe
    # invariata. Sparisce solo il CONTENUTO del contesto, sostituito da un
    # oggetto vuoto esplicito (non NULL: un job risolto resta distinguibile
    # da un job che non ha mai portato un contesto).
    def submit(self, job_id: str, nonce: str, decision: dict, now: float) -> bool:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if (r is None or r["status"] != "claimed" or r["nonce"] != nonce
                    or r["deadline_ts"] <= now):
                return False
            self._conn.execute(
                "UPDATE reasoning_jobs SET status='decided', decided_ts=?, decision_json=?, "
                "nonce=NULL, context_json='{}' WHERE job_id=?",
                (now, json.dumps(decision), job_id))
            self._conn.commit()
        return True

    def sweep_expired(self, now: float) -> list[dict]:
        # Stesso azzeramento del commento sopra `submit()`, per la seconda
        # strada di chiusura di un job: quello che scade invece di essere
        # risolto. Un contesto che sopravvivesse solo su questo ramo sarebbe
        # un buco, non un dettaglio -- un job instradato sul ponte che
        # non riceve risposta in tempo (deadline breve, minuti) e' il caso
        # comune, non l'eccezione.
        #
        # `rows` e' letto PRIMA di questa UPDATE: i dict restituiti da
        # `_row(r)` sotto portano ancora il `context` originale (oltre a
        # `kind`, l'unico campo che `conservazione.reasoning_sweep` legge dal
        # valore di ritorno per il suo log). Non e' una svista -- e' il valore
        # di ritorno di QUESTA chiamata, non una rilettura del DB: il
        # `context_json` sulla riga persistita e' comunque '{}' da subito
        # dopo, come dimostra `get(job_id)` chiamato di nuovo.
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE status IN ('pending','claimed') "
                "AND deadline_ts <= ?",
                (now,)).fetchall()
            for r in rows:
                self._conn.execute(
                    "UPDATE reasoning_jobs SET status='expired', context_json='{}' WHERE job_id=?",
                    (r["job_id"],))
            self._conn.commit()
        return [_row(r) for r in rows]

    # ── Il ripiego: da qui il ponte smette di essere un bivio ──────────────
    #
    # fetta «la catena diventa l'unica verita'», Task 14. Fino alla 2.4.1 un
    # turno instradato sul ponte aveva una strada sola: o il piano rispondeva
    # entro la scadenza, o `sweep_expired` lo marcava 'expired' e il messaggio
    # era perso -- la catena non veniva consultata MAI, perche' il bivio sta
    # a monte del router (`api/handlers_chat.handle_chat`) e non ha ritorno.
    # I due metodi qui sotto sono cio' che manca per farne un anello: si
    # prende in carico il turno scaduto (una volta sola, chiunque lo chieda),
    # lo si rifa' sulla catena, e lo si chiude con la risposta arrivata da li'.
    #
    # Lo stato nuovo si chiama 'ripiego' e NON e' uno stato terminale: `prune`
    # cancella 'decided', 'expired' e 'failed', mai lui. Un ripiego che si
    # schianta a meta' (processo caduto durante la chiamata al modello) resta
    # quindi in volo per sempre, ed e' `fail_stuck_downgrades` -- chiamata
    # dallo sweep di `server.py` -- a raccoglierlo.

    def reclaim_expired(self, job_id: str, now: float) -> dict | None:
        """Prende in carico un job di chat scaduto, per ripiegarlo sulla catena.

        Atomico: due poll concorrenti (il browser ne fa uno ogni 3,5 s, e due
        schede aperte sulla stessa conversazione ne fanno due) non possono
        ripiegare due volte lo stesso turno -- il secondo trova lo stato
        'ripiego' e riceve None.

        Restituisce la riga col CONTESTO INTATTO: e' l'unico momento in cui si
        puo', perche' `sweep_expired` lo azzera quando marca 'expired'. Il
        contesto porta la cronologia, il prompt e il nucleo: e' cio' che serve
        per rifare il turno sulla catena senza ricomporlo da capo -- e
        ricomporlo da capo darebbe una risposta a una domanda leggermente
        diversa (il nucleo di ADESSO, non quello del momento in cui l'utente
        ha scritto).

        `claimed_ts` viene riscritto: il reclamo E' una presa in carico, ed e'
        da quel momento che si conta per decidere se un ripiego si e'
        schiantato (vedi `fail_stuck_downgrades`). Il `nonce` va a NULL
        perche' non c'e' piu' nessun worker a cui appartenga questo job: il
        reclamo ha gia' fatto il lavoro che il nonce faceva -- la mutua
        esclusione -- e lasciarlo li' significherebbe che una `submit` in
        ritardo del worker del ponte potrebbe ancora chiudere il job mentre il
        ripiego e' in corso.
        """
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE job_id=? AND kind='chat' "
                "AND status IN ('pending','claimed') AND deadline_ts <= ?",
                (job_id, now)).fetchone()
            if r is None:
                return None
            self._conn.execute(
                "UPDATE reasoning_jobs SET status='ripiego', nonce=NULL, "
                "claimed_ts=? WHERE job_id=?", (now, job_id))
            self._conn.commit()
        out = _row(r)
        out["status"] = "ripiego"
        out["nonce"] = None
        return out

    def resolve_downgrade(self, job_id: str, decision: dict, now: float) -> bool:
        """Chiude un job in 'ripiego' con la risposta arrivata dalla catena.

        Stesso azzeramento di `submit`/`sweep_expired` (vedi il commento sopra
        `submit`): il contesto porta il nucleo per intero e non deve restare su
        disco fino alla potatura a 7 giorni. Non c'e' nonce da verificare -- il
        reclamo e' gia' avvenuto, ed e' lui la mutua esclusione."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE reasoning_jobs SET status='decided', decided_ts=?, "
                "decision_json=?, context_json='{}' WHERE job_id=? AND status='ripiego'",
                (now, json.dumps(decision), job_id))
            self._conn.commit()
            return cur.rowcount > 0

    def fail_stuck_downgrades(self, before_ts: float) -> int:
        """Chiude come 'failed' i ripieghi presi in carico e mai finiti.

        Un job resta in 'ripiego' finche' `resolve_downgrade` non lo chiude: se
        il processo cade a meta' della chiamata al modello, nessuno lo chiude
        piu'. E 'ripiego' non e' fra gli stati che `prune` cancella, quindi
        quella riga -- col suo contesto, cioe' col nucleo -- resterebbe su
        disco per sempre. Si azzera anche qui il contesto, per la stessa
        ragione delle altre due chiusure.

        `before_ts` e' un CONFINE, non una durata: lo calcola il chiamante
        (`conservazione.reasoning_sweep`) dalla scadenza configurata, cosi' questo
        modulo non ha bisogno di conoscere ne' l'archivio ne' un orologio."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE reasoning_jobs SET status='failed', context_json='{}' "
                "WHERE status='ripiego' AND claimed_ts <= ?", (before_ts,))
            self._conn.commit()
            return cur.rowcount

    def latest(self, kind: str, *, wake_key: str | None = None,
               wake_value: str | None = None) -> dict | None:
        """L'ultimo turno accodato di quella specie, con la sua decisione.

        **Perche' esiste, e perche' sta qui.** Un turno instradato sul ponte
        non torna subito: chi l'ha chiesto se ne va, e lo ritrova al giro dopo
        (fetta «l'osservatore chiede a chi risponde davvero», 11/09/2026).
        Ritrovarlo vuol dire conoscerne il `job_id`, e l'unico posto in cui
        quel fatto vive gia' e' questa tabella. Tenerlo anche altrove -- un
        campo su un altro archivio, una variabile sull'app -- sarebbe un
        doppione ai sensi della fondamenta 2, e per giunta uno che **non
        sopravvive a un riavvio**, mentre il job si'.

        **L'ULTIMO, non il primo.** Chi accoda due volte -- il primo turno
        scaduto senza risposta, il secondo appena partito -- deve trovare il
        secondo: leggendo il primo aspetterebbe per sempre una risposta che
        nessuno dara' piu'.

        Con `wake_key`, solo i turni la cui sveglia porta quella chiave (e,
        con `wake_value`, quel valore).

        La forma e' quella di `get()`, `decision` compresa: sono la stessa
        riga letta con due chiavi diverse, e due forme diverse per la stessa
        riga sarebbero la fondamenta 3 rotta dentro un file solo.
        """
        sql, args = "SELECT * FROM reasoning_jobs WHERE kind=?", [kind]
        if wake_key is not None:
            # **Due domande nella stessa specie** (attori, Task 4.4): il giro
            # orario del proponente porta `giorno` nella sveglia, un
            # «Rifalla» porta `proposta`. Senza questo filtro l'ultimo
            # «Rifalla» nasconderebbe al giro la risposta che aspetta.
            path = "$." + wake_key
            if wake_value is None:
                sql += " AND json_extract(wake_json, ?) IS NOT NULL"
                args.append(path)
            else:
                sql += " AND json_extract(wake_json, ?) = ?"
                args += [path, wake_value]
        with self._lock:
            r = self._conn.execute(
                sql + " ORDER BY created_ts DESC, id DESC LIMIT 1", args).fetchone()
        if r is None:
            return None
        out = _row(r)
        out["decision"] = json.loads(r["decision_json"]) if r["decision_json"] else None
        # **Quando la risposta e' arrivata**, non quando la domanda e' partita.
        # Serve a chi raccoglie per sapere se ha gia' letto QUESTA risposta:
        # una raccolta fallita non scrive nessuna riconsiderazione, quindi
        # senza questo istante lo stesso turno storto verrebbe riletto e
        # riannotato a ogni giro (rilievo della review indipendente,
        # 11/09/2026).
        out["decided_ts"] = r["decided_ts"]
        return out

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if r is None:
            return None
        out = _row(r)
        out["decision"] = json.loads(r["decision_json"]) if r["decision_json"] else None
        return out

    def has_pending_chat(self, thread: ChatThread, now: float | None = None) -> bool:
        """True se QUESTO filo ha gia' un kind="chat" in volo (status
        'pending'/'claimed' non ancora scaduto, o 'ripiego'). Slice 4b Task 3
        -- guardia «una risposta alla volta» sul percorso async del piano.

        fetta «le chat divise», Task 2: il 409 e' del FILO, non della casa.
        Fino a qui era un COUNT unico su tutta la tabella (fetta E4 Task 5,
        "un bot solo": con un bot solo "in volo per questa conversazione" e
        "in volo" erano la stessa domanda). Con piu' fili quella scorciatoia
        blocca il filo sbagliato -- due persone, o due ingressi della stessa
        persona, possono avere ciascuno un turno in volo senza bloccarsi a
        vicenda. `thread` non ha un default apposta: un 409 sganciato dal
        filo di chi chiede sarebbe il vecchio difetto tornato di un livello
        piu' su.

        Task 5 fix (Task 3 review, MEDIUM; preservato): un job il cui
        deadline_ts e' gia' passato e' escluso anche se lo status e' ancora
        'pending'/'claimed' -- altrimenti un job scaduto e mai spazzato (lo
        sweep di server.py spento o non ancora girato) darebbe 409 per
        sempre, senza modo di liberarsi. `now` esplicito come ogni altro
        metodo di questa classe, time.time() solo quando il chiamante di
        produzione non lo passa.

        Task 14 (il ripiego): 'ripiego' conta come in volo, SENZA il filtro
        sulla scadenza -- che per lui sarebbe sempre passata, visto che ci si
        entra solo dopo. La chiamata al modello sulla catena puo' durare
        decine di secondi, e un secondo turno intanto metterebbe due risposte
        in volo sullo stesso filo. Il rischio simmetrico (un ripiego
        schiantato che tiene bloccato il filo per sempre) lo chiude
        `fail_stuck_downgrades`, non un filtro sul tempo qui.

        **Debito accettato, alla frontiera dell'aggiornamento.** Un job di
        chat accodato PRIMA di questa versione (senza `thread`, quindi con
        `subject_key`/`entry_point` NULL) non corrisponde a nessun `thread`
        reale, ed e' quindi invisibile a QUALSIASI chiamata di questo
        metodo -- per lui la guardia «una risposta alla volta» non vale, per
        al massimo una finestra di scadenza (i pochi minuti di
        `ponte.scadenza_min`): dopo, o e' stato risolto o `sweep_expired`/
        `fail_stuck_downgrades` lo hanno chiuso, e non ce n'e' piu' uno in
        volo da perdere di vista."""
        ts = time.time() if now is None else now
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM reasoning_jobs "
                f"WHERE kind='chat' AND {thread_condition()} AND "
                "(status='ripiego' OR "
                "(status IN ('pending','claimed') AND deadline_ts > ?)) LIMIT 1",
                (*thread_params(thread), ts)).fetchone()
        return row is not None

    def claimed(self, job_id: str) -> dict | None:
        """Il job SOLO se e' preso in carico (status='claimed'), di qualunque
        specie; altrimenti None.

        La chiama `/api/mcp` (`handlers_mcp._exchange_species`) per verificare
        `X-HIRIS-Lavoro`: un job che non e' in lavorazione non presta a
        nessuno il catalogo del suo mestiere (attori, Task 3.6)."""
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE job_id=? AND status='claimed'",
                (job_id,)).fetchone()
        return _row(r) if r is not None else None

    def claimed_chat(self, job_id: str) -> dict | None:
        """Il job SOLO se e' una chat presa in carico (`claimed`), altrimenti
        None -- qualunque altro stato o specie.

        La chiama `/api/mcp` (`handlers_mcp._exchange_chat_job`) per
        verificare `X-HIRIS-Chat`: un job che non e' una chat presa in carico
        non presta a nessuno il suo soggetto ne' il suo soffitto."""
        job = self.claimed(job_id)
        return job if job is not None and job.get("kind") == "chat" else None

    def count_exchanges_today(self, now: float | None = None) -> int:
        """Quanti turni del piano sono stati accodati oggi -- di OGNI specie.

        Fino al 22/08/2026 si chiamava `count_chat_today` e filtrava
        `kind='chat'`. Con la fetta «le promesse seguono la catena» il piano
        serve anche i risvegli, e un tetto che ne contasse meta' sarebbe una
        mezza verita': chi lo mette a 150 lo mette per non sfondare
        l'abbonamento, non per limitare una superficie sola.

        Conta ogni turno accodato oggi qualunque sia il suo stato adesso: un
        turno risolto o scaduto il budget della giornata l'ha comunque
        consumato.

        Takes an explicit `now`, like every other method on this class
        (enqueue/claim/submit/sweep_expired), defaulting to time.time() only
        when the caller (production code) doesn't pass one -- tests can pin
        an exact day boundary instead of depending on wall clock.

        Il confine e' mezzanotte della CASA, non del container: senza fuso
        il tetto si azzererebbe alle due di notte invece che a mezzanotte
        (`historian.home_space_zone` ricade su UTC quando il fuso non si sa,
        e non lo inventa mai)."""
        ts = time.time() if now is None else now
        # I confini del giorno sono quelli di `historian.day_boundaries`
        # (Tappa 3, Task 10, B-15): qui c'era una seconda copia del calcolo,
        # con la stessa cura per i giorni di 23 e 25 ore.
        timezone = self._read_timezone()
        day_start, day_end = day_boundaries(local_date(ts, timezone).isoformat(), timezone)
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(*) AS c FROM reasoning_jobs "
                "WHERE created_ts >= ? AND created_ts < ?",
                (day_start, day_end)).fetchone()
        return r["c"]

    def mark_delivered(self, job_id: str, now: float) -> None:
        """La risposta di questo lavoro e' arrivata a destinazione.

        Si segna alla PRIMA consegna e non si riscrive: se la pagina rifa' il
        poll dopo un ricaricamento, il momento che conta e' il primo, o la
        finestra si allungherebbe a ogni sguardo.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE reasoning_jobs SET delivered_ts=? "
                "WHERE job_id=? AND delivered_ts IS NULL", (now, job_id))
            self._conn.commit()

    def forget_delivered(self, *, before_ts: float) -> int:
        """Svuota la RISPOSTA dei lavori consegnati prima di `before_ts`.

        **Il reperto C-6.** La cancellazione della conversazione svuotava
        `chat.db`, ma la risposta del modello restava qui fino alla potatura a
        sette giorni: il proprietario premeva «cancella» e il testo restava sul
        disco per una settimana. La domanda era gia' azzerata alla consegna
        (`submit`); adesso lo e' anche la risposta.

        **Sparisce il contenuto, non la riga.** Il conteggio giornaliero del
        ponte e la potatura contano le righe: toglierle qui falserebbe il tetto
        che il proprietario ha impostato.

        Chi e' gia' vuoto non si riconta: il numero che torna finisce in una
        riga di registro, e contare due volte direbbe che il prodotto sta
        lavorando mentre gira a vuoto.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE reasoning_jobs SET decision_json='{}' "
                "WHERE delivered_ts IS NOT NULL AND delivered_ts < ? "
                "AND decision_json IS NOT NULL AND decision_json != '{}'",
                (before_ts,))
            self._conn.commit()
            return cur.rowcount

    def prune(self, before_ts: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM reasoning_jobs WHERE status IN ('decided','expired','failed') "
                "AND created_ts < ?",
                (before_ts,))
            self._conn.commit()
            return cur.rowcount
