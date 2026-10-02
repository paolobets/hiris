"""L'archivio dei consumi: l'UNICA casa di «quanto ho speso, e per cosa».

Un secchiello al giorno per `(provider, modello)`: cinque righe al giorno anche
usando cinque modelli, meno di duemila l'anno. La storia si tiene per sempre
senza una politica di ritenzione da governare e senza mai cancellare dati
dell'utente a scadenza.

Non legge l'orologio: lo riceve (`now=`), come l'archivio delle promesse e
come `home_space/briefing.compose`. E non legge il fuso alla costruzione ma a ogni
scrittura: la casa puo' cambiarlo (`core_config_updated`), e un fuso cotto qui
dentro sarebbe quello di quando l'add-on e' partito.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading

from ..home_space.privacy import POSITION_ATTRIBUTES
from ..proxy.entity_cache import CALL_ARGUMENT_SECRETS, is_credential
from ..storage import connect, init_schema
from .vocabulary import local_day, piu_debole

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consumo_giorno (
    giorno            TEXT    NOT NULL,
    provider          TEXT    NOT NULL,
    modello           TEXT    NOT NULL,
    richieste         INTEGER NOT NULL DEFAULT 0,
    token_in          INTEGER NOT NULL DEFAULT 0,
    token_out         INTEGER NOT NULL DEFAULT 0,
    cache_lettura     INTEGER NOT NULL DEFAULT 0,
    cache_scrittura   INTEGER NOT NULL DEFAULT 0,
    costo_usd         REAL,
    costo_stato       TEXT    NOT NULL,
    errori_rate_limit INTEGER NOT NULL DEFAULT 0,
    primo_ts          REAL    NOT NULL,
    ultimo_ts         REAL    NOT NULL,
    PRIMARY KEY (giorno, provider, modello)
);
CREATE INDEX IF NOT EXISTS idx_consumo_giorno ON consumo_giorno(giorno);
CREATE TABLE IF NOT EXISTS ancora (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    da_ts REAL NOT NULL,
    da_giorno TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ancora_saldo (
    provider TEXT NOT NULL, modello TEXT NOT NULL,
    richieste INTEGER NOT NULL DEFAULT 0, token_in INTEGER NOT NULL DEFAULT 0,
    token_out INTEGER NOT NULL DEFAULT 0, cache_lettura INTEGER NOT NULL DEFAULT 0,
    cache_scrittura INTEGER NOT NULL DEFAULT 0, costo_usd REAL,
    errori_rate_limit INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, modello)
);
CREATE TABLE IF NOT EXISTS legacy_importati (percorso TEXT PRIMARY KEY);
-- **I giri passati dal forfait al consumo** (reperto C-5, 23/09/2026).
--
-- Sta QUI perche' un ripiego e' un fatto sui soldi, e questo archivio e' gia'
-- «l'UNICA casa di quanto ho speso, e per cosa». La pagina Consumi e' dove il
-- proprietario va a chiedersi perche' la bolletta e' cresciuta.
--
-- La chiave e' (giorno, agente, motivo) e non una sola delle tre. L'agente
-- perche' e' quello che si va a spegnere o a limitare; il motivo perche'
-- «manca il token» si risolve incollando un token e «tetto giornaliero» si
-- risolve alzando un numero -- sommarli direbbe una cosa sola dove ce ne sono
-- due, e nessuna delle due azioni.
-- Colonne NUOVE, quindi in inglese: le italiane di questo file sono debito
-- dichiarato, e si migrano in una fetta loro.
CREATE TABLE IF NOT EXISTS fallback (
    day       TEXT    NOT NULL,
    agent     TEXT    NOT NULL,
    reason    TEXT    NOT NULL,
    count     INTEGER NOT NULL DEFAULT 0,
    first_ts  REAL    NOT NULL,
    last_ts   REAL    NOT NULL,
    PRIMARY KEY (day, agent, reason)
);
-- **I due registri della misura** (23/09/2026). Stanno qui e non in un
-- archivio nuovo perche' rispondono alla stessa domanda di questo file --
-- quanto costa un turno -- solo che la misurano in token E in secondi.
--
-- `turn` e' un turno intero; `payload` e' UN GIRO di quel turno. La divisione
-- non e' normalizzazione per gusto: la moltiplicazione della latenza avviene
-- per giro, e una media per turno la nasconderebbe.
--
-- `tools` porta i NOMI in ordine; `tool_args` (dal 29/09/2026, spec «una porta
-- sola» §7) i loro ARGOMENTI, ridotti (testi a 200 caratteri, 20 chiavi) e
-- allineati per posizione. Il 29/09 nessuno ha saputo dire quale `search`
-- avesse mancato l'Indifferenziato, perche' c'erano solo i nomi. Un `view`
-- porta il nome di una stanza e questo archivio entra nei backup di Home
-- Assistant: e' una scelta dichiarata, e le CREDENZIALI non entrano mai --
-- il valore di `code`, `pin`, `password`, `token`... si scrive `***`.
--
-- Colonne NUOVE, quindi in inglese.
-- `subject_json` ha la STESSA forma del soggetto della cronaca
-- (`action/journal.py`), e non e' un caso: e' la stessa domanda -- chi sta
-- chiedendo, e da quale sistema. Oggi la chat e' una sola; il giorno in cui
-- HIRIS riceve input da chat diverse per utente e per sistema (Retro Panel,
-- per dire), `species='chat'` le schiaccerebbe insieme -- lo stesso difetto
-- di `agent_type='observer'` che schiaccia osservatore e ricette. Una
-- colonna sola per tutte e quattro le specie di soggetto, come per la
-- cronaca: `NULL` quando non c'e' nessuna persona, che e' il fatto giusto
-- per i giri notturni.
--
-- `channel` e' QUALE dei quattro composer ha spedito. I quattro compongono
-- la stessa cosa in quattro posti, e sono gia' divergiti una volta -- il
-- fix e' inchiodato da `tests/test_composition_order.py`. Senza questa
-- colonna, «il ponte e la catena mandano la stessa cosa?» resta una
-- speranza.
CREATE TABLE IF NOT EXISTS turn (
    id           TEXT    PRIMARY KEY,
    ts           REAL    NOT NULL,
    species      TEXT    NOT NULL,
    provider     TEXT    NOT NULL,
    model        TEXT    NOT NULL,
    channel      TEXT    NOT NULL,
    subject_json TEXT,
    duration_ms  INTEGER NOT NULL,
    iterations   INTEGER NOT NULL,
    tools        TEXT    NOT NULL,
    outcome      TEXT    NOT NULL,
    -- `list_cost_usd`: quanto sarebbe costato il turno A CONSUMO, come lo
    -- dichiara la CLI del ponte (`modelUsage[*].costUSD`). NON e' un costo
    -- pagato -- sul ponte il turno e' compreso nell'abbonamento -- e per
    -- questo non sta in `payload.cost_usd`: due cose diverse, due colonne.
    output_tokens INTEGER,
    list_cost_usd REAL,
    tool_args     TEXT
);
CREATE INDEX IF NOT EXISTS idx_turn_ts ON turn(ts DESC);
-- `prefix_hash` e' l'impronta di cio' che DOVREBBE essere stabile fra un
-- turno e l'altro -- guida piu' definizioni degli strumenti. E' la misura
-- che decide da sola una domanda che altrimenti resta un'ipotesi: sulla
-- catena il 74% della materia in ingresso si paga a prezzo pieno, e il
-- caching di quei provider e' implicito e per PREFISSO. Se l'impronta
-- cambia fra i turni, la cache non puo' colpire e il colpevole e' dentro il
-- prefisso; se resta uguale e il 74% non scende, non e' roba nostra.
--
-- `tools_sent` e' quante definizioni sono state SPEDITE. Con `turn.tools`,
-- che dice quante ne sono state usate, la differenza e' lo spreco --
-- moltiplicato per il numero di giri.
--
-- **I token accanto ai caratteri** (28/09/2026, spec «le misure complete»
-- §2). I caratteri dicono DI COSA e' fatto il carico; i token dicono QUANTO
-- e' costato davvero, cache compresa. Tutti NULL-abili: una riga scritta
-- prima di questa versione, o un provider che non dichiara la cache, non ha
-- il numero, e NULL e' «non misurato» -- zero sarebbe «non e' costato niente».
-- `cache_ttl`: `5m`, `1h`, `misto`, o NULL quando il provider non lo dice.
CREATE TABLE IF NOT EXISTS payload (
    turn_id       TEXT    NOT NULL,
    iteration     INTEGER NOT NULL,
    ts            REAL    NOT NULL,
    tools_chars   INTEGER NOT NULL,
    tools_sent    INTEGER NOT NULL DEFAULT 0,
    guide_chars   INTEGER NOT NULL,
    core_chars    INTEGER NOT NULL,
    history_chars INTEGER NOT NULL,
    results_chars INTEGER NOT NULL,
    prefix_hash   TEXT    NOT NULL DEFAULT '',
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    cache_ttl          TEXT,
    cost_usd           REAL,
    PRIMARY KEY (turn_id, iteration)
);
"""

#: **Per quanto si tengono i due registri della misura.** Trenta giorni, e si
#: dichiara: un registro di misura che cresce per sempre e' esattamente il
#: difetto che il reperto C-6 ha chiuso il 23/09/2026 -- ogni archivio dice
#: per quanto tiene. E' il SOLO contenuto di questo file che scade: i
#: secchielli al giorno sono minuscoli (meno di duemila righe l'anno) e
#: restano per sempre, con la loro ragione scritta in cima al modulo. Questi
#: no: un turno puo' scrivere fino a cinquanta righe di `payload`.
TURNS_RETENTION_S = 30 * 86400

#: Le colonne dei token di un giro, nell'ordine della tabella. **Una sola
#: lista, dentro questo file**: la leggono la migrazione, l'INSERT e la
#: lettura, e una colonna nuova non puo' entrare in due posti su tre. Chi
#: compone le righe (`steering`, `usage/giro.py`) NON la legge: scrive le
#: chiavi per nome, e `log_payload` le riceve come argomenti.
TOKEN_COLUMNS = ("input_tokens", "output_tokens", "cache_read_tokens",
                 "cache_write_tokens", "cache_ttl", "cost_usd")


def _migration_2(conn) -> None:
    """Versione 2 (28/09/2026, spec «le misure complete» §2): i token.

    `ALTER TABLE ADD COLUMN` solo se la colonna manca, come le altre
    migrazioni del progetto (`reasoning/queue.py::_migration_2`). Non per
    una seconda apertura -- quella la salta `user_version` -- ma per due
    casi in cui la migrazione ritrova colonne gia' aggiunte:

    (a) il ritorno alla 3.69.x: la versione vecchia apre l'archivio con
        `version=1` e lo ritimbra `user_version = 1`, ma le colonne restano;
        il nuovo aggiornamento rifa' la migrazione 2 su di esse;
    (b) il DDL di SQLite fa commit da solo: un crollo fra gli `ALTER` e il
        timbro lascia un archivio alla versione 1 con parte delle colonne.

    Le righe gia' scritte restano NULL -- non sono state misurate, e non si
    inventa che lo siano.
    """
    columns = {r[1] for r in conn.execute("PRAGMA table_info(payload)").fetchall()}
    column_types = {"cache_ttl": "TEXT", "cost_usd": "REAL"}
    for name in TOKEN_COLUMNS:
        if name not in columns:
            conn.execute(f"ALTER TABLE payload ADD COLUMN {name} "
                         f"{column_types.get(name, 'INTEGER')}")
    turn_columns = {r[1] for r in conn.execute(
        "PRAGMA table_info(turn)").fetchall()}
    if "output_tokens" not in turn_columns:
        conn.execute("ALTER TABLE turn ADD COLUMN output_tokens INTEGER")
    if "list_cost_usd" not in turn_columns:
        conn.execute("ALTER TABLE turn ADD COLUMN list_cost_usd REAL")


def _migration_3(conn) -> None:
    """Versione 3 (29/09/2026, spec «una porta sola» §7): gli argomenti.

    Stessa cura della 2: la colonna si aggiunge solo se manca. Le righe gia'
    scritte restano NULL -- gli argomenti non furono registrati, e non si
    inventa che siano `[]`."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(turn)").fetchall()}
    if "tool_args" not in columns:
        conn.execute("ALTER TABLE turn ADD COLUMN tool_args TEXT")


#: Quanto si tiene di un argomento. Testo libero lungo non deve gonfiare il
#: registro; e sono filtri e nomi della casa, non contenuti.
_ARG_TEXT_MAX = 200
_ARG_KEYS_MAX = 20
#: Fin dove si scende nei dati annidati (`execute` mette i dati del servizio
#: sotto una chiave). Oltre, il ramo si sostituisce: un contenitore piu'
#: profondo non e' un filtro, e non si lascia passare senza guardarlo.
_ARG_DEPTH_MAX = 4
#: Il segnaposto delle credenziali: lo stesso stile di `runner.REDATTO`.
_ARG_MASK = "***"
_ARG_TRUNCATED = "..."


def _compact_value(value, depth: int):
    """Un valore ridotto: credenziali mascherate, testi e contenitori tagliati.

    Le chiavi credenziali le decide `entity_cache.is_credential` -- per NOME,
    sull'insieme `entity_cache.CALL_ARGUMENT_SECRETS` (`code`, `pin`,
    `password`, `token`... e gli attributi che lo specchio trattiene), e per
    VALORE (un indirizzo con `token=`, una chiave esadecimale, un MAC). La
    funzione e' una e gli insiemi sono dichiarati la': qui non se ne scrive
    un terzo.

    Nei contenitori annidati valgono gli stessi tetti del livello alto: al
    massimo 20 chiavi (o elementi), testi a 200 caratteri, e la discesa si
    ferma a `_ARG_DEPTH_MAX` livelli."""
    if isinstance(value, str):
        return value[:_ARG_TEXT_MAX]
    if isinstance(value, (dict, list, tuple)):
        if depth >= _ARG_DEPTH_MAX:
            return _ARG_TRUNCATED
        if isinstance(value, dict):
            return _compact_mapping(value, depth + 1)
        out = []
        for item in list(value)[:_ARG_KEYS_MAX]:
            if isinstance(item, str) and is_credential("", item, CALL_ARGUMENT_SECRETS):
                out.append(_ARG_MASK)
            else:
                out.append(_compact_value(item, depth + 1))
        return out
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_ARG_TEXT_MAX]


def _compact_mapping(item: dict, depth: int) -> dict:
    kept = {}
    for key in list(item)[:_ARG_KEYS_MAX]:
        value = item[key]
        # La posizione di persone e dispositivi non si salva: stesso elenco
        # del filtro della porta (`privacy.POSITION_ATTRIBUTES`, spec §3).
        if str(key).lower() in POSITION_ATTRIBUTES:
            continue
        if is_credential(str(key).lower(), value, CALL_ARGUMENT_SECRETS):
            kept[str(key)] = _ARG_MASK
        else:
            kept[str(key)] = _compact_value(value, depth)
    return kept


def compact_tool_args(inputs: list) -> list[dict]:
    """Gli argomenti di ogni chiamata, ridotti, con le credenziali mascherate
    e senza la posizione di persone e dispositivi.

    Sono filtri e nomi della casa, non contenuti -- ma un testo libero lungo
    non deve gonfiare il registro (200 caratteri, 20 chiavi). `execute` e
    `propose` portano i dati di un servizio, e quel servizio puo' essere il
    disarmo di un allarme: il valore di una chiave credenziale (`code`,
    `user_code`, `pin`, `password`, `token`...) diventa `***`, a qualunque
    profondita'; le chiavi di posizione (`latitude`, `longitude`, `gps`...,
    `privacy.POSITION_ATTRIBUTES`) si tolgono.

    **Il limite, dichiarato**: il mascheramento va per NOME della chiave e per
    FORMA del valore (un indirizzo con `token=`, una chiave esadecimale, un
    MAC). Il TESTO LIBERO non si maschera: `{"message": "codice 4321"}` si
    salva com'e'. Restano in casa, in `consumi.db`, con la sua retention."""
    out = []
    for item in inputs or []:
        out.append(_compact_mapping(item, 0) if isinstance(item, dict) else {})
    return out


# I contatori che si sommano. Un elenco solo, perche' scritto a mano in ogni
# query e' il modo in cui una colonna nuova entra in una e non nell'altra.
CAMPI = ("richieste", "token_in", "token_out", "cache_lettura",
         "cache_scrittura", "errori_rate_limit")


class UsageStore:
    def __init__(self, db_path: str, *, read_timezone=None) -> None:
        self._read_timezone = read_timezone
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=3,
                    migrations={2: _migration_2, 3: _migration_3})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _timezone(self) -> str:
        """Il fuso della casa, o «» se non si puo' sapere.

        Non solleva mai: un consumo non si perde perche' l'anagrafe non e'
        ancora stata letta. Si conta in UTC e lo si dichiara -- e' la stessa
        disciplina del nucleo, che tace sul fuso invece di inventarne uno.
        """
        try:
            return (self._read_timezone() if self._read_timezone else "") or ""
        except Exception as exc:
            logger.warning("fuso della casa non leggibile, si conta in UTC: %s", exc)
            return ""

    def empty(self) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM consumo_giorno LIMIT 1").fetchone() is None

    def log(self, provider: str, model: str, *, richieste: int = 1,
                 token_in: int = 0, token_out: int = 0,
                 cache_read: int = 0, cache_write: int = 0,
                 cost_usd: float | None = None, cost_state: str,
                 errori_rate_limit: int = 0, now: float) -> None:
        """Una chiamata entra nel secchiello del suo giorno.

        `richieste=0` e' il caso del rifiuto (429): si conta chi ha rifiutato,
        sulla riga del modello che l'ha preso, senza contarla come una
        richiesta servita.
        """
        day = local_day(now, self._timezone())
        with self._lock:
            row = self._conn.execute(
                "SELECT costo_usd, costo_stato FROM consumo_giorno "
                "WHERE giorno=? AND provider=? AND modello=?",
                (day, provider, model)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO consumo_giorno (giorno, provider, modello, "
                    "richieste, token_in, token_out, cache_lettura, "
                    "cache_scrittura, costo_usd, costo_stato, "
                    "errori_rate_limit, primo_ts, ultimo_ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (day, provider, model, richieste, token_in, token_out,
                     cache_read, cache_write, cost_usd, cost_state,
                     errori_rate_limit, now, now))
            else:
                state = piu_debole(row["costo_stato"], cost_state)
                if state != row["costo_stato"]:
                    logger.info(
                        "consumi: %s/%s del %s degrada da «%s» a «%s» -- il "
                        "provider ha cambiato comportamento",
                        provider, model, day, row["costo_stato"], state)
                # I costi si sommano solo fra quelli NOTI. Una riga degradata
                # tiene cio' che ha gia' pagato e diventa un pavimento -- lo
                # stesso concetto del totale in cima alla pagina, a una scala
                # piu' piccola. Buttarlo direbbe «non ho speso niente», che e'
                # falso quanto lo zero da cui nasce la fetta.
                noti = [c for c in (row["costo_usd"], cost_usd) if c is not None]
                self._conn.execute(
                    "UPDATE consumo_giorno SET richieste=richieste+?, "
                    "token_in=token_in+?, token_out=token_out+?, "
                    "cache_lettura=cache_lettura+?, cache_scrittura=cache_scrittura+?, "
                    "costo_usd=?, costo_stato=?, "
                    "errori_rate_limit=errori_rate_limit+?, "
                    "primo_ts=MIN(primo_ts, ?), ultimo_ts=MAX(ultimo_ts, ?) "
                    "WHERE giorno=? AND provider=? AND modello=?",
                    (richieste, token_in, token_out, cache_read,
                     cache_write, sum(noti) if noti else None, state,
                     errori_rate_limit, now, now,
                     day, provider, model))
            self._conn.commit()

    def log_fallback(self, agent: str, reason: str, *, now: float) -> None:
        """Un giro e' passato dal forfait al consumo: si conta.

        Si CONTA, non si annota una riga per volta: duecento ripieghi in un
        giorno e uno solo sono due storie diverse, e il numero e' quello che le
        distingue -- ma duecento righe uguali renderebbero la pagina
        illeggibile proprio nel caso in cui serve.

        Non solleva mai, e non e' pigrizia: questa scrittura sta sul percorso
        dell'analista e dell'attuatore, e un guasto qui non deve impedire un
        giro. La dichiarazione serve a informare.
        """
        if not agent or not reason:
            return
        day = local_day(now, self._timezone())
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO fallback (day, agent, reason, count, "
                    "first_ts, last_ts) VALUES (?,?,?,1,?,?) "
                    "ON CONFLICT(day, agent, reason) DO UPDATE SET "
                    "count=count+1, last_ts=MAX(last_ts, ?)",
                    (day, agent, reason, now, now, now))
                self._conn.commit()
        except Exception as error:  # pragma: no cover - guasto dell'archivio
            logger.warning("consumi: il ripiego di «%s» non si e' scritto "
                           "(%s: %s)", agent, type(error).__name__, error)

    # ── I due registri della misura ──────────────────────────────────────
    #
    # **Nessuno dei due cambia comportamento**: sono due letture, e nascono per
    # rispondere a una domanda che il 23/09/2026 non aveva strumento. «Quali
    # luci sono accese in casa adesso?» ha impiegato 69 secondi per 35 token
    # di risposta, e non si poteva sapere perche': il registro dell'add-on
    # dice solo che la richiesta HTTP e' durata 69 secondi.

    def log_turn(self, *, species: str, provider: str, model: str,
                 channel: str, duration_ms: int, iterations: int, tools: list,
                 outcome: str, now: float, subject: dict | None = None,
                 output_tokens: int | None = None,
                 list_cost_usd: float | None = None,
                 tool_args: list | None = None) -> str:
        """Un turno intero, e quanto e' costato in giri e in secondi.

        **`tools` porta i nomi in ORDINE**, non un insieme: «search, view,
        search» racconta una ricerca che non ha trovato al primo colpo, tre
        nomi in un insieme no.

        **Gli argomenti si salvano, ridotti e senza credenziali** (decisione
        del 29/09/2026, spec «una porta sola» §7, che ribalta il «mai gli
        argomenti» della 3.70). Il 29/09 non si e' potuto sapere quale
        `search` avesse mancato l'Indifferenziato: c'erano solo i nomi.
        `tool_args` e' allineato a `tools` (stessa lunghezza, stesso ordine)
        e passa da `compact_tool_args`: testi a 200 caratteri, 20 chiavi, e il
        valore di ogni chiave credenziale (`code`, `pin`, `password`,
        `token`... -- la lista e' quella di `entity_cache`) diventa `***`,
        anche annidato. Restano dati personali (il nome di una stanza), e
        questo archivio entra nei backup di Home Assistant, non cifrati se il
        proprietario non ci mette una password: per questo le credenziali non
        entrano mai. `None` = non registrati.

        **Si scrive anche quando il turno e' andato male**, ed e' il caso piu'
        interessante di tutti: un giro che esaurisce le cinquanta iterazioni
        e' quello che ha speso di piu' senza dare niente. Registrare i soli
        riusciti misurerebbe la casa nei giorni belli.
        """
        # **Il vocabolario delle specie NON vive qui**, e non e' una
        # distrazione: lo possiede `steering`, che e' anche l'unico imbuto che
        # scrive questo registro, ed e' li' che una specie inventata viene
        # rifiutata. Un archivio che conoscesse l'elenco sarebbe il secondo
        # posto in cui la stessa regola vive, libero di divergere -- e
        # renderebbe questo modulo (ambito convertito) dipendente da un nome
        # di dominio italiano.
        ident = secrets.token_urlsafe(9)
        with self._lock:
            self._scadi_misure(now)
            self._conn.execute(
                "INSERT INTO turn(id,ts,species,provider,model,channel,"
                "subject_json,duration_ms,iterations,tools,outcome,"
                "output_tokens,list_cost_usd,tool_args) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ident, now, species, provider, model, channel,
                 None if subject is None else json.dumps(subject),
                 int(duration_ms), int(iterations), json.dumps(list(tools)),
                 outcome, None if output_tokens is None else int(output_tokens),
                 None if list_cost_usd is None else float(list_cost_usd),
                 None if tool_args is None else json.dumps(
                     compact_tool_args(tool_args), ensure_ascii=False)))
            self._conn.commit()
        return ident

    def log_payload(self, turn_id: str, *, iteration: int, tools_chars: int,
                    guide_chars: int, core_chars: int, history_chars: int,
                    results_chars: int, now: float, tools_sent: int = 0,
                    prefix_hash: str = "", input_tokens: int | None = None,
                    output_tokens: int | None = None,
                    cache_read_tokens: int | None = None,
                    cache_write_tokens: int | None = None,
                    cache_ttl: str | None = None,
                    cost_usd: float | None = None) -> None:
        """Di cosa e' fatto il carico a UN giro di quel turno.

        Per iterazione e non per turno: la moltiplicazione della latenza
        avviene per giro, e una media per turno la nasconderebbe. E
        `results_chars` e' l'unico che cresce di giro in giro -- i risultati
        degli strumenti si accumulano nella conversazione -- quindi e' il solo
        modo di vedere la curva invece del suo punto medio.

        I token sono NULL-abili: vedi il commento su `payload` nello schema.
        """
        valori_token = (input_tokens, output_tokens, cache_read_tokens,
                        cache_write_tokens, cache_ttl, cost_usd)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO payload(turn_id,iteration,ts,"
                "tools_chars,tools_sent,guide_chars,core_chars,history_chars,"
                f"results_chars,prefix_hash,{','.join(TOKEN_COLUMNS)}) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (turn_id, int(iteration), now, int(tools_chars),
                 int(tools_sent), int(guide_chars), int(core_chars),
                 int(history_chars), int(results_chars), prefix_hash,
                 *valori_token))
            self._conn.commit()

    def _scadi_misure(self, now: float) -> None:
        """I due registri scadono INSIEME, e il carico non sopravvive al suo
        turno: righe di `payload` orfane non rispondono a nessuna domanda --
        la specie del turno e' cio' che distingue «l'analista spende cosi'» da
        «la chat spende cosi'»."""
        limit = now - TURNS_RETENTION_S
        self._conn.execute(
            "DELETE FROM payload WHERE turn_id IN "
            "(SELECT id FROM turn WHERE ts < ?)", (limit,))
        self._conn.execute("DELETE FROM turn WHERE ts < ?", (limit,))

    def turns(self, *, limit: int = 500) -> list[dict]:
        """I turni, dal piu' recente. `tools` torna SCIOLTO dal JSON: una
        stringa che somiglia a una lista fa dire alla prima `len()` il numero
        di caratteri."""
        with self._lock:
            righe = self._conn.execute(
                "SELECT id,ts,species,provider,model,channel,subject_json,"
                "duration_ms,iterations,tools,outcome,output_tokens,"
                "list_cost_usd,tool_args FROM turn "
                "ORDER BY ts DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "species": r["species"],
                 "provider": r["provider"], "model": r["model"],
                 "channel": r["channel"],
                 "subject": (None if r["subject_json"] is None
                             else json.loads(r["subject_json"])),
                 "duration_ms": r["duration_ms"], "iterations": r["iterations"],
                 "tools": json.loads(r["tools"]), "outcome": r["outcome"],
                 "output_tokens": r["output_tokens"],
                 "list_cost_usd": r["list_cost_usd"],
                 "tool_args": (None if r["tool_args"] is None
                               else json.loads(r["tool_args"]))}
                for r in righe]

    def payloads(self, turn_id: str) -> list[dict]:
        """Il carico di un turno, giro per giro, in ordine."""
        with self._lock:
            righe = self._conn.execute(
                "SELECT iteration,ts,tools_chars,tools_sent,guide_chars,"
                "core_chars,history_chars,results_chars,prefix_hash"
                f",{','.join(TOKEN_COLUMNS)} "
                "FROM payload WHERE turn_id=? "
                "ORDER BY iteration", (turn_id,)).fetchall()
        return [dict(r) for r in righe]

    def fallbacks(self, *, da: str = "", from_anchor: bool = False) -> list[dict]:
        """I giri passati a consumo, i piu' recenti per primi.

        Stesso interruttore delle sezioni («da ultimo azzeramento / da
        sempre»): quella che si azzera dev'essere tutta la pagina, o un numero
        resterebbe indietro rispetto all'altro accanto.
        """
        if from_anchor and not da:
            da = self._anchor_day()
        # `_where` compone su `giorno`, che e' la colonna delle tabelle
        # vecchie: questa e' nuova e la sua colonna si chiama `day`.
        where, params = ("WHERE day >= ?", (da,)) if da else ("", ())
        with self._lock:
            righe = self._conn.execute(
                "SELECT day, agent, reason, count, first_ts, last_ts "
                f"FROM fallback {where} "
                "ORDER BY day DESC, count DESC, agent ASC",
                params).fetchall()
        return [dict(r) for r in righe]

    # -- leggere -------------------------------------------------------
    #
    # `totali` NON ha una query propria: somma le sezioni. Due strade di
    # calcolo per lo stesso numero sono due strade libere di divergere, e
    # divergerebbero proprio su `partial_cost` -- il campo che impedisce
    # alla pagina di spacciare un pavimento per un costo.

    def _where(self, da: str) -> tuple[str, tuple]:
        return ("WHERE giorno >= ?", (da,)) if da else ("", ())

    def sezioni(self, *, da: str = "", from_anchor: bool = False) -> list[dict]:
        """Una voce per provider USATO, coi suoi modelli dentro.

        I provider mai usati non compaiono: e' un'ASSENZA, non uno zero -- ed
        e' il «al primo utilizzo si attiva» che il proprietario ha chiesto.
        """
        from .vocabulary import LABEL, NOTE

        if from_anchor:
            da = self._anchor_day() or da
        where, arg = self._where(da)
        somme = ", ".join(f"SUM({c}) AS {c}" for c in CAMPI)
        with self._lock:
            righe = self._conn.execute(
                f"SELECT provider, modello, {somme}, SUM(costo_usd) AS costo_usd, "
                "MIN(costo_stato) AS uno_stato, "
                "SUM(CASE WHEN costo_stato='non_noto' THEN 1 ELSE 0 END) AS ignoti, "
                "MIN(giorno) AS primo_uso, MAX(giorno) AS ultimo_uso "
                f"FROM consumo_giorno {where} GROUP BY provider, modello "
                "ORDER BY provider, modello", arg).fetchall()

        per_provider: dict[str, dict] = {}
        for r in righe:
            section = per_provider.setdefault(r["provider"], {
                "provider": r["provider"],
                "etichetta": LABEL.get(r["provider"], r["provider"]),
                "nota": NOTE.get(r["provider"], ""),
                # `None`, non `0.0`: una sezione i cui modelli non hanno NESSUN
                # costo noto -- l'abbonamento, per dirne una -- affermerebbe
                # «zero euro» per una cosa che un costo non ce l'ha. E' lo zero
                # che afferma, rientrato un piano piu' su di dove la fetta lo
                # aveva tolto. Trovato MISURANDO la pagina viva il 22/08/2026:
                # la riga diceva «compreso» e la sezione che la conteneva
                # diceva 0,0. Diventa un numero appena un modello ne porta uno.
                "costo_usd": None,
                "costo_parziale": False,
                "modelli": [],
                **{c: 0 for c in CAMPI},
            })
            for c in CAMPI:
                section[c] += r[c] or 0
            if r["costo_usd"] is not None:
                section["costo_usd"] = (section["costo_usd"] or 0.0) + r["costo_usd"]
            section["costo_parziale"] = section["costo_parziale"] or bool(r["ignoti"])
            section["modelli"].append({
                "modello": r["modello"],
                "costo_usd": r["costo_usd"],
                # `MIN(cost_state)` e' alfabetico e non significa niente: se
                # anche un solo giorno e' ignoto, la riga lo e'. Si sceglie
                # esplicitamente invece di fidarsi dell'ordine delle lettere.
                "costo_stato": "non_noto" if r["ignoti"] else r["uno_stato"],
                "primo_uso": r["primo_uso"],
                "ultimo_uso": r["ultimo_uso"],
                **{c: r[c] or 0 for c in CAMPI},
            })
        if from_anchor:
            self._sottrai_saldo(per_provider)
        return list(per_provider.values())

    def totali(self, *, da: str = "", from_anchor: bool = False) -> dict:
        """I contatori sommati su tutte le sezioni. `costo_usd` puo' essere
        `None`, ed e' l'intero punto.

        **Uno zero e' un'affermazione** (audit delle fondamenta, rilievo 6).
        Prima questa funzione faceva `sum(costo_usd or 0.0)`: con 111
        richieste tutte in abbonamento -- misurato sulla casa del proprietario
        l'08/09/2026 -- la porta HTTP rispondeva `measured: true, cost_usd:
        0.0, partial_cost: false`, cioe' «ho misurato, e non e' costato
        niente». La sezione, un piano piu' sotto, diceva gia' `null`: lo
        stesso fatto usciva in due forme dalle due porte, e la pagina lo
        correggeva a valle mentre chiunque altro leggesse la rotta (il
        gateway MCP) leggeva lo zero.

        Le due regole, entrambe alla fonte:

        - `costo_usd` e' `None` quando NESSUNA sezione porta un costo noto.
          Appena una lo porta il totale torna un numero -- la somma di cio'
          che si conosce.
        - `costo_parziale` («questo totale e' un pavimento, scrivilo con
          `>=`») si alza per due ragioni, non piu' per una sola: una sezione
          che si dichiara gia' parziale (una riga `non_noto`), **oppure** una
          sezione senza nessun costo noto -- l'abbonamento. Un turno
          `compreso` un costo ce l'ha, e' l'abbonamento che non lo espone per
          turno: escluderlo dalla somma senza dirlo faceva passare un minimo
          per un totale.

        `gratuito` non entra in nessuna delle due: Ollama in casa costa zero
        DAVVERO, la sua sezione porta `0.0` (un costo noto), e il totale
        resta esatto.
        """
        sezioni = self.sezioni(da=da, from_anchor=from_anchor)
        fuori = {c: sum(s[c] for s in sezioni) for c in CAMPI}
        noti = [s["costo_usd"] for s in sezioni if s["costo_usd"] is not None]
        fuori["costo_usd"] = sum(noti) if noti else None
        fuori["costo_parziale"] = (any(s["costo_parziale"] for s in sezioni)
                                   or len(noti) != len(sezioni))
        return fuori

    def storia(self, *, da: str, a: str) -> list[dict]:
        """Un secchiello per giorno e provider, per il grafico."""
        somme = ", ".join(f"SUM({c}) AS {c}" for c in CAMPI)
        with self._lock:
            righe = self._conn.execute(
                f"SELECT giorno, provider, {somme}, SUM(costo_usd) AS costo_usd "
                "FROM consumo_giorno WHERE giorno >= ? AND giorno <= ? "
                "GROUP BY giorno, provider ORDER BY giorno, provider", (da, a)).fetchall()
        giorni: dict[str, dict] = {}
        for r in righe:
            g = giorni.setdefault(r["giorno"],
                                  {"giorno": r["giorno"], "per_provider": {}})
            g["per_provider"][r["provider"]] = {
                "costo_usd": r["costo_usd"],
                **{c: r[c] or 0 for c in CAMPI},
            }
        return list(giorni.values())

    # -- l'ancora: azzerare senza cancellare ---------------------------

    def anchor(self) -> float:
        """L'istante da cui si conta, o `0.0` se non e' mai stata spostata."""
        with self._lock:
            r = self._conn.execute("SELECT da_ts FROM ancora WHERE id=1").fetchone()
        return r["da_ts"] if r else 0.0

    def _anchor_day(self) -> str:
        with self._lock:
            r = self._conn.execute("SELECT da_giorno FROM ancora WHERE id=1").fetchone()
        return r["da_giorno"] if r else ""

    def sposta_anchor(self, now: float) -> float:
        """«Riparti da adesso»: fissa il punto da cui contare. Non cancella nulla.

        Fotografa i contatori del giorno CORRENTE in `ancora_saldo`. Senza
        quella fotografia, un'ancora che fosse soltanto una data lascerebbe in
        pagina il consumo gia' fatto stamattina, e il pulsante sembrerebbe
        rotto proprio nel momento in cui lo si preme.

        Il saldo non e' un doppione di un fatto che vive altrove: e' la
        POSIZIONE dell'ancora, espressa nelle uniche coordinate che l'archivio
        possiede. Nessun altro posto la sa.
        """
        day = local_day(now, self._timezone())
        colonne = ", ".join(CAMPI)
        with self._lock:
            self._conn.execute("DELETE FROM ancora_saldo")
            self._conn.execute(
                f"INSERT INTO ancora_saldo (provider, modello, {colonne}, costo_usd) "
                f"SELECT provider, modello, {colonne}, costo_usd "
                "FROM consumo_giorno WHERE giorno = ?",
                (day,))
            self._conn.execute(
                "INSERT INTO ancora (id, da_ts, da_giorno) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET da_ts=excluded.da_ts, "
                "da_giorno=excluded.da_giorno", (now, day))
            self._conn.commit()
        return now

    def _sottrai_saldo(self, per_provider: dict) -> None:
        """Toglie da ogni riga il valore che aveva all'istante dell'ancora.

        `max(0, ...)`: se una riga di saldo non trovasse piu' il suo modello --
        non dovrebbe succedere, i secchielli non si cancellano -- si preferisce
        uno zero a un numero negativo, che a schermo non vorrebbe dire niente.
        """
        with self._lock:
            saldi = self._conn.execute("SELECT * FROM ancora_saldo").fetchall()
        for s in saldi:
            section = per_provider.get(s["provider"])
            if section is None:
                continue
            for model in section["modelli"]:
                if model["modello"] != s["modello"]:
                    continue
                for c in CAMPI:
                    model[c] = max(0, model[c] - (s[c] or 0))
                if model["costo_usd"] is not None and s["costo_usd"] is not None:
                    model["costo_usd"] = max(0.0, model["costo_usd"] - s["costo_usd"])
        # I totali di sezione si RICALCOLANO dai modelli, non si correggono a
        # parte: due strade per lo stesso numero divergono al primo caso limite.
        #
        # `costo_usd` con la STESSA regola di `sezioni()`: `None` finche'
        # nessun modello ne porta uno. Qui c'era la terza occorrenza dello
        # zero che afferma (audit, rilievo 6), e proprio perche' era una
        # SECONDA strada per lo stesso numero divergeva: con l'ancora spostata
        # la sezione dell'abbonamento diceva `0.0`, senza ancora diceva
        # `null`. Il commento qui sopra lo aveva previsto; la somma sotto non
        # lo rispettava.
        for section in per_provider.values():
            for c in CAMPI:
                section[c] = sum(m[c] for m in section["modelli"])
            noti = [m["costo_usd"] for m in section["modelli"]
                    if m["costo_usd"] is not None]
            section["costo_usd"] = sum(noti) if noti else None

    # -- i file di prima -----------------------------------------------

    def importa_legacy(self, percorsi: list[str], *, now: float) -> int:
        """I quattro `usage_*.json` entrano UNA volta, come una riga sola.

        Il totale ereditato non si puo' attribuire a un modello: nessuno lo ha
        mai registrato. Si dichiara -- modello `(prima del dettaglio)` --
        invece di spalmarlo su modelli che potrebbero non averlo speso.

        Datato all'ultimo azzeramento, che e' l'unica data vera che quei file
        portano. I file NON vengono cancellati: mai dati dell'utente rimossi in
        silenzio.
        """
        import json as _json
        import os
        from datetime import datetime

        _PROVIDER_BY_SUFFIX = {"_openai": "openai", "_openrouter": "openrouter",
                     "_ollama": "ollama"}
        importati = 0
        for path in percorsi:
            if not os.path.exists(path):
                continue
            with self._lock:
                gia = self._conn.execute(
                    "SELECT 1 FROM legacy_importati WHERE percorso=?",
                    (path,)).fetchone()
            if gia:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
            except Exception as exc:
                logger.warning("usage.json illeggibile (%s): %s -- saltato, e "
                               "il file resta dov'e'", path, exc)
                continue
            base = os.path.splitext(os.path.basename(path))[0]
            provider = next((p for suff, p in _PROVIDER_BY_SUFFIX.items()
                             if base.endswith(suff)), "claude")
            when = now
            try:
                when = datetime.fromisoformat(
                    data.get("last_reset") or "").timestamp()
            except (TypeError, ValueError):
                pass
            self.log(
                provider, "(prima del dettaglio)",
                richieste=int(data.get("total_requests") or 0),
                token_in=int(data.get("total_input_tokens") or 0),
                token_out=int(data.get("total_output_tokens") or 0),
                cost_usd=float(data.get("total_cost_usd") or 0.0),
                cost_state="misurato",
                errori_rate_limit=int(data.get("total_rate_limit_errors") or 0),
                now=when)
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO legacy_importati (percorso) VALUES (?)",
                    (path,))
                self._conn.commit()
            importati += 1
            logger.info("consumi: importato %s come «(prima del dettaglio)» "
                        "sul provider %s", path, provider)
        return importati
