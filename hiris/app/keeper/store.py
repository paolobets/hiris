"""L'archivio delle promesse: l'UNICA casa di «cosa e quando».

Non esiste un timer per promessa. Un timer in memoria muore al riavvio e
diventa un secondo posto che sa quando: qui la verita' e' la tabella, e
l'orologio (`orologio.py`) non fa che chiederle chi e' scaduto.

Non solleva mai verso il chiamante per un ingresso sbagliato: `create` e
`cancel` rispondono con un dizionario che porta `errore`, perche' chi li
chiama e' uno strumento che parla a un modello. Solleva soltanto cio' che
sollevano SQLite e il filesystem, che non sono errori d'ingresso.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time

from ..chat_thread import ChatThread
from ..storage import connect, init_schema
from .promise import (
    CEILING_IN_SOSPESO,
    CONSERVAZIONE_S,
    HOUSE_CEILING_IN_SOSPESO,
    STATES_CONCLUSI,
    STATES_ESITO,
    STATES_SOSPESO,
    serializza,
    validate,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS promesse (
    id TEXT PRIMARY KEY,
    specie TEXT NOT NULL,
    frase TEXT NOT NULL,
    quando_ts REAL NOT NULL,
    quando_detto TEXT,
    fuso TEXT,
    chiamata_json TEXT,
    domanda TEXT,
    istantanea_json TEXT,
    -- Il servizio notify che il MODELLO sceglieva alla nascita. Dalla fetta
    -- «il seguito delle chat divise» (spec 2026-09-26 §2) non si scrive
    -- piu' e non si legge piu' per recapitare: il recapito si risolve al
    -- risveglio dal soggetto di chi ha chiesto (`keeper/recipient.py`). La
    -- colonna resta perche' le righe vecchie la portano, e togliere una
    -- colonna in SQLite e' una riscrittura della tabella per niente.
    recapito TEXT,
    stato TEXT NOT NULL DEFAULT 'in_attesa',
    motivo TEXT,
    esecuzione_id TEXT,
    testo TEXT,
    avvisare INTEGER,
    nata_ts REAL NOT NULL,
    risvegliata_ts REAL,
    esito_letto_ts REAL,
    entities_at_birth INTEGER,
    -- Il filo di chi l'ha chiesta (spec 2026-09-26 §2): gli stessi nomi di
    -- `chat_sessions`, `reasoning_jobs`, `costruzioni`. NULL per le promesse
    -- nate prima, invisibili a tutti finche' il proprietario non le adotta.
    subject_key TEXT,
    entry_point TEXT
);
CREATE INDEX IF NOT EXISTS idx_promesse_scadenza ON promesse(stato, quando_ts);
"""

_CONCLUSI = ",".join(f"'{s}'" for s in STATES_CONCLUSI)
# Stessa forma di `_CONCLUSI` qui sopra, per lo stesso motivo: composta UNA
# volta dal vocabolario di `promessa.py`, mai riscritta a mano nelle due
# query sotto (review finale, rilievo ②).
_SOSPESI = ",".join(f"'{s}'" for s in STATES_SOSPESO)
# Gli stati che sono una notizia per chi legge: `STATES_CONCLUSI` meno
# `disdetta`. Composto UNA volta dal vocabolario di `promise.py`, come i due
# qui sopra -- vedi li' perche' non coincide con `_CONCLUSI`.
_ESITI = ",".join(f"'{s}'" for s in STATES_ESITO)


def _migration_2(conn) -> None:
    """v1 -> v2: l'archivio ricorda se un esito e' stato letto.

    Una colonna aggiunta, nessuna riscritta -- stessa forma di
    `action/journal.py::_migration_2`, che e' il precedente di questo
    archivio.

    **Il travaso non e' neutro, ed e' una decisione.** Dopo l'`ALTER TABLE`
    ogni riga vale NULL, cioe' «non letta»: su una casa vera vuol dire che
    tutto lo storico degli ultimi 90 giorni (`CONSERVAZIONE_S`) risulterebbe
    da leggere, e il pallino degli Impegni si accenderebbe al primo avvio con
    un numero che parla di fatti di settimane fa. Le concluse che esistono
    gia' si segnano lette. Non e' vero che il proprietario le ha lette: e' che
    **il segno di lettura comincia a contare dal giorno in cui esiste**, e
    cio' che e' successo prima e' storia, non notizia.

    Le promesse ancora IN SOSPESO restano NULL, ed e' giusto: non hanno
    ancora nessun esito da leggere. Lo prenderanno concludendosi.

    **L'`UPDATE` sta FUORI dall'`if`, e la ragione e' una caduta di corrente**
    (review indipendente della fetta, rilievo 2). In questo modulo
    `ALTER TABLE` si auto-committa -- misurato: `conn.in_transaction` e'
    `False` subito dopo -- mentre l'`UPDATE` no, e `init_schema` fa un solo
    `commit()` in fondo. Fra i due c'e' quindi una finestra in cui la colonna
    e' gia' sul disco e il travaso non lo e'. Se il Raspberry si spegne li'
    dentro, al riavvio la colonna esiste ma `user_version` e' ancora 1:
    `init_schema` richiama questa funzione, e una guardia che saltasse tutto
    perche' «la colonna c'e' gia'» lascerebbe il travaso non fatto PER
    SEMPRE -- nessun altro codice lo rifarebbe. Il pallino si accenderebbe
    con novanta giorni di storico, che e' esattamente il difetto per cui il
    travaso esiste.

    A rendere l'`UPDATE` ripetibile senza danno basta `esito_letto_ts IS
    NULL`: una riga gia' segnata non viene ri-timbrata, che era la sola cosa
    che la vecchia guardia proteggeva davvero.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(promesse)")}
    if "esito_letto_ts" not in existing:
        conn.execute("ALTER TABLE promesse ADD COLUMN esito_letto_ts REAL")
    conn.execute(
        f"UPDATE promesse SET esito_letto_ts=? WHERE stato IN ({_ESITI}) "
        "AND esito_letto_ts IS NULL",
        (time.time(),))


def _migration_3(conn) -> None:
    """`entities_at_birth`: quante entita' toccava il bersaglio ALLA NASCITA
    (reperto B-6, 22/09/2026).

    Su un bersaglio per area la verifica alla nascita si fermava prima -- «lo
    risolvera' la porta, al momento» -- quindi una promessa nasceva senza che
    nessuno sapesse cosa avrebbe toccato, e poteva risvegliarsi trenta giorni
    dopo su una casa diversa.

    **Si AGGIUNGE, non si riscrive**, e senza `NOT NULL`: le promesse nate
    prima di oggi quel numero non ce l'hanno, e `None` e' esattamente cio' che
    sono -- non `0`, che direbbe «nessuna entita'», che e' un'altra cosa. Lo
    stesso precedente di `action/journal.py::_migration_3` (`soggetto_json`).

    Il nome e' in INGLESE perche' le colonne nuove lo sono: le italiane sono
    debito, e si migrano in una fetta loro.
    """
    colonne = {r[1] for r in conn.execute("PRAGMA table_info(promesse)")}
    if "entities_at_birth" not in colonne:
        conn.execute("ALTER TABLE promesse ADD COLUMN entities_at_birth INTEGER")


def _migration_4(conn) -> None:
    """v3 -> v4: il filo di chi ha chiesto (fetta «il seguito delle chat
    divise», spec 2026-09-26 §2).

    `ALTER TABLE` solo se la colonna manca -- un archivio che nasce oggi la
    porta gia' da `_SCHEMA` (stesso pattern di `revisions.py::_migration_2`).
    **Nessun indice**: le letture per filo restano entro il tetto della casa
    (`HOUSE_CEILING_IN_SOSPESO` in sospeso, piu' novanta giorni di storico),
    e l'indice su `stato` le serve gia'. Le righe esistenti restano NULL:
    sono di prima, e le adotta il proprietario (`chat_thread.adopt_if_owner`).
    """
    colonne = {r[1] for r in conn.execute("PRAGMA table_info(promesse)")}
    if "subject_key" not in colonne:
        conn.execute("ALTER TABLE promesse ADD COLUMN subject_key TEXT")
    if "entry_point" not in colonne:
        conn.execute("ALTER TABLE promesse ADD COLUMN entry_point TEXT")


# La condizione «di questo filo», una volta sola: ogni lettura e scrittura per
# conto di qualcuno la porta, con i due valori come parametri (`?`), mai
# incollati nel testo della query.
_OF_THREAD = "subject_key = ? AND entry_point = ?"


def _thread_params(thread: ChatThread) -> tuple[str, str]:
    return (thread.subject_key, thread.entry_point)


def _json(value) -> str | None:
    return None if value is None else json.dumps(value)


class AgendaStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=4,
                    migrations={2: _migration_2, 3: _migration_3, 4: _migration_4})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- scrivere ------------------------------------------------------

    def create(self, data: dict, *, thread: ChatThread, now: float) -> dict:
        """Una promessa nuova, nel filo di chi l'ha chiesta.

        `thread` non ha un default: una promessa senza nessuno che l'abbia
        chiesta non avrebbe a chi tornare. Chi non ha un filo lo dice prima
        (`ToolDispatcher._promise`). `recapito` non si scrive, anche se
        arriva nei dati: vedi lo schema.

        Due tetti, in quest'ordine: quello del filo (e' il caso normale, e il
        messaggio parla delle TUE promesse) e quello della casa (vedi
        `promise.HOUSE_CEILING_IN_SOSPESO` per il perche').
        """
        reason = validate(data, now=now)
        if reason is not None:
            return {"errore": reason}
        with self._lock:
            self._prune(now)
            mine = self._conn.execute(
                f"SELECT count(*) FROM promesse WHERE stato IN ({_SOSPESI}) "
                f"AND {_OF_THREAD}", _thread_params(thread)).fetchone()[0]
            if mine >= CEILING_IN_SOSPESO:
                return {"errore": (
                    f"hai gia' {CEILING_IN_SOSPESO} promesse in sospeso, che e' "
                    "il tetto che HIRIS si e' dato: disdicine una prima di "
                    "farne un'altra."
                )}
            house = self._conn.execute(
                f"SELECT count(*) FROM promesse WHERE stato IN ({_SOSPESI})"
            ).fetchone()[0]
            if house >= HOUSE_CEILING_IN_SOSPESO:
                return {"errore": (
                    f"in questa casa ci sono gia' {HOUSE_CEILING_IN_SOSPESO} "
                    "promesse in sospeso, che e' il tetto che HIRIS si e' dato "
                    "per tutti insieme: ne potro' prendere un'altra quando "
                    "qualcuna si sara' conclusa."
                )}
            ident = secrets.token_urlsafe(9)
            self._conn.execute(
                "INSERT INTO promesse(id,specie,frase,quando_ts,quando_detto,fuso,"
                "chiamata_json,domanda,istantanea_json,stato,nata_ts,"
                "entities_at_birth,subject_key,entry_point) "
                "VALUES(?,?,?,?,?,?,?,?,?,'in_attesa',?,?,?,?)",
                (ident, data["specie"], data["frase"].strip(), float(data["quando_ts"]),
                 data.get("quando_detto"), data.get("fuso"),
                 _json(data.get("chiamata")), data.get("domanda"),
                 _json(data.get("istantanea")),
                 now,
                 # Quante entita' toccava il bersaglio alla nascita (B-6).
                 # `None` quando non c'e' niente da risolvere -- un bersaglio
                 # di sole entita' -- ed e' diverso da `0`, che direbbe
                 # «nessuna entita'».
                 data.get("entities_at_birth"),
                 *_thread_params(thread)))
            self._conn.commit()
        return {"promessa": self.read(ident)}

    def prendi(self, promise_id: str, *, now: float) -> bool:
        """`in_attesa` -> `in_corso`, atomica. `False` se qualcuno e' arrivato prima.

        E' QUI che vive «mai due volte»: non nel chiamante, che potrebbe
        dimenticarsene, ma in una `UPDATE ... WHERE stato='in_attesa'` che il
        database serializza per noi.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET stato='in_corso', risvegliata_ts=? "
                "WHERE id=? AND stato='in_attesa'", (now, promise_id))
            self._conn.commit()
            return cur.rowcount == 1

    def concludi(self, promise_id: str, *, state: str, now: float,
                 reason: str | None = None, execution_id: str | None = None,
                 text: str | None = None, avvisare: bool | None = None) -> None:
        if state not in STATES_CONCLUSI:
            raise ValueError(f"«{state}» non e' uno stato conclusivo")
        with self._lock:
            self._conn.execute(
                "UPDATE promesse SET stato=?, motivo=?, esecuzione_id=?, testo=?, "
                "avvisare=?, risvegliata_ts=COALESCE(risvegliata_ts, ?) WHERE id=?",
                (state, reason, execution_id, text,
                 None if avvisare is None else int(avvisare), now, promise_id))
            self._conn.commit()

    def mark_read(self, ids: list[str], *, thread: ChatThread, now: float) -> int:
        """Segna letti gli esiti degli id passati. Torna quante righe ha toccato.

        Le tre condizioni della `WHERE` servono tutte, e ognuna esclude un
        difetto diverso:
        - `id IN (...)`: si segna cio' che e' stato MOSTRATO, non «tutto il
          non letto». Una pagina che disegna dieci righe non deve poter
          spegnere un esito che l'utente non ha davanti;
        - `stato IN (conclusi)`: una promessa in sospeso non ha un esito da
          leggere, e scriverle addosso un'ora di lettura sarebbe un fatto
          falso in archivio;
        - `esito_letto_ts IS NULL`: rimarcare una riga gia' letta ne
          falserebbe il momento;
        - il filo: l'id di un'altra persona non si segna, e conta zero come
          uno inesistente (spec 2026-09-26 §2).
        """
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE promesse SET esito_letto_ts=? WHERE id IN ({marks}) "
                f"AND stato IN ({_ESITI}) AND esito_letto_ts IS NULL "
                f"AND {_OF_THREAD}",
                (now, *ids, *_thread_params(thread)))
            self._conn.commit()
            return cur.rowcount

    def cancel(self, promise_id: str, *, thread: ChatThread, now: float) -> dict:
        """`in_attesa` -> `disdetta`, atomica sullo stesso modello di `prendi`.

        Non si legge lo stato per DECIDERE: si scrive con una
        `UPDATE ... WHERE stato='in_attesa'` e si guarda il `rowcount`. Se si
        leggesse prima e si scrivesse dopo, l'orologio potrebbe infilare un
        `prendi` (e l'azione vera) nella finestra fra le due mosse: l'azione
        sarebbe avvenuta e l'archivio direbbe comunque «disdetta». La lettura
        resta -- serve a dire ALL'UTENTE perche' non si e' disdetta -- ma
        arriva dopo, per costruire il messaggio, mai per arbitrare.

        **Solo nel filo di chi disdice**, in tutte e due le mosse: una
        promessa di un altro filo risponde esattamente come una che non
        esiste (spec 2026-09-26 §2) -- un «esiste, ma non e' tua» direbbe a
        Marta che Paolo ha qualcosa in programma.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET stato='disdetta', "
                "risvegliata_ts=COALESCE(risvegliata_ts, ?) "
                f"WHERE id=? AND stato='in_attesa' AND {_OF_THREAD}",
                (now, promise_id, *_thread_params(thread)))
            self._conn.commit()
            riuscita = cur.rowcount == 1
        row = self.read_in_thread(promise_id, thread)
        if riuscita:
            return {"promessa": row}
        if row is None:
            return {"errore": "non ho nessuna promessa con quell’identificatore."}
        return {
            "errore": "quella promessa e' gia' {}: non si disdice, si legge.".format(row["stato"])
        }

    def risana(self, *, now: float) -> int:
        """Le prese a meta' al riavvio: `fallita`, col motivo, e non ripartono.

        Una promessa `in_corso` all'avvio significa una cosa sola: l'add-on si
        e' fermato mentre la manteneva.

        **Non si riprova, ne' l'una ne' l'altra specie**, e non e' timidezza:
        il momento della promessa e' passato. Rieseguire «il delta rispetto a
        un'ora fa» tre ore dopo darebbe una risposta confidentemente falsa --
        la stessa ragione per cui esiste la tolleranza dei 120 secondi
        (`promessa.TOLLERANZA_S`). Fallire e' meglio che rispondere sbagliato.
        Questo vale ancora di piu' dalla fetta «le promesse seguono la catena»,
        che ha allargato da secondi a minuti la finestra in cui una promessa e'
        `in_corso`: piu' spesso, non diversamente.

        **Cio' che cambia e' cosa l'utente puo' CONCLUDERE**, e per le due
        specie non e' la stessa cosa. Per un `fai` il dubbio e' se la casa sia
        stata toccata: una luce accesa due volte e' innocua, una serranda no.
        Per un `chiedi` la casa non e' stata toccata di sicuro -- quel turno ha
        solo strumenti di lettura per costruzione (`turno.SOLA_LETTURA`) -- e
        l'unico dubbio e' la notifica, che parte PRIMA che la promessa si
        chiuda (`orologio.concludi_chiedi`). Due dubbi diversi, due frasi
        diverse: una sola li appiattisce, e manda a cercare un problema che
        non c'e'.
        """
        _REASON_FAI = (
            "l’add-on si e' fermato mentre la manteneva: non l’ho ripetuta, "
            "perche' non so se fosse gia' partita.")
        _REASON_CHIEDI = (
            "l’add-on si e' fermato mentre guardavo: non ho toccato niente in "
            "casa, ma non so se la notifica fosse gia' partita. Non l’ho "
            "ripetuta: l’ora che mi avevi dato e' passata, e una risposta "
            "fuori tempo sarebbe sbagliata.")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET stato='fallita', "
                "motivo=CASE WHEN specie='fai' THEN ? ELSE ? END "
                "WHERE stato='in_corso'",
                (_REASON_FAI, _REASON_CHIEDI))
            self._conn.commit()
            count = cur.rowcount
        if count:
            logger.warning("schedulatore: %d promesse erano in corso all'avvio, "
                           "dichiarate fallite (non ripetute)", count)
        return count

    # -- leggere -------------------------------------------------------

    def read(self, promise_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM promesse WHERE id=?", (promise_id,)).fetchone()
        return None if row is None else serializza(row)

    def read_in_thread(self, promise_id: str, thread: ChatThread) -> dict | None:
        """La promessa, se e' di QUESTO filo; `None` se non esiste o e' di un
        altro -- per chi chiede sono la stessa cosa (spec 2026-09-26 §2).

        `read` senza filo resta, ed e' per chi lavora per conto della
        promessa e non di chi guarda: l'orologio, la consegna del ponte, la
        rotta MCP che verifica `X-HIRIS-Promessa`."""
        with self._lock:
            row = self._conn.execute(
                f"SELECT * FROM promesse WHERE id=? AND {_OF_THREAD}",
                (promise_id, *_thread_params(thread))).fetchone()
        return None if row is None else serializza(row)

    def read_by_execution(self, execution_id: str) -> dict | None:
        """La promessa che ha prodotto questa esecuzione, o `None`.

        Serve a `GET /api/executions/{id}`: la cronaca di cio' che una
        promessa ha fatto e' di chi l'ha chiesta, non di chiunque ne indovini
        l'id.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM promesse WHERE esecuzione_id=? LIMIT 1",
                (execution_id,)).fetchone()
        return None if row is None else serializza(row)

    def list(self, *, thread: ChatThread, solo_in_sospeso: bool = False,
             limit: int = 50) -> list[dict]:
        with self._lock:
            if solo_in_sospeso:
                righe = self._conn.execute(
                    f"SELECT * FROM promesse WHERE stato IN ({_SOSPESI}) "
                    f"AND {_OF_THREAD} ORDER BY quando_ts ASC LIMIT ?",
                    (*_thread_params(thread), int(limit))).fetchall()
            else:
                righe = self._conn.execute(
                    f"SELECT * FROM promesse WHERE {_OF_THREAD} "
                    "ORDER BY quando_ts DESC LIMIT ?",
                    (*_thread_params(thread), int(limit))).fetchall()
        return [serializza(r) for r in righe]

    def count_pending(self, thread: ChatThread) -> int:
        """Quante promesse di questo filo sono in sospeso: cio' che il tetto
        per filo (`CEILING_IN_SOSPESO`) misura."""
        with self._lock:
            return self._conn.execute(
                f"SELECT count(*) FROM promesse WHERE stato IN ({_SOSPESI}) "
                f"AND {_OF_THREAD}", _thread_params(thread)).fetchone()[0]

    def has_orphans(self) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM promesse WHERE subject_key IS NULL LIMIT 1"
            ).fetchone() is not None

    def adopt_orphans(self, thread: ChatThread) -> int:
        """Le promesse senza filo diventano di `thread`. Torna quante.

        CHI adotta non si decide qui: lo decide `chat_thread.adopt_if_owner`,
        l'unico chiamante, con la stessa regola della cronologia. Una volta
        sola per costruzione: dopo, nessuna riga ha piu' `subject_key IS
        NULL`, e le promesse nuove nascono tutte con un filo.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET subject_key = ?, entry_point = ? "
                "WHERE subject_key IS NULL", _thread_params(thread))
            self._conn.commit()
            return cur.rowcount

    def count_unread(self, thread: ChatThread) -> int:
        """Quante promesse concluse hanno un esito che nessuno ha letto.

        E' il numero del pallino degli Impegni. NON conta le promesse in
        sospeso, e la differenza e' il punto: una promessa in sospeso non
        aspetta l'utente, aspetta l'ora. Contarle terrebbe il pallino acceso
        tutte le volte che HIRIS ha qualcosa in programma per domani -- cioe'
        quasi sempre -- e un pallino sempre acceso smette di essere letto.

        Le due condizioni sono ENTRAMBE necessarie: `esito_letto_ts` e' NULL
        anche per ogni promessa in sospeso (non ha ancora un esito), quindi
        da sola non dice «da leggere». E il filo: il pallino di Marta non si
        accende per un esito di Paolo (spec 2026-09-26 §2).
        """
        with self._lock:
            return self._conn.execute(
                f"SELECT count(*) FROM promesse WHERE stato IN ({_ESITI}) "
                f"AND esito_letto_ts IS NULL AND {_OF_THREAD}",
                _thread_params(thread)).fetchone()[0]

    def scadute(self, now: float) -> list[dict]:
        with self._lock:
            righe = self._conn.execute(
                "SELECT * FROM promesse WHERE stato='in_attesa' AND quando_ts<=? "
                "ORDER BY quando_ts ASC", (now,)).fetchall()
        return [serializza(r) for r in righe]

    # -- potare --------------------------------------------------------

    def _prune(self, now: float) -> None:
        """Alla scrittura, non con un lavoro periodico (spec §8.1).

        Un lavoro in piu' sarebbe un secondo posto che sa QUANDO, cioe'
        precisamente cio' che la fetta successiva si e' impegnata a togliere.
        Le promesse in sospeso non si potano mai, qualunque eta' abbiano: il
        tetto dei 30 giorni le tiene gia' entro un limite.

        **L'eta' si misura da `risvegliata_ts`, non da `nata_ts`** (fix
        review finale, rilievo minore). La spec §8.1 dice novanta giorni
        «per le promesse CONCLUSE»: l'orologio della potatura deve partire
        da quando una promessa si e' conclusa, non da quando e' nata. Una
        promessa nata 91 giorni fa e mantenuta ieri (legittimo -- l'orizzonte
        di nascita e' 30 giorni, non di conclusione) doveva restare per
        novanta giorni dalla conclusione, e con `nata_ts` spariva domani.
        `risvegliata_ts` e' sempre popolato per uno stato concluso: sia
        `concludi()` sia `cancel()` lo scrivono con
        `COALESCE(risvegliata_ts, adesso)`, quindi non serve un ripiego su
        `nata_ts` per le righe che non sono mai passate da `prendi()`.

        Chiamata con il lock gia' preso.
        """
        self._conn.execute(
            f"DELETE FROM promesse WHERE stato IN ({_CONCLUSI}) AND risvegliata_ts < ?",
            (now - CONSERVAZIONE_S,),
        )
