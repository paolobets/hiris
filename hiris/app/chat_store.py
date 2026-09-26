import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta

from .chat_thread import ChatThread
from .proxy._sanitize import truncate_with_marker
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


def unanswered_assistant_lines(history: list[dict]) -> list[str]:
    """I messaggi di HIRIS che aprono la conversazione, prima del primo turno
    dell'utente -- gli esiti di promesse arrivati mentre la persona non c'era
    (fetta «il seguito delle chat divise»).

    La casa sola di questa domanda, per i suoi tre lettori: `_trim_history`
    li toglie (l'API di Claude non accetta una cronologia che comincia con un
    `assistant`), `compose_chat_context` li rimette nel contesto perche' il
    modello sappia a cosa la persona sta rispondendo, e `_close_session` li
    tiene nel riassunto, dove non fanno coppia con nessun turno utente.
    """
    lines: list[str] = []
    for message in history or []:
        if message.get("role") != "assistant":
            break
        lines.append(str(message.get("content") or ""))
    return lines


def conversation_title(first_user_message: str | None) -> str:
    """La prima frase di `first_user_message`, spazi ricomposti, dentro
    `CONVERSATION_TITLE_MAX_CHARS`; `OUTCOME_ONLY_TITLE` se non c'e'."""
    text = (first_user_message or "").strip()
    sentence = " ".join(_SENTENCE_END_RE.split(text, maxsplit=1)[0].split())
    if not sentence:
        return OUTCOME_ONLY_TITLE
    return truncate_with_marker(sentence, CONVERSATION_TITLE_MAX_CHARS)


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

#: Il titolo di una conversazione (spec 2026-09-26 §4) non si salva: e' la
#: prima frase dell'utente nella sessione, letta quando serve. Il tetto e'
#: una scelta, non una misura: un titolo in una barra laterale, non un
#: paragrafo -- il resto lo taglia gia' l'ellissi del CSS. Il segno del taglio
#: e' quello della casa (`truncate_with_marker`), non un secondo.
CONVERSATION_TITLE_MAX_CHARS = 60
#: Il titolo di una conversazione senza nessuna frase dell'utente: l'ha
#: aperta l'esito di una promessa (RULING 3.9). Non si inventa un turno
#: dell'utente per avere un titolo.
OUTCOME_ONLY_TITLE = "Esito di una promessa"
# Una frase finisce su `.`, `!` o `?` seguiti da uno spazio, o su un a capo:
# lo spazio richiesto tiene intero «22.5 gradi».
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s|\n")

# Una sessione di cui la conservazione ricorda ancora almeno un messaggio.
# Frammento di SQL, non funzione: sta dentro la WHERE sulla sessione `s`.
_HAS_RETAINED_MESSAGE = ("EXISTS (SELECT 1 FROM chat_messages m "
                         "WHERE m.session_id = s.session_id AND m.timestamp >= ?)")


def _retention_cutoff(days: int) -> str:
    """Il primo istante che la conservazione ricorda; `""` quando `days` e'
    `0` (nessun filtro: ogni `timestamp` e' `>= ""`), la stessa regola di
    `delete_old_messages`."""
    if days <= 0:
        return ""
    return (datetime.now(UTC) - timedelta(days=days)).strftime(_TS_FMT)


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
        self._close_other_open_sessions(thread, keep=sid)
        return sid

    def _close_other_open_sessions(self, thread: ChatThread, keep: str | None) -> None:
        """Chiude, riassumendole, le sessioni aperte del filo tranne `keep`."""
        rows = self._conn.execute(
            "SELECT session_id FROM chat_sessions WHERE summary IS NULL "
            "AND subject_key = ? AND entry_point = ?",
            (thread.subject_key, thread.entry_point),
        ).fetchall()
        for row in rows:
            if row["session_id"] != keep:
                self._close_session(thread, row["session_id"])

    def _close_session(self, thread: ChatThread, session_id: str) -> None:
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
            # Gli esiti di promesse che hanno aperto la conversazione non
            # fanno coppia con nessun turno utente: senza questa riga il
            # riassunto li perderebbe.
            if turns:
                opening = unanswered_assistant_lines(
                    [{"role": r["role"], "content": r["content"]}
                     for r in reversed(rows)])
                for a in opening:
                    a_trunc = a[:_DIGEST_MSG_LEN] + "…" if len(a) > _DIGEST_MSG_LEN else a
                    pairs.append(f"A: {a_trunc}")
            for u, a in turns[-_DIGEST_TURNS:]:
                u_trunc = u[:_DIGEST_MSG_LEN] + "…" if len(u) > _DIGEST_MSG_LEN else u
                a_trunc = a[:_DIGEST_MSG_LEN] + "…" if len(a) > _DIGEST_MSG_LEN else a
                pairs.append(f"U: {u_trunc}\nA: {a_trunc}")
            summary = "\n---\n".join(pairs) if pairs else rows[0]["content"][:SUMMARY_MAX_CHARS]
        else:
            summary = "(nessuna risposta)"
        # Il filo nella clausola anche qui: chiudere e' scrivere, e una
        # scrittura su `chat_sessions` lega sempre id, soggetto e ingresso
        # (security 6.3) -- un id arrivato da fuori non chiude la sessione
        # di un altro filo.
        self._conn.execute(
            "UPDATE chat_sessions SET summary = ? "
            "WHERE session_id = ? AND subject_key = ? AND entry_point = ?",
            (summary, session_id, thread.subject_key, thread.entry_point),
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
            rows = self._conn.execute(
                "SELECT role, content, timestamp FROM chat_messages "
                "WHERE session_id = ? AND timestamp >= ? ORDER BY id",
                (sid, _retention_cutoff(days)),
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

    # ------------------------------------------------------------------
    # Le conversazioni del filo (fetta «il seguito delle chat divise», spec
    # 2026-09-26 §4). Una conversazione e' una sessione. Ogni istruzione su
    # `chat_sessions` lega id, soggetto E ingresso: un id arrivato dalla rotta
    # che non e' di questo filo -- di un altro, o orfano -- non trova niente,
    # esattamente come un id che non esiste (security 6.3).
    # ------------------------------------------------------------------

    def list_conversations(self, thread: ChatThread, *, days: int = 90) -> list[dict]:
        """Le conversazioni del filo, la piu' recente in testa: `{id, titolo,
        ultimo_messaggio, attiva}`.

        `days` e' `ChatSettings.retention_days`, con la regola di
        `load_context`: una conversazione di cui la conservazione ha fatto
        dimenticare ogni messaggio non si elenca, e il titolo si legge fra i
        messaggi ancora ricordati. `attiva` e' la sessione che il prossimo
        turno continuerebbe -- una al piu'."""
        cutoff = _retention_cutoff(days)
        with self._mu:
            active = self._fresh_session_id(thread)
            rows = self._conn.execute(
                "SELECT s.session_id, s.last_msg_at, "
                "(SELECT m.content FROM chat_messages m "
                " WHERE m.session_id = s.session_id AND m.role = 'user' "
                " AND trim(m.content) != '' AND m.timestamp >= ? "
                " ORDER BY m.id LIMIT 1) AS first_user "
                "FROM chat_sessions s "
                "WHERE s.subject_key = ? AND s.entry_point = ? AND "
                + _HAS_RETAINED_MESSAGE
                # A pari secondo (una ripresa subito dopo l'ultimo messaggio)
                # l'attiva sta in testa: e' la conversazione piu' recente.
                + " ORDER BY s.last_msg_at DESC, s.session_id = ? DESC, s.rowid DESC",
                (cutoff, thread.subject_key, thread.entry_point, cutoff, active),
            ).fetchall()
        return [{"id": r["session_id"],
                 "titolo": conversation_title(r["first_user"]),
                 "ultimo_messaggio": r["last_msg_at"],
                 "attiva": r["session_id"] == active}
                for r in rows]

    def new_conversation(self, thread: ChatThread) -> None:
        """Chiude, col riassunto, la conversazione aperta del filo.

        Non crea niente: la sessione nuova nasce alla prossima `append`, perche'
        la regola «una sessione nasce solo quando si scrive» (spec §4) resta
        una sola. Ripetuta, non trova niente da chiudere (security 6.10)."""
        with self._mu:
            try:
                self._close_other_open_sessions(thread, keep=None)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def resume_conversation(self, thread: ChatThread, session_id: str, *,
                            days: int = 90) -> bool:
        """Torna attiva una conversazione del filo; `False` se non ce n'e'
        una con quell'id -- altrui, orfana, inesistente o dimenticata.

        Chiude, col riassunto, quella aperta del filo (di NESSUN altro filo,
        security 6.4), e riapre questa: il riassunto si azzera (si rifara'
        alla prossima chiusura) e `last_msg_at` diventa adesso, cosi' la
        conversazione ripresa rientra nella regola delle due ore invece di
        richiudersi al primo turno. `days` come in `list_conversations`: si
        riprende solo cio' che l'elenco mostra, e `load_context` rilegge poi
        solo i messaggi dentro la conservazione (security 6.9)."""
        key = (session_id, thread.subject_key, thread.entry_point)
        with self._mu:
            found = self._conn.execute(
                "SELECT 1 FROM chat_sessions s WHERE s.session_id = ? "
                "AND s.subject_key = ? AND s.entry_point = ? AND "
                + _HAS_RETAINED_MESSAGE,
                (*key, _retention_cutoff(days)),
            ).fetchone()
            if found is None:
                return False
            try:
                self._close_other_open_sessions(thread, keep=session_id)
                self._conn.execute(
                    "UPDATE chat_sessions SET summary = NULL, last_msg_at = ? "
                    "WHERE session_id = ? AND subject_key = ? AND entry_point = ?",
                    (self._now(), *key),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return True

    def delete_conversation(self, thread: ChatThread, session_id: str) -> bool:
        """Cancella una conversazione del filo -- messaggi e sessione nella
        STESSA transazione, cosi' nessun messaggio resta appeso a una sessione
        che non c'e' piu' (security 6.6). `False` se non c'e' una conversazione
        del filo con quell'id. Le orfane e gli altri fili restano intatti: la
        condizione sul filo sta in tutte e due le istruzioni."""
        key = (session_id, thread.subject_key, thread.entry_point)
        with self._mu:
            try:
                self._conn.execute(
                    "DELETE FROM chat_messages WHERE session_id IN "
                    "(SELECT session_id FROM chat_sessions "
                    "WHERE session_id = ? AND subject_key = ? AND entry_point = ?)", key)
                cur = self._conn.execute(
                    "DELETE FROM chat_sessions "
                    "WHERE session_id = ? AND subject_key = ? AND entry_point = ?", key)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return cur.rowcount > 0

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
        cutoff = _retention_cutoff(retention_days)
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


def list_conversations(data_dir: str, *, thread: ChatThread,
                       days: int = 90) -> list[dict]:
    """Le conversazioni del filo -- vedi `ChatStore.list_conversations`."""
    return _get_store(data_dir).list_conversations(thread, days=days)


def new_conversation(data_dir: str, *, thread: ChatThread) -> None:
    """Chiude la conversazione aperta del filo -- vedi `ChatStore.new_conversation`."""
    _get_store(data_dir).new_conversation(thread)


def resume_conversation(data_dir: str, *, thread: ChatThread, session_id: str,
                        days: int = 90) -> bool:
    """Riprende una conversazione del filo -- vedi `ChatStore.resume_conversation`."""
    return _get_store(data_dir).resume_conversation(thread, session_id, days=days)


def delete_conversation(data_dir: str, *, thread: ChatThread, session_id: str) -> bool:
    """Cancella una conversazione del filo -- vedi `ChatStore.delete_conversation`."""
    return _get_store(data_dir).delete_conversation(thread, session_id)


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
