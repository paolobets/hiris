"""L'archivio dell'osservatore: i cambi, i resoconti, le analisi.

**Due vite, non due tabelle.** I cambi grezzi vivono 22 giorni; cio' che di
quei cambi si e' capito -- il resoconto di ogni giorno e l'analisi -- resta
finche' l'utente non lo cancella.

Lo strato degli **oggetti** e' uscito con la 3.43.0 (`_migration_10`, DROP
TABLE), dopo aver misurato che i comprimari erano zero su 200 oggetti e che
ogni giorno-oggetto aveva gia' un resoconto: questa testata lo nominava ancora
il 15/09/2026, e l'ha trovato la revisione indipendente.

**Perche' 21 giorni e non una notte.** La proprieta' che rende buono lo schema
a due strati e' che sbagliare l'aggregazione costa un GIORNO, non tutto: finche'
il grezzo c'e', i resoconti si rifanno. Ma il modo di costruirli cambiera' --
le prime settimane sono quelle in cui si sta ancora imparando -- e con una notte
sola ogni miglioramento varrebbe solo da domani. Ventuno giorni sono TRE
MERCOLEDI', l'unita' dell'esempio da cui nasce tutto il cervello.

**Perche' la soglia vera e' 22 e non 21.** Ventun giorni sono la promessa; il
ventiduesimo e' la guardia che la rende vera al bordo. Vedi il commento accanto
a `READING_RETENTION_S`.

**Perche' non e' il ritorno di `history.db`.** Quello scriveva e nessuno
leggeva, e l'avvio lo tratta ancora oggi come un residuo da rimuovere. La
differenza non e' di forma, e' di destino: quello nasceva senza lettore, questo
ha i suoi -- l'aggregazione del giorno (`mind/facts.py`), la pagina
dell'osservatore e l'analista, che legge le misure dei resoconti. Un archivio
che scrive senza lettori va cancellato, non lasciato a scrivere: e' la regola
che ha condannato il primo.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time as _time
import uuid

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

#: **Per quanto tiene ogni tabella, e perche'** (reperto C-6, 23/09/2026).
#:
#: Fino a oggi la conservazione copriva **una tabella su otto**: solo il
#: grezzo. Le altre sette non avevano nessun cancellatore -- non perche'
#: qualcuno avesse deciso «per sempre», ma perche' **nessuno aveva deciso
#: niente**, che e' una cosa diversa e non si vede guardando il disco.
#:
#: Misurate, sei delle sette devono restare, e adesso lo dichiarano. Il valore
#: di questa tabella non e' aver aggiunto sette cancellatori: e' che una
#: tabella nuova che nascesse domani **non puo' entrare senza una decisione
#: scritta accanto** -- lo impedisce una prova che confronta questo elenco con
#: le tabelle vere.
#:
#: `(giorni | None, ragione, cancellazione)`. `giorni` a `None` = per sempre,
#: e allora la `cancellazione` e' `None` anche lei.
#:
#: **La `cancellazione` e' una frase SQL intera e letterale**, non un nome di
#: colonna da cui comporla: `f"DELETE FROM {tabella}"` renderebbe questo file
#: cieco al censimento (`scripts/censimento.py` vede una scrittura solo se il
#: nome della tabella sta nello stesso letterale della parola chiave), e
#: perderebbe la copertura su tutte le ventiquattro tabelle scritte qui.
#: Misurato: il censimento passava da 38 reperti a 39.
CONSERVAZIONE: dict[str, tuple[int | None, str, str | None]] = {
    # Chiesto a `READING_RETENTION_S`, non ricopiato (G-18, Tappa 8): i 22
    # giorni del grezzo sono un fatto solo, letto da cronaca, osservatore e
    # pagina da li', e da `prune` da qui.
    "cambi": (
        READING_RETENTION_S // 86400,
        ("il grezzo: serve a vedere cosa e' successo di recente, e oltre tre "
         "settimane nessuno lo rilegge piu'"),
        "DELETE FROM cambi WHERE quando_ts < ?"),
    "scope_attempt": (
        30,
        ("tentativi: diagnostica pura, una riga a ogni giro anche fallito, e "
         "la pagina ne mostra una manciata. E' l'unica che cresce senza "
         "portare niente con se'"),
        "DELETE FROM scope_attempt WHERE tried_ts < ?"),
    "analisi": (
        None,
        ("un'analisi al giorno, e ognuna e' cio' che si e' capito di quel "
         "giorno: cancellarle libererebbe qualche megabyte e perderebbe mesi"),
        None),
    "resoconto": (
        None,
        ("un resoconto al giorno: e' la storia misurata della casa, la materia "
         "prima dell'analista"),
        None),
    "proposte": (
        None,
        ("ogni riga porta la decisione che il proprietario ci ha messo sopra "
         "-- accettata, rifiutata, fatta a mano: e' un registro delle sue "
         "scelte, non un archivio tecnico"),
        None),
    "objective": (None, "parole sue", None),
    "scope": (
        None, "il perimetro: parole sue, una riga per soggetto", None),
    "reconsideration": (
        None,
        ("quando e perche' il perimetro e' stato ripensato: poche righe, e "
         "spiegano come si e' arrivati a quello di oggi"),
        None),
}


logger = logging.getLogger(__name__)


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
    il 26/08, la scelta giusta allora). Il pavimento e la gamba che leggeva
    queste tre classi sono usciti interi il 17/09/2026 (spec 2026-09-16 §11):
    oggi solo `device_class` ha un lettore vivo (`facts.genre_for` e
    `facts._is_on`, attraverso l'istantanea dei giudizi); `state_class` e
    `source_type` non ne hanno nessuno, e sono uscite con `_migration_15`
    (Tappa 8, G-06): una colonna scritta a ogni cambio e mai letta e' un
    doppione dello specchio di Home Assistant che nessuno interroga. Questa
    migrazione resta com'e', perche' deve dire fra due anni la stessa cosa:
    un archivio alla versione 1 le riceve qui e le perde alla 15.

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
    motivo, proprio di questa colonna: il grezzo e cio' che se ne capisce
    hanno due vite -- i `cambi` vivono 22 giorni, i resoconti (allora gli
    `oggetti`, usciti con `_migration_10`) finche' l'utente non li cancella.
    Un giorno di sei mesi fa su un'entita' sostituita non avrebbe NESSUN
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
    quello che mostra e' un identificatore (`describeWatchedSubject`, nelle
    pagine dell'osservatore in `static/config/`), mai inventando un nome dall'id.
    """
    _add_missing_columns(conn, ("friendly_name",))


def _migration_7(conn) -> None:
    """v6 -> v7: `attributes`, gli attributi che la ricetta chiede (spec §5.4).

    **Il fatto vive spesso in un attributo, non nello stato.** Lo stato di un
    termostato e' `heat` e resta `heat`; `hvac_action` dice `idle`/`heating`.
    Senza questa colonna l'esempio fondativo del cervello -- *«il riscaldamento
    parte alle 15:30, la casa e' calda alle 16:30»* -- non e' rispondibile, e
    non lo sarebbe mai stato, perche' il grezzo e' l'unica cosa che si puo'
    rileggere.

    **`current_temperature` NON e' fra gli attributi voluti**, e vale la pena
    dirlo qui perche' la prima stesura di questa colonna lo citava come
    motivazione: e' una grandezza continua, e tenerla riaprirebbe il flusso di
    righe che il filtro `da == a` ha chiuso. La domanda la risponde
    `hvac_action`, che passa a `idle` QUANDO la casa e' arrivata in
    temperatura. Vedi `mind/seed._WANTED_ATTRIBUTES`.

    Le righe scritte prima rileggono `None`, ed e' vero: quegli attributi non
    li avevano. **Non si riempiono a posteriori** dallo specchio di oggi --
    sarebbe attribuire a ieri lo stato di adesso, la stessa ragione gia'
    scritta per `friendly_name`.
    """
    _add_missing_columns(conn, ("attributes",))


#: Cosa si scrive al posto di un numero calcolato con un'operazione che il
#: registro non sa piu' eseguire dentro una ricetta. Sta qui accanto alla
#: migrazione perche' una migrazione deve dire fra
#: due anni la stessa cosa che dice adesso.
_WITHDRAWN_REASON = (
    "calcolata con \u00ab{operazione}\u00bb, che il registro non sa piu' eseguire "
    "dentro una ricetta: il numero non e' attendibile e non si rifa'")


def _migration_8(conn) -> None:
    """v7 -> v8: si **disinnescano** i numeri calcolati con un'operazione
    ritirata dalle ricette.

    **Un numero sbagliato gia' archiviato**, misurato sulla casa vera il
    14/09/2026: il resoconto del 26/08 portava `energia_consumata = -0,98 kWh`.
    `primo_ultimo_differenza` risponde a «quanto e' salito un contatore: ultima
    meno prima» e vuole le letture cumulate; dentro una ricetta riceveva le
    statistiche orarie, dove ogni punto e' il CAMBIO di quell'ora. La ricetta
    esce dal sapere con la sua migrazione, ma **il numero resta scritto qui**, e
    nessuno lo rifa': un giorno si rifa' solo finche' il suo grezzo esiste, e
    l'analista legge i resoconti, non le ricette.

    La riga diventa un **«non calcolabile» col suo perche'** -- il posto dove
    l'analista guarda cio' che manca -- e resta al suo posto, col suo nome:
    sparire sarebbe peggio, perche' «non c'e' mai stato» e «c'era e non
    vale» sono due cose diverse.

    **La cronaca non si tocca, e il resoconto non si cancella.** Per un giorno
    il cui grezzo e' scaduto quello e' l'unica copia rimasta.

    **Solo i resoconti toccati si riscrivono**: una migrazione che riscrive
    cio' che non deve e' peggio del difetto che ripara.
    """
    from .operations import REGISTRY

    rows = conn.execute("SELECT giorno, corpo_json FROM resoconto").fetchall()
    for row in rows:
        try:
            body = json.loads(row["corpo_json"])
        except (TypeError, ValueError):
            continue
        if not isinstance(body, dict):
            continue
        changed = False
        for section in ("misure", "forme"):
            for line in body.get(section) or []:
                if not isinstance(line, dict) or "valore" not in line:
                    continue
                used = str(line.get("operazione") or "")
                entry = REGISTRY.get(used)
                if entry is not None and entry.offerable:
                    continue
                line.pop("valore", None)
                line.pop("unita", None)
                line.pop("copertura", None)
                line.pop("esclusi", None)
                line["non_calcolabile"] = _WITHDRAWN_REASON.format(operazione=used)
                changed = True
        if changed:
            conn.execute("UPDATE resoconto SET corpo_json = ? WHERE giorno = ?",
                         (json.dumps(body, ensure_ascii=False), row["giorno"]))
            logger.info(
                "resoconto di %s: numeri calcolati con un'operazione ritirata "
                "disinnescati", row["giorno"])


def _migration_9(conn) -> None:
    """v8 -> v9: l'**obiettivo** sui resoconti gia' archiviati (spec §11).

    Chi legge trenta giorni di misure in serie deve sapere se in mezzo la
    domanda e' cambiata, o legge una tendenza dove c'e' un cambio d'obiettivo.
    La riga e' nata il 14/09/2026, dopo i diciannove giorni gia' scritti sulla
    casa vera (26/08 -> 13/09): quelli non ce l'hanno.

    **Si puo' scrivere senza inventare niente**, perche' l'obiettivo vive
    nella stessa base dati: si cerca quello che valeva alla FINE di quel
    giorno -- lo stesso istante che usa `aggregate_day`, o due strade sullo
    stesso giorno darebbero risposte diverse.

    **Un resoconto che ce l'ha gia' non si tocca**: puo' portare un obiettivo
    DIVERSO da quello di adesso, ed e' il suo; sovrascriverlo direbbe che quel
    giorno rispondeva a una domanda che non era la sua.

    La query dell'obiettivo e' ricopiata qui invece di chiamare
    `objective_at`: una migrazione deve dire fra due anni la stessa cosa che
    dice adesso, anche se quel metodo cambiasse.
    """
    rows = conn.execute("SELECT giorno, corpo_json FROM resoconto").fetchall()
    for row in rows:
        try:
            body = json.loads(row["corpo_json"])
        except (TypeError, ValueError):
            continue
        if not isinstance(body, dict) or body.get("obiettivo") is not None:
            continue
        end = _end_of_day_ts(row["giorno"])
        if end is None:
            continue
        aim = conn.execute(
            "SELECT text, written_ts FROM objective WHERE written_ts <= ? "
            "ORDER BY written_ts DESC, id DESC LIMIT 1", (end,)).fetchone()
        body["obiettivo"] = (
            {"testo": DEFAULT_OBJECTIVE, "scritto_ts": None} if aim is None
            else {"testo": aim["text"], "scritto_ts": aim["written_ts"]})
        conn.execute("UPDATE resoconto SET corpo_json = ? WHERE giorno = ?",
                     (json.dumps(body, ensure_ascii=False), row["giorno"]))


def _end_of_day_ts(day: str) -> float | None:
    """La mezzanotte che chiude quel giorno, in UTC.

    **Il fuso non si puo' sapere qui**, e va bene: l'obiettivo cambia qualche
    volta all'anno, non qualche volta all'ora, e due ore di scarto sul confine
    sceglierebbero lo stesso obiettivo in ogni caso reale. Inventare un fuso
    sarebbe peggio: sarebbe un'affermazione, e questa e' un'approssimazione
    dichiarata.
    """
    try:
        pieces = [int(n) for n in str(day).split("-")]
        return dt.datetime(pieces[0], pieces[1], pieces[2], tzinfo=dt.UTC).timestamp() + 86400.0
    except (ValueError, IndexError, TypeError):
        return None


def _migration_10(conn) -> None:
    """v9 -> v10: la tabella degli **oggetti** esce (spec §13).

    **Misurato sulla casa vera prima di cancellarla**, il 15/09/2026: 200
    oggetti dal 26/08 al 14/09, e ognuno di quei giorni aveva gia' il suo
    resoconto -- la storia era gia' salva nella forma che resta. I comprimari,
    l'unica cosa che l'oggetto portava e la cronaca no, erano **zero su 200**:
    il campo `misure` vuoto in tutti.

    Quindi **niente conversione**: non c'era niente da convertire che non fosse
    gia' scritto altrove. Si cancella, e con lei escono `facts()` e
    `replace_day()`.
    """
    conn.execute("DROP TABLE IF EXISTS oggetti")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS cambi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando_ts REAL NOT NULL,
    fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')),
    soggetto TEXT NOT NULL,
    da TEXT,
    a TEXT,
    device_class TEXT,
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
    -- per una in piu' che vale solo per lui: i resoconti vivono piu' a
    -- lungo dei `cambi`, quindi un nome risolto dopo su un giorno vecchio
    -- non si troverebbe piu'. NULL per le condizioni di sistema (un
    -- `problema:`/`integrazione:`/`log:`/`automazione:` non e' un'entita' e
    -- non ne porta uno) e per le entita' su cui HA non scrive l'attributo.
    -- Vedi `_migration_5`.
    friendly_name TEXT,
    -- Gli attributi che qualcuno ha deciso valga la pena tenere PER QUESTO
    -- TIPO (fetta «il sapere e le ricette», 12/09/2026, spec §5.4), come
    -- JSON. **Non sono tutti**: tenerli tutti rimetterebbe nel grezzo le
    -- 6.503 righe al giorno di soli attributi che il filtro `da == a` ha
    -- tolto. Quali valgano la pena lo dice il sapere (`mind/knowledge.py`,
    -- campo `attributi` sul soggetto del tipo), non una lista qui.
    --
    -- **Perche' una colonna JSON e non una per attributo.** Gli attributi
    -- utili cambiano per dispositivo e cambiano nel tempo: una colonna
    -- ciascuno vorrebbe dire una migrazione a ogni ricetta nuova, cioe' un
    -- rilascio per ogni cosa imparata -- esattamente cio' che questa fetta
    -- esiste per togliere. Il costo e' che non si possono interrogare in SQL;
    -- chi li legge e' `mind/facts.py`, che rilegge la riga intera comunque.
    --
    -- NULL per le righe scritte prima di questa colonna, per le condizioni
    -- di sistema, e per ogni entita' di cui nessuno ha ancora deciso niente.
    attributes TEXT
);
CREATE INDEX IF NOT EXISTS idx_cambi_quando ON cambi(quando_ts);
CREATE INDEX IF NOT EXISTS idx_cambi_soggetto ON cambi(soggetto, quando_ts);

-- L'ANALISI di un giorno (spec §10): cosa l'analista ha visto, e perche'.
-- Una per giorno, sostituibile come il resoconto: rifare un giorno lo rifa'.
--
-- **Il silenzio si archivia.** «Ho guardato e non c'era niente da dire» e «non
-- ho guardato» sono due cose diverse, ed e' la stessa legge del resoconto
-- vuoto: un'analisi con zero osservazioni e' una riga, non un'assenza.
CREATE TABLE IF NOT EXISTS analisi (
    giorno       TEXT PRIMARY KEY,
    corpo_json   TEXT NOT NULL,
    scritto_ts   REAL NOT NULL
);

-- Le PROPOSTE che deve applicare una persona (spec 2026-09-21 §3).
--
-- **Perche' non stanno in `costruzioni`**: quella tabella ha `gesto`,
-- `dominio`, `chiave`, `prima_json`, `dopo_json`, `anteprima` -- ogni colonna
-- parla di un oggetto che HIRIS sa scrivere -- e sopra ci vive la macchina
-- dell'officina (scadenza, claim, applicazione, ripristino). «Sposta i consumi
-- nel pomeriggio» non ha niente di tutto questo: infilarla li' vorrebbe dire
-- cinque colonne di finti valori e meta' macchina che non si applica.
--
-- «Un posto solo dove si decide» e' una promessa sulla PAGINA, non sulla
-- tabella: e' la pagina a mostrarle insieme, con l'etichetta di chi le applica.
--
-- `impronta` e `prova_json` sono l'anti-ripetizione: il proponente salta una
-- domanda gia' decisa **finche' la sua prova non cambia**
-- (`proposer_turn.already_answered`).
--
-- `giri_json` e' il filo del «Rifalla»: ogni giro porta la richiesta di
-- modifica e la forma che ne e' uscita, cosi' il modello vede il filo intero e
-- non ripropone cio' che e' stato appena scartato.
--
-- Non c'e' chi la applica (e' sempre una persona: lo dice la porta delle
-- Proposte), ne' quando e' stata toccata o chiusa l'ultima volta: nessuno lo
-- leggeva (vedi `_migration_12`).
CREATE TABLE IF NOT EXISTS proposte (
    id            TEXT PRIMARY KEY,
    creata_ts     REAL NOT NULL,
    stato         TEXT NOT NULL,
    testo         TEXT NOT NULL,
    perche        TEXT NOT NULL,
    impronta      TEXT NOT NULL,
    prova_json    TEXT NOT NULL,
    giri_json     TEXT NOT NULL,
    esito_nota    TEXT,
    -- Il LIVELLO (attori, strato 4, D13): lo stesso campo delle costruzioni
    -- (`action/construction/stakes.py`), con lo stesso vocabolario. NULL
    -- quando nessuno l'ha detto, e per le righe nate prima del 06/10/2026
    -- (vedi `_migration_11`). Colonna nuova, quindi in inglese.
    stakes        TEXT,
    -- «Rendila automatica» (attori, strato 4, Task 4.5; `_migration_13`):
    -- l'id della costruzione che ne e' nata (un riferimento all'archivio
    -- delle costruzioni, non una copia), e perche' non si e' potuta rendere
    -- automatica. Il secondo resta su una proposta ancora in attesa.
    construction_id    TEXT,
    automation_refusal TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposte_stato ON proposte(stato, creata_ts DESC);

-- IL RESOCONTO DEL GIORNO (spec §9, fetta 5). Una riga per giorno, e **resta**:
-- il grezzo scade, il resoconto no.
--
-- **Una colonna JSON e non due tabelle**, e la ragione e' che le due parti si
-- leggono insieme o non si leggono affatto: l'analista scorre le misure di
-- trenta giorni e poi chiede la cronaca di UNO -- due letture, non due
-- tabelle. E la forma delle due parti cambiera' ancora (le ricette crescono,
-- l'ancora della cronaca puo' stringersi): una colonna per campo vorrebbe dire
-- una migrazione a ogni cosa imparata, che e' cio' che questa fetta esiste per
-- togliere.
CREATE TABLE IF NOT EXISTS resoconto (
    giorno       TEXT PRIMARY KEY,
    corpo_json   TEXT NOT NULL,
    scritto_ts   REAL NOT NULL
);

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
-- ha cambiato idea la porta gia' `decided_ts` insieme all'autore -- e cio' che
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


def _migration_11(conn) -> None:
    """v10 -> v11 (attori, strato 4, Task 4.3): `proposte.stakes`, il livello
    della proposta da fare a mano.

    Le righe scritte prima rileggono `None`: quelle proposte non sono mai
    state chieste con un livello, e riempirlo oggi attribuirebbe a ieri un
    fatto di adesso.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(proposte)")}
    if "stakes" not in existing:
        conn.execute("ALTER TABLE proposte ADD COLUMN stakes TEXT")


#: Le colonne di `proposte` alla versione 12, quelle che la ricostruzione
#: ricopia. Sono la forma di QUEL gradino, e restano ferme: una colonna nata
#: dopo arriva con la sua migrazione, come `stakes` con `_migration_11`.
_PROPOSAL_COLUMNS = ("id", "creata_ts", "stato", "testo", "perche", "impronta",
                     "prova_json", "giri_json", "esito_nota", "stakes")


def _migration_12(conn) -> None:
    """v11 -> v12 (attori, strato 4, Task 4.6): escono `proposte.chi_applica`,
    `aggiornata_ts` ed `esito_ts` (censimento del 01/10/2026, punti 6 e 7).

    `chi_applica` era una costante salvata: si scriveva sempre «tu», e la
    porta delle Proposte la sovrascriveva con la sua
    (`handlers_constructions._both_queues`). Le due date si scrivevano e
    nessuno le leggeva: la pagina ordina per `creata_ts`.

    **Si ricostruisce la tabella, non si usa `DROP COLUMN`**: quello vuole
    SQLite 3.35, e la versione dentro l'immagine dell'add-on non e' stata
    misurata. La ricostruzione funziona su tutte. Le righe restano, con ogni
    colonna che resta.

    **Tutto o niente, in una transazione** (revisione indipendente, giro 14,
    G14-1). Il modulo `sqlite3` non apre una transazione per `ALTER` e
    `CREATE`: senza `BEGIN` ogni passo si confermava da solo, e una
    ricostruzione interrotta dopo il `RENAME` lasciava una `proposte` vuota,
    con le righe in `proposte_v11` dove nessuno le legge. Se un passo fallisce
    si torna indietro e l'archivio resta alla versione 11, intero: la
    migrazione si rifara' al prossimo avvio.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(proposte)")}
    if not existing & {"chi_applica", "aggiornata_ts", "esito_ts"}:
        return
    columns = ",".join(_PROPOSAL_COLUMNS)
    # Una migrazione precedente dello stesso avvio puo' averne gia' aperta una
    # (il modulo la apre da se' davanti a un `UPDATE`): si continua in quella.
    if not conn.in_transaction:
        conn.execute("BEGIN")
    try:
        conn.execute("ALTER TABLE proposte RENAME TO proposte_v11")
        conn.execute("DROP INDEX IF EXISTS idx_proposte_stato")
        conn.execute(
            "CREATE TABLE proposte (id TEXT PRIMARY KEY, creata_ts REAL NOT NULL, "
            "stato TEXT NOT NULL, testo TEXT NOT NULL, perche TEXT NOT NULL, "
            "impronta TEXT NOT NULL, prova_json TEXT NOT NULL, "
            "giri_json TEXT NOT NULL, esito_nota TEXT, stakes TEXT)")
        conn.execute(f"INSERT INTO proposte({columns}) SELECT {columns} FROM proposte_v11")
        conn.execute("DROP TABLE proposte_v11")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proposte_stato "
                     "ON proposte(stato, creata_ts DESC)")
    except BaseException:
        conn.rollback()
        raise


def _migration_13(conn) -> None:
    """v12 -> v13 (attori, strato 4, Task 4.5): `proposte.construction_id` e
    `proposte.automation_refusal`, l'esito di «Rendila automatica». Le righe
    di prima rileggono `None`: nessuno l'aveva chiesto."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(proposte)")}
    for column in ("construction_id", "automation_refusal"):
        if column not in existing:
            conn.execute(f"ALTER TABLE proposte ADD COLUMN {column} TEXT")


#: La chiave sotto cui il vecchio attuatore scriveva i suoi esiti dentro
#: l'analisi, e i suoi tre gesti. Sono nomi RITIRATI (attori, strato 4, Task
#: 4.6): non esiste una fonte da interrogare, l'elenco e' il fatto, e serve
#: solo a `_migration_14` per leggere le righe di allora.
_RETIRED_KEY = "attuazione"
_RETIRED_INQUIRY = "indagine"
_RETIRED_REPAIR = "riparazione"
_RETIRED_PROPOSAL = "proposta"


def _retired_outcome(conn, outcome, written_ts: float) -> dict | None:
    """Un esito del vecchio attuatore nella forma del proponente, o `None`
    se non si lega a niente (`_migration_14`)."""
    from . import proposer_turn

    if not isinstance(outcome, dict) or not outcome.get("impronta"):
        return None
    key = outcome["impronta"]
    gesture = outcome.get("gesto")
    if gesture in (_RETIRED_INQUIRY, _RETIRED_REPAIR):
        why = str(outcome.get("trovato") or "").strip()
        return {"impronta": key, "esito": proposer_turn.NOTHING,
                "perche": why} if why else None
    if gesture != _RETIRED_PROPOSAL:
        return None
    if outcome.get("costruibile"):
        return {"impronta": key, "esito": proposer_turn.BUILT}
    row = conn.execute(
        "SELECT id FROM proposte WHERE impronta = ? AND creata_ts <= ? "
        "ORDER BY creata_ts DESC, rowid DESC LIMIT 1", (key, written_ts)).fetchone()
    if row is None:
        # Senza la riga la pagina direbbe «la trovi in Proposte» dove non
        # c'e' niente: come l'esito senza impronta, non si porta (revisione,
        # giro 74, N74-2).
        return None
    return {"impronta": key, "esito": proposer_turn.BY_HAND, "proposta_id": row["id"]}


def _migration_14(conn) -> None:
    """v13 -> v14 (attori, strato 4, Task 4.6): gli esiti del vecchio
    attuatore, archiviati dentro l'analisi sotto `attuazione`, passano alla
    chiave del proponente (`proposer_turn.OUTCOMES_KEY`), nella sua forma.

    Fino al 06/10/2026 le due chiavi convivevano: la pagina leggeva la
    vecchia, il proponente scriveva la nuova, e i suoi esiti non arrivavano
    mai alla pagina. Due chiavi vorrebbero due lettori (fondamenta 2): si
    portano le righe a una, e il lettore resta uno (`outcomes_of`).

    - un'**indagine** e una **riparazione** non proponevano niente: «niente»,
      col perche' che l'attuatore aveva scritto (dal 05/10/2026 l'indagine e'
      dell'analista e la riparazione del giro delle ricette);
    - una **proposta da fare a mano** cita la riga di `proposte` con la stessa
      impronta nata prima che l'analisi fosse scritta: il giro di allora la
      metteva li', o ne trovava gia' una. Senza quella riga non si porta;
    - una **proposta costruibile** e' «costruita» senza id: l'id della
      costruzione allora non si scriveva, e non si inventa;
    - un esito senza impronta non si legava a nessuna osservazione e la pagina
      non lo mostrava: non si porta.

    Per un'impronta che ha gia' un esito del proponente vale il suo: e' il
    piu' recente. **Solo le analisi con `attuazione` si riscrivono.**
    """
    from . import proposer_turn

    rows = conn.execute(
        "SELECT giorno, corpo_json, scritto_ts FROM analisi").fetchall()
    for row in rows:
        try:
            body = json.loads(row["corpo_json"])
        except (TypeError, ValueError):
            continue
        if not isinstance(body, dict) or _RETIRED_KEY not in body:
            continue
        retired = body.pop(_RETIRED_KEY)
        retired = retired.get("esiti") or [] if isinstance(retired, dict) else []
        beside = proposer_turn.outcomes_of(body)
        answered = {o.get("impronta") for o in beside}
        for outcome in retired:
            moved = _retired_outcome(conn, outcome, row["scritto_ts"])
            if moved is not None and moved["impronta"] not in answered:
                beside.append(moved)
                answered.add(moved["impronta"])
        body[proposer_turn.OUTCOMES_KEY] = beside
        conn.execute("UPDATE analisi SET corpo_json = ? WHERE giorno = ?",
                     (json.dumps(body, ensure_ascii=False), row["giorno"]))
        logger.info("analisi di %s: esiti dell'attuatore portati al proponente",
                    row["giorno"])


#: Le colonne di `cambi` alla versione 15, quelle che la ricostruzione
#: ricopia. Sono la forma di QUEL gradino, e restano ferme come
#: `_PROPOSAL_COLUMNS`: una colonna nata dopo arriva con la sua migrazione.
_READING_COLUMNS = ("id", "quando_ts", "fonte", "soggetto", "da", "a",
                    "device_class", "domain", "title", "first_occurred",
                    "friendly_name", "attributes")


def _drop_unread_reading_columns(conn) -> None:
    """Escono `cambi.state_class` e `cambi.source_type` (Tappa 8, G-06 e
    M-40): si scrivevano a ogni cambio e nessuno le leggeva dal 17/09/2026,
    quando e' uscita la gamba che le usava (vedi `_migration_2`). Il fatto
    vive gia' nello specchio di Home Assistant, che e' dove chi ne ha bisogno
    lo chiede (`house.mirror.state_classes`).

    **Si ricostruisce la tabella**, come `_migration_12`: `DROP COLUMN` vuole
    SQLite 3.35. Gli indici seguono la tabella rinominata e se ne vanno con
    lei: si ricreano dopo il `DROP`, quando il nome e' di nuovo libero. Il
    contatore di `AUTOINCREMENT` riparte dall'id piu' alto ricopiato, e basta:
    la potatura toglie le righe piu' vecchie, mai l'ultima, quindi nessun id
    gia' dato torna.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(cambi)")}
    if not existing & {"state_class", "source_type"}:
        return
    columns = ",".join(_READING_COLUMNS)
    conn.execute("ALTER TABLE cambi RENAME TO cambi_v14")
    conn.execute(
        "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "quando_ts REAL NOT NULL, "
        "fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')), "
        "soggetto TEXT NOT NULL, da TEXT, a TEXT, device_class TEXT, "
        "domain TEXT, title TEXT, first_occurred TEXT, friendly_name TEXT, "
        "attributes TEXT)")
    conn.execute(f"INSERT INTO cambi({columns}) SELECT {columns} FROM cambi_v14")
    conn.execute("DROP TABLE cambi_v14")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cambi_quando ON cambi(quando_ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cambi_soggetto "
                 "ON cambi(soggetto, quando_ts)")


#: L'istante in cui e' nato il codice del proponente: il commit `b79c347`
#: («il turno con `propose`», attori, Task 4.2), 06/10/2026 16:00:56 UTC.
#: **Una proposta nata prima non l'ha scritta il proponente**, perche' il
#: codice che la scrive non esisteva: l'ha scritta l'attuatore, che dal
#: 01/10/2026 era in pausa. E' il fatto da cui si legge «chi l'ha scritta»,
#: che la riga non porta: `stakes` e' nullo anche sulle righe del proponente
#: (`proposer_round`, D13), e la prova ha la stessa forma.
_PROPOSER_BORN_TS = 1791302456.0


def _drop_actuator_proposals(conn) -> None:
    """Escono le proposte da fare a mano scritte dall'attuatore (Tappa 8,
    G-04, D3: decisione del proprietario dell'08/10/2026, «elimina anche le 2
    rifiutate»). Misurato l'08/10/2026 sul backup dell'add-on: 9 righe, 7
    `attesa` e 2 `rifiutata`, `esito_nota` vuota su tutte, nessuna del
    proponente.

    **Perche' escono.** Nate su dati rotti (0 utili su 9), e una in attesa
    blocca il proponente: ritrovando la stessa impronta non scrive il suo
    testo, cita la vecchia (`proposer_round`, D24-1). Le 2 rifiutate escono
    anche loro: il proponente le avrebbe lette come una decisione su una
    domanda posta male.

    Una riga di log per id, con lo stato. **Escono anche gli esiti che le
    citano** dentro le analisi (`a_mano` con quel `proposta_id`, portati li'
    da `_migration_14` o scritti dal proponente che le ha trovate in attesa):
    la pagina direbbe «la trovi in Proposte» dove non c'e' niente, la stessa
    ragione per cui `_migration_14` non porta un «a mano» senza la sua riga
    (N74-2). Solo le analisi toccate si riscrivono.
    """
    from . import proposer_turn

    gone = conn.execute(
        "SELECT id, stato FROM proposte WHERE creata_ts < ? ORDER BY creata_ts",
        (_PROPOSER_BORN_TS,)).fetchall()
    if not gone:
        return
    for row in gone:
        logger.info("proposta a mano %s (%s) dell'attuatore cancellata", row["id"],
                    row["stato"])
    conn.execute("DELETE FROM proposte WHERE creata_ts < ?", (_PROPOSER_BORN_TS,))
    idents = {row["id"] for row in gone}
    for row in conn.execute("SELECT giorno, corpo_json FROM analisi").fetchall():
        try:
            body = json.loads(row["corpo_json"])
        except (TypeError, ValueError):
            continue
        if not isinstance(body, dict):
            continue
        outcomes = proposer_turn.outcomes_of(body)
        kept = [o for o in outcomes
                if not (isinstance(o, dict) and o.get("esito") == proposer_turn.BY_HAND
                        and o.get("proposta_id") in idents)]
        if len(kept) == len(outcomes):
            continue
        body[proposer_turn.OUTCOMES_KEY] = kept
        conn.execute("UPDATE analisi SET corpo_json = ? WHERE giorno = ?",
                     (json.dumps(body, ensure_ascii=False), row["giorno"]))


#: I passi della migrazione 15, in ordine (Tappa 8, Task 3). **Una
#: migrazione sola per la tappa**, con un passo per cambio: chi porta il suo
#: (la marca `regole` dei resoconti del Task 2, le parole degli stati delle
#: proposte del Task 4) aggiunge una funzione qui, idempotente, senza
#: riscrivere le altre. Vale finche' la 15 non e' uscita in un rilascio: dopo,
#: un passo nuovo e' una migrazione 16.
_MIGRATION_15_STEPS = (_drop_unread_reading_columns, _drop_actuator_proposals)


def _migration_15(conn) -> None:
    """v14 -> v15 (Tappa 8, «gli archivi seguono la casa»): i passi di
    `_MIGRATION_15_STEPS`.

    **Tutto o niente, in una transazione**, per la ragione di `_migration_12`
    (G14-1): un passo interrotto a meta' non lascia l'archivio dichiarato
    alla 15 con meta' dei cambi. Se uno fallisce si torna indietro, l'archivio
    resta alla 14 e la migrazione si rifa' al prossimo avvio.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN")
    try:
        for step in _MIGRATION_15_STEPS:
            step(conn)
    except BaseException:
        conn.rollback()
        raise


#: A che versione sta lo schema di questo archivio. Vive qui perche' chi lo
#: prova non debba ricopiarne il numero: un letterale in una prova e' un
#: doppione che mente al primo schema nuovo, e questa riga esiste perche' e'
#: successo (`test_migration_5...` inchiodava il 5).
SCHEMA_VERSION = 15

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


#: Le chiavi dentro un'analisi o un filo del «Rifalla» che `reseal` non
#: sigilla: non sono frasi, sono legami (l'impronta dell'antiripetizione, l'id
#: di una proposta, l'identita' di un turno). Oscurarne un pezzo romperebbe il
#: legame senza nascondere niente che qualcuno abbia scritto.
_SEAL_KEEPS = frozenset({"impronta", "proposta_id", "turno"})

#: Cio' che `_json_column` torna per un corpo che non si legge. Un oggetto e
#: non `None`: `null` e' un JSON valido, e una riga che lo porta non e' guasta.
_UNREADABLE = object()

#: Le righe guaste gia' dette nel log, `(tabella, chiave)`: una pagina che si
#: ricarica ogni pochi secondi non deve ripetere la stessa riga a ogni giro.
_unreadable_told: set[tuple[str, str]] = set()


def _json_column(raw, *, table: str, key) -> object:
    """Il corpo JSON di una colonna, o `_UNREADABLE` se non si legge (C-48,
    Tappa 8). **L'unico `json.loads` delle letture di questo archivio**: lo
    pretende `tests/test_mind_store.py`, chiedendolo ad `ast`. Le migrazioni
    hanno i loro, perche' devono dire fra due anni la stessa cosa.

    Fino alla Tappa 8 quattro letture avevano la guardia e sette no: con una
    riga storta `proposals()` faceva cadere l'intera `GET /api/constructions`,
    che fonde le due code. **Chi legge un elenco salta la riga guasta**, e il
    log lo dice una volta per riga, con la tabella e la chiave per ritrovarla.
    """
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        told = (table, str(key))
        if told not in _unreadable_told:
            _unreadable_told.add(told)
            logger.warning("osservazioni: la riga %s di `%s` ha un corpo JSON "
                           "illeggibile, e chi legge la salta", key, table)
        return _UNREADABLE


def _reading_row(r) -> dict:
    # `first_occurred` e' TEXT in colonna (stessa forma di `_add_missing_
    # columns`, vedi il suo docstring), ma e' un ISTANTE: si torna al
    # chiamante come `float | None`, non come la stringa grezza di SQLite --
    # e' l'unica delle colonne nuove per cui questo vale, perche' e' l'unica
    # numerica: `domain`/`title` sono gia' testo, nessuna conversione da fare.
    first_occurred = r["first_occurred"]
    return {"quando_ts": r["quando_ts"], "fonte": r["fonte"],
            "soggetto": r["soggetto"], "da": r["da"], "a": r["a"],
            "device_class": r["device_class"],
            "domain": r["domain"], "title": r["title"],
            "friendly_name": r["friendly_name"],
            # Il JSON resta una STRINGA fino a chi lo legge: una riga vecchia
            # potrebbe portare qualcosa che non si legge come JSON, e farlo
            # esplodere qui fermerebbe l'intera lettura del giorno invece di
            # una riga. Chi lo apre e' `mind/facts.py`, che sa cosa farsene.
            "attributes": r["attributes"],
            "first_occurred": None if first_occurred is None else float(first_occurred)}


def _scope_decision(r) -> dict:
    """Una riga di `scope` nella forma che ne esce, da `scope()` e da
    `decision()`: la stessa decisione ha la stessa forma dalle due porte."""
    return {"dentro": bool(r["inside"]), "motivo": r["reason"],
            "autore": r["author"], "quando": r["decided_ts"]}


class ObservationsStore:
    """La memoria dell'osservatore. Il lock e' lo stesso delle scritture anche
    in lettura: la connessione e' condivisa fra thread (`check_same_thread=
    False`), ed e' il pattern gia' consolidato in `action/journal.py`."""

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=SCHEMA_VERSION,
                    migrations={2: _migration_2, 3: _migration_3, 4: _migration_4,
                                5: _migration_5, 6: _migration_6,
                                7: _migration_7, 8: _migration_8,
                                9: _migration_9,
                                10: _migration_10, 11: _migration_11,
                                12: _migration_12, 13: _migration_13,
                                14: _migration_14, 15: _migration_15})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- i cambi -------------------------------------------------------

    def record(self, *, quando_ts: float, source: str, subject: str,
               da, a, device_class: str | None = None,
               domain: str | None = None, title: str | None = None,
               friendly_name: str | None = None,
               first_occurred: float | None = None,
               attributes: str | None = None) -> None:
        """Un cambio, cosi' com'e'. **Nessun giudizio in scrittura**: e' la
        condizione da cui dipende tutto il resto -- una decisione presa qui non
        si corregge piu', una presa in aggregazione si'.

        `fonte` e' vincolata a `'entita'` o `'sistema'` (CHECK di schema): un
        refuso dello scrittore futuro non deve entrare in silenzio.

        `device_class` e' la classe che Home Assistant dichiara sull'entita'
        -- **grezzo per definizione**, non un giudizio nostro: serve a
        `facts.genre_for` per decidere il genere di `sensor` e `binary_sensor`
        quando l'aggregazione rilegge la riga, giorni dopo che l'evento e'
        passato. Annullabile: le condizioni di sistema non la portano, e una
        riga scritta prima che la colonna esistesse la rilegge come `None`.
        `state_class` e `source_type` non si scrivono piu': nessuno le leggeva
        (`_migration_15`).

        `domain` e `title` sono dominio e titolo della voce di configurazione
        di una condizione di SISTEMA (`watcher.py::watch_system`) -- **grezzo
        anche loro**: stanno qui perche' fra tre settimane la voce potrebbe
        non esistere piu', e la riga deve dire ancora cosa si era rotto.
        Annullabili: le condizioni di entita' non li portano, e un `problema:`
        (un *repair* di Home Assistant) non ha un titolo -- `title=None` e'
        un campo vuoto dichiarato, non un buco.

        `friendly_name` e' il nome che Home Assistant ha GIA' composto per
        l'entita' al momento del cambio -- **grezzo anche lui**, e per la
        stessa ragione degli altri, piu' una che vale solo per lui: i
        resoconti sopravvivono ai `cambi`, quindi un nome risolto dopo su un
        giorno vecchio non si troverebbe piu' (vedi `_migration_5`).
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
                "domain,title,friendly_name,first_occurred,attributes) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (float(quando_ts), source, subject,
                 None if da is None else str(da), None if a is None else str(a),
                 device_class, domain, title, friendly_name,
                 None if first_occurred is None else str(float(first_occurred)),
                 attributes))
            self._conn.commit()

    # -- il resoconto --------------------------------------------------

    def replace_report(self, day: str, report: dict) -> None:
        """Scrive il resoconto di un giorno, **sostituendo** quello che c'era.

        **Rifare un giorno lo sostituisce e non lo accoda.** Sbagliare un
        resoconto costa **un giorno**, e solo
        finche' il grezzo di quel giorno esiste -- e' la promessa dei due
        strati, e senza la sostituzione non sarebbe vera.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO resoconto(giorno, corpo_json, scritto_ts) "
                "VALUES(?,?,?) ON CONFLICT(giorno) DO UPDATE SET "
                "corpo_json=excluded.corpo_json, scritto_ts=excluded.scritto_ts",
                (day, json.dumps(report, ensure_ascii=False), _time.time()))
            self._conn.commit()

    def reseal(self, seal_text) -> dict[str, int]:
        """Ripassa `seal_text` sui titoli GIA' scritti delle condizioni `log:`,
        sui `titolo` dei resoconti, sulle analisi e sulle proposte da fare a
        mano, e torna quante righe ha cambiato in ciascuna tabella.

        **Perche' esiste** (Tappa 3, Task 0, decisione del proprietario del
        03/10/2026). Fino alla 3.73.2 l'osservatore archiviava il titolo di
        una voce del registro di Home Assistant senza il sigillo dei segreti;
        le righe scritte allora restano nell'archivio ventidue giorni, e i
        resoconti che le citano piu' a lungo. Le sigilla l'add-on, all'avvio.

        `seal_text` e' una funzione testo -> testo (il sigillo lo sceglie chi
        chiama): l'archivio sa dove stanno i titoli, non cosa sia segreto.

        **Dei resoconti si sigilla ogni `titolo`**, a qualunque profondita':
        dentro la cronaca e il primo piano, anche quello di un'integrazione,
        che e' un nome scritto dal proprietario -- lo stesso prezzo dichiarato
        dal sigillo, un pezzo identico a un segreto viene oscurato.
        **`scritto_ts` non cambia**: sigillare non e' rifare il giorno, e
        l'istante e' cio' che sveglia il giro dell'analista
        (`report_stamps`).

        **Anche le analisi e le proposte da fare a mano** (S-32, Tappa 8):
        l'analista legge i resoconti e il proponente le analisi, e cio' che
        hanno scritto prima del sigillo puo' citare un titolo in chiaro, in
        qualunque frase. Dell'analisi si sigilla ogni testo; della proposta
        il testo, il perche', la nota dell'esito e il filo del «Rifalla». Non
        l'impronta: e' la chiave dell'antiripetizione, non una frase. Lo
        stesso prezzo dichiarato del sigillo, su piu' testo.

        Torna `{tabella: righe cambiate}` per `cambi`, `resoconto`, `analisi`
        e `proposte`. Idempotente: un testo gia' sigillato non cambia, e dal
        secondo avvio torna tutti zeri senza scrivere niente.
        """
        def prose(text):
            return seal_text(text) if isinstance(text, str) else text

        def resealed(value, *, every: bool = False):
            if isinstance(value, dict):
                return {key: (item if key in _SEAL_KEEPS
                              else seal_text(item)
                              if isinstance(item, str) and (every or key == "titolo")
                              else resealed(item, every=every))
                        for key, item in value.items()}
            if isinstance(value, list):
                return [seal_text(item) if every and isinstance(item, str)
                        else resealed(item, every=every) for item in value]
            return value

        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title FROM cambi WHERE fonte = 'sistema' "
                "AND soggetto LIKE 'log:%' AND title IS NOT NULL").fetchall()
            changed_rows = [(sealed, r["id"]) for r in rows
                            if (sealed := seal_text(r["title"])) != r["title"]]
            reports = self._conn.execute(
                "SELECT giorno, corpo_json FROM resoconto").fetchall()
            changed_reports = []
            for r in reports:
                body = _json_column(r["corpo_json"], table="resoconto", key=r["giorno"])
                if body is _UNREADABLE:
                    continue
                sealed = resealed(body)
                if sealed != body:
                    changed_reports.append(
                        (json.dumps(sealed, ensure_ascii=False), r["giorno"]))
            changed_analyses = []
            for r in self._conn.execute("SELECT giorno, corpo_json FROM analisi").fetchall():
                body = _json_column(r["corpo_json"], table="analisi", key=r["giorno"])
                if body is _UNREADABLE:
                    continue
                sealed = resealed(body, every=True)
                if sealed != body:
                    changed_analyses.append(
                        (json.dumps(sealed, ensure_ascii=False), r["giorno"]))
            changed_proposals = []
            for r in self._conn.execute(
                    "SELECT id, testo, perche, esito_nota, giri_json "
                    "FROM proposte").fetchall():
                rounds = _json_column(r["giri_json"], table="proposte", key=r["id"])
                if rounds is _UNREADABLE:
                    continue
                before = (r["testo"], r["perche"], r["esito_nota"], rounds)
                after = (prose(r["testo"]), prose(r["perche"]),
                         prose(r["esito_nota"]), resealed(rounds, every=True))
                if after != before:
                    changed_proposals.append(
                        (*after[:3], json.dumps(after[3], ensure_ascii=False), r["id"]))
            if changed_rows or changed_reports or changed_analyses or changed_proposals:
                self._conn.executemany("UPDATE cambi SET title = ? WHERE id = ?",
                                       changed_rows)
                self._conn.executemany(
                    "UPDATE resoconto SET corpo_json = ? WHERE giorno = ?",
                    changed_reports)
                self._conn.executemany(
                    "UPDATE analisi SET corpo_json = ? WHERE giorno = ?",
                    changed_analyses)
                self._conn.executemany(
                    "UPDATE proposte SET testo = ?, perche = ?, esito_nota = ?, "
                    "giri_json = ? WHERE id = ?", changed_proposals)
                self._conn.commit()
        return {"cambi": len(changed_rows), "resoconto": len(changed_reports),
                "analisi": len(changed_analyses), "proposte": len(changed_proposals)}

    def report(self, day: str) -> dict | None:
        """Il resoconto di un giorno, o `None` se quel giorno non e' mai stato
        aggregato. **Non e' un resoconto vuoto**: «non e' successo niente» e
        «non l'abbiamo guardato» sono due cose diverse.

        Un corpo illeggibile torna `None` come `analysis()`, e il log lo dice
        (`_json_column`): il giro dei resoconti lo rifa' finche' il grezzo
        c'e', e lo rifa' sostituendolo."""
        with self._lock:
            row = self._conn.execute(
                "SELECT corpo_json FROM resoconto WHERE giorno = ?",
                (day,)).fetchone()
        if row is None:
            return None
        body = _json_column(row["corpo_json"], table="resoconto", key=day)
        return None if body is _UNREADABLE else body

    def reports(self, *, limit: int = 30) -> list[dict]:
        """Gli ultimi resoconti, dal piu' recente.

        E' la lettura che serve all'analista: **le misure di molti giorni
        insieme**, che e' il modo in cui due dei suoi tre inneschi si pongono.
        Il tetto e' un mese perche' e' la finestra in cui uno scostamento ha
        senso su una casa -- e perche' oltre, per l'84% delle entita', non c'e'
        piu' niente con cui scavare.
        """
        with self._lock:
            righe = self._conn.execute(
                "SELECT giorno, corpo_json FROM resoconto ORDER BY giorno DESC LIMIT ?",
                (int(max(1, limit)),)).fetchall()
        bodies = (_json_column(r["corpo_json"], table="resoconto", key=r["giorno"])
                  for r in righe)
        return [body for body in bodies if body is not _UNREADABLE]

    def oldest_reading_ts(self) -> float | None:
        """L'istante della riga piu' vecchia del grezzo, o `None` se non ce
        n'e' nessuna.

        Serve a sapere **fin dove indietro ha senso rifare un giorno**: un
        giorno si rifa' solo finche' il suo grezzo esiste (spec §9), e oltre
        questo istante non c'e' piu' niente da rileggere. Lo sa l'archivio, non
        chi lo usa: chiederlo altrove vorrebbe dire ricostruire la potatura a
        mano, e una copia del ragionamento che diverge alla prima modifica
        della conservazione.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(quando_ts) AS primo FROM cambi").fetchone()
        return None if row is None or row["primo"] is None else float(row["primo"])

    def readings_count(self, *, from_ts: float, to_ts: float) -> int:
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
        with self._lock:
            return int(self._conn.execute(sql, args).fetchone()["n"])

    def readings(self, *, from_ts: float, to_ts: float,
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
        if source is not None:
            sql += " AND fonte = ?"
            args.append(source)
        sql += " ORDER BY quando_ts ASC, id ASC LIMIT ?"
        args.append(int(max(1, limit)))
        with self._lock:
            rows = self._conn.execute(sql, tuple(args)).fetchall()
        return [_reading_row(r) for r in rows]

    def last_before(self, ts: float, *, since_ts: float,
                    source: str = "entita") -> list[dict]:
        """L'ultima riga PRIMA di un istante, **una per soggetto**, dentro la
        finestra `[since_ts, ts)`.

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

        **La finestra la dichiara chi chiede** (`since_ts`, Task 1.4 degli
        attori, 05/10/2026). Fino a quel giorno non c'era: «la potatura tiene
        il grezzo a 22 giorni» -- ma la potatura gira alle 03:00 e puo' non
        girare, e una riga che sopravvive solo per quello cambiava la cronaca
        di un giorno secondo l'ora in cui la si costruiva. Misurato sulla casa
        vera: 4 voci fra il 30/09 e il 04/10 venivano da una riga dell'11/09.
        Il `ROW_NUMBER()` fa il lavoro nel motore invece di portare in Python
        centomila righe per tenerne una manciata.

        **Non e' l'inizio di niente**: e' l'ultima riga, di qualunque stato.
        Da dove comincia cio' che e' in corso lo ricostruisce chi giudica
        (`facts.build_episodes`) rigiocando `transitions`.
        """
        sql = ("SELECT * FROM (SELECT *, ROW_NUMBER() OVER "
               "(PARTITION BY soggetto ORDER BY quando_ts DESC, id DESC) AS rn "
               "FROM cambi WHERE quando_ts >= ? AND quando_ts < ? AND fonte = ?) "
               "WHERE rn = 1")
        with self._lock:
            rows = self._conn.execute(sql, (float(since_ts), float(ts), source)).fetchall()
        return [_reading_row(r) for r in rows]

    def transitions(self, subjects, *, from_ts: float, to_ts: float) -> list[dict]:
        """I cambi di STATO di questi soggetti nella finestra semi-aperta
        `[from_ts, to_ts)`, dal piu' vecchio: le righe in cui `da` e `a`
        differiscono, e la prima riga di ciascuno.

        Le righe di solo attributo (`da == a`, scritte da `watcher` quando
        cambia un attributo voluto) restano fuori: non aprono e non chiudono
        niente, e sui termostati sono la maggior parte del grezzo. **Tranne la
        PRIMA riga di ciascun soggetto nella finestra**, di qualunque forma:
        dice in che stato la finestra comincia. Senza, un termostato acceso
        prima della finestra -- la riga che l'ha acceso potata -- non aveva
        nessun cambio da rigiocare, e il suo episodio in corso spariva dalla
        cronaca (revisione cloud, giro 3, 05/10/2026). **Nessun
        giudizio**: quale stato sia un riposo lo decide chi legge
        (`facts.build_episodes`, che rigioca queste righe con la regola del
        giorno per sapere da quando e' in corso cio' che e' in corso a
        mezzanotte). Solo `fonte = 'entita'`.
        """
        wanted = sorted({str(s) for s in subjects or ()})
        if not wanted:
            return []
        marks = ",".join("?" * len(wanted))
        window = (f"fonte = 'entita' AND quando_ts >= ? AND quando_ts < ? "
                  f"AND soggetto IN ({marks})")
        sql = (f"SELECT * FROM cambi WHERE {window} AND (da IS NOT a OR id IN ("
               "SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY soggetto "
               f"ORDER BY quando_ts ASC, id ASC) AS rn FROM cambi WHERE {window}) "
               "WHERE rn = 1)) ORDER BY quando_ts ASC, id ASC")
        args = (float(from_ts), float(to_ts), *wanted)
        with self._lock:
            rows = self._conn.execute(sql, args + args).fetchall()
        return [_reading_row(r) for r in rows]

    def last_seen(self, subjects) -> dict[str, float]:
        """L'istante dell'ultima riga del grezzo di ciascun soggetto, **di
        qualunque stato e di qualunque giorno**: l'ultima volta che Home
        Assistant ce ne ha parlato. Un soggetto senza righe non c'e'.

        Serve alla cronaca per chiudere l'episodio di una fonte che Home
        Assistant non nomina piu' (`facts.build_episodes`, Task 1.4 degli
        attori): un'entita' disabilitata o rimossa non manda un ultimo cambio
        (`watcher.watch_reading` scarta `new_state` a `None`), e la sua ultima
        riga -- spesso l'`unavailable` di un riavvio -- e' l'ultima cosa che
        se ne sa. Solo `fonte = 'entita'`: una condizione di sistema non e' una
        fonte della casa.
        """
        wanted = sorted({str(s) for s in subjects or ()})
        if not wanted:
            return {}
        marks = ",".join("?" * len(wanted))
        with self._lock:
            rows = self._conn.execute(
                "SELECT soggetto, MAX(quando_ts) AS ultimo FROM cambi "
                f"WHERE fonte = 'entita' AND soggetto IN ({marks}) GROUP BY soggetto",
                tuple(wanted)).fetchall()
        return {r["soggetto"]: float(r["ultimo"]) for r in rows}

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
        return {r["subject"]: _scope_decision(r) for r in rows}

    def decision(self, subject: str) -> dict | None:
        """La decisione su un soggetto, nella forma di una voce di `scope()`,
        o `None` se nessuno ha deciso (A-37, Tappa 8). **Una riga per chiave
        primaria**: chi decide su un soggetto solo non rilegge il perimetro
        intero, centinaia di righe a ogni decisione."""
        with self._lock:
            row = self._conn.execute(
                "SELECT inside, reason, author, decided_ts FROM scope WHERE subject = ?",
                (subject,)).fetchone()
        return None if row is None else _scope_decision(row)

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
        standing = self.decision(subject)
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

        E' l'ultimo scritto, a qualunque istante: lo stesso `_objective_row`
        di `objective_at`, senza confine.
        """
        return self._objective_row(float("inf"))

    def _objective_row(self, ts: float) -> dict:
        """L'ultimo obiettivo scritto fino a `ts` incluso, o quello di
        fabbrica (G-17, Tappa 8): la query sta qui una volta, per `objective`
        e `objective_at`. La copia in `_migration_9` resta: una migrazione
        deve dire fra due anni la stessa cosa, anche se questo metodo cambia."""
        with self._lock:
            row = self._conn.execute(
                "SELECT text, written_ts FROM objective WHERE written_ts <= ? "
                "ORDER BY written_ts DESC, id DESC LIMIT 1", (float(ts),)).fetchone()
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

    def objective_at(self, ts: float) -> dict:
        """L'obiettivo che valeva a quell'istante -- la domanda che il resoconto
        porra' a ogni giornata che rilegge.

        Il confine e' incluso: un obiettivo scritto alle 14:00 vale per le
        14:00. Prima del primo scritto vale quello di fabbrica: la casa c'era
        comunque, e l'osservatore guardava.
        """
        return self._objective_row(ts)

    # -- l'analisi (spec §10) ------------------------------------------

    def replace_analysis(self, day: str, analysis: dict) -> None:
        """Scrive l'analisi di un giorno, sostituendo quella che c'era.

        Stessa disciplina di `replace_report`: rifare un giorno lo RIFA', non
        lo accoda -- e un'analisi accodata darebbe due verita' sullo stesso
        giorno, che e' il difetto che «costruire» ha gia' pagato.
        """
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO analisi(giorno,corpo_json,scritto_ts) "
                "VALUES(?,?,?)",
                (day, json.dumps(analysis, ensure_ascii=False), _time.time()))
            self._conn.commit()

    def report_stamps(self, *, limit: int = 30) -> list[tuple[str, float]]:
        """`(giorno, scritto_ts)` degli ultimi resoconti, **senza i corpi**.

        E' la lettura con cui il giro dell'analista si chiede se il suo
        fondamento e' cambiato, e gira ogni ora: caricare 146 serie per
        confrontare un'impronta sarebbe pagare un costo per non usarlo.

        **`scritto_ts` e non il solo giorno**: un giorno rifatto -- dopo una
        correzione di giudizio, o un recupero -- puo' avere lo stesso
        contenuto e lo stesso nome, ed e' l'istante a dire che qualcuno lo ha
        toccato.
        """
        with self._lock:
            righe = self._conn.execute(
                "SELECT giorno, scritto_ts FROM resoconto ORDER BY giorno DESC LIMIT ?",
                (int(max(1, limit)),)).fetchall()
        return [(r[0], r[1]) for r in righe]

    #: Gli esiti che chiudono una proposta da fare a mano. **Chiusi**: una
    #: parola nuova arriverebbe da una rotta e diventerebbe uno stato che
    #: nessuna pagina sa disegnare. `crea` non c'e' -- qui non c'e' niente da
    #: scrivere in Home Assistant: quella strada e' l'officina. `superata`
    #: la scrive solo il proponente, quando la stessa domanda torna come
    #: proposta costruita (D24-1, scelta del proprietario del 06/10/2026):
    #: nessuna rotta la offre.
    PROPOSAL_OUTCOMES = ("rifiutata", "fatta_fuori", "superata")

    #: L'esito di una proposta da fare a mano da cui e' nata un'automazione
    #: («Rendila automatica», attori Task 4.5; chiudere col legame, scelta
    #: del proprietario del 06/10/2026). Non sta fra `PROPOSAL_OUTCOMES`:
    #: quelli li chiude una persona dalla pagina, questo lo chiude solo
    #: `automate_proposal`, con l'id della costruzione accanto.
    PROPOSAL_AUTOMATED = "automatizzata"

    #: Lo stato di una proposta da fare a mano che aspetta la tua risposta.
    #: Scritto una volta: lo usano le istruzioni qui sotto e la pagina delle
    #: Proposte, che lo riceve gia' deciso (`sospesa`,
    #: `handlers_constructions._both_queues`; C-12, Tappa 4, Task 5).
    PROPOSAL_PENDING = "attesa"

    def add_proposal(self, *, text: str, perche: str, fingerprint: str,
                     prova: dict, stakes: str | None, now_ts: float) -> str:
        """Scrive una proposta da fare a mano, e torna il suo identificativo.

        **Senza impronta non si scrive**: e' cio' su cui si regge
        l'anti-ripetizione, e senza la stessa proposta tornerebbe ogni giorno.
        """
        if not str(fingerprint or "").strip():
            raise ValueError("una proposta senza impronta tornerebbe ogni giorno")
        ident = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO proposte(id,creata_ts,stato,testo,perche,"
                "impronta,prova_json,giri_json,stakes) "
                "VALUES(?,?,?,?,?,?,?,'[]',?)",
                (ident, now_ts, self.PROPOSAL_PENDING, text, perche, fingerprint,
                 json.dumps(prova or {}, ensure_ascii=False), stakes))
            self._conn.commit()
        return ident

    def proposals(self, *, pending_only: bool = False, limit: int = 200,
                  ident: str | None = None) -> list[dict]:
        """Le proposte da fare a mano, dalla piu' recente. Con `ident`, solo
        quella (`proposal`)."""
        sql = ("SELECT id,creata_ts,stato,testo,perche,impronta,prova_json,"
               "giri_json,esito_nota,stakes,construction_id,automation_refusal "
               "FROM proposte")
        args: tuple = ()
        if pending_only:
            sql += " WHERE stato = ?"
            args = (self.PROPOSAL_PENDING,)
        if ident is not None:
            sql += (" AND" if args else " WHERE") + " id = ?"
            args = (*args, ident)
        sql += " ORDER BY creata_ts DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(sql, (*args, int(max(1, limit)))).fetchall()
        out = []
        for r in rows:
            prova = _json_column(r[6], table="proposte", key=r[0])
            rounds = _json_column(r[7], table="proposte", key=r[0])
            if prova is _UNREADABLE or rounds is _UNREADABLE:
                continue
            out.append({"id": r[0], "creata_ts": r[1], "stato": r[2], "testo": r[3],
                        "perche": r[4], "impronta": r[5], "prova": prova,
                        "giri": rounds, "esito_nota": r[8], "livello": r[9],
                        "costruzione_id": r[10], "non_automatizzabile": r[11]})
        return out

    def proposal(self, ident: str) -> dict | None:
        """Una proposta da fare a mano per id, o `None`. **Per id, non fra le
        ultime**: cercarla nelle prime `limit` di `proposals()` la perdeva
        quando ce n'erano piu' di 200 piu' recenti, e la tabella non ha
        scadenza (revisione C3, 07/10/2026)."""
        found = self.proposals(ident=ident, limit=1)
        return found[0] if found else None

    def pending_proposals_count(self) -> int:
        """Quante proposte da fare a mano aspettano una risposta, **contate in
        SQL** (Tappa 8, T3): la lunghezza di `proposals()` si fermava al suo
        tetto di 200 senza dirlo, la stessa ragione di `readings_count`."""
        with self._lock:
            return int(self._conn.execute(
                "SELECT COUNT(*) FROM proposte WHERE stato = ?",
                (self.PROPOSAL_PENDING,)).fetchone()[0])

    def proposal_origins(self, construction_ids) -> dict[str, dict]:
        """`{id della costruzione: {"id", "testo"}}`: la proposta a mano da cui
        e' nata ciascuna di queste costruzioni («Rendila automatica», Task
        4.5), chiesta per legame (Tappa 8, T3). Cercata fra le ultime 200 di
        `proposals()` si perdeva quando la proposta era piu' vecchia."""
        wanted = sorted({str(c) for c in construction_ids or () if c})
        if not wanted:
            return {}
        marks = ",".join("?" * len(wanted))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, testo, construction_id FROM proposte "
                f"WHERE construction_id IN ({marks})", tuple(wanted)).fetchall()
        return {r["construction_id"]: {"id": r["id"], "testo": r["testo"]} for r in rows}

    def close_proposal(self, ident: str, occurrence: str, *,
                       why: str | None = None) -> bool:
        """Chiude una proposta con uno dei suoi esiti. Torna se ha toccato una riga."""
        if occurrence not in self.PROPOSAL_OUTCOMES:
            raise ValueError(
                f"esito sconosciuto: {occurrence!r}. Gli esiti sono "
                + ", ".join(self.PROPOSAL_OUTCOMES))
        with self._lock:
            cur = self._conn.execute(
                "UPDATE proposte SET stato=?, esito_nota=? WHERE id=? AND stato=?",
                (occurrence, why, ident, self.PROPOSAL_PENDING))
            self._conn.commit()
        return cur.rowcount > 0

    def automate_proposal(self, ident: str, construction_id: str) -> bool:
        """Chiude una proposta in attesa perche' ne e' nata la costruzione
        `construction_id`. Torna se ha toccato una riga: una proposta gia'
        decisa non si richiude, e una seconda costruzione dello stesso turno
        non sostituisce la prima."""
        if not str(construction_id or "").strip():
            raise ValueError("una proposta automatizzata porta l'id della costruzione")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE proposte SET stato=?, construction_id=? "
                "WHERE id=? AND stato=?",
                (self.PROPOSAL_AUTOMATED, construction_id, ident,
                 self.PROPOSAL_PENDING))
            self._conn.commit()
        return cur.rowcount > 0

    def refuse_automation(self, ident: str, reason: str) -> bool:
        """Scrive perche' una proposta in attesa non si e' potuta rendere
        automatica. La proposta resta in attesa: la si puo' ancora fare, o
        rifare."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE proposte SET automation_refusal=? WHERE id=? AND stato=?",
                (reason, ident, self.PROPOSAL_PENDING))
            self._conn.commit()
        return cur.rowcount > 0

    def add_proposal_round(self, ident: str, *, request: str, outcome: str,
                           turn: str, now_ts: float, text: str | None = None,
                           why: str | None = None,
                           built: str | None = None) -> bool:
        """Accoda un giro di «Rifalla» al filo della proposta. Torna se l'ha
        scritto.

        Il filo si accoda e non si sostituisce: il modello deve vedere cosa e'
        stato scartato, o potrebbe tornare alla prima forma al secondo giro.
        Un giro **non chiude niente**: la proposta resta com'e', in attesa o
        no -- la chiude, quando serve, chi lo chiama.

        `outcome` e' l'esito del proponente (`proposer_turn.OUTCOMES`, attori,
        Task 4.4):
        - **a mano**: `text` e `why` sostituiscono testo e perche', e il
          giro conserva la forma scartata;
        - **niente**: la proposta resta com'era, e il giro porta il perche';
        - **costruita**: il giro porta l'id della proposta costruita.

        `turn` e' l'identita' del turno che ha risposto: **lo stesso turno non
        scrive due giri**, ed e' cio' che rende innocua una seconda consegna.
        """
        if outcome not in ("a_mano", "niente", "costruita"):
            raise ValueError(f"esito di un giro sconosciuto: {outcome!r}")
        with self._lock:
            row = self._conn.execute(
                "SELECT testo, perche, giri_json FROM proposte WHERE id=?",
                (ident,)).fetchone()
            if row is None:
                return False
            # Un filo illeggibile non si riscrive da capo: si perderebbe
            # cio' che c'era. Il giro non si scrive, e il log lo dice.
            rounds = _json_column(row[2], table="proposte", key=ident)
            if rounds is _UNREADABLE or any(r.get("turno") == turn for r in rounds):
                return False
            entry = {"richiesta": request, "esito": outcome, "turno": turn,
                     "quando_ts": now_ts}
            kept_text, kept_why = row[0], row[1]
            refusal_sql = ""
            if outcome == "a_mano":
                entry["scartata"] = kept_text
                # Il testo cambia, e la ragione con lui: una proposta nuova
                # con la ragione vecchia sarebbe una riga che non si spiega.
                kept_text, kept_why = text or kept_text, why or kept_why
                # Una forma nuova si puo' rendere automatica anche se la
                # vecchia no: il rifiuto di «Rendila automatica» era di
                # quella. Con «niente» la forma e' la stessa e il rifiuto
                # resta vero; con «costruita» la proposta si chiude.
                refusal_sql = ", automation_refusal=NULL"
            elif outcome == "niente":
                entry["perche"] = why
            else:
                entry["proposta_id"] = built
            rounds.append(entry)
            self._conn.execute(
                "UPDATE proposte SET testo=?, perche=?, giri_json=?"
                + refusal_sql + " WHERE id=?",
                (kept_text, kept_why, json.dumps(rounds, ensure_ascii=False), ident))
            self._conn.commit()
        return True

    def decided_proposals(self) -> dict[str, dict]:
        """`{impronta: {"prova", "aperta", "creata_ts", "id", "a_mano"}}`:
        cio' che il proponente deve sapere per non rifare una proposta
        (`proposer_turn.already_answered`). La stessa forma di
        `ConstructionStore.decided_proposals`: le due code si fondono in
        `proposer_turn.latest_decided`.

        Per ogni impronta conta **l'ultima** proposta: dopo una prova cambiata
        la stessa domanda ha due righe, e a decidere e' la piu' recente.
        `aperta` dice se aspetta ancora una risposta. Una decisa vale solo per
        la prova contro cui e' stata decisa (S-26, scelta del proprietario del
        06/10/2026).
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT impronta, prova_json, stato, creata_ts, id FROM proposte "
                "ORDER BY creata_ts, rowid").fetchall()
        decided = {}
        for r in rows:
            prova = _json_column(r[1], table="proposte", key=r[4])
            if prova is not _UNREADABLE:
                decided[r[0]] = {"prova": prova, "aperta": r[2] == self.PROPOSAL_PENDING,
                                 "creata_ts": r[3], "id": r[4], "a_mano": True}
        return decided

    def analysis(self, day: str) -> dict | None:
        """L'analisi di quel giorno, o `None` se non ne ha una.

        `None` significa **non e' girata**, e non «non aveva niente da dire»:
        il silenzio e' una riga con zero osservazioni, e si distingue.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT corpo_json FROM analisi WHERE giorno = ?", (day,)).fetchone()
        if row is None:
            return None
        body = _json_column(row["corpo_json"], table="analisi", key=day)
        return None if body is _UNREADABLE else body

    def analyses(self, *, limit: int = 30) -> list[dict]:
        """Le analisi, **dalla piu' recente**: una cronaca si legge da adesso
        all'indietro, come gli obiettivi e i resoconti."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT giorno, corpo_json FROM analisi "
                "ORDER BY giorno DESC LIMIT ?", (int(limit),)).fetchall()
        out = []
        for row in rows:
            body = _json_column(row["corpo_json"], table="analisi", key=row["giorno"])
            if body is not _UNREADABLE:
                out.append({**body, "giorno": row["giorno"]})
        return out

    def prune(self, now_ts: float) -> int:
        """Applica `CONSERVAZIONE`, tabella per tabella. Torna le righe tolte.

        **Non c'e' piu' una tabella senza una decisione scritta accanto**
        (reperto C-6, 23/09/2026). Prima questa funzione conosceva una sola
        tabella e le altre sette restavano per sempre senza che nessuno
        l'avesse deciso.

        Chi sta a `None` non si tocca, ed e' la maggioranza: analisi,
        resoconti, proposte, obiettivo, perimetro e riconsiderazioni sono cio'
        che si e' capito e cio' che il proprietario ha deciso -- una potatura
        che se li portasse via cancellerebbe mesi per liberare qualche
        megabyte.
        """
        righe_tolte = 0
        with self._lock:
            for giorni, _ragione, cancellazione in CONSERVAZIONE.values():
                if giorni is None or cancellazione is None:
                    continue
                cur = self._conn.execute(
                    cancellazione, (float(now_ts) - giorni * 86400,))
                righe_tolte += cur.rowcount or 0
            self._conn.commit()
        return righe_tolte
