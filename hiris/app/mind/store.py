"""L'archivio dell'osservatore: i cambi e gli oggetti.

**Due tabelle, due vite.** I cambi grezzi vivono 22 giorni; gli oggetti --
cio' che di quei cambi si e' capito -- restano finche' l'utente non li
cancella.

**Perche' 21 giorni e non una notte.** La proprieta' che rende buono lo schema
a due strati e' che sbagliare l'aggregazione costa un GIORNO, non tutto: finche'
il grezzo c'e', gli oggetti si rifanno. Ma il modo di costruirli cambiera' --
le prime settimane sono quelle in cui si sta ancora imparando -- e con una notte
sola ogni miglioramento varrebbe solo da domani. Ventuno giorni sono TRE
MERCOLEDI', l'unita' dell'esempio da cui nasce tutto il cervello.

**Perche' la soglia vera e' 22 e non 21.** Ventun giorni sono la promessa; il
ventiduesimo e' la guardia che la rende vera al bordo. Vedi il commento accanto
a `READING_RETENTION_S`.

**Perche' non e' il ritorno di `history.db`.** Quello scriveva e nessuno
leggeva, e l'avvio lo tratta ancora oggi come un residuo da rimuovere. La
differenza non e' di forma, e' di destino: quello nasceva senza lettore, questo
nasce col lettore -- l'analista e' la fetta successiva, e senza gli oggetti non
puo' esistere. **Se l'analista non venisse costruito, questo archivio va
cancellato**, non lasciato a scrivere: e' la stessa regola che ha condannato il
primo.
"""
from __future__ import annotations

import json
import threading

from ..storage import connect, init_schema

# 22 giorni, non 21: i 21 sono la promessa (tre mercoledi'), il 22esimo e' la
# guardia che la rende vera al bordo. Una soglia in secondi assoluti non
# allinea le mezzanotti locali: se la potatura gira alle 03:00, del giorno a
# -21 sopravvive solo cio' che e' successo dopo le 03:00; e nel weekend
# d'ottobre in cui l'ora torna indietro -- un giorno da 25 ore -- a cadere
# oltre la soglia sarebbe l'evento fondativo stesso, il mercoledi' alle
# 17:30. Il 22esimo giorno copre con margine l'ora dell'ora legale, senza far
# entrare il fuso orario nell'archivio.
READING_RETENTION_S = 22 * 86400


def _migration_2(conn) -> None:
    """v1 -> v2: il grezzo porta anche `device_class`, `state_class` e
    `source_type` (Task 3 del giro di correzioni: prima non c'erano, e mezzo
    pavimento -- energia, i rilevatori della sesta gamba -- non produceva
    mai un oggetto).

    **Non piu' "le tre classi che il pavimento legge"** (frase corretta dal
    mandato «il bilancio dell'energia», punto 4, 27/08/2026 -- falsa al
    presente: era vera ed era stata dichiarata fuori scope quando scritta
    il 26/08, la scelta giusta allora). Dopo la correzione del 27/08 sul
    traffico di rete (`pavimento.py::aspect`, il suo docstring), `pavimento.
    aspect()` legge solo `device_class` e `source_type` per decidere la
    gamba di `sensor` e `binary_sensor` -- `state_class` NON e' piu' fra i
    criteri. Resta comunque QUI, nel grezzo: non e' tolta dallo schema, e'
    `pavimento.aspect()` che ha smesso di leggerla per decidere la gamba, non
    `archivio.py` che smette di conservarla -- i 22 giorni di grezzo
    permettono di rifare il giudizio anche se un domani tornasse a servire.

    Tre colonne aggiunte, nessuna riscritta: le righe gia' in casa restano
    esattamente com'erano e diventano NULL sulle tre, che e' cio' che sono
    -- grezzo scritto prima che queste colonne esistessero. Una migrazione
    che ricostruisse la tabella per tre colonne rischierebbe di perdere
    settimane di osservazione per un guadagno estetico.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(cambi)")}
    for column in ("device_class", "state_class", "source_type"):
        if column not in existing:
            conn.execute(f"ALTER TABLE cambi ADD COLUMN {column} TEXT")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cambi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando_ts REAL NOT NULL,
    fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')),
    soggetto TEXT NOT NULL,
    da TEXT,
    a TEXT,
    device_class TEXT,
    state_class TEXT,
    source_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_cambi_quando ON cambi(quando_ts);
CREATE INDEX IF NOT EXISTS idx_cambi_soggetto ON cambi(soggetto, quando_ts);

CREATE TABLE IF NOT EXISTS oggetti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    giorno TEXT NOT NULL,
    genere TEXT NOT NULL,
    protagonista TEXT NOT NULL,
    inizio_ts REAL NOT NULL,
    fine_ts REAL,
    corpo_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oggetti_giorno ON oggetti(giorno, inizio_ts);
"""


def _reading_row(r) -> dict:
    return {"quando_ts": r["quando_ts"], "fonte": r["fonte"],
            "soggetto": r["soggetto"], "da": r["da"], "a": r["a"],
            "device_class": r["device_class"], "state_class": r["state_class"],
            "source_type": r["source_type"]}


def _fact_row(r) -> dict:
    return {"id": r["id"], "giorno": r["giorno"], "genere": r["genere"],
            "protagonista": r["protagonista"], "inizio_ts": r["inizio_ts"],
            "fine_ts": r["fine_ts"], "corpo": json.loads(r["corpo_json"])}


class ObservationsStore:
    """La memoria dell'osservatore. Il lock e' lo stesso delle scritture anche
    in lettura: la connessione e' condivisa fra thread (`check_same_thread=
    False`), ed e' il pattern gia' consolidato in `action/journal.py`."""

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=2, migrations={2: _migration_2})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- i cambi -------------------------------------------------------

    def record(self, *, quando_ts: float, source: str, subject: str,
               da, a, device_class: str | None = None,
               state_class: str | None = None,
               source_type: str | None = None) -> None:
        """Un cambio, cosi' com'e'. **Nessun giudizio in scrittura**: e' la
        condizione da cui dipende tutto il resto -- una decisione presa qui non
        si corregge piu', una presa in aggregazione si'.

        `fonte` e' vincolata a `'entita'` o `'sistema'` (CHECK di schema): un
        refuso dello scrittore futuro non deve entrare in silenzio.

        `device_class`, `state_class` e `source_type` sono le tre classi che
        Home Assistant dichiara sull'entita' -- **grezzo per definizione**, non
        un giudizio nostro: e' cio' che serve a `pavimento.aspect()` per
        decidere la gamba di `sensor` e `binary_sensor` quando l'aggregazione
        rilegge la riga, giorni dopo che l'evento e' passato. Tutti e tre
        annullabili: le condizioni di sistema non li portano, e una riga
        scritta prima che queste colonne esistessero li rilegge come `None`.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a,device_class,"
                "state_class,source_type) VALUES(?,?,?,?,?,?,?,?)",
                (float(quando_ts), source, subject,
                 None if da is None else str(da), None if a is None else str(a),
                 device_class, state_class, source_type))
            self._conn.commit()

    def readings(self, *, from_ts: float, to_ts: float, subject: str | None = None,
              source: str | None = None, limit: int = 200_000) -> list[dict]:
        """I cambi di una finestra, **dal piu' vecchio**.

        Al contrario della cronaca degli atti, che torna dal piu' recente:
        qui chi legge ricostruisce cose che cominciano e finiscono, e le vuole
        in ordine di accadimento.

        **La finestra e' semi-aperta: `[from_ts, to_ts)`** -- `from_ts` incluso,
        `to_ts` escluso. E' la convenzione che fa combaciare i giorni adiacenti
        senza sovrapporli: con due estremi inclusivi, un cambio esattamente a
        mezzanotte finirebbe contato in entrambi i giorni che lo interrogano.

        `fonte`, se dato, filtra **nella query SQL**, non dopo la lettura: chi
        chiede solo le condizioni di sistema (poche centinaia su 22 giorni,
        contro le ~320.000 di entita') non deve ne' pagarne il costo ne'
        rischiare che il `LIMIT` tagli via proprio le righe di sistema piu'
        recenti, seppellite dal volume delle altre.

        Il tetto e' alto apposta: misurato sulla casa vera, una giornata fa
        ~14.600 cambi, e l'aggregazione deve vederla intera.
        """
        sql = "SELECT * FROM cambi WHERE quando_ts >= ? AND quando_ts < ?"
        args: list = [float(from_ts), float(to_ts)]
        if subject is not None:
            sql += " AND soggetto = ?"
            args.append(subject)
        if source is not None:
            sql += " AND fonte = ?"
            args.append(source)
        sql += " ORDER BY quando_ts ASC, id ASC LIMIT ?"
        args.append(int(max(1, limit)))
        with self._lock:
            rows = self._conn.execute(sql, tuple(args)).fetchall()
        return [_reading_row(r) for r in rows]

    def prune(self, now_ts: float) -> int:
        """Butta i cambi oltre la conservazione. **Non tocca gli oggetti**: le
        due tabelle hanno due vite, e una potatura che si portasse via cio' che
        si e' capito cancellerebbe mesi per liberare qualche megabyte."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM cambi WHERE quando_ts < ?",
                                     (float(now_ts) - READING_RETENTION_S,))
            self._conn.commit()
            return cur.rowcount or 0

    # -- gli oggetti ---------------------------------------------------

    def facts(self, *, day: str | None = None, limit: int = 200) -> list[dict]:
        """Gli oggetti, dal piu' recente."""
        sql = "SELECT * FROM oggetti"
        args: list = []
        if day is not None:
            sql += " WHERE giorno = ?"
            args.append(day)
        sql += " ORDER BY inizio_ts DESC, id DESC LIMIT ?"
        args.append(int(max(1, limit)))
        with self._lock:
            rows = self._conn.execute(sql, tuple(args)).fetchall()
        return [_fact_row(r) for r in rows]

    # `salva_oggetto` (un INSERT nudo) e `dimentica_oggetti` (un DELETE nudo)
    # sono uscite qui (giro di correzioni, task-5-fix-brief.md punto 4):
    # nessun chiamante di produzione le usava -- `aggregate_day` scrive
    # SEMPRE attraverso `replace_day`, l'unica via transazionale, e i
    # mandati dei task 6 e 7 non le reclamano (cercato in tutto `hiris/`,
    # non solo nel cervello). Lasciarle accanto a quella transazionale era un
    # invito a usarle in sequenza -- ed e' esattamente il difetto che
    # `replace_day` esiste per chiudere: un crash fra un DELETE e
    # l'INSERT che lo segue lascia il giorno vuoto o mezzo scritto, e
    # nessuno se ne accorge finche' non serve rileggerlo. Se la
    # cancellazione utente della spec (§8, "dimentica un giorno") tornera'
    # a servire, si riscrivera' allora, con i suoi test e la sua
    # transazione.
    def replace_day(self, day: str, facts: list[dict]) -> int:
        """Rifa' un giorno per intero, in **una sola transazione**: cancella
        gli oggetti esistenti di `giorno` e inserisce quelli nuovi.

        E' la correzione al difetto che questo prodotto ha gia' pagato una
        volta -- nella fetta «costruire» il vecchio accodava invece di
        sostituire, e le ancore YAML lo nascondevano. Un INSERT nudo,
        ripetuto sullo stesso giorno, accoderebbe una seconda copia senza
        errore. E se lo svuotamento e il reinserimento fossero due commit
        separati, un crash a meta' lascia un giorno mezzo scritto,
        indistinguibile da uno completo.

        Se un inserimento fallisce (es. un dato che rompe un vincolo di
        schema), **l'intera transazione va indietro**: il giorno resta quello
        di prima, mai mezzo riscritto.

        Ogni elemento di `facts` e' un dict con le chiavi `genere`,
        `protagonista`, `inizio_ts`, `fine_ts`, `corpo` -- meno `giorno` che
        qui e' comune a tutti.
        """
        with self._lock:
            try:
                self._conn.execute("DELETE FROM oggetti WHERE giorno = ?", (day,))
                for o in facts:
                    self._conn.execute(
                        "INSERT INTO oggetti(giorno,genere,protagonista,inizio_ts,fine_ts,"
                        "corpo_json) VALUES(?,?,?,?,?,?)",
                        (day, o["genere"], o["protagonista"], float(o["inizio_ts"]),
                         None if o.get("fine_ts") is None else float(o["fine_ts"]),
                         json.dumps(o["corpo"], ensure_ascii=False)))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return len(facts)
