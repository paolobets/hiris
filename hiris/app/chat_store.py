import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta

from .chat_thread import ChatThread
from .storage import connect, init_schema

logger = logging.getLogger(__name__)

# Identifies historical assistant turns that should NOT be replayed back to the
# model on the next chat call because they would degrade the response. Kept in
# this module (rather than imported from backends.openai_compat_runner) because
# chat_store has no other dependency on backends and we want a tight separation.
#
# Patterns covered:
# 1. Tool-call leaked as raw text by some Mistral/Hermes routings on OpenRouter
#    (identifier + non-ASCII separator like Hebrew/Vietnamese codepoints), e.g.
#    `get_ha_healthיׂ{"sections":["all"]}`. The runner now intercepts these on
#    the way out (v0.9.8) but turns saved BEFORE the upgrade are still in
#    chat_history.db and would otherwise be re-served to every new chat.
# 2. Synthetic error sentinels persisted by the chat handler when an upstream
#    call failed ("Errore temporaneo del servizio AI...", rate-limit message,
#    402-credit message). These add no information and dilute the prompt.
# 3. fetta E4, fix della review totale (I5): i sentinella del RUNNER DEL PONTE
#    (agent/runner.py). Sono CINQUE, e l'elenco va tenuto pari alla tupla
#    `_TOXIC_ASSISTANT_PREFIXES` qui sotto: `[errore runner rc=...]`,
#    `[runner non disponibile]`, `[vuoto]`, `[mock] risposta di prova` e
#    `[flusso incompleto]` -- quest'ultimo aggiunto dalla fetta "il ponte
#    riceve gli strumenti" (parita' B, Task 2) e rimasto fuori da questo
#    elenco fino alla review totale della stessa fetta (I-6): un commento che
#    ENUMERA e ne salta uno e' una dichiarazione falsa al presente, la classe
#    di difetto che questa fetta ha gia' pagato quattro volte.
#    Tutti e cinque sono la stessa specie della #2 --
#    testo sintetico che non e' una risposta -- ma arrivano dall'altro capo,
#    via `server._submit_chat_reply`, e non erano in nessun insieme qui: la
#    review ha trovato due `[errore runner rc=3221226505]` gia' dentro
#    chat_history.db, che ogni turno successivo rileggeva e rimandava al
#    modello. Corretto QUI e non nel ramo di `_submit_chat_reply` per due
#    motivi: (a) `_submit_chat_reply` gia' delega a `_is_toxic_assistant`,
#    quindi un solo punto copre scrittura e rilettura invece di due filtri da
#    tenere allineati; (b) solo qui la correzione vale anche per le righe GIA'
#    scritte su disco -- `_purge_toxic_turns` gira in lettura
#    (`load_context`), quindi le installazioni gia' avvelenate si ripuliscono
#    da sole al primo turno, senza migrazione. Prefissi e non uguaglianze
#    esatte perche' `[errore runner rc=...]` porta in coda un dettaglio
#    variabile (fino a 300 caratteri di stdout del CLI).
# I TESTI CHE NON SONO RISPOSTE, in un posto solo.
#
# Stanno QUI e non in `agent/runner.py`, che pure li produce, per una ragione
# di dipendenze: questo modulo e' una foglia (importa solo `.storage`), quindi
# tutti possono importarlo e nessuno rischia un ciclo. Il contrario non e'
# vero. Ed e' anche il modulo che sull'argomento ha gia' ragionato per esteso,
# qui sopra.
#
# Le sentinelle erano cinque stringhe RICOPIATE a mano, compresa quella che nel
# runner aveva gia' una costante. Il punto 3 qui sopra racconta che l'elenco e'
# gia' andato fuori sincrono una volta (rilievo I-6) e chiama quell'evento «la
# classe di difetto che questa fetta ha gia' pagato quattro volte»: la
# struttura che l'aveva prodotto era intatta, e una sesta sentinella non
# avrebbe fatto fallire nessun test. Adesso non c'e' un secondo elenco.
#
# Prefissi e non uguaglianze esatte: `[errore runner rc=...]` porta in coda un
# dettaglio variabile, `[flusso incompleto]` una frase di spiegazione.
RUNNER_ERROR_PREFIX = "[errore runner rc="
MISSING_RUNNER_SENTINEL = "[runner non disponibile]"
EMPTY_SENTINEL = "[vuoto]"
MOCK_SENTINEL = "[mock] risposta di prova"
INCOMPLETE_STREAM_SENTINEL = "[flusso incompleto]"
BRIDGE_SENTINELS = (
    RUNNER_ERROR_PREFIX,
    MISSING_RUNNER_SENTINEL,
    EMPTY_SENTINEL,
    MOCK_SENTINEL,
    INCOMPLETE_STREAM_SENTINEL,
)

# Un nome di strumento trapelato nel testo (un identificatore seguito da un
# carattere non ASCII: la firma del guasto misurato). Una regola sola, un solo
# ancoraggio.
#
# Erano DUE regex identiche tranne che per uno spazio tollerato in testa --
# quella del runner (`backends/openai_compat_runner._TOOL_LEAK_RE`) lo
# tollerava, questa no. E la differenza contava proprio qui:
# `_purge_toxic_turns` gira in lettura per ripulire le righe GIA' su disco,
# quindi una riga avvelenata con uno spazio iniziale -- scritta da una versione
# precedente del filtro, o arrivata dal ponte -- non veniva mai riconosciuta e
# tornava al modello a ogni turno, per sempre.
#
# Vince la piu' TOLLERANTE: qui si riconosce, non si valida, e un
# riconoscitore troppo stretto lascia passare il guasto che deve cogliere.
LEAKED_TOOL_NAME_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]{2,})[^\x00-\x7F\s]")
_TOXIC_ASSISTANT_RE = LEAKED_TOOL_NAME_RE
_TOXIC_ASSISTANT_EXACT = frozenset({
    "Errore temporaneo del servizio AI. Riprova tra poco.",
    "Rate limit — riprova tra poco.",
    "",
})
_TOXIC_ASSISTANT_PREFIXES = (
    "Crediti OpenRouter insufficienti",
    "Il modello selezionato non gestisce correttamente i tool",
    # Le sentinelle del ponte: dall'elenco unico qui sopra, non ricopiate.
    *BRIDGE_SENTINELS,
)


def _is_toxic_assistant(content: str) -> bool:
    """Return True if this assistant content should be filtered from history."""
    if content in _TOXIC_ASSISTANT_EXACT:
        return True
    if _TOXIC_ASSISTANT_RE.match(content):
        return True
    return any(content.startswith(p) for p in _TOXIC_ASSISTANT_PREFIXES)


def _purge_toxic_turns(messages: list[dict]) -> list[dict]:
    """Drop assistant turns matching the toxic patterns AND their preceding user
    turn (so we don't leave dangling user messages with no answer in context).

    Operates in-order, single pass. Empty assistant content also counts as toxic.
    """
    out: list[dict] = []
    for msg in messages:
        if msg.get("role") == "assistant" and _is_toxic_assistant(msg.get("content", "")):
            if out and out[-1].get("role") == "user":
                out.pop()
            continue
        out.append(msg)
    return out

# fetta "Modelli" (2.0), Task 12: la costante di modulo `HISTORY_RETENTION_DAYS`
# e' uscita -- viveva qui, letta all'IMPORT da due lettori (questo modulo
# stesso, in `ChatStore.load_context`, e `server.py::_run_retention`), e
# scriverla a runtime (com'era pensato dal vecchio commento "overridable at
# startup via configure()", che non esisteva davvero: nessun `configure()` e'
# mai stato definito in questo file) non l'avrebbe mai fatta arrivare a un
# lettore che la importa per valore all'avvio. La sorgente di verita' e' ora
# `ChatSettings.retention_days` (`chat_settings.py`): entrambi i
# lettori la ricevono come PARAMETRO a ogni chiamata, non piu' come un globale
# fissato una volta. `load_context` sotto porta `days` con un default (90,
# lo stesso valore che questa costante aveva) solo per i chiamanti di questo
# repo che non hanno un'opinione sulla conservazione (i test che non la
# esercitano); i due lettori di produzione lo passano sempre esplicitamente.
SESSION_GAP_HOURS = 2
PAST_SESSIONS_LIMIT = 3
SUMMARY_MAX_CHARS = 200
_DIGEST_TURNS = 3       # user+assistant pairs to include in the session digest
_DIGEST_MSG_LEN = 120   # max chars per message in the digest
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_stores: dict[str, "ChatStore"] = {}
_lock = threading.Lock()

# fetta E4 Task 5 ("un bot solo"): niente piu' `chatbot_id` in nessuna delle
# due tabelle -- era una chiave di partizione su un insieme di cardinalita'
# uno, ereditata da un mondo con piu' bot che l'entita' Chatbot rappresentava
# (uscita per intero col Task 4). Gli indici tornano dentro _SCHEMA (prima
# vivevano fuori, creati a mano da ChatStore.__init__ DOPO init_schema: quel
# giro esisteva solo perche' il vecchio idx_msg_chatbot/idx_sess_chatbot
# referenziava una colonna che su un DB v1 non esisteva ancora al momento
# dell'executescript -- senza chatbot_id negli indici quel problema non c'e'
# piu', session_id/last_msg_at esistono in ogni versione dello schema).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    last_msg_at TEXT NOT NULL,
    summary     TEXT,
    -- Il FILO (fetta «le chat divise», Task 3): di CHI e' la sessione e da
    -- quale ingresso (spec §3). NULL = orfana: una sessione scritta prima di
    -- questa versione, che nessuno vede finche' il proprietario non la adotta.
    subject_key TEXT,
    entry_point TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_session  ON chat_messages(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sess_last_msg ON chat_sessions(last_msg_at);
"""

# L'indice del filo NON sta in `_SCHEMA`: `init_schema` esegue lo script PRIMA
# delle migrazioni, e su un archivio v3 (senza le due colonne) un `CREATE INDEX`
# su `subject_key` farebbe fallire l'apertura invece di migrare. Si crea in
# `ChatStore.__init__`, subito dopo `init_schema()`: li' le colonne esistono
# sempre, che l'archivio sia appena nato o appena migrato. Stesso giro di
# `reasoning/queue.py::_IDX_THREAD_SQL`.
_IDX_THREAD_SQL = ("CREATE INDEX IF NOT EXISTS idx_sess_thread "
                   "ON chat_sessions(subject_key, entry_point, last_msg_at)")


def _reset(conn: sqlite3.Connection) -> None:
    """v1/v2 -> v3 ("un bot solo", fetta E4 Task 5): NESSUNA conversione.

    Decisione esplicita dell'utente (vedi il commit): *"anche se perdiamo i
    dati ora non c'e' problema, partiamo puliti, non serve migrare nulla"*.
    Un DB 1.x aveva `chatbot_id NOT NULL` in entrambe le tabelle -- una
    chiave partizionata su un insieme di cardinalita' uno, ora che esiste un
    solo bot (`chat_settings.py`, senza id). Non si rinomina/droppa la
    colonna con un ALTER TABLE mirato come faceva `_migrate_v2` (uscita con
    questo task, che rinominava `agent_id` in `chatbot_id`): si droppano le
    due tabelle e si ricreano da `_SCHEMA`, che quella colonna non ce l'ha
    piu'.

    Il salto NON e' silenzioso: la cronologia che butta via e' esattamente
    il difetto che questo prodotto ripete -- un azzeramento muto sarebbe
    indistinguibile da un guasto. Logga quante righe scarta, cosi' chi
    aggiorna da 1.x lo legge nei log invece di scoprirlo dalla chat vuota
    (pinnato da tests/test_chat_store_azzeramento.py, stessa disciplina di
    tests/test_startup_legacy_db_silence.py).

    Idempotente se richiamata due volte in sequenza sullo stesso DB (caso
    limite: `init_schema` la richiama per i target 2 E 3 quando parte da un
    DB pre-versioning, `user_version` mai stampato prima d'ora) -- la
    seconda passata trova le tabelle gia' vuote/nuove e logga zero righe
    scartate."""
    n_msg = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
    n_sess = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
    conn.execute("DROP TABLE IF EXISTS chat_messages")
    conn.execute("DROP TABLE IF EXISTS chat_sessions")
    conn.executescript(_SCHEMA)
    logger.info(
        "cronologia 1.x azzerata, non convertita -- si parte puliti: %d messaggi e "
        "%d sessioni di conversazioni precedenti sono stati scartati. Lo schema "
        "precedente partizionava la cronologia per chatbot_id (NOT NULL in "
        "chat_messages/chat_sessions), pensato per piu' bot; con un bot solo "
        "quella colonna non ha piu' senso ed e' uscita insieme alle righe che "
        "portava. Nessuna migrazione, per decisione esplicita dell'utente.",
        n_msg, n_sess,
    )


def _migration_4(conn: sqlite3.Connection) -> None:
    """v3 -> v4 (fetta «le chat divise», Task 3): il filo della sessione.

    NON un `_reset`: decisione 5 del proprietario (spec §0, §3) -- la
    cronologia di oggi resta, con `subject_key`/`entry_point` NULL, cioe'
    orfana: invisibile a tutti finche' `adopt_orphans` non la da' al
    proprietario. `ALTER TABLE` solo se la colonna manca: un DB che arriva
    qui passando da `_reset` (pre-v3) ha gia' le colonne da `_SCHEMA`."""
    colonne = {r[1] for r in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
    if "subject_key" not in colonne:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN subject_key TEXT")
    if "entry_point" not in colonne:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN entry_point TEXT")


class ChatStore:
    def __init__(self, db_path: str):
        self._conn = connect(db_path)
        self._mu = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=4,
                    migrations={2: _reset, 3: _reset, 4: _migration_4})
        self._conn.execute(_IDX_THREAD_SQL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers (called with self._mu already held)
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(UTC).strftime(_TS_FMT)

    def _fresh_session_id(self, thread: ChatThread) -> str | None:
        """Return the thread's open session_id only if within the gap window — no side effects."""
        row = self._conn.execute(
            "SELECT session_id, last_msg_at FROM chat_sessions "
            "WHERE summary IS NULL AND subject_key = ? AND entry_point = ? "
            "ORDER BY last_msg_at DESC LIMIT 1",
            (thread.subject_key, thread.entry_point),
        ).fetchone()
        if not row:
            return None
        try:
            last = datetime.strptime(row["last_msg_at"], _TS_FMT).replace(tzinfo=UTC)
        except ValueError:
            return row["session_id"]
        if (datetime.now(UTC) - last).total_seconds() < SESSION_GAP_HOURS * 3600:
            return row["session_id"]
        return None

    def _active_session(self, thread: ChatThread) -> str | None:
        """Return the thread's fresh session_id, closing every OTHER open
        session of the thread as side effect (write path only).

        Una regola sola: un filo ha al piu' UNA sessione aperta, la piu'
        fresca. Prima si chiudeva solo l'ultima ferma; ma l'adozione
        (`adopt_orphans`) puo' portare in un filo una seconda sessione aperta
        accanto a quella che il proprietario ha gia' cominciato, e quella non
        si sarebbe chiusa mai -- ne' riassunta, ne' mostrata fra le sessioni
        precedenti. La chiusura tocca SOLO questo filo: il silenzio di Paolo
        non chiude la conversazione di Marta."""
        sid = self._fresh_session_id(thread)
        rows = self._conn.execute(
            "SELECT session_id FROM chat_sessions WHERE summary IS NULL "
            "AND subject_key = ? AND entry_point = ?",
            (thread.subject_key, thread.entry_point),
        ).fetchall()
        for row in rows:
            if row["session_id"] != sid:
                self._close_session(row["session_id"])
        return sid

    def _close_session(self, session_id: str) -> None:
        rows = self._conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, _DIGEST_TURNS * 2),
        ).fetchall()
        if rows:
            # Rows are newest-first; reverse to chronological order, then build digest
            pairs: list[str] = []
            turns: list[tuple[str, str]] = []
            cur: dict[str, str] = {}
            for r in reversed(rows):
                role, content = r["role"], r["content"]
                if role == "user":
                    cur = {"u": content}
                elif role == "assistant" and cur:
                    cur["a"] = content
                    turns.append((cur["u"], cur["a"]))
                    cur = {}
            for u, a in turns[-_DIGEST_TURNS:]:
                u_trunc = u[:_DIGEST_MSG_LEN] + "…" if len(u) > _DIGEST_MSG_LEN else u
                a_trunc = a[:_DIGEST_MSG_LEN] + "…" if len(a) > _DIGEST_MSG_LEN else a
                pairs.append(f"U: {u_trunc}\nA: {a_trunc}")
            summary = "\n---\n".join(pairs) if pairs else rows[0]["content"][:SUMMARY_MAX_CHARS]
        else:
            summary = "(nessuna risposta)"
        self._conn.execute(
            "UPDATE chat_sessions SET summary = ? WHERE session_id = ?",
            (summary, session_id),
        )

    def _new_session(self, thread: ChatThread) -> str:
        session_id = str(uuid.uuid4())
        ts = self._now()
        self._conn.execute(
            "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, "
            "subject_key, entry_point) VALUES(?,?,?,?,?)",
            (session_id, ts, ts, thread.subject_key, thread.entry_point),
        )
        return session_id

    def _get_or_create_session(self, thread: ChatThread) -> str:
        sid = self._active_session(thread)
        if sid:
            return sid
        return self._new_session(thread)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, messages: list[dict], thread: ChatThread) -> None:
        with self._mu:
            sid = self._get_or_create_session(thread)
            ts = self._now()
            for m in messages:
                self._conn.execute(
                    "INSERT INTO chat_messages(session_id, role, content, timestamp) "
                    "VALUES(?,?,?,?)",
                    (sid, m["role"], m["content"], ts),
                )
            self._conn.execute(
                "UPDATE chat_sessions SET last_msg_at = ? WHERE session_id = ?", (ts, sid)
            )
            self._conn.commit()

    def load_context(
        self, thread: ChatThread, max_turns: int = 30, *, days: int = 90,
        include_timestamp: bool = False,
    ) -> list[dict]:
        """Return last max_turns pairs from the thread's active (non-stale) session.

        `days` is the second job of `ChatSettings.retention_days`
        (Task 12): it does NOT free disk space here, it makes HIRIS forget
        sooner -- messages older than `days` days, even inside the still-open
        active session, are not read back into the model's context. `0`
        disables this (never filters), and the nightly pruning agrees on what
        `0` means -- `delete_old_messages` below writes the same rule the other
        way round, `if retention_days <= 0: return 0`.

        `include_timestamp` (collaudo 3.22, C4 -- "la chat inventa l'ora dei
        messaggi"): di default `False`, e il dizionario resta `{role, content}`
        -- il formato che l'API del modello si aspetta, e che
        `test_load_strips_timestamps_from_output` pinna. Il SOLO chiamante che
        passa `True` e' `handlers_chat_history.handle_get_chat_history`: la
        pagina disegnava ogni bolla ripristinata con `new Date()` **al momento
        del disegno**, cioe' l'ora del ricaricamento -- non quella in cui il
        messaggio era stato scritto. La cronologia porta gia' l'ora vera in
        colonna (`timestamp`, scritta da `append()` a ogni turno): mancava
        solo restituirla a chi la chiede, non inventare una seconda fonte."""
        with self._mu:
            sid = self._fresh_session_id(thread)
            if not sid:
                return []
            if days > 0:
                cutoff = (
                    datetime.now(UTC) - timedelta(days=days)
                ).strftime(_TS_FMT)
                rows = self._conn.execute(
                    "SELECT role, content, timestamp FROM chat_messages "
                    "WHERE session_id = ? AND timestamp >= ? ORDER BY id",
                    (sid, cutoff),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT role, content, timestamp FROM chat_messages "
                    "WHERE session_id = ? ORDER BY id",
                    (sid,),
                ).fetchall()
            messages = [
                {"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]}
                for r in rows
            ]
            # Strip toxic assistant turns (and their dangling user pair) before
            # the model ever sees them — protects against the leaked-tool-call
            # poisoning observed pre-v0.9.8 and against repeated synthetic
            # error sentinels.
            messages = _purge_toxic_turns(messages)
            if len(messages) > max_turns * 2:
                messages = messages[-(max_turns * 2):]
            if not include_timestamp:
                messages = [{"role": m["role"], "content": m["content"]} for m in messages]
            return messages

    def get_past_summaries(
        self, thread: ChatThread, n: int = PAST_SESSIONS_LIMIT
    ) -> list[dict]:
        """Return the thread's closed sessions with summaries, most recent first."""
        with self._mu:
            rows = self._conn.execute(
                "SELECT session_id, started_at, last_msg_at, summary FROM chat_sessions "
                "WHERE summary IS NOT NULL AND subject_key = ? AND entry_point = ? "
                "ORDER BY last_msg_at DESC LIMIT ?",
                (thread.subject_key, thread.entry_point, n),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_user_turns(self, thread: ChatThread) -> int:
        """Count user messages in the thread's active (non-stale) session."""
        with self._mu:
            sid = self._fresh_session_id(thread)
            if not sid:
                return 0
            cnt = self._conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role = 'user'",
                (sid,),
            ).fetchone()
            return cnt[0] if cnt else 0

    def clear(self, thread: ChatThread) -> None:
        """Cancella SOLO il filo dato: «cancella la cronologia» di Marta non
        tocca quella di Paolo, ne' le orfane (che aspettano il proprietario)."""
        key = (thread.subject_key, thread.entry_point)
        with self._mu:
            self._conn.execute(
                "DELETE FROM chat_messages WHERE session_id IN "
                "(SELECT session_id FROM chat_sessions "
                "WHERE subject_key = ? AND entry_point = ?)", key)
            self._conn.execute(
                "DELETE FROM chat_sessions WHERE subject_key = ? AND entry_point = ?", key)
            self._conn.commit()

    def has_orphans(self) -> bool:
        """C'e' ancora cronologia di prima delle chat divise, di nessuno?"""
        with self._mu:
            return self._conn.execute(
                "SELECT 1 FROM chat_sessions WHERE subject_key IS NULL LIMIT 1"
            ).fetchone() is not None

    def adopt_orphans(self, thread: ChatThread) -> int:
        """Le sessioni orfane diventano del filo dato; ritorna quante.

        CHI adotta non si decide qui (lo decide `chat_thread.adopt_if_owner`):
        l'archivio non sa chi sia il proprietario. Una volta sola per
        costruzione -- dopo, nessuna riga ha piu' `subject_key IS NULL`."""
        with self._mu:
            cur = self._conn.execute(
                "UPDATE chat_sessions SET subject_key = ?, entry_point = ? "
                "WHERE subject_key IS NULL",
                (thread.subject_key, thread.entry_point),
            )
            self._conn.commit()
            return cur.rowcount

    def delete_old_messages(self, retention_days: int) -> int:
        """Hard-delete chat messages older than retention_days. Returns row count deleted."""
        if retention_days <= 0:
            return 0
        cutoff = (
            datetime.now(UTC) - timedelta(days=retention_days)
        ).strftime(_TS_FMT)
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM chat_messages WHERE timestamp < ?", (cutoff,)
            )
            self._conn.execute(
                "DELETE FROM chat_sessions WHERE session_id NOT IN "
                "(SELECT DISTINCT session_id FROM chat_messages)"
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._mu:
            self._conn.close()


# ---------------------------------------------------------------------------
# Module-level lazy init keyed by data_dir (supports multiple test fixtures)
# ---------------------------------------------------------------------------

def _get_store(data_dir: str) -> ChatStore:
    if data_dir not in _stores:
        with _lock:
            if data_dir not in _stores:
                db_path = os.path.join(data_dir, "chat_history.db")
                _stores[data_dir] = ChatStore(db_path)
    return _stores[data_dir]


# ---------------------------------------------------------------------------
# Funzioni di modulo. Fetta «le chat divise»: una cronologia PER FILO (un
# soggetto da un ingresso, `chat_thread.py`). `thread` e' keyword obbligatorio
# e senza default, apposta: un default sarebbe il filo unico che rientra dalla
# porta di servizio, e un chiamante dimenticato scriverebbe nella chat di
# qualcun altro invece di fallire subito.
# ---------------------------------------------------------------------------

def load_history(
    data_dir: str, *, thread: ChatThread, days: int = 90,
    include_timestamp: bool = False,
) -> list[dict]:
    """Return [{role, content}] for the thread's active session (Claude API format).

    `days` threads through to `ChatStore.load_context` -- see its docstring
    for why this is NOT a housekeeping knob. Production callers pass
    `chat_settings.giorni_conservazione` explicitly; the default here only
    covers this repo's callers that don't have an opinion on retention.

    `include_timestamp` threads through too -- see `ChatStore.load_context`.
    Default `False`: the model-facing callers (`api/handlers_chat.py`) must
    keep getting pure `{role, content}`, unchanged."""
    return _get_store(data_dir).load_context(
        thread, days=days, include_timestamp=include_timestamp)


def append_messages(messages: list[dict], data_dir: str, *, thread: ChatThread) -> None:
    """Append [{role, content}] to the thread's active session."""
    _get_store(data_dir).append(messages, thread)


def append_assistant_line(content: str, data_dir: str, *,
                          thread: ChatThread | None,
                          quoted: str | None = None) -> bool:
    """Una riga di HIRIS nel filo dato, senza un turno utente davanti; `True`
    se e' stata scritta.

    E' la strada dell'esito di una promessa (spec 2026-09-26 §2.4): chi ha
    chiesto la ritrova nella sua conversazione attiva. Due rifiuti, entrambi
    silenziosi per chi scrive e dichiarati dal `False`:
    - **nessun filo, nessuna scrittura** (vincolo 3.2): una promessa orfana
      non ha un padrone, e un filo inventato sarebbe la chat di qualcun altro;
    - **un testo velenoso non entra** (`_is_toxic_assistant`, lo stesso filtro
      delle risposte di chat): una sentinella d'errore tornerebbe al modello
      a ogni turno. `quoted` e' il testo del MODELLO citato dentro `content`
      (l'esito di un `chiedi`, dopo la riga che nomina la promessa): la riga
      di HIRIS davanti lo nasconderebbe al filtro, quindi si filtra anche lui.
    """
    if thread is None:
        return False
    if not isinstance(content, str) or _is_toxic_assistant(content):
        return False
    if quoted is not None and (not isinstance(quoted, str)
                               or _is_toxic_assistant(quoted)):
        return False
    _get_store(data_dir).append([{"role": "assistant", "content": content}], thread)
    return True


#: Il titolo di una conversazione che non ha una frase dell'utente (ruling
#: 3.9): una conversazione aperta da un esito di promessa comincia con un
#: messaggio di HIRIS, e inventare un turno utente per darle un titolo
#: sarebbe scrivere nella cronologia una frase che nessuno ha detto.
OUTCOME_ONLY_TITLE = "Esito di una promessa"


def conversation_title(messages: list[dict]) -> str:
    """Il titolo di una conversazione: la prima frase dell'utente, o
    `OUTCOME_ONLY_TITLE` se non ce n'e'. Il tetto e il marcatore del taglio
    li decide la pagina delle conversazioni (Task 6 della stessa fetta)."""
    for message in messages:
        if message.get("role") == "user":
            text = str(message.get("content") or "").strip()
            if text:
                return text
    return OUTCOME_ONLY_TITLE


def clear_history(data_dir: str, *, thread: ChatThread) -> None:
    """Delete the thread's history and sessions -- only that thread."""
    _get_store(data_dir).clear(thread)


def get_past_summaries(
    data_dir: str, *, thread: ChatThread, n: int = PAST_SESSIONS_LIMIT
) -> list[dict]:
    """Return up to n of the thread's closed session summaries, most recent first."""
    return _get_store(data_dir).get_past_summaries(thread, n)


def count_user_turns(data_dir: str, *, thread: ChatThread) -> int:
    """Count user turns in the thread's active session (max_chat_turns enforcement)."""
    return _get_store(data_dir).count_user_turns(thread)


def has_orphans(data_dir: str) -> bool:
    """C'e' cronologia di prima della fetta ancora senza filo?"""
    return _get_store(data_dir).has_orphans()


def adopt_orphans(data_dir: str, *, thread: ChatThread) -> int:
    """Le sessioni orfane passano al filo dato; ritorna quante."""
    return _get_store(data_dir).adopt_orphans(thread)


def delete_old_messages(data_dir: str, retention_days: int) -> int:
    """Hard-delete chat messages older than retention_days days."""
    return _get_store(data_dir).delete_old_messages(retention_days)


def close_all_stores() -> None:
    """Close all SQLite connections (call on app shutdown)."""
    with _lock:
        for store in _stores.values():
            store.close()
        _stores.clear()
