from __future__ import annotations
import json, secrets, threading, time
from datetime import datetime
from typing import Optional
from ..storage import connect, init_schema

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
    decision_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reasoning_status ON reasoning_jobs(status, created_ts);
"""

def _row(r) -> dict:
    return {"job_id": r["job_id"], "kind": r["kind"], "status": r["status"],
            "nonce": r["nonce"], "wake": json.loads(r["wake_json"]),
            "context": json.loads(r["context_json"]), "deadline_ts": r["deadline_ts"]}

class ReasoningQueue:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def enqueue(self, kind: str, wake: dict, context: dict, deadline_ts: float,
                *, job_id: Optional[str] = None, now: float) -> str:
        jid = job_id or secrets.token_urlsafe(12)
        with self._lock:
            self._conn.execute(
                "INSERT INTO reasoning_jobs(job_id,kind,wake_json,context_json,status,deadline_ts,created_ts) "
                "VALUES(?,?,?,?, 'pending', ?, ?)",
                (jid, kind, json.dumps(wake), json.dumps(context), deadline_ts, now))
            self._conn.commit()
        return jid

    def claim(self, now: float) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE status='pending' AND deadline_ts > ? "
                "ORDER BY created_ts ASC, id ASC LIMIT 1", (now,)).fetchone()
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
    # detto" (`casa/nucleo.py::componi`) -- e senza questo azzeramento resterebbe
    # nel file `reasoning.db` fino alla potatura a 7 giorni (`prune()`,
    # chiamata da `server.py` con `before_ts = now - 7*86400`), ben oltre il
    # tempo in cui serve a qualcuno. Verificato (non assunto) che nessun
    # lettore lo riapre dopo la risoluzione: `handle_chat_reply_poll` legge
    # solo `decision` dal job (`handlers_chat.py`, il ramo di poll), MAI
    # `context`; `handle_reasoning_submit` chiama `q.get(job_id)` anche lui
    # DOPO il proprio submit, ma legge solo `job.get("kind")`
    # (`handlers_reasoning.py`); `has_pending_chat()` e' un COUNT indicizzato
    # su `status`/`deadline_ts` che non riapre mai `context_json` (il metodo
    # e' piu' sotto in questo stesso file: si cerca per NOME, perche' un
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
            r = self._conn.execute("SELECT * FROM reasoning_jobs WHERE job_id=?", (job_id,)).fetchone()
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
        # `kind`, l'unico campo che `_reasoning_sweep`, server.py, legge dal
        # valore di ritorno per il suo log). Non e' una svista -- e' il valore
        # di ritorno di QUESTA chiamata, non una rilettura del DB: il
        # `context_json` sulla riga persistita e' comunque '{}' da subito
        # dopo, come dimostra `get(job_id)` chiamato di nuovo.
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE status IN ('pending','claimed') AND deadline_ts <= ?",
                (now,)).fetchall()
            for r in rows:
                self._conn.execute(
                    "UPDATE reasoning_jobs SET status='expired', context_json='{}' WHERE job_id=?",
                    (r["job_id"],))
            self._conn.commit()
        return [_row(r) for r in rows]

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM reasoning_jobs WHERE job_id=?", (job_id,)).fetchone()
        if r is None:
            return None
        out = _row(r)
        out["decision"] = json.loads(r["decision_json"]) if r["decision_json"] else None
        return out

    def has_pending_chat(self, now: Optional[float] = None) -> bool:
        """True if ANY kind="chat" job is still in flight (status 'pending'
        or 'claimed') AND its deadline hasn't passed yet. Slice 4b Task 3 --
        "one answer in flight per conversation" guard on the async
        subscription path.

        fetta E4 Task 5 ("un bot solo"): this used to take a `chatbot_id`
        and scan each in-flight row's context_json to match it (a
        conversation was a chatbot's active session, keyed by chatbot_id).
        With one bot there's exactly one conversation, so "in flight for
        this id" and "in flight" collapsed into the same question -- the
        per-row context parse is gone, this is now a single indexed COUNT.

        Task 5 fix (Task 3 review, MEDIUM; preserved through this
        simplification): a job whose deadline_ts is already in the past is
        excluded even if its status is still 'pending'/'claimed' -- e.g.
        because the ponte-push sweep (server.py's _reasoning_sweep, gated on
        BRIDGE_ENABLED) never ran or is off. Without this, an
        expired-but-unswept job would 409 the conversation forever with no
        way to clear it. Takes an explicit `now`, like every other method on
        this class (enqueue/claim/submit/sweep_expired/count_chat_today),
        defaulting to time.time() only when the caller (production code)
        doesn't pass one."""
        ts = time.time() if now is None else now
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM reasoning_jobs "
                "WHERE kind='chat' AND status IN ('pending','claimed') "
                "AND deadline_ts > ? LIMIT 1", (ts,)).fetchone()
        return row is not None

    def count_chat_today(self, now: Optional[float] = None) -> int:
        """Count of kind="chat" jobs enqueued (created_ts) on the same local
        calendar day as `now`. Slice 4b Task 3's separate daily chat cap --
        counts every chat turn enqueued today regardless of its current
        status (resolved/expired turns still consumed the day's budget).

        Takes an explicit `now`, like every other method on this class
        (enqueue/claim/submit/sweep_expired), defaulting to time.time() only
        when the caller (production code) doesn't pass one -- tests can pin
        an exact day boundary instead of depending on wall clock."""
        ts = time.time() if now is None else now
        dt = datetime.fromtimestamp(ts)
        day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        day_end = day_start + 86400
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(*) AS c FROM reasoning_jobs "
                "WHERE kind='chat' AND created_ts >= ? AND created_ts < ?",
                (day_start, day_end)).fetchone()
        return r["c"]

    def prune(self, before_ts: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM reasoning_jobs WHERE status IN ('decided','expired','failed') AND created_ts < ?",
                (before_ts,))
            self._conn.commit()
            return cur.rowcount
