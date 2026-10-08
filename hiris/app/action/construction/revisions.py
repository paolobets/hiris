"""L'archivio delle costruzioni: cosa e' stato proposto, cosa e' stato fatto,
e com'era prima.

**Una proposta e l'atto che ne nasce sono lo stesso oggetto in due momenti**,
e stanno nella stessa tabella con uno `stato` (spec §7). Due tabelle sarebbero
due case per un fatto solo -- fondamenta 2 -- e la seconda finirebbe per
divergere dalla prima.

Vive nell'archivio e non nella conversazione: se chiudi la chat, la proposta
resta. E' la stessa correzione che il proprietario ha imposto per le promesse
(«la verita' vive nello Schedulatore, non nella chat»).

**La regola di conservazione ha un'eccezione, ed e' quella che conta.** Home
Assistant non tiene storico di automazioni, script e scene: l'ultima versione
precedente di un oggetto, custodita qui, e' **l'unica copia esistente al
mondo**. Potarla dopo novanta giorni come una riga di cronaca sarebbe
cancellare un backup. Le righe vecchie se ne vanno; l'ultima applicata di
ogni oggetto no, per sempre.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading

from ...chat_thread import ChatThread, thread_from_columns, thread_params
from ...storage import (
    Retention,
    add_missing_columns,
    archive_name,
    connect,
    init_schema,
    prune_declared,
    rekey,
)

logger = logging.getLogger(__name__)

#: Il motivo scritto quando chi costruisce dice no da questa pagina, prima
#: che l'officina abbia mai provato a scrivere niente (fetta "il seguito
#: delle chat divise", Task 5, 26/09/2026). Diceva letteralmente «rifiutata
#: dal proprietario»: un testo che assumeva un proprietario solo, mentre la
#: pagina Costruzioni e' oggi di chiunque abbia `costruire` (spec 2026-09-26
#: §3, decisione 5) -- non una persona per nome, che richiederebbe leggerla
#: da un soggetto che questo metodo non riceve. UNA costante: la pagina la
#: legge dal campo `motivo` che l'API espone gia' su ogni riga (`_row`,
#: `handlers_constructions._out`), non la retipa in JavaScript.
#:
#: Fix round 1 (review Task 5): si chiamava `MOTIVO_DISDETTA` -- un
#: identificatore italiano nell'ambito chiuso `action/`, dove il glossario
#: decide gia' `motivo -> reason` (`docs/GLOSSARIO.md`). Rinominata seguendo
#: la stessa convenzione della sorella `STATES_SOSPESO` due righe sotto:
#: prefisso inglese deciso (`REASON`), radice del dominio non tradotta
#: (`DISDETTA`, un valore di dominio che il glossario rinvia di proposito,
#: vedi «I valori di dominio»). Il VALORE resta italiano: e' testo per
#: l'archivio e per la pagina, non un nome.
REASON_DISDETTA = "rifiutata dalla pagina"

# L'insieme «in sospeso» -- stessa forma di `STATES_SOSPESO` in
# `keeper/promise.py`, per lo stesso motivo: una proposta rivendicata
# (`in_corso`) non e' ancora conclusa, e non deve sparire dall'elenco delle
# pendenti ne' smettere di contare contro il tetto nella finestra fra
# `claim` e la transizione finale (`applicata`/`rifiutata`).
STATES_SOSPESO = ("in_attesa", "in_corso")
_SOSPESI_SQL = ",".join(f"'{s}'" for s in STATES_SOSPESO)

#: **Quando una proposta e' scaduta**: in attesa da prima del limite (il
#: parametro e' `adesso - DEADLINE_S`). Il predicato vive qui una volta, e lo
#: usano chi la segna (`_scadi`), chi la legge (`read`, `list`), chi la conta
#: (`count_pending`) e chi la rivendica o la rifiuta (`claim`,
#: `mark_cancelled`): fino al 06/10/2026 la scadenza la scriveva la LETTURA
#: dell'elenco (`GET /api/constructions` chiamava `scadi`), e una proposta
#: scaduta restava confermabile dalla chat finche' nessuno apriva la pagina.
_EXPIRED_SQL = "(stato='in_attesa' AND creata_ts < ?)"

#: Il motivo di una proposta scaduta, scritto o letto.
REASON_EXPIRED = "scaduta senza risposta"

#: **Lo stato del dubbio** (E-11, decisione D3a della Tappa 7, 07/10/2026):
#: la scrittura e' partita e non si sa se Home Assistant l'abbia fatta. Non
#: e' `rifiutata` -- puo' essere arrivata -- e non e' `applicata` -- puo' non
#: esserlo. Nasce in due posti: l'officina, quando dopo un silenzio della
#: scrittura nemmeno la rilettura dell'oggetto risponde (`Workshop.apply`), e
#: `risana`, all'avvio, per una riga rimasta `in_corso`. Una riga cosi' **non
#: si pota** (`CONSERVAZIONE`): puo' portare l'unico «prima» rimasto al mondo.
#: Il nome e' il minimo, al femminile come gli altri stati della costruzione;
#: il vocabolario unico degli stati e' della Tappa 8, che non ne ha ancora
#: uno per questo caso (piano della Tappa 8, D4, letto il 07/10/2026).
UNCERTAIN = "incerta"

#: Il motivo di una riga rimasta `in_corso` a un riavvio (`risana`). Una
#: costante perche' la legge anche `_migration_6`, che porta a `incerta` le
#: righe che `risana` segnava `rifiutata` fino al 07/10/2026.
REASON_RESTARTED = ("l’add-on si e' riavviato mentre la stavo applicando: non so "
                    "se la scrittura sia arrivata a Home Assistant.")

#: I giorni dopo cui una proposta si pota: una costante perche' li dichiarano
#: due tabelle, la proposta e i suoi avvisi, che la seguono.
_RETENTION_DAYS = 90

#: **Per quanto si tiene una proposta, e i suoi avvisi** (spec §7), nella
#: forma di ogni archivio (`storage.Retention`).
#:
#: Le righe vecchie se ne vanno -- **tranne l'ultima applicata di ogni
#: oggetto**, che e' l'unica copia del «prima» rimasta al mondo, **e le
#: `incerta`** (E-11, D3a): di una scrittura che forse e' arrivata, il «prima»
#: puo' essere l'unica copia anche lui. E' l'unica operazione irreversibile
#: del modulo: il lavoro notturno (`conservazione.nightly`) scrive nel
#: registro quante righe ha tolto, cosi' una regressione nella soglia o nella
#: chiave di partizione lascia una traccia invece di sparire in silenzio.
#:
#: Fino alla Tappa 8 (D5) la potatura girava a ogni proposta nuova.
CONSERVAZIONE: Retention = {
    "costruzioni": (
        _RETENTION_DAYS,
        ("le proposte di costruzione e le versioni: la pagina Costruzioni le "
         "mostra, e «Rimetti com'era» rilegge il «prima»; l'ultima applicata "
         "di ogni oggetto e le incerte restano, perche' portano l'unico «prima» "
         "rimasto"),
        ("DELETE FROM costruzioni WHERE creata_ts < ? "
         f"AND stato != '{UNCERTAIN}' AND id NOT IN ("
         "  SELECT id FROM ("
         "    SELECT id, ROW_NUMBER() OVER ("
         "      PARTITION BY dominio, chiave ORDER BY creata_ts DESC) AS rn"
         "    FROM costruzioni WHERE stato='applicata'"
         "  ) WHERE rn = 1)")),
    "avvisi": (
        _RETENTION_DAYS,
        ("gli avvisi seguono la loro proposta: una riga senza proposta non "
         "dice piu' niente a nessuno"),
        "DELETE FROM avvisi WHERE proposta_id NOT IN (SELECT id FROM costruzioni)"),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS costruzioni (
    id TEXT PRIMARY KEY,
    creata_ts REAL NOT NULL,
    aggiornata_ts REAL NOT NULL,
    stato TEXT NOT NULL,
    gesto TEXT NOT NULL,
    dominio TEXT NOT NULL,
    chiave TEXT NOT NULL,
    origine TEXT NOT NULL,
    turno TEXT,
    frase TEXT,
    prima_json TEXT,
    dopo_json TEXT,
    helper_json TEXT,
    anteprima TEXT,
    esecuzione_id TEXT,
    motivo TEXT,
    -- Il FILO di chi ha proposto (fetta «le chat divise», Task 7, spec §5
    -- "confirm e' del filo"): (soggetto, ingresso) di chi ha aperto il turno
    -- che ha chiamato `propose`. NULL per le proposte nate prima di questa
    -- versione, o da un attore senza filo (l'attuatore, un ripristino
    -- interno): quelle restano confermabili per id come oggi, e nessuna
    -- riga con questa colonna vuota entra mai nella scelta implicita di un
    -- filo (vedi `Workshop._only_pending`).
    subject_key TEXT,
    entry_point TEXT,
    -- Il LIVELLO della proposta (attori, strato 4, D13): banale, lieve,
    -- medio o alto (`stakes.STAKES`), scritto quando la proposta nasce.
    -- NULL quando nessuno l'ha detto e il codice non aveva niente da
    -- imporre, e per le righe nate prima del 06/10/2026: e' vero, non
    -- l'hanno mai avuto (vedi `_migration_4`).
    stakes TEXT,
    -- L'IMPRONTA e la PROVA della domanda dell'analista a cui la proposta
    -- risponde (`mind/analyst.observation_key`, `evidence_of`), quando l'ha
    -- costruita il proponente. NULL per quelle della chat e per i
    -- ripristini: non rispondono a nessuna domanda. Servono
    -- all'anti-ripetizione (`decided_proposals`), come le stesse colonne di
    -- `proposte`.
    impronta TEXT,
    prova_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_costruzioni_stato ON costruzioni(stato, creata_ts DESC);
CREATE INDEX IF NOT EXISTS idx_costruzioni_oggetto ON costruzioni(dominio, chiave, creata_ts DESC);
-- L'AVVISO agli amministratori per una proposta `alto` (attori, strato 4,
-- Task 4.3, D14): una riga quando almeno una push e' arrivata. Finche' manca,
-- il giro del proponente ritenta (scelta del proprietario, 06/10/2026,
-- «Ritenta»); smette quando la proposta non e' piu' in attesa -- decisa o
-- scaduta, un fatto della proposta e non un numero di tentativi. Una tabella
-- a parte, legata per id, e non una colonna: questo schema si esegue a ogni
-- apertura, quindi nasce anche negli archivi esistenti, senza gradino di
-- versione.
CREATE TABLE IF NOT EXISTS avvisi (
    proposta_id TEXT PRIMARY KEY,
    avvisata_ts REAL NOT NULL
);
"""


def _migration_2(conn) -> None:
    """v1 -> v2 (fetta «le chat divise», Task 7): il filo della proposta.

    `ALTER TABLE` solo se la colonna manca -- un archivio che nasce oggi la
    porta gia' da `_SCHEMA` (stesso pattern di `chat_store.py::_migration_4`
    e `reasoning/queue.py::_migration_3`). **Nessun indice qui**: a
    differenza di `chat_sessions`/`reasoning_jobs`, le costruzioni non hanno
    un volume che lo giustifichi -- il tetto e' 20 pendenti, e le due query
    che leggono il filo (`_only_pending`, il controllo per id) gia' passano
    da `list(pending_only=True)`/`read`, che restano su `stato`/`id`."""
    add_missing_columns(conn, "costruzioni",
                        {"subject_key": "TEXT", "entry_point": "TEXT"})


def _migration_3(conn) -> None:
    """v2 -> v3 (fetta "il seguito delle chat divise", Task 5, fix round 1,
    26/09/2026 -- RULING del controllore: nessun lettore di produzione legge
    il testo legacy, quindi si migra invece di tenere una seconda costante a
    runtime che nessuno usa).

    Il "no" scritto da `mark_cancelled` cambiava testo da «rifiutata dal
    proprietario» a `REASON_DISDETTA` ("rifiutata dalla pagina"): un
    proprietario solo non e' piu' vero (spec 2026-09-26 §3). Le righe
    scritte PRIMA di questa versione portano ancora il vecchio letterale sul
    disco -- e qui si riscrivono UNA volta sola, invece di lasciarle
    diverse per sempre. Il vecchio testo vive SOLO qui, con la sua data e la
    sua ragione: nessun'altra riga del modulo lo nomina piu'.

    Doppia guardia (`stato='disdetta' AND motivo=?`) perche' e' un'UPDATE
    sui DATI, non sullo schema: tocca solo le righe che portano ESATTAMENTE
    il vecchio testo, mai una `rifiutata`/`applicata` che porta un motivo
    diverso per un'altra ragione."""
    conn.execute(
        "UPDATE costruzioni SET motivo=? WHERE stato='disdetta' AND motivo=?",
        (REASON_DISDETTA, "rifiutata dal proprietario"))


def _migration_4(conn) -> None:
    """v3 -> v4 (attori, strato 4, Task 4.3): il livello della proposta.

    Le righe scritte prima rileggono `None`, e non si riempiono: calcolare
    oggi il livello di una proposta di ieri le attribuirebbe un fatto che
    allora non c'era, e nessuno di quei si' e' stato chiesto con un livello.
    """
    add_missing_columns(conn, "costruzioni", {"stakes": "TEXT"})


def _migration_5(conn) -> None:
    """v4 -> v5 (revisione indipendente, giro 24, D24-2): impronta e prova
    della domanda a cui la proposta risponde.

    Fino al 06/10/2026 una proposta costruita dal cervello non lasciava
    l'impronta da nessuna parte, e la stessa domanda con la stessa prova
    tornava all'officina a ogni giro (misurato dal revisore: tre giri, tre
    bozze). Le righe scritte prima rileggono `None`: quale domanda le abbia
    fatte nascere non e' scritto da nessuna parte, e non si indovina.
    """
    add_missing_columns(conn, "costruzioni",
                        {"impronta": "TEXT", "prova_json": "TEXT"})


def _migration_6(conn) -> None:
    """v5 -> v6 (Tappa 7, Task 3, E-11): il dubbio ha il suo stato.

    Fino al 07/10/2026 `risana` chiudeva `rifiutata` una riga rimasta
    `in_corso` a un riavvio, pur scrivendo nel motivo «non so se la
    scrittura sia arrivata»: e la potatura, che protegge solo l'ultima
    `applicata`, poteva poi cancellare l'unico «prima» di un oggetto che Home
    Assistant aveva forse gia' cambiato. Le righe che portano ESATTAMENTE
    quel motivo passano a `incerta`; nessun'altra `rifiutata` si tocca."""
    conn.execute(
        "UPDATE costruzioni SET stato=? WHERE stato='rifiutata' AND motivo=?",
        (UNCERTAIN, REASON_RESTARTED))


def _load(text):
    return None if text is None else json.loads(text)


# L'estrattore dei servizi vive nell'officina, accanto all'anteprima che
# gia' lo usa: due cammini sullo stesso corpo divergerebbero.
from .workshop import services_named


def _row(r) -> dict:
    """Una riga com'e' **adesso**: `scaduta_ora` (calcolata da `read` e
    `list` con `_EXPIRED_SQL`) la legge scaduta anche quando nessuno l'ha
    ancora segnata. Una lettura non scrive."""
    expired = bool(r["scaduta_ora"])
    return {
        "id": r["id"],
        "creata_ts": r["creata_ts"],
        "aggiornata_ts": r["aggiornata_ts"],
        "stato": "scaduta" if expired else r["stato"],
        "gesto": r["gesto"],
        "dominio": r["dominio"],
        "chiave": r["chiave"],
        "origine": r["origine"],
        "turno": r["turno"],
        "frase": r["frase"],
        # Il FILO di chi ha proposto (spec §5), come `ChatThread` -- la stessa
        # forma che la coda espone (`reasoning/queue.py::_row`): un filo solo
        # fra le porte, non due campi piatti che ogni lettore ricompone a
        # modo suo. `None` per una riga nata senza filo (vedi `_SCHEMA`).
        "thread": thread_from_columns(r["subject_key"], r["entry_point"]),
        "prima": _load(r["prima_json"]),
        "dopo": _load(r["dopo_json"]),
        # **Cosa chiamera'**, sui due lati (reperto B-4, 22/09/2026). La
        # pagina ha gia' i corpi interi e potrebbe camminarli in JavaScript:
        # sarebbe lo stesso cammino scritto due volte, in due linguaggi,
        # libero di divergere -- e a divergere sarebbe quello che nessuno
        # riesegue. L'estrattore resta uno, e la pagina riceve la risposta.
        #
        # DUE lati e non uno, perche' cio' che serve al proprietario e' cosa
        # CAMBIA: una lista sola non lo direbbe. E un lato assente da una
        # lista vuota, non `None`: una creazione non ha un «prima», e un buco
        # costringerebbe la pagina a un ramo in piu' per dire la stessa cosa.
        "chiama_prima": services_named(_load(r["prima_json"])),
        "chiama_dopo": services_named(_load(r["dopo_json"])),
        "helper": _load(r["helper_json"]) or [],
        "anteprima": r["anteprima"],
        "esecuzione_id": r["esecuzione_id"],
        "motivo": REASON_EXPIRED if expired else r["motivo"],
        "livello": r["stakes"],
        # La stessa coppia, con gli stessi nomi, delle proposte da fare a
        # mano (`mind/store.proposals`): le due code, una forma.
        "impronta": r["impronta"],
        "prova": _load(r["prova_json"]),
    }


class ConstructionStore:
    """L'unica casa delle proposte e delle versioni. Non parla con Home Assistant."""

    # Tetti dichiarati (spec §7). Non sono opzioni: un numero che l'utente puo'
    # cambiare e' un secondo comportamento da mantenere.
    MAX_PENDING = 20
    DEADLINE_S = 7 * 86400
    CONSERVAZIONE = CONSERVAZIONE

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self.archive_name = archive_name(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=6,
                   migrations={2: _migration_2, 3: _migration_3, 4: _migration_4,
                               5: _migration_5, 6: _migration_6})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def rekey_subjects(self, renames: dict[str, str]) -> int:
        """Le costruzioni dei soggetti di `renames` (chiave vecchia -> nuova)
        passano alla chiave nuova; ritorna quante. CHI cambia chiave lo decide
        `servizi.migrate_service_threads` (G83-3, 07/10/2026): con la chiave
        vecchia una costruzione chiesta da un servizio perdeva il nome di chi
        l'aveva chiesta (`soffitto.subject_name` cerca per impronta), e il
        servizio non la ritrovava nel suo filo."""
        with self._lock:
            return rekey(self._conn, "UPDATE costruzioni SET subject_key = ? "
                                     "WHERE subject_key = ?", renames)

    def propose(self, *, operation: str, domain: str, key: str, actor: str,
                exchange: str | None, phrase: str | None, prima: dict | None,
                dopo: dict | None, helper: list, preview: str,
                stakes: str | None, now: float,
                thread: ChatThread | None = None) -> dict:
        ident = secrets.token_urlsafe(9)
        with self._lock:
            # Le scadute si segnano qui, dove si scrive comunque, e si
            # contano fuori dal tetto: e' l'unico punto che le scrive sul
            # disco. Chi legge non lo aspetta (`_EXPIRED_SQL`).
            self._scadi(now)
            # `stato IN (STATES_SOSPESO)`, non solo `in_attesa`: una proposta
            # rivendicata (`in_corso`) e' ancora in sospeso, e deve continuare
            # a occupare un posto sotto il tetto -- se contasse solo
            # `in_attesa`, due `apply` in corsa potrebbero far salire il
            # numero vero di proposte in volo oltre il tetto nella finestra
            # fra `claim` e la transizione finale.
            aperte = self._conn.execute(
                f"SELECT count(*) FROM costruzioni WHERE stato IN ({_SOSPESI_SQL})").fetchone()[0]
            if aperte >= self.MAX_PENDING:
                return {"errore": (f"ci sono gia' {aperte} proposte in attesa (il tetto e' "
                                   f"{self.MAX_PENDING}): decidi quelle prima di farne altre.")}
            self._conn.execute(
                "INSERT INTO costruzioni(id,creata_ts,aggiornata_ts,stato,gesto,dominio,"
                "chiave,origine,turno,frase,prima_json,dopo_json,helper_json,anteprima,"
                "esecuzione_id,motivo,subject_key,entry_point,stakes) "
                "VALUES(?,?,?,'in_attesa',?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?,?)",
                (ident, now, now, operation, domain, key, actor, exchange, phrase,
                 None if prima is None else json.dumps(prima),
                 None if dopo is None else json.dumps(dopo),
                 json.dumps(list(helper)), preview,
                 *thread_params(thread), stakes))
            self._conn.commit()
        return {"id": ident}

    def read(self, ident: str, *, now: float) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                f"SELECT *, {_EXPIRED_SQL} AS scaduta_ora FROM costruzioni WHERE id=?",
                (now - self.DEADLINE_S, ident)).fetchone()
        return None if r is None else _row(r)

    def list(self, *, now: float, pending_only: bool = False,
             limit: int = 200) -> list[dict]:
        """`pending_only=True` elenca le pendenti -- `stato IN
        (STATES_SOSPESO)`, non solo `in_attesa`: una proposta rivendicata
        (`in_corso`) non e' ancora conclusa, e non deve sparire dall'elenco
        nella finestra fra `claim` e la transizione finale. Le scadute non
        sono pendenti, segnate o no."""
        cutoff = now - self.DEADLINE_S
        sql = f"SELECT *, {_EXPIRED_SQL} AS scaduta_ora FROM costruzioni"
        params: tuple = (cutoff,)
        if pending_only:
            sql += f" WHERE stato IN ({_SOSPESI_SQL}) AND NOT {_EXPIRED_SQL}"
            params += (cutoff,)
        sql += " ORDER BY creata_ts DESC LIMIT ?"
        with self._lock:
            righe = self._conn.execute(sql, params + (int(limit),)).fetchall()
        return [_row(r) for r in righe]

    def proposed_in(self, exchange: str | None, *, actor: str) -> frozenset[str]:
        """Gli id delle proposte che `actor` ha fatto nel turno `exchange`.

        E' come il proponente sa quali proposte sono nate nel suo turno
        (attori, Task 4.2, D12): lo dice l'archivio, che le ha scritte col
        turno accanto, non il modello -- che cosi' non puo' dichiarare una
        proposta che non c'e'. Senza turno, nessuna."""
        if not exchange:
            return frozenset()
        with self._lock:
            righe = self._conn.execute(
                "SELECT id FROM costruzioni WHERE turno=? AND origine=?",
                (exchange, actor)).fetchall()
        return frozenset(r["id"] for r in righe)

    def answers(self, ident: str, *, actor: str, fingerprint: str,
                prova: dict) -> bool:
        """Scrive sulla riga `ident` l'impronta e la prova della domanda a cui
        risponde (D24-2). Torna se ha toccato una riga.

        La scrive il giro del proponente dopo il turno, quando il modello dice
        per quale osservazione l'ha costruita: `propose` e' lo strumento della
        chat, e dentro il turno non sa per quale domanda compone. Solo su una
        riga di `actor` ancora senza impronta: una domanda gia' legata non si
        riscrive.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET impronta=?, prova_json=? "
                "WHERE id=? AND origine=? AND impronta IS NULL",
                (fingerprint, json.dumps(prova), ident, actor))
            self._conn.commit()
        return cur.rowcount > 0

    def unbound(self, *, actor: str, now: float) -> list[dict]:
        """Le proposte di `actor` che aspettano una risposta e non sono legate
        a nessuna domanda (`impronta` vuota).

        Per il proponente sono le costruite di un turno la cui risposta non le
        ha citate (rifiutata o troncata, revisione giro 61): senza impronta
        l'anti-ripetizione non le vede, e al giro dopo la stessa domanda
        farebbe nascere una seconda bozza accanto alla prima. Il giro le
        rimostra al modello, che puo' citarle invece di rifarle. Non scrive.
        """
        cutoff = now - self.DEADLINE_S
        with self._lock:
            righe = self._conn.execute(
                f"SELECT *, {_EXPIRED_SQL} AS scaduta_ora FROM costruzioni "
                f"WHERE origine=? AND impronta IS NULL AND stato IN ({_SOSPESI_SQL}) "
                f"AND NOT {_EXPIRED_SQL} ORDER BY creata_ts",
                (cutoff, actor, cutoff)).fetchall()
        return [_row(r) for r in righe]

    def decided_proposals(self, *, now: float) -> dict[str, dict]:
        """`{impronta: {"prova", "aperta", "creata_ts", "id", "a_mano"}}` per
        le proposte che rispondono a una domanda del cervello: la stessa forma
        di `mind/store.ObservationsStore.decided_proposals`, con cui il
        proponente la fonde (`proposer_turn.latest_decided`).

        Per ogni impronta conta l'ultima. `aperta` e' «aspetta ancora una
        risposta»: sospesa e non scaduta, come la conta `count_pending`.
        """
        with self._lock:
            rows = self._conn.execute(
                f"SELECT impronta, prova_json, creata_ts, stato IN ({_SOSPESI_SQL}) "
                f"AND NOT {_EXPIRED_SQL}, id FROM costruzioni WHERE impronta IS NOT NULL "
                "ORDER BY creata_ts, rowid", (now - self.DEADLINE_S,)).fetchall()
        return {r[0]: {"prova": _load(r[1]), "aperta": bool(r[3]), "creata_ts": r[2],
                       "id": r[4], "a_mano": False}
                for r in rows}

    def to_alert(self, *, actor: str, stakes: str, now: float) -> list[dict]:
        """Le proposte di `actor` a livello `stakes` ancora in attesa e mai
        avvisate (D14). Non scaduta con `_EXPIRED_SQL`: una proposta scaduta
        che nessuno ha ancora segnato non chiede piu' niente a nessuno. La
        colonna `scaduta_ora` e' la forma con cui `_row` legge le righe. Non
        scrive."""
        cutoff = now - self.DEADLINE_S
        with self._lock:
            righe = self._conn.execute(
                f"SELECT *, {_EXPIRED_SQL} AS scaduta_ora FROM costruzioni "
                f"WHERE origine=? AND stakes=? AND stato='in_attesa' "
                f"AND NOT {_EXPIRED_SQL} "
                "AND id NOT IN (SELECT proposta_id FROM avvisi) "
                "ORDER BY creata_ts",
                (cutoff, actor, stakes, cutoff)).fetchall()
        return [_row(r) for r in righe]

    def mark_alerted(self, ident: str, *, now: float) -> None:
        """L'avviso per `ident` e' arrivato: non si ritenta piu'."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO avvisi(proposta_id, avvisata_ts) VALUES(?,?)",
                (ident, now))
            self._conn.commit()

    def count_pending(self, *, now: float) -> int:
        """Quante proposte aspettano una risposta di chi costruisce.

        Qui il pallino conta i sospesi e sugli Impegni no
        (`keeper/store.py::count_unread`), e non e' un'incoerenza: una
        proposta in attesa aspetta letteralmente chi costruisce -- senza il
        suo si' non succede niente -- mentre un impegno in sospeso aspetta
        l'ora.

        `in_corso` conta: rivendicata non vuol dire decisa, ed e' la stessa
        ragione per cui `propose` guarda `STATES_SOSPESO` e non il solo
        `in_attesa`.

        Non scrive, e non puo' ignorare la scadenza (review indipendente
        della fetta, rilievo 6): una proposta lasciata scadere senza che
        nessuno la segni resterebbe `in_attesa` sul disco, e il pallino
        direbbe «1 in attesa» mandando chi costruisce in una pagina vuota.
        Per questo conta con `_EXPIRED_SQL`, come la pagina elenca.

        `in_corso` non ha scadenza: e' rivendicata, qualcuno ci sta gia'
        lavorando -- e infatti `_EXPIRED_SQL` guarda solo `in_attesa`.
        """
        with self._lock:
            return self._conn.execute(
                f"SELECT count(*) FROM costruzioni WHERE stato IN ({_SOSPESI_SQL}) "
                f"AND NOT {_EXPIRED_SQL}",
                (now - self.DEADLINE_S,)).fetchone()[0]

    def claim(self, ident: str, *, now: float) -> dict:
        """Prende in carico una proposta PRIMA di scrivere su Home Assistant
        (spec §7).

        E' la stessa guardia gia' usata per le promesse in
        `keeper/store.py`: una UPDATE atomica `WHERE stato=
        'in_attesa'` e' l'UNICO punto in cui due conferme quasi simultanee
        della stessa proposta si possono distinguere. Chi la chiama per primo
        vince e la proposta passa a `in_corso`; l'altro trova `rowcount == 0`
        e deve fermarsi PRIMA di scrivere -- un controllo fatto leggendo lo
        stato con `read()` non basta, perche' quella lettura e' gia' stantia
        nel momento stesso in cui la si confronta con una richiesta
        concorrente.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato='in_corso', aggiornata_ts=? "
                f"WHERE id=? AND stato='in_attesa' AND NOT {_EXPIRED_SQL}",
                (now, ident, now - self.DEADLINE_S))
            self._conn.commit()
        if cur.rowcount == 0:
            return {"errore": "quella proposta non e' piu' in attesa"}
        return {"id": ident, "stato": "in_corso"}

    def risana(self, *, now: float) -> int:
        """Le proposte rimaste `in_corso` al riavvio: chiuse, non ripescate.

        Stessa forma di `AgendaStore.risana` (`keeper/store.py`):
        una riga `in_corso` all'avvio significa una cosa sola, l'add-on si e'
        fermato fra `claim` e la transizione finale (`apply` non ha
        fatto in tempo a chiamare `mark_applied` o `mark_rejected`).

        **Senza questa chiusura la riga resterebbe un fantasma per sempre**:
        con `claim` a farla uscire da `in_attesa`, nessun altro percorso
        del modulo la riporta a uno stato terminale -- non `_scadi` (filtra
        su `stato='in_attesa'`), non un secondo `claim` (la sua UPDATE e'
        anch'essa `WHERE stato='in_attesa'`), non l'utente (ogni `apply`
        successiva la troverebbe gia' "in corso" e rifiuterebbe). Invisibile
        a `list(pending_only=True)` PRIMA di questa correzione, non piu'
        adesso che quella query legge `STATES_SOSPESO` -- ma restare `in_corso`
        per sempre resterebbe comunque un fantasma: mai scaduta, sempre
        contata contro il tetto, cancellata in silenzio dalla potatura dopo
        novanta giorni senza che nessuno abbia mai saputo com'e' andata.

        **Non si riprova a scrivere.** Dopo un riavvio a meta' non sappiamo
        se Home Assistant abbia gia' ricevuto la scrittura: ripeterla
        rischierebbe un doppione, non ripeterla rischierebbe di perdere una
        modifica riuscita -- e indovinare in una direzione o nell'altra
        sarebbe peggio che dirlo. Si dichiara **l'incertezza**, non un esito.

        Va chiamata all'avvio (dal Task 8, che monta l'officina), PRIMA che
        una nuova `apply` possa rivendicare qualcosa.

        **Lo stato e' `incerta`** (`UNCERTAIN`, E-11, 07/10/2026), lo stesso
        che l'officina da' al dubbio vero dopo una scrittura: fino a quel
        giorno qui si scriveva `rifiutata` accanto a «non so», e la potatura
        poteva cancellare il «prima» di una scrittura forse arrivata. Il
        motivo resta in questa riga (`REASON_RESTARTED`): al riavvio non c'e'
        nessuna cronaca da citare, perche' nessun tentativo si e' concluso.

        Restituisce quante righe ha chiuso.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato=?, aggiornata_ts=?, motivo=? "
                "WHERE stato='in_corso'",
                (UNCERTAIN, now, REASON_RESTARTED))
            self._conn.commit()
            count = cur.rowcount
        if count:
            logger.warning("costruzioni: %d proposte erano in_corso all'avvio, "
                           "risanate a %s (non riprovate)", count, UNCERTAIN)
        return count

    def mark_applied(self, ident: str, *, now: float,
                        execution_id: str | None) -> dict:
        return self._change_state(ident, "applicata", now, execution_id, None)

    def mark_rejected(self, ident: str, *, now: float,
                      execution_id: str | None) -> dict:
        """La scrittura non e' stata fatta. **Il motivo non si copia qui**
        (D-26, Tappa 7, Task 3, 07/10/2026): vive nella cronaca, e la riga lo
        cita per `esecuzione_id` -- fino a quel giorno lo stesso testo stava
        in `costruzioni.motivo` e in `esecuzioni.errore`, due archivi dello
        stesso esito. Chi mostra la riga lo legge dalla cronaca
        (`handlers_constructions._out`)."""
        return self._change_state(ident, "rifiutata", now, execution_id, None)

    def mark_uncertain(self, ident: str, *, now: float,
                       execution_id: str | None) -> dict:
        """Non si sa se la scrittura sia arrivata (`UNCERTAIN`, D3a): il
        motivo, come per `mark_rejected`, vive nella cronaca."""
        return self._change_state(ident, UNCERTAIN, now, execution_id, None)

    def mark_cancelled(self, ident: str, *, now: float) -> dict:
        """Il «no» di chi costruisce -- che NON e' un fallimento.

        `rifiutata` vuol dire che l'applicazione non e' andata a buon fine:
        validazione caduta, Home Assistant che rifiuta, una scrittura che
        rileggendo non c'e'. Quando non si sa se lo sia -- il riavvio a meta'
        (`risana`), il silenzio che nemmeno la rilettura scioglie -- lo stato
        e' `incerta` (`UNCERTAIN`, dal 07/10/2026). Questo e' l'altro
        caso, ed e' quello che vogliamo sia facile: la persona ha guardato la
        proposta e ha detto di no. Tenerli separati e' cio' che permette alla
        pagina di non colorare di rosso l'esercizio del controllo per cui
        l'intero giro in due tempi esiste. Stessa distinzione che lo
        schedulatore fa gia' fra `fallita` e `disdetta`, e stessa parola.

        **Transita SOLO da `in_attesa`** -- una `WHERE` dedicata, non quella
        (`IN ('in_attesa','in_corso')`) condivisa da `_change_state` (ondata
        finale, punto 2). L'invariante della potatura (`CONSERVAZIONE`) fu
        dimostrato quando la transizione `in_attesa -> applicata` era a senso
        unico: aggiungere `disdetta` sopra la `WHERE` di `_change_state`
        l'ha rotto in silenzio. La corsa che apriva: una conferma dalla chat
        rivendica la riga (`in_corso`) e comincia a scrivere su Home
        Assistant; nella stessa finestra un Rifiuta dalla pagina la porta a
        `disdetta` PRIMA che la scrittura torni. La scrittura arriva
        comunque a Home Assistant, `mark_applied` trova la riga gia'
        `disdetta` e fallisce -- ma l'automazione E' stata scritta davvero, e
        la riga che la descrive resta `disdetta`: FUORI dall'insieme protetto
        dalla potatura, quindi il suo «prima» -- l'unica copia esistente al
        mondo di com'era quell'oggetto -- diventa cancellabile a 90 giorni.
        Impedire la disdetta di una riga gia' rivendicata chiude la corsa
        alla radice: chi ha vinto la rivendicazione porta la transizione
        finale fino in fondo (`applicata`, `rifiutata` o `incerta`), e solo allora la
        riga torna leggibile come non piu' in sospeso.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato='disdetta', aggiornata_ts=?, motivo=? "
                f"WHERE id=? AND stato='in_attesa' AND NOT {_EXPIRED_SQL}",
                (now, REASON_DISDETTA, ident, now - self.DEADLINE_S))
            self._conn.commit()
        if cur.rowcount == 0:
            return {"errore": "quella proposta non e' piu' in attesa"}
        return {"id": ident, "stato": "disdetta"}

    def _change_state(self, ident: str, state: str, now: float,
                      execution_id: str | None, reason: str | None) -> dict:
        with self._lock:
            # `IN ('in_attesa','in_corso')`: la transizione finale arriva
            # quasi sempre da `in_corso` (dopo `claim`), ma resta valida
            # anche direttamente da `in_attesa` -- i chiamanti che non passano
            # da `claim` (i test di questo modulo, per esempio) devono
            # continuare a funzionare esattamente come prima. La UPDATE resta
            # atomica: e' cosi' che due conferme simultanee non applicano due
            # volte la stessa proposta. Stessa forma della presa in carico di
            # una promessa (`keeper/store.py`).
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato=?, aggiornata_ts=?, esecuzione_id=?, motivo=? "
                "WHERE id=? AND stato IN ('in_attesa','in_corso')",
                (state, now, execution_id, reason, ident))
            self._conn.commit()
        if cur.rowcount == 0:
            return {"errore": "quella proposta non e' piu' in attesa"}
        return {"id": ident, "stato": state}

    def _scadi(self, now: float) -> int:
        """Le proposte troppo vecchie si SEGNANO `scaduta`, sul disco.
        Restituisce quante. **Senza lock**: lo chiama `propose`, che il lock
        ce l'ha gia' in mano (`threading.Lock` non e' rientrante).

        Non si cancellano: sparire in silenzio renderebbe indistinguibile «e'
        scaduta» da «non l'ho mai proposta». Chi legge non aspetta questa
        scrittura: `read` e `list` le leggono scadute da sole.
        """
        cur = self._conn.execute(
            "UPDATE costruzioni SET stato='scaduta', aggiornata_ts=?, motivo=? "
            f"WHERE {_EXPIRED_SQL}",
            (now, REASON_EXPIRED, now - self.DEADLINE_S))
        self._conn.commit()
        return cur.rowcount

    def prune(self, now: float) -> int:
        """Applica `CONSERVAZIONE`; torna le proposte e gli avvisi tolti."""
        with self._lock:
            return prune_declared(self._conn, CONSERVAZIONE, now)
