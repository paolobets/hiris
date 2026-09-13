"""Il sapere: cio' che HIRIS ha capito della casa, con la provenienza e le prove.

Spec `docs/design/2026-09-10-i-tre-attori.md` §8.

**Una casa sola, col soggetto come colonna.** Prima di questa fetta cio' che
HIRIS aveva capito viveva sparso: una tabella a mano in `proxy/ha_client.py`
per le direzioni dell'energia, una in `home_space/ha_vocabulary.py` per il
significato delle classi, la ricetta dell'inverter dentro il motore di
aggregazione. Tre posti, tre forme, nessuna provenienza, e per correggerne una
serviva un rilascio.

**I due assi restano due, e non si negoziano.** `provenance` dice **da dove
viene** -- chiesto al proprietario, importato da una fonte, nostro come
giudizio, dedotto dal modello, ereditato da un altro soggetto. `verification`
dice **cosa ha detto il controllo** -- confermata, non confermabile, non
capito, oppure niente perche' nessun controllo era possibile. Fonderle in una
parola sola («attendibilita'», «qualita'», «stato») e' il difetto che questo
progetto ha gia' pagato sei volte, e il modo di non rifarlo non e'
ricordarselo: e' un costruttore che non lascia nascere la riga sbagliata.

Il precedente della disciplina e' `home_space/type_vocabulary.Field`, che e'
astratta apposta -- *«una prova dice che oggi nessuno l'ha fatto, il
costruttore dice che non si puo' fare»*.

**Il file si chiama `sapere.db`, e non `knowledge.db`.** Non e' un capriccio di
lingua: un file `knowledge.db` ESISTE gia' in `/data` sulle installazioni che
hanno attraversato la fetta «esce il documentale», con lo schema di un archivio
documentale morto che nessuno legge piu' (`server.py` ne dichiara l'incontro
nel log). Aprirlo qui troverebbe le sue tabelle, e il `CREATE TABLE IF NOT
EXISTS` non direbbe niente. Misurato il 12/09/2026, vedi
`docs/design/2026-09-12-il-sapere-e-le-ricette.md`.

**`ambito` non e' una colonna.** Sarebbe un doppione: `tipo` e `integrazione`
sono universali per natura -- valgono per chiunque abbia quel tipo o quella
integrazione -- ed `entita` e' di questa casa. Il genere lo dice gia', e una
colonna in piu' potrebbe divergere da lui.
"""
from __future__ import annotations

import logging
import threading
import time as _time
from dataclasses import dataclass

from ..storage import connect, init_schema

logger = logging.getLogger(__name__)

#: I tre generi di soggetto di cui il sapere puo' parlare. Tre, non quattro:
#: un «dispositivo» sarebbe un `ambito` travestito da genere.
#:
#: **Il genere dice anche cosa puo' uscire di casa**, e per questo `ambito` non
#: e' una colonna: `tipo` e `integrazione` sono universali per natura -- «un
#: inverter zcsazzurro si misura cosi'» vale per chiunque ne abbia uno --
#: mentre `entita` e' di questa casa e non si esporta. La porta che esporta
#: non c'e' ancora (spec §12, a backlog): quando arrivera', la regola si legge
#: da qui e non da un campo in piu' che potrebbe divergere.
SUBJECT_KINDS = ("tipo", "integrazione", "entita")

#: Da dove viene un campo. **Non dice se e' vero**: quello lo dice l'altro asse.
#:
#: - `chiesto`    -- il proprietario l'ha detto;
#: - `importato`  -- letto da una fonte che lo dichiara (l'installazione, la
#:                   documentazione di Home Assistant);
#: - `nostro`     -- un giudizio nostro, che nessuna API puo' darci;
#: - `dedotto`    -- il modello l'ha inferito da cio' che ha letto;
#: - `ereditato`  -- viene da un soggetto piu' generale (il tipo, l'integrazione).
PROVENANCES = ("chiesto", "importato", "nostro", "dedotto", "ereditato")

#: Cosa ha detto il controllo. `None` e' il quarto esito e significa «nessun
#: controllo era possibile», che e' diverso da «non capito».
VERIFICATIONS = ("confermata", "non_confermabile", "non_capito")

# -- il vocabolario dei campi -----------------------------------------------
#
# I nomi dei campi vivono qui e non nel seme: sono la FORMA dell'archivio --
# come si chiama una cosa e come si compone il soggetto -- e chi legge ne ha
# bisogno quanto chi semina. Tenerli nel seme obbligava il lettore a
# importarli da li', cioe' a dipendere da chi scrive per poter leggere.

#: Il campo sotto cui vive una direzione dell'energia. Il soggetto e'
#: l'integrazione, il resto del nome e' il `translation_key` a cui la riga si
#: riferisce: `direzione:energy_generating_today`.
DIRECTION_FIELD_PREFIX = "direzione:"


#: Il campo sotto cui vive il significato di un tipo. Il soggetto e' il tipo
#: stesso -- `sensor`, oppure `sensor.power` per una coppia dominio/classe --
#: esattamente come la spec §8 lo scrive nel suo esempio.
MEANING_FIELD = "significato"


def type_subject(domain: str, device_class: str | None = None) -> str:
    """Il soggetto di un tipo: `sensor`, oppure `sensor.power`.

    Un posto solo dove si compone, perche' due composizioni divergono al
    primo dominio con un punto nel nome.
    """
    return f"{domain}.{device_class}" if device_class else domain


#: Il campo sotto cui vive l'elenco degli attributi da tenere per un tipo.
#:
#: **Fisso, e il tipo sta nel SOGGETTO** -- `("tipo", "climate", "attributi")`,
#: non `("tipo", "climate", "attributi:climate")`. La prima stesura scriveva il
#: tipo due volte nella stessa chiave primaria (revisione indipendente,
#: 13/09/2026): lo stesso fatto in due posti della stessa riga, cioe' la
#: seconda fondamenta rotta dentro la chiave che dovrebbe garantirla. E'
#: anche la forma che `significato` usa gia'.
ATTRIBUTE_FIELD = "attributi"


@dataclass(frozen=True)
class Fact:
    """Una riga del sapere. **Non nasce se e' malformata.**

    I controlli non sono pedanteria di forma: ognuno chiude una porta da cui
    questo progetto e' gia' passato.

    - **un campo `nostro` non puo' essere verificato.** La spec lo dice alla
      lettera: *«e' un giudizio che HA non puo' darci, e `verifica` per lui e'
      NULL»*. Scrivere «confermata» su un giudizio nostro afferma che qualcuno
      la' fuori ce l'ha confermato, e non e' successo: e' la forma esatta
      della motivazione falsa;
    - **una verifica confermata senza la sua citazione non nasce.** `source` e'
      *«la citazione, con la versione»*: una conferma che nessuno puo'
      controllare non e' una conferma;
    - **una deduzione senza prove non nasce.** `evidence` e' *«cosa e' stato
      letto per dedurlo»*: senza, la deduzione non si puo' ne' rifare ne'
      smentire, e fra sei mesi resta li' come se fosse un fatto.
    """

    subject_kind: str
    subject: str
    field: str
    value: str
    provenance: str
    who: str
    when_ts: float
    verification: str | None = None
    evidence: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if self.subject_kind not in SUBJECT_KINDS:
            raise ValueError(
                f"genere di soggetto sconosciuto: {self.subject_kind!r}. "
                f"Sono tre, e sono {', '.join(SUBJECT_KINDS)}")
        if not str(self.subject or "").strip():
            raise ValueError("un soggetto senza nome non e' un soggetto")
        if not str(self.field or "").strip():
            raise ValueError("un campo senza nome non dice di cosa parla la riga")
        if self.provenance not in PROVENANCES:
            raise ValueError(
                f"provenienza sconosciuta: {self.provenance!r}. "
                f"Sono {', '.join(PROVENANCES)}")
        if self.verification is not None and self.verification not in VERIFICATIONS:
            raise ValueError(
                f"verifica sconosciuta: {self.verification!r}. Sono "
                f"{', '.join(VERIFICATIONS)}, oppure niente quando nessun "
                "controllo era possibile")
        if self.provenance == "nostro" and self.verification is not None:
            raise ValueError(
                "un campo nostro non puo' portare una verifica: e' un giudizio "
                "che Home Assistant non puo' darci, e dire «confermata» "
                "affermerebbe che qualcuno l'ha confermato")
        if self.verification == "confermata" and not str(self.source or "").strip():
            raise ValueError(
                "una verifica confermata senza la sua fonte non e' una "
                "conferma: serve la citazione, con la versione")
        if self.provenance == "dedotto" and not str(self.evidence or "").strip():
            raise ValueError(
                "una deduzione senza prove non si puo' ne' rifare ne' "
                "smentire: `evidence` dice cosa e' stato letto per dedurla")
        if not str(self.who or "").strip():
            raise ValueError("chi ha scritto la riga e' obbligatorio")
        if not self.when_ts:
            raise ValueError("quando la riga e' stata scritta e' obbligatorio")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge (
    subject_kind TEXT NOT NULL,
    subject      TEXT NOT NULL,
    field        TEXT NOT NULL,
    value        TEXT,
    provenance   TEXT NOT NULL,
    verification TEXT,
    evidence     TEXT,
    source       TEXT,
    who          TEXT NOT NULL,
    when_ts      REAL NOT NULL,
    -- Cosa il SEME aveva scritto l'ultima volta, e con quale precedenza.
    --
    -- **Serve perche' `who` non basta** (revisione indipendente su Fable 5.1,
    -- 13/09/2026): questo archivio e' fatto per essere corretto a mano, e chi
    -- corregge una riga con un `UPDATE` non cambia `who` -- nessuno glielo ha
    -- detto. Con la regola «il seme tocca solo cio' che e' suo» letta da
    -- `who`, quella correzione tornava indietro al riavvio successivo, in
    -- silenzio. Confrontare il valore con cio' che il seme aveva scritto
    -- risponde alla domanda vera: «l'ha toccata qualcuno?».
    --
    -- E risolve un secondo difetto: se il nome dell'autore del seme cambiasse,
    -- con la regola su `who` tutte le sue righe diventerebbero orfane per
    -- sempre -- ne' inseribili (chiave primaria) ne' aggiornabili.
    seeded_value    TEXT,
    seeded_priority INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subject_kind, subject, field)
);
-- Nessun indice su `field`: l'unico accesso per campo e' `by_field_prefix`,
-- che usa `substr(field, 1, ?)` -- una funzione sulla colonna, che l'indice non
-- puo' servire. Un indice che nessuna query puo' usare costa scritture e non
-- fa risparmiare nessuna lettura (Fable 5.1, 13/09/2026).
"""
def _migration_2(conn) -> None:
    """v1 -> v2: `seeded_value` e `seeded_priority` (13/09/2026).

    Le righe scritte prima rileggono `NULL` e `0`: e' vero, il seme di allora
    non si ricordava cosa avesse scritto. Una riga con `seeded_value` nullo non
    e' piu' correggibile dal seme -- il che e' il comportamento prudente:
    «non so se qualcuno l'ha toccata» si tratta come «qualcuno l'ha toccata».
    """
    for column, kind in (("seeded_value", "TEXT"),
                         ("seeded_priority", "INTEGER NOT NULL DEFAULT 0")):
        esistenti = {r[1] for r in conn.execute("PRAGMA table_info(knowledge)")}
        if column not in esistenti:
            conn.execute(f"ALTER TABLE knowledge ADD COLUMN {column} {kind}")


_SCHEMA_VERSION = 2

_COLUMNS = ("subject_kind", "subject", "field", "value", "provenance",
            "verification", "evidence", "source", "who", "when_ts")


def _facts(rows) -> list[Fact]:
    """Le righe lette dal disco, **saltando quelle che non si reggono**.

    `Fact` rivaluta i suoi controlli su cio' che arriva dall'archivio, ed e'
    giusto: una riga incoerente non deve circolare come se fosse un fatto. Ma
    questo archivio e' fatto per essere corretto a mano, e una sola riga storta
    -- `nostro` con una verifica, una provenienza scritta male -- farebbe
    sollevare la lettura di TUTTO il soggetto. Il chiamante lo
    tradurrebbe in un messaggio che parla d'altro: «comprimari non costruiti,
    riparazione saltata» (`server.py`), cioe' esattamente il difetto che quella
    prova esiste per impedire (revisione indipendente, 13/09/2026).

    Quindi: si salta e si dichiara nel registro. La riga resta sul disco --
    non si cancella mai niente dell'utente -- e chi guarda il log sa quale.
    """
    facts = []
    for row in rows:
        try:
            facts.append(Fact(**dict(row)))
        except (ValueError, TypeError) as error:
            logger.warning(
                "sapere: riga saltata perche' non si regge (%s/%s/%s): %s",
                row["subject_kind"], row["subject"], row["field"], error)
    return facts


class KnowledgeStore:
    """L'archivio del sapere. Una riga per `(genere, soggetto, campo)`.

    **Riscrivere una terna SOSTITUISCE**, non affianca: la stessa cosa detta
    due volte deve restare una cosa sola, o le due copie divergono e nessuno
    sa quale valga. E' la seconda fondamenta applicata all'archivio.
    """

    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        self._conn = connect(db_path)
        init_schema(self._conn, _SCHEMA, version=_SCHEMA_VERSION,
                    migrations={2: _migration_2})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- scrittura ---------------------------------------------------------

    def write(self, fact: Fact) -> None:
        """Scrive la riga, sostituendo quella che c'era per la stessa terna."""
        with self._lock:
            self._conn.execute(
                f"INSERT INTO knowledge ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(_COLUMNS))}) "
                "ON CONFLICT(subject_kind, subject, field) DO UPDATE SET "
                "value=excluded.value, provenance=excluded.provenance, "
                "verification=excluded.verification, evidence=excluded.evidence, "
                "source=excluded.source, who=excluded.who, when_ts=excluded.when_ts",
                tuple(getattr(fact, c) for c in _COLUMNS))
            self._conn.commit()

    def seed(self, facts, *, priority: int = 0) -> int:
        """Il seme del repo: scrive **solo cio' che ancora non c'e'**.

        *«Il repo diventa il seme»* (spec §8): le righe scritte, riviste,
        linterate e in git si caricano all'avvio con la loro provenienza, **e
        la casa scrive sopra**. Un seme che sovrascrivesse cancellerebbe a
        ogni riavvio cio' che la casa ha imparato -- e il difetto sarebbe
        invisibile, perche' il valore tornerebbe semplicemente a essere quello
        scritto nel repo, che sembra giusto.

        **Ma il seme corregge le righe che NESSUNO HA TOCCATO**, e senza questo
        un difetto del repo sarebbe irreparabile: con un `INSERT OR IGNORE`
        nudo, il giorno in cui si scoprisse che `power_autoconsuming` non
        significa «autoconsumo», correggerlo nel repo non riparerebbe nessuna
        installazione gia' avviata -- prima serviva un rilascio, dopo non
        basterebbe nemmeno quello.

        **«Nessuno l'ha toccata» si legge dal VALORE, non da `who`** (Fable
        5.1, 13/09/2026). La prima stesura guardava l'autore, e sbagliava due
        volte: chi corregge una riga a mano con un `UPDATE` non cambia `who`
        -- nessuno glielo ha detto -- e si vedeva la correzione tornare
        indietro al riavvio, in silenzio; e il giorno in cui il nome
        dell'autore del seme cambiasse, tutte le sue righe sarebbero diventate
        orfane per sempre. Adesso il confronto e' fra il valore di adesso e
        quello che **il seme stesso** aveva scritto l'ultima volta.

        **`priority` decide chi vince fra due semi.** Il repo (priorita' alta)
        porta una frase che dice cosa un valore E'; l'installazione (priorita'
        bassa) porta il nome che Home Assistant pubblica. Senza una priorita'
        esplicita vinceva **chi arrivava prima**: su una casa che aveva gia'
        importato «Indice AQI», la frase piu' ricca aggiunta da un rilascio
        successivo non sarebbe atterrata mai.

        Torna quante righe ha davvero scritto o corretto.
        """
        written = 0
        with self._lock:
            for fact in facts:
                cur = self._conn.execute(
                    f"INSERT INTO knowledge ({', '.join(_COLUMNS)}, "
                    "seeded_value, seeded_priority) "
                    f"VALUES ({', '.join('?' * (len(_COLUMNS) + 2))}) "
                    "ON CONFLICT(subject_kind, subject, field) DO UPDATE SET "
                    "value=excluded.value, provenance=excluded.provenance, "
                    "verification=excluded.verification, evidence=excluded.evidence, "
                    "source=excluded.source, who=excluded.who, "
                    "when_ts=excluded.when_ts, seeded_value=excluded.seeded_value, "
                    "seeded_priority=excluded.seeded_priority "
                    "WHERE knowledge.seeded_value IS NOT NULL "
                    "  AND knowledge.value IS knowledge.seeded_value "
                    "  AND excluded.seeded_priority >= knowledge.seeded_priority "
                    "  AND (knowledge.value IS NOT excluded.value "
                    "       OR knowledge.source IS NOT excluded.source)",
                    tuple(getattr(fact, c) for c in _COLUMNS)
                    + (fact.value, int(priority)))
                written += cur.rowcount or 0
            self._conn.commit()
        return written

    # -- lettura -----------------------------------------------------------

    def read(self, *, subject_kind: str, subject: str) -> list[Fact]:
        """Tutto cio' che si sa di un soggetto. Vuoto se non se ne sa niente --
        **non un errore**: «non lo so» e' una risposta legittima."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM knowledge "
                "WHERE subject_kind = ? AND subject = ? ORDER BY field",
                (subject_kind, subject)).fetchall()
        return _facts(rows)

    def get(self, subject_kind: str, subject: str, field: str) -> Fact | None:
        """Un campo solo, o `None` se non c'e'."""
        with self._lock:
            row = self._conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM knowledge "
                "WHERE subject_kind = ? AND subject = ? AND field = ?",
                (subject_kind, subject, field)).fetchone()
        if row is None:
            return None
        found = _facts([row])
        return found[0] if found else None

    def by_field_prefix(self, prefix: str) -> list[Fact]:
        """Tutte le righe il cui campo comincia per `prefix`.

        Serve ai campi che portano una chiave dentro il nome --
        `direzione:energy_generating_today` -- dove il prefisso e' il tipo di
        cosa e il resto e' di chi parla.

        `substr(...) = ?` e non `LIKE ?`: in un `LIKE` i caratteri `%` e `_`
        sono jolly, e `_` compare in ogni nome di campo di questo archivio.
        Con `LIKE` servirebbe un `ESCAPE` e tre `replace` prima della
        chiamata -- tre righe di quoting a mano che sbagliano al primo campo
        con un carattere inatteso. Il confronto sul prefisso non ha jolly.
        """
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM knowledge "
                "WHERE substr(field, 1, ?) = ? ORDER BY subject, field",
                (len(prefix), prefix)).fetchall()
        return _facts(rows)

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT count(*) FROM knowledge").fetchone()[0]


def now_ts() -> float:
    """L'orologio, in un posto solo: le prove lo sostituiscono senza toccare
    ogni sito di chiamata."""
    return _time.time()


def directions_by_translation_key(store, integration: str | None = None) -> dict[str, str]:
    """`{translation_key: direzione}` come lo vuole `HAClient.energy_directions`.

    **La lettura e' del sapere, non del proxy.** Il lettore di Home Assistant
    sa leggere un registro di entita': non sa, e non deve sapere, che
    `energy_generating_today` voglia dire «produzione». Quel salto e' un
    giudizio, vive nel sapere con la sua provenienza, e arriva al proxy come
    un parametro -- la stessa disciplina con cui `episodio` riceve `is_on` e
    `quando_succede` riceve il fuso gia' risolto.

    Senza `integration` raccoglie le direzioni di tutte le integrazioni note.
    Due integrazioni che usassero la stessa chiave per direzioni diverse sono
    un caso che questa casa non ha: quando capitera', questa funzione dovra'
    prendere l'integrazione dell'entita' invece di appiattire.
    """
    by_key: dict[str, str] = {}
    for fact in store.by_field_prefix(DIRECTION_FIELD_PREFIX):
        if integration is not None and fact.subject != integration:
            continue
        by_key[fact.field[len(DIRECTION_FIELD_PREFIX):]] = fact.value
    return by_key


def attributes_wanted_for(store, *, domain: str,
                          device_class: str | None = None) -> tuple[str, ...]:
    """Gli attributi da tenere per questo tipo, dal sapere.

    **Prima la coppia, poi il dominio.** Un `sensor.power` puo' volere cose
    che un `sensor` qualunque non vuole: la riga piu' specifica vince, come
    fa Home Assistant stesso quando risolve una traduzione.

    Vuoto quando nessuno ha deciso niente -- e il vuoto significa **non
    tenere niente**, non «tieni tutto».
    """
    for subject in ([type_subject(domain, device_class)] if device_class else []) + [domain]:
        fact = store.get("tipo", subject, ATTRIBUTE_FIELD)
        if fact is not None and fact.value:
            return tuple(a.strip() for a in fact.value.split(",") if a.strip())
    return ()
