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
import time as _time

from ..storage import connect, init_schema
from .scope import may_overwrite

# 22 giorni, non 21: i 21 sono la promessa (tre mercoledi'), il 22esimo e' la
# guardia che la rende vera al bordo. Una soglia in secondi assoluti non
# allinea le mezzanotti locali: se la potatura gira alle 03:00, del giorno a
# -21 sopravvive solo cio' che e' successo dopo le 03:00; e nel weekend
# d'ottobre in cui l'ora torna indietro -- un giorno da 25 ore -- a cadere
# oltre la soglia sarebbe l'evento fondativo stesso, il mercoledi' alle
# 17:30. Il 22esimo giorno copre con margine l'ora dell'ora legale, senza far
# entrare il fuso orario nell'archivio.
READING_RETENTION_S = 22 * 86400


def _add_missing_columns(conn, columns: tuple[str, ...]) -> None:
    """Aggiunge a `cambi` le colonne di `columns` che non ci sono ancora --
    tutte di tipo `TEXT`, tutte nullable: e' la forma che condividono tutte
    le migrazioni di questo schema (vedi `_migration_2` e `_migration_3`),
    perche' non ce ne sia una seconda scritta a mano, un'altra strategia
    accanto a questa -- due migrazioni adiacenti con due meccanismi diversi
    sarebbero un invito al copia-incolla sbagliato la prossima volta.

    Il controllo su `PRAGMA table_info` (non un `try`/`except` attorno
    all'`ALTER`) e' la scelta deliberata: un `except sqlite3.OperationalError`
    inghiottirebbe QUALUNQUE errore dell'`ALTER`, non solo «la colonna c'e'
    gia'» -- anche un archivio bloccato o un disco pieno -- e la migrazione
    proseguirebbe come se fosse andata bene. `init_schema` stampa comunque
    `PRAGMA user_version` alla fine: un fallimento inghiottito lascerebbe
    l'archivio dichiarato alla versione nuova SENZA le colonne, e il primo
    `record` dopo fallirebbe per sempre -- l'osservatore smetterebbe di
    scrivere, esattamente il rischio che questa migrazione esiste per
    evitare.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(cambi)")}
    for column in columns:
        if column not in existing:
            conn.execute(f"ALTER TABLE cambi ADD COLUMN {column} TEXT")


def _migration_2(conn) -> None:
    """v1 -> v2: il grezzo porta anche `device_class`, `state_class` e
    `source_type` (Task 3 del giro di correzioni: prima non c'erano, e mezzo
    pavimento -- energia, i rilevatori della sesta gamba -- non produceva
    mai un oggetto).

    **Non piu' "le tre classi che il pavimento legge"** (frase corretta dal
    mandato «il bilancio dell'energia», punto 4, 27/08/2026 -- falsa al
    presente: era vera ed era stata dichiarata fuori scope quando scritta
    il 26/08, la scelta giusta allora). Dopo la correzione del 27/08 sul
    traffico di rete (`type_vocabulary.aspect_of`, il suo docstring), quella funzione
    legge solo `device_class` e `source_type` per decidere la
    gamba di `sensor` e `binary_sensor` -- `state_class` NON e' piu' fra i
    criteri. Resta comunque QUI, nel grezzo: non e' tolta dallo schema, e'
    `type_vocabulary.aspect_of()` che ha smesso di leggerla per decidere la gamba, non
    `store.py` che smette di conservarla -- i 22 giorni di grezzo
    permettono di rifare il giudizio anche se un domani tornasse a servire.

    Tre colonne aggiunte, nessuna riscritta: le righe gia' in casa restano
    esattamente com'erano e diventano NULL sulle tre, che e' cio' che sono
    -- grezzo scritto prima che queste colonne esistessero. Una migrazione
    che ricostruisse la tabella per tre colonne rischierebbe di perdere
    settimane di osservazione per un guadagno estetico.
    """
    _add_missing_columns(conn, ("device_class", "state_class", "source_type"))


def _migration_3(conn) -> None:
    """`CREATE TABLE IF NOT EXISTS` non tocca una tabella che esiste gia':
    senza queste due colonne il primo `record` dopo l'aggiornamento
    fallirebbe, e l'osservatore smetterebbe di scrivere.

    Le righe scritte prima rileggono `None` su entrambe -- e' vero: quelle
    righe quei fatti non li avevano.
    """
    _add_missing_columns(conn, ("domain", "title"))


def _migration_4(conn) -> None:
    """v3 -> v4: `first_occurred`, l'istante che Home Assistant dichiara per
    una voce del registro di errori (`system_log/list`, Task 2 di «le
    tracce e il log»).

    **Non e' `quando_ts`.** `quando_ts` resta l'istante della riga nella
    NOSTRA linea del tempo -- l'orologio del giro che l'ha scritta, come per
    ogni altra condizione di sistema -- perche' significhi la stessa cosa
    per ogni soggetto: farlo significare altro per un prefisso solo (l'idea
    iniziale di questo task) rompeva `aggregate_day`, che legge solo la
    finestra del giorno e ignora in silenzio una `chiuso` senza apertura nel
    giorno. Una nascita scritta oggi con l'istante che HA dichiara -- giorni
    prima, sulla casa vera, perche' HA tiene le voci dall'ultimo suo riavvio
    -- non veniva mai aggregata, e la sua chiusura futura cadeva nel vuoto:
    un difetto che sarebbe scattato al primo deploy di questa fetta.
    `first_occurred` porta quell'istante SENZA spostare `quando_ts`: chi
    legge l'oggetto potra' avere «rilevato stamattina, va avanti dal 2»
    invece di una data sola (vedi `facts.py::aggregate_day`, il ramo
    `guasto`).

    **Colonna a se', non dentro `title`**: e' un fatto di tipo diverso (un
    istante, non un'etichetta), e mischiarli costringerebbe chi legge a
    fare il parsing di una stringa composita.

    Le righe scritte prima -- ogni condizione di sistema che non e' una voce
    di log, e ogni voce di log scritta prima di questa colonna -- rileggono
    `None`: e' vero, quelle righe quell'istante non lo portavano (o non
    esistono per un soggetto che non lo dichiara mai, un *repair* o
    un'integrazione).
    """
    _add_missing_columns(conn, ("first_occurred",))


def _migration_5(conn) -> None:
    """v4 -> v5: `friendly_name`, il nome che Home Assistant ha gia' composto
    per l'entita' al momento del cambio (fetta «il nome», 07/09/2026).

    **Perche' si SALVA e non si risolve dopo dall'anagrafe.** E' parola per
    parola la ragione gia' scritta accanto a `domain`/`title` nello schema
    qui sotto: fra tre settimane quell'entita' potrebbe non esistere piu', e
    la riga deve dire ancora di CHE COSA si parlava. E c'e' un secondo
    motivo, proprio di questa colonna: le due tabelle hanno due vite -- i
    `cambi` vivono 22 giorni, gli `oggetti` finche' l'utente non li cancella.
    Un oggetto di sei mesi fa su un'entita' sostituita non avrebbe NESSUN
    nome da risolvere, e la riga tornerebbe all'`entity_id` grezzo: il
    difetto che questa fetta chiude ricrescerebbe da solo, un pezzo alla
    volta, senza che nessuno se ne accorga.

    **Non e' ricomposto da noi.** E' `attributes.friendly_name` dello
    specchio dello stato, cioe' la stringa che HA ha GIA' composto con la
    sua precedenza (`homeassistant/helpers/entity.py:1161` ->
    `entity_registry.py:592-603` @ `2026.9.1`: il nome scritto dall'utente,
    altrimenti nome del dispositivo + nome dell'entita', altrimenti niente
    attributo affatto). Ricomporla vorrebbe dire riscrivere otto righe di
    logica altrui e divergere alla prima versione di HA che le cambia.

    Le righe scritte prima rileggono `None`, ed e' vero: quelle righe quel
    nome non lo portavano. **Non si riempiono a posteriori** dall'anagrafe
    di oggi -- sarebbe attribuire a ieri il nome di oggi, esattamente cio'
    che questa colonna esiste per non fare. Chi legge le rende dicendo che
    quello che mostra e' un identificatore (`static/config/watcher-route.js`,
    `describeWatchedSubject`), mai inventando un nome dall'id.
    """
    _add_missing_columns(conn, ("friendly_name",))


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
    source_type TEXT,
    -- Le colonne NUOVE si scrivono in inglese (decisione del proprietario,
    -- 04/09/2026). Le italiane qui sopra sono debito in attesa della fetta
    -- «il vocabolario del dato», non un modello da imitare.
    --
    -- Dominio e titolo della voce di configurazione: Home Assistant li manda
    -- e finora si buttavano. Stanno nel GREZZO e non si risolvono dopo
    -- dall'anagrafe, perche' fra tre settimane quella voce potrebbe non
    -- esistere piu' e la riga deve dire ancora cosa si era rotto.
    domain TEXT,
    title TEXT,
    -- L'istante che HA dichiara per una voce del registro di errori
    -- (Task 2, «le tracce e il log») -- SOLO per quelle: NULL per un
    -- repair o un'integrazione, che non lo dichiarano mai. Non e'
    -- `quando_ts` (vedi `_migration_4`): quello resta l'orologio del giro.
    first_occurred TEXT,
    -- Il nome che Home Assistant ha gia' composto per l'entita' al momento
    -- del cambio (`attributes.friendly_name` dello specchio dello stato).
    -- Sta nel GREZZO per la stessa ragione di `domain`/`title` qui sopra, e
    -- per una in piu' che vale solo per lui: gli `oggetti` vivono piu' a
    -- lungo dei `cambi`, quindi un nome risolto dopo su un oggetto vecchio
    -- non si troverebbe piu'. NULL per le condizioni di sistema (un
    -- `problema:`/`integrazione:`/`log:`/`automazione:` non e' un'entita' e
    -- non ne porta uno) e per le entita' su cui HA non scrive l'attributo.
    -- Vedi `_migration_5`.
    friendly_name TEXT
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

-- L'OBIETTIVO, con la sua storia. Vive qui e non in un archivio suo perche' e'
-- cio' che governa quel che l'osservatore raccoglie, e il resoconto giornaliero
-- dovra' mettere accanto a ogni giornata l'obiettivo che valeva allora: stesso
-- file, una query sola -- e `ATTACH` in questo prodotto non compare mai.
--
-- Si ACCODA, non si sostituisce: se l'obiettivo cambia, i resoconti scritti
-- prima rispondono a un'altra domanda, e chi legge trenta giorni di misure deve
-- saperlo o legge una tendenza dove c'e' un cambio di domanda (spec §11).
-- Colonne in inglese: tabella nuova (regola del 04/09/2026).
CREATE TABLE IF NOT EXISTS objective (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    written_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_objective_written ON objective(written_ts);

-- LO SCOPE: cosa si guarda, perche', e CHI l'ha deciso.
--
-- Una riga per soggetto, non una cronaca: la domanda che questa tabella deve
-- saper rispondere in fretta e' «questo soggetto lo guardo?», e la pone il
-- rubinetto degli eventi a ogni cambio di stato della casa. La storia di chi
-- ha cambiato idea la porta gia' `deciso_ts` insieme all'autore -- e cio' che
-- serve al proprietario («da quando guardo questa cosa») e' esattamente quello.
--
-- `author` non e' un dettaglio: senza, la decisione dell'analista non saprebbe
-- di essere una revisione di quella dell'osservatore, e verrebbe cancellata al
-- giro dopo da chi ha meno informazione (vedi `mind/scope.py`).
CREATE TABLE IF NOT EXISTS scope (
    subject TEXT PRIMARY KEY,
    inside INTEGER NOT NULL,
    reason TEXT NOT NULL,
    author TEXT NOT NULL,
    decided_ts REAL NOT NULL
);

-- LA RICONSIDERAZIONE: quando l'osservatore ha ripensato tutta la casa, e con
-- quale misura in mano.
--
-- Non basta «l'ho fatto il 9». La pagina deve poter dire **perche' ogni 84
-- ore**, e quel numero viene da una misura della memoria di Home Assistant
-- (`mind/cadence.py`) che cambia se il proprietario cambia il recorder:
-- scritta accanto alla riconsiderazione, resta vera per QUELLA
-- riconsiderazione anche quando la misura successiva dara' altro.
--
-- `window_s` e `cadence_s` ammettono NULL: la memoria puo' non essere
-- misurabile -- Home Assistant muto -- e l'osservatore gira lo stesso al primo
-- avvio. La riga si scrive con la misura mancante DICHIARATA, invece di non
-- scriverla: senza, la pagina direbbe «mai riconsiderato» di una casa appena
-- riconsiderata.
-- `reason` porta la CAUSA: quale delle quattro (primo avvio, obiettivo
-- cambiato, qualcosa di nuovo in casa, cadenza scaduta) ha fatto girare
-- l'osservatore quella volta. Senza, di una riconsiderazione resterebbe solo
-- una data, e la pagina non potrebbe dire «l'ultima e' stata il 9, perche'
-- era comparso un termostato nuovo».
--
-- **Nessuna migrazione, e si puo' verificare**: questa tabella e' nata in
-- questa stessa fetta e non e' mai stata rilasciata -- l'ultima versione
-- pubblicata (3.25.0) non la contiene affatto -- quindi non esiste nessun
-- archivio in cui manchi solo questa colonna.
CREATE TABLE IF NOT EXISTS reconsideration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    done_ts REAL NOT NULL,
    window_s REAL,
    cadence_s REAL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_reconsideration_done ON reconsideration(done_ts);

-- **Il tentativo, che non e' la riconsiderazione.** `reconsideration` conserva
-- i giri RIUSCITI: e' la cronaca di come la cadenza si e' adattata alla casa.
-- Un giro FALLITO non e' una riconsiderazione e non puo' finire li' dentro --
-- farebbe scadere la cadenza come se la casa fosse stata ripensata -- ma
-- nemmeno puo' sparire, e fino all'11/09/2026 spariva: la pagina dello scope
-- diceva «non e' mai stata fatta», vero alla lettera e falso come racconto.
--
-- Misurato sulla casa vera l'11/09/2026: l'osservatore ha provato e fallito
-- ogni dieci minuti per quaranta minuti, il cancello di `watch_reading` e' lo
-- scope e quindi HIRIS **non registrava piu' una riga sulla casa**, e nessuna
-- porta lo diceva. E' la distinzione a tre stati che questo prodotto difende
-- ovunque: **un guasto non si appiattisce su un'assenza.**
CREATE TABLE IF NOT EXISTS scope_attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tried_ts REAL NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN
        ('accodata', 'riuscito', 'non_riuscito', 'scaduta')),
    detail TEXT,
    version TEXT
);
CREATE INDEX IF NOT EXISTS idx_scope_attempt_tried ON scope_attempt(tried_ts);
"""

def _migration_6(conn) -> None:
    """v5 -> v6: `scope_attempt.version`, la versione di HIRIS su cui il
    tentativo e' avvenuto.

    **Un aggiornamento e' un fatto nuovo**, e senza questa colonna il freno che
    rallenta i tentativi (`server._retry_hold`) conta i fallimenti di una
    versione gia' riparata. Misurato l'11/09/2026: quattro fallimenti sulla
    3.27.0 hanno tenuto fermo l'osservatore per ottanta minuti DOPO
    l'aggiornamento alla 3.27.1, cioe' hanno ritardato la verifica della loro
    stessa riparazione.

    Le righe scritte prima rileggono `None`: e' vero, quella versione non
    l'hanno mai portata, e riempirla oggi attribuirebbe a ieri un fatto di
    adesso.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(scope_attempt)")}
    if "version" not in existing:
        conn.execute("ALTER TABLE scope_attempt ADD COLUMN version TEXT")


#: A che versione sta lo schema di questo archivio. Vive qui perche' chi lo
#: prova non debba ricopiarne il numero: un letterale in una prova e' un
#: doppione che mente al primo schema nuovo, e questa riga esiste perche' e'
#: successo (`test_migration_5...` inchiodava il 5).
SCHEMA_VERSION = 6

#: L'obiettivo di fabbrica, deciso dal proprietario il 25/08/2026. Non e' un
#: ripiego: e' il criterio con cui l'osservatore decide cosa guardare su una
#: casa appena installata, e senza di esso la domanda al modello non avrebbe
#: un rispetto-a-cosa. Un obiettivo vuoto sarebbe una manopola girata a zero,
#: non una manopola assente.
DEFAULT_OBJECTIVE = "ottimizzare la casa e renderla confortevole"

#: Quanti tentativi mostra la pagina. Abbastanza da distinguere «e' andata
#: male una volta» da «sta fallendo da un'ora» -- con un giro ogni dieci
#: minuti, dieci righe sono l'ultima ora e mezza -- e non tanti da far
#: diventare un elenco la risposta a «sta funzionando?».
ATTEMPTS_SHOWN = 10

#: I quattro esiti di un tentativo, e **vivono qui**. Il `CHECK` accanto alla
#: colonna e' il cancello: `cambi.fonte` ce l'ha da sempre, e senza, un refuso
#: in un `record_attempt` scriverebbe un esito che nessuna pagina sa rendere
#: -- e la pagina, prima della correzione della review indipendente
#: dell'11/09/2026, su un esito ignoto moriva del tutto.
ATTEMPT_QUEUED = "accodata"
ATTEMPT_DONE = "riuscito"
ATTEMPT_FAILED = "non_riuscito"
ATTEMPT_EXPIRED = "scaduta"
ATTEMPT_OUTCOMES = (ATTEMPT_QUEUED, ATTEMPT_DONE, ATTEMPT_FAILED, ATTEMPT_EXPIRED)


def _reading_row(r) -> dict:
    # `first_occurred` e' TEXT in colonna (stessa forma di `_add_missing_
    # columns`, vedi il suo docstring), ma e' un ISTANTE: si torna al
    # chiamante come `float | None`, non come la stringa grezza di SQLite --
    # e' l'unica delle colonne nuove per cui questo vale, perche' e' l'unica
    # numerica: `domain`/`title` sono gia' testo, nessuna conversione da fare.
    first_occurred = r["first_occurred"]
    return {"quando_ts": r["quando_ts"], "fonte": r["fonte"],
            "soggetto": r["soggetto"], "da": r["da"], "a": r["a"],
            "device_class": r["device_class"], "state_class": r["state_class"],
            "source_type": r["source_type"],
            "domain": r["domain"], "title": r["title"],
            "friendly_name": r["friendly_name"],
            "first_occurred": None if first_occurred is None else float(first_occurred)}


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
        init_schema(self._conn, _SCHEMA, version=SCHEMA_VERSION,
                    migrations={2: _migration_2, 3: _migration_3, 4: _migration_4,
                                5: _migration_5, 6: _migration_6})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- i cambi -------------------------------------------------------

    def record(self, *, quando_ts: float, source: str, subject: str,
               da, a, device_class: str | None = None,
               state_class: str | None = None,
               source_type: str | None = None,
               domain: str | None = None, title: str | None = None,
               friendly_name: str | None = None,
               first_occurred: float | None = None) -> None:
        """Un cambio, cosi' com'e'. **Nessun giudizio in scrittura**: e' la
        condizione da cui dipende tutto il resto -- una decisione presa qui non
        si corregge piu', una presa in aggregazione si'.

        `fonte` e' vincolata a `'entita'` o `'sistema'` (CHECK di schema): un
        refuso dello scrittore futuro non deve entrare in silenzio.

        `device_class`, `state_class` e `source_type` sono le tre classi che
        Home Assistant dichiara sull'entita' -- **grezzo per definizione**, non
        un giudizio nostro: e' cio' che serve a `type_vocabulary.aspect_of()` per
        decidere la gamba di `sensor` e `binary_sensor` quando l'aggregazione
        rilegge la riga, giorni dopo che l'evento e' passato. Tutti e tre
        annullabili: le condizioni di sistema non li portano, e una riga
        scritta prima che queste colonne esistessero li rilegge come `None`.

        `domain` e `title` sono dominio e titolo della voce di configurazione
        di una condizione di SISTEMA (`watcher.py::watch_system`) -- **grezzo
        anche loro**: stanno qui perche' fra tre settimane la voce potrebbe
        non esistere piu', e la riga deve dire ancora cosa si era rotto.
        Annullabili: le condizioni di entita' non li portano, e un `problema:`
        (un *repair* di Home Assistant) non ha un titolo -- `title=None` e'
        un campo vuoto dichiarato, non un buco.

        `friendly_name` e' il nome che Home Assistant ha GIA' composto per
        l'entita' al momento del cambio -- **grezzo anche lui**, e per la
        stessa ragione degli altri, piu' una che vale solo per lui: gli
        `oggetti` sopravvivono ai `cambi`, quindi un nome risolto dopo su un
        oggetto vecchio non si troverebbe piu' (vedi `_migration_5`).
        Annullabile: una condizione di sistema non e' un'entita' e non ne
        porta uno, e su un'entita' HA scrive l'attributo solo se il nome
        composto non e' vuoto (`helpers/entity.py:1166-1167` @ `2026.9.1`).
        `None` e' allora un campo vuoto dichiarato, e chi legge deve dire
        che sta mostrando un identificatore -- mai inventare un nome
        dall'`entity_id`.

        `first_occurred` e' l'istante che Home Assistant dichiara per una
        voce del registro di errori (`watcher.py::watch_system`, Task 2 di
        «le tracce e il log») -- **solo per quelle**: un *repair* o
        un'integrazione non lo dichiarano mai, e restano `None`, non zero.
        **Non e' `quando_ts`**: quello resta l'orologio del giro per OGNI
        soggetto, la stessa colonna che ha sempre significato la stessa cosa
        -- vedi `_migration_4` in questo stesso file per il perche' di questa
        separazione, scoperto contro `aggregate_day`.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a,device_class,"
                "state_class,source_type,domain,title,friendly_name,first_occurred) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (float(quando_ts), source, subject,
                 None if da is None else str(da), None if a is None else str(a),
                 device_class, state_class, source_type, domain, title, friendly_name,
                 None if first_occurred is None else str(float(first_occurred))))
            self._conn.commit()

    def readings_count(self, *, from_ts: float, to_ts: float,
                       source: str | None = None) -> int:
        """Quante righe grezze sono state scritte in questa finestra.

        **E' un numero del prodotto, non una diagnostica.** La spec dei tre
        attori promette **-83%** di grezzo -- da 29.227 a 4.951 righe al giorno,
        misurate sulla casa vera il 10/09/2026 -- e quella promessa e' la
        contropartita onesta dello scope: si guarda meno, e questo e' quanto
        costa cio' che si guarda. La pagina «cosa guardo e perche'» lo dice
        accanto all'elenco.

        **Si conta in SQL.** `readings()` qui sotto tronca a 200.000 righe:
        contare la lunghezza della lista che torna darebbe il numero giusto
        finche' il tetto non scatta, e uno sbagliato **in silenzio** proprio
        sulla giornata piu' rumorosa -- quella che si guarda per capire se il
        filtro funziona.

        Stessa finestra semi-aperta di `readings()`, `[from_ts, to_ts)`, per la
        stessa ragione: due estremi inclusivi conterebbero due volte il cambio
        di mezzanotte, e i giorni adiacenti non tornerebbero mai.
        """
        sql = "SELECT count(*) AS n FROM cambi WHERE quando_ts >= ? AND quando_ts < ?"
        args: list = [float(from_ts), float(to_ts)]
        if source is not None:
            sql += " AND fonte = ?"
            args.append(source)
        with self._lock:
            return int(self._conn.execute(sql, args).fetchone()["n"])

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

    def last_before(self, ts: float, *, source: str = "entita") -> list[dict]:
        """L'ultima riga PRIMA di un istante, **una per soggetto**.

        Risponde a *«in che stato era la casa quando questo giorno e'
        cominciato?»*, ed e' cio' che permette all'aggregazione di sapere che
        un termostato acceso da quattro giorni e' acceso anche oggi. Senza,
        un giorno vede solo cio' che e' cambiato dentro di se': misurato sulla
        casa vera il 10/09/2026, gli otto termostati hanno prodotto otto
        oggetti il 06/09 -- il giorno del loro ultimo cambio vero -- e **zero**
        nei tre giorni successivi, in cui erano accesi tutto il tempo.

        `fonte = "entita"` di proposito: le condizioni di sistema hanno gia'
        un meccanismo che le tiene aperte fra i riavvii
        (`watcher.rebuild_conditions`), e riseminarle anche da qui sarebbero
        due risposte alla stessa domanda.

        Nessun tetto e nessuna finestra all'indietro: la potatura tiene il
        grezzo a 22 giorni, e il `ROW_NUMBER()` fa il lavoro nel motore invece
        di portare in Python centomila righe per tenerne una manciata.
        """
        sql = ("SELECT * FROM (SELECT *, ROW_NUMBER() OVER "
               "(PARTITION BY soggetto ORDER BY quando_ts DESC, id DESC) AS rn "
               "FROM cambi WHERE quando_ts < ? AND fonte = ?) WHERE rn = 1")
        with self._lock:
            rows = self._conn.execute(sql, (float(ts), source)).fetchall()
        return [_reading_row(r) for r in rows]

    # -- Lo scope ----------------------------------------------------------

    def scope(self) -> dict[str, dict]:
        """Tutto cio' su cui qualcuno ha deciso, **dentro e fuori**.

        Chi e' stato escluso resta qui con la sua ragione: e' la trasparenza, ed
        e' da questa mappa che la pagina disegna sia «cosa guardo» sia «cosa ho
        lasciato fuori, e perche'». Per il filtro vero c'e'
        `is_watched()`.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT subject, inside, reason, author, decided_ts FROM scope").fetchall()
        return {r["subject"]: {"dentro": bool(r["inside"]), "motivo": r["reason"],
                               "autore": r["author"], "deciso_ts": r["decided_ts"]}
                for r in rows}

    def is_watched(self, subject: str) -> bool:
        """Se questo soggetto e' dentro lo scope. **La domanda che il rubinetto
        pone a ogni evento della casa**, quindi una riga per chiave primaria e
        non un insieme da ricostruire.

        Misurato l'11/09/2026 su uno scope di 833 righe (381 dentro): **24 us**
        a evento cosi', **1.084 us** tornando l'insieme intero -- 0,7 secondi
        di lavoro al giorno contro 32, sui 29.227 eventi misurati.

        **Chi non c'e' e' fuori.** Non esser mai stati considerati e l'esser
        stati esclusi sono, per il rubinetto, la stessa cosa: in nessuno dei
        due casi qualcuno ha deciso che quel soggetto pesa. Il contrario
        rimetterebbe dentro tutta la casa proprio quando lo scope e' vuoto --
        al primo avvio, prima che l'osservatore abbia parlato.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT inside FROM scope WHERE subject = ?", (subject,)).fetchone()
        return bool(row["inside"]) if row is not None else False

    def undecided(self, subjects: list[str]) -> list[str]:
        """Quali di questi soggetti **non sono ancora stati giudicati**: ne'
        dentro ne' fuori.

        **E' l'impronta**, e non ce n'e' una seconda da costruire. «Questa
        entita' e' nuova?» non e' una domanda a cui Home Assistant sappia
        rispondere (spec §4): si sa solo confrontando con com'era. Lo scope
        *e'* com'era -- una struttura in piu' che tenesse la stessa verita'
        divergerebbe al primo disallineamento fra le due scritture -- ed e'
        anche piu' esatta di un'anagrafe di ieri, che direbbe «esisteva gia'»
        anche di un'entita' su cui l'osservatore non ha mai aperto bocca.

        **Chi e' stato ESCLUSO non e' nuovo.** E' stato guardato e giudicato:
        ripresentarlo farebbe girare l'osservatore per sempre sulle stesse 452
        entita' di servizio, e ogni giro costa una lettura dell'intera casa al
        modello.

        Si chiede fra i soggetti **di adesso** e si risponde nel loro ordine,
        senza ripetizioni: l'elenco finisce in un prompt e in una pagina, e un
        ordine che cambia a ogni giro rende due risposte impossibili da
        confrontare.
        """
        decided = set(self.scope())
        out: list[str] = []
        for subject in subjects:
            if subject not in decided and subject not in out:
                out.append(subject)
        return out

    def decide_scope(self, subject: str, *, inside: bool, reason: str,
                     author: str, when_ts: float | None = None) -> bool:
        """Registra una decisione. Torna `False` se non ha scritto niente.

        **Due rifiuti, due ragioni diverse.**

        Una decisione **senza motivo** non si scrive: e' la stessa disciplina di
        `type_vocabulary.Field`, che non si puo' costruire senza provenienza.
        Una scelta senza ragione non e' rivedibile da nessuno -- ne'
        dall'analista ne' dal proprietario -- e la pagina esiste proprio per far
        vedere le ragioni.

        Una decisione di **chi ha meno informazione** non sovrascrive quella di
        chi ne ha di piu' (`scope.may_overwrite`): senza questa guardia
        l'analista rimette dentro, l'osservatore al giro successivo ritoglie, e
        la casa oscilla per sempre senza che nessuno lo veda.
        """
        clean = (reason or "").strip()
        if not clean:
            return False
        standing = self.scope().get(subject)
        if not may_overwrite(author, standing["autore"] if standing else None):
            return False
        with self._lock:
            self._conn.execute(
                "INSERT INTO scope (subject, inside, reason, author, decided_ts) "
                "VALUES (?,?,?,?,?) ON CONFLICT(subject) DO UPDATE SET "
                "inside = excluded.inside, reason = excluded.reason, "
                "author = excluded.author, decided_ts = excluded.decided_ts",
                (subject, 1 if inside else 0, clean, author,
                 float(when_ts if when_ts is not None else _time.time())))
            self._conn.commit()
        return True

    # -- La riconsiderazione -----------------------------------------------

    def last_reconsideration(self) -> dict | None:
        """L'ultima volta che l'osservatore ha ripensato tutta la casa, con la
        misura che aveva in mano allora. `None` se non e' mai successo.

        Si ordina per `done_ts` **decrescente**: la domanda e' «quand'e'
        l'ultima volta?», e la prima riga della tabella e' la piu' vecchia.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT done_ts, window_s, cadence_s, reason FROM reconsideration "
                "ORDER BY done_ts DESC, id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return {"quando_ts": row["done_ts"],
                "finestra_s": row["window_s"],
                "cadenza_s": row["cadence_s"],
                "motivo": row["reason"]}

    def record_reconsideration(self, *, when_ts: float | None = None,
                               window_s: float | None,
                               cadence_s: float | None,
                               reason: str | None = None) -> None:
        """Annota una riconsiderazione avvenuta, con la **causa** che l'ha
        provocata. Si ACCODA: quante volte, con quale memoria di Home Assistant
        e per quale ragione e' la cronaca di come la cadenza si e' adattata
        alla casa, e una riga sola non la direbbe."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO reconsideration (done_ts, window_s, cadence_s, reason) "
                "VALUES (?,?,?,?)",
                (float(when_ts if when_ts is not None else _time.time()),
                 None if window_s is None else float(window_s),
                 None if cadence_s is None else float(cadence_s),
                 reason))
            self._conn.commit()

    def recent_attempts(self, limit: int = ATTEMPTS_SHOWN) -> list[dict]:
        """Gli ultimi tentativi, **dal piu' recente**.

        **La domanda vera non e' «com'e' andata l'ultima volta», e' «sta
        funzionando?»** -- e un tentativo solo non la distingue: fra un
        fallimento e il successivo il giro riaccoda, quindi l'ultimo esito
        torna a essere «accodata» e il guasto sparirebbe dalla vista mentre
        continua. Misurato l'11/09/2026: quattro fallimenti di fila in quaranta
        minuti, con la casa che intanto non veniva registrata affatto. Questa
        e' la riga che serviva, e non esisteva.

        **Serve anche al freno**: `server._retry_hold` conta da qui quanti
        fallimenti di fila ci sono stati, invece di tenere un contatore suo che
        il primo riavvio azzererebbe.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT tried_ts, outcome, detail, version FROM scope_attempt "
                "ORDER BY tried_ts DESC, id DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"quando_ts": r["tried_ts"], "esito": r["outcome"],
                 "dettaglio": r["detail"], "versione": r["version"]}
                for r in rows]

    def record_attempt(self, *, when_ts: float | None = None, outcome: str,
                       detail: str | None = None,
                       version: str | None = None) -> None:
        """Annota un tentativo. Si ACCODA, come le riconsiderazioni: tre
        fallimenti di fila e uno solo sono due storie diverse, e una riga sola
        non le distinguerebbe."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO scope_attempt (tried_ts, outcome, detail, version) "
                "VALUES (?,?,?,?)",
                (float(when_ts if when_ts is not None else _time.time()),
                 outcome, detail, version))
            self._conn.commit()

    # -- L'obiettivo -------------------------------------------------------

    def objective(self) -> dict:
        """L'obiettivo che vale adesso: `{"testo", "scritto_ts"}`.

        `scritto_ts` a `None` dice che nessuno l'ha mai scritto e vale quello di
        fabbrica -- che non e' la stessa cosa di «l'ha scritto qualcuno e per
        caso coincide col default».
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT text, written_ts FROM objective "
                "ORDER BY written_ts DESC, id DESC LIMIT 1").fetchone()
        if row is None:
            return {"testo": DEFAULT_OBJECTIVE, "scritto_ts": None}
        return {"testo": row["text"], "scritto_ts": row["written_ts"]}

    def set_objective(self, text: str, *, when_ts: float | None = None) -> bool:
        """Scrive un obiettivo nuovo. Torna `False` se non ha scritto niente.

        **Un testo vuoto si rifiuta**: e' l'unica manopola del prodotto, e un
        campo svuotato per errore non deve poter lasciare l'osservatore senza
        criterio. Stessa dottrina del sistema di riferimento, che vuoto non
        cancella quello di prima.

        **Riscrivere lo stesso testo non e' un cambio d'obiettivo** e non
        sporca la storia: la pagina dice «da quando guardo questa cosa», e
        direbbe che tutto e' cambiato ogni volta che qualcuno preme «salva»
        senza aver toccato niente.
        """
        clean = (text or "").strip()
        if not clean:
            return False
        if self.objective()["testo"] == clean:
            return False
        with self._lock:
            self._conn.execute(
                "INSERT INTO objective (text, written_ts) VALUES (?,?)",
                (clean, float(when_ts if when_ts is not None else _time.time())))
            self._conn.commit()
        return True

    def objective_history(self) -> list[dict]:
        """Tutti gli obiettivi, **dal piu' recente**: e' una cronaca, e una
        cronaca si legge da adesso all'indietro."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT text, written_ts FROM objective "
                "ORDER BY written_ts DESC, id DESC").fetchall()
        return [{"testo": r["text"], "scritto_ts": r["written_ts"]} for r in rows]

    def objective_at(self, ts: float) -> dict:
        """L'obiettivo che valeva a quell'istante -- la domanda che il resoconto
        porra' a ogni giornata che rilegge.

        Il confine e' incluso: un obiettivo scritto alle 14:00 vale per le
        14:00. Prima del primo scritto vale quello di fabbrica: la casa c'era
        comunque, e l'osservatore guardava.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT text, written_ts FROM objective WHERE written_ts <= ? "
                "ORDER BY written_ts DESC, id DESC LIMIT 1", (float(ts),)).fetchone()
        if row is None:
            return {"testo": DEFAULT_OBJECTIVE, "scritto_ts": None}
        return {"testo": row["text"], "scritto_ts": row["written_ts"]}

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
