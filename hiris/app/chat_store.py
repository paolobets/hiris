import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta

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
PREFISSO_ERRORE_RUNNER = "[errore runner rc="
SENTINELLA_RUNNER_ASSENTE = "[runner non disponibile]"
SENTINELLA_VUOTO = "[vuoto]"
SENTINELLA_MOCK = "[mock] risposta di prova"
SENTINELLA_FLUSSO_INCOMPLETO = "[flusso incompleto]"
SENTINELLE_DEL_PONTE = (
    PREFISSO_ERRORE_RUNNER,
    SENTINELLA_RUNNER_ASSENTE,
    SENTINELLA_VUOTO,
    SENTINELLA_MOCK,
    SENTINELLA_FLUSSO_INCOMPLETO,
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
RE_NOME_STRUMENTO_TRAPELATO = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]{2,})[^\x00-\x7F\s]")
_TOXIC_ASSISTANT_RE = RE_NOME_STRUMENTO_TRAPELATO
_TOXIC_ASSISTANT_EXACT = frozenset({
    "Errore temporaneo del servizio AI. Riprova tra poco.",
    "Rate limit — riprova tra poco.",
    "",
})
_TOXIC_ASSISTANT_PREFIXES = (
    "Crediti OpenRouter insufficienti",
    "Il modello selezionato non gestisce correttamente i tool",
    # Le sentinelle del ponte: dall'elenco unico qui sopra, non ricopiate.
    *SENTINELLE_DEL_PONTE,
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
# `ImpostazioniChat.giorni_conservazione` (`impostazioni_chat.py`): entrambi i
# lettori la ricevono come PARAMETRO a ogni chiamata, non piu' come un globale
# fissato una volta. `load_context` sotto porta `giorni` con un default (90,
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
    summary     TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_session  ON chat_messages(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sess_last_msg ON chat_sessions(last_msg_at);
"""


def _azzera(conn: sqlite3.Connection) -> None:
    """v1/v2 -> v3 ("un bot solo", fetta E4 Task 5): NESSUNA conversione.

    Decisione esplicita dell'utente (vedi il commit): *"anche se perdiamo i
    dati ora non c'e' problema, partiamo puliti, non serve migrare nulla"*.
    Un DB 1.x aveva `chatbot_id NOT NULL` in entrambe le tabelle -- una
    chiave partizionata su un insieme di cardinalita' uno, ora che esiste un
    solo bot (`impostazioni_chat.py`, senza id). Non si rinomina/droppa la
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


class ChatStore:
    def __init__(self, db_path: str):
        self._conn = connect(db_path)
        self._mu = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=3, migrations={2: _azzera, 3: _azzera})

    # ------------------------------------------------------------------
    # Internal helpers (called with self._mu already held)
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(UTC).strftime(_TS_FMT)

    def _fresh_session_id(self) -> str | None:
        """Return the open session_id only if within the gap window — no side effects."""
        row = self._conn.execute(
            "SELECT session_id, last_msg_at FROM chat_sessions "
            "WHERE summary IS NULL ORDER BY last_msg_at DESC LIMIT 1"
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

    def _active_session(self) -> str | None:
        """Return fresh session_id, closing stale ones as side effect (write path only)."""
        sid = self._fresh_session_id()
        if sid:
            return sid
        row = self._conn.execute(
            "SELECT session_id FROM chat_sessions WHERE summary IS NULL "
            "ORDER BY last_msg_at DESC LIMIT 1"
        ).fetchone()
        if row:
            self._close_session(row["session_id"])
        return None

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

    def _new_session(self) -> str:
        session_id = str(uuid.uuid4())
        ts = self._now()
        self._conn.execute(
            "INSERT INTO chat_sessions(session_id, started_at, last_msg_at) VALUES(?,?,?)",
            (session_id, ts, ts),
        )
        return session_id

    def _get_or_create_session(self) -> str:
        sid = self._active_session()
        if sid:
            return sid
        return self._new_session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, messages: list[dict]) -> None:
        with self._mu:
            sid = self._get_or_create_session()
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

    def load_context(self, max_turns: int = 30, *, giorni: int = 90) -> list[dict]:
        """Return last max_turns pairs from the active (non-stale) session.

        `giorni` is the second job of `ImpostazioniChat.giorni_conservazione`
        (Task 12): it does NOT free disk space here, it makes HIRIS forget
        sooner -- messages older than `giorni` days, even inside the still-open
        active session, are not read back into the model's context. `0`
        disables this (never filters), matching the nightly pruning's own `if
        giorni > 0` in `delete_old_messages` below -- the two readers agree on
        what `0` means."""
        with self._mu:
            sid = self._fresh_session_id()
            if not sid:
                return []
            if giorni > 0:
                cutoff = (
                    datetime.now(UTC) - timedelta(days=giorni)
                ).strftime(_TS_FMT)
                rows = self._conn.execute(
                    "SELECT role, content FROM chat_messages "
                    "WHERE session_id = ? AND timestamp >= ? ORDER BY id",
                    (sid, cutoff),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT role, content FROM chat_messages "
                    "WHERE session_id = ? ORDER BY id",
                    (sid,),
                ).fetchall()
            messages = [{"role": r["role"], "content": r["content"]} for r in rows]
            # Strip toxic assistant turns (and their dangling user pair) before
            # the model ever sees them — protects against the leaked-tool-call
            # poisoning observed pre-v0.9.8 and against repeated synthetic
            # error sentinels.
            messages = _purge_toxic_turns(messages)
            if len(messages) > max_turns * 2:
                messages = messages[-(max_turns * 2):]
            return messages

    def get_past_summaries(self, n: int = PAST_SESSIONS_LIMIT) -> list[dict]:
        """Return closed sessions with summaries, most recent first."""
        with self._mu:
            rows = self._conn.execute(
                "SELECT session_id, started_at, last_msg_at, summary FROM chat_sessions "
                "WHERE summary IS NOT NULL ORDER BY last_msg_at DESC LIMIT ?",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_user_turns(self) -> int:
        """Count user messages in the active (non-stale) session."""
        with self._mu:
            sid = self._fresh_session_id()
            if not sid:
                return 0
            cnt = self._conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role = 'user'",
                (sid,),
            ).fetchone()
            return cnt[0] if cnt else 0

    def clear(self) -> None:
        with self._mu:
            self._conn.execute("DELETE FROM chat_messages")
            self._conn.execute("DELETE FROM chat_sessions")
            self._conn.commit()

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
# Backward-compatible public functions (same signatures as old JSON store,
# minus `chatbot_id` -- fetta E4 Task 5, "un bot solo": c'e' UNA cronologia)
# ---------------------------------------------------------------------------

def load_history(data_dir: str, *, giorni: int = 90) -> list[dict]:
    """Return [{role, content}] for the active session (Claude API format).

    `giorni` threads through to `ChatStore.load_context` -- see its docstring
    for why this is NOT a housekeeping knob. Production callers pass
    `impostazioni_chat.giorni_conservazione` explicitly; the default here only
    covers this repo's callers that don't have an opinion on retention."""
    return _get_store(data_dir).load_context(giorni=giorni)


def append_messages(messages: list[dict], data_dir: str) -> None:
    """Append [{role, content}] to the active session."""
    _get_store(data_dir).append(messages)


def clear_history(data_dir: str) -> None:
    """Delete all history and sessions."""
    _get_store(data_dir).clear()


def get_past_summaries(data_dir: str, n: int = PAST_SESSIONS_LIMIT) -> list[dict]:
    """Return up to n closed session summaries, most recent first."""
    return _get_store(data_dir).get_past_summaries(n)


def count_user_turns(data_dir: str) -> int:
    """Count user turns in the active session (used for max_chat_turns enforcement)."""
    return _get_store(data_dir).count_user_turns()


def delete_old_messages(data_dir: str, retention_days: int) -> int:
    """Hard-delete chat messages older than retention_days days."""
    return _get_store(data_dir).delete_old_messages(retention_days)


def close_all_stores() -> None:
    """Close all SQLite connections (call on app shutdown)."""
    with _lock:
        for store in _stores.values():
            store.close()
        _stores.clear()
