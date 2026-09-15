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

import json
import logging
import threading
import time as _time
from dataclasses import dataclass

from ..storage import connect, init_schema

logger = logging.getLogger(__name__)

#: I generi di soggetto di cui il sapere puo' parlare.
#:
#: **Erano tre fino al 13/09/2026**, e il quarto -- `dispositivo` -- e' nato
#: con le ricette che l'osservatore chiede al modello (`mind/recipe_turn.py`,
#: spec §7). Non contraddice la spec: quello che §8 esclude e' una colonna
#: `ambito`, perche' sarebbe un doppione del genere. Il genere continua a dire
#: da solo se una riga e' universale -- `tipo` e `integrazione` lo sono,
#: `entita` e `dispositivo` sono di questa casa -- e l'invariante regge.
#:
#: **Una ricetta non ha nessun altro soggetto onesto**: non e'
#: dell'integrazione (nomina entita' che un'altra casa non ha) e non e' di
#: un'entita' sola (ne mette insieme sette).
#:
#: **Il genere dice anche cosa puo' uscire di casa**, e per questo `ambito` non
#: e' una colonna: `tipo` e `integrazione` sono universali per natura -- «un
#: inverter zcsazzurro si misura cosi'» vale per chiunque ne abbia uno --
#: mentre `entita` e `dispositivo` sono di questa casa e non si esportano. La porta che esporta
#: non c'e' ancora (spec §12, a backlog): quando arrivera', la regola si legge
#: da qui e non da un campo in piu' che potrebbe divergere.
SUBJECT_KINDS = ("tipo", "integrazione", "entita", "dispositivo")

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
                f"Sono {', '.join(SUBJECT_KINDS)}")
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


def _migration_3(conn) -> None:
    """v2 -> v3: si tolgono i rifiuti di ricetta scritti da un ponte muto.

    **Ogni riga di `ricetta_non_capita` esistente e' una falsa affermazione**,
    e si puo' dire con certezza perche' quel campo e' nato con la 3.31.0, il
    13/09/2026, e il suo unico scrittore era rotto dal primo minuto: il ponte
    non sapeva ragionare la specie di turno «ricetta», restituiva una decisione
    VUOTA, e quella risposta inesistente veniva registrata come «il modello non
    ha capito questo dispositivo». Un'affermazione sulla comprensione di un
    modello che non e' mai stato interpellato -- e siccome un rifiuto vale come
    risposta data, quel dispositivo non sarebbe stato chiesto mai piu'.

    **Si cancella, e non e' un'eccezione alla regola «mai dati dell'utente».**
    Non sono dati dell'utente: sono righe che questo programma ha scritto su se
    stesso, sbagliando. Lasciarle sarebbe lasciare una bugia in un archivio che
    esiste per non dirne.
    """
    cur = conn.execute("DELETE FROM knowledge WHERE field = 'ricetta_non_capita'")
    if cur.rowcount:
        logger.info(
            "sapere: %d rifiuti di ricetta tolti -- erano stati scritti da un "
            "ponte che non sapeva ragionare quel turno, e dicevano «non "
            "capito» di un modello mai interpellato", cur.rowcount)


def _migration_4(conn) -> None:
    """v3 -> v4: si tolgono le ricette che il registro **non sa piu' eseguire**.

    **La prima ricetta che il modello abbia mai scritto era ineseguibile, e non
    per colpa sua.** Il catalogo che le si mostrava elencava ogni voce del
    registro, `episodio` compresa -- e `episodio` vuole `is_on`, che e' una
    FUNZIONE, che nessun dato puo' portare. La validazione di allora guardava
    solo che il nome esistesse: accettata, scritta, e il resoconto l'ha
    eseguita. Misurato sulla casa vera il 14/09/2026:

        riparazione: {"oggetti": "sollevata",
                      "perche": "TypeError: _episode() missing 2 required
                                 keyword-only arguments: 'is_on' and 'period_end'"}

    e la riaggregazione moriva a ogni riavvio, portandosi via oggetti e
    resoconti di due giorni.

    La validazione nuova la rifiuta, quindi il giorno non muore piu'. Ma la
    riga resterebbe li' per sempre: `devices_to_ask` non richiede a chi una
    risposta l'ha gia' data, e quel dispositivo non avrebbe una ricetta mai
    piu'. Si toglie, e il giro dopo lo richiede -- con un catalogo che non
    offre piu' cio' che non si puo' scrivere.

    **Si guarda solo cio' che non dipende dalla casa.** La validazione completa
    vuole le entita' del dispositivo, che una migrazione non ha; consegnandole
    quelle che la ricetta stessa nomina restano in piedi esattamente i
    controlli sull'operazione -- esiste, si puo' scrivere, ha i parametri, ha
    gli ingressi giusti -- che sono quelli che questa riparazione riguarda. Una
    ricetta che nomina un'entita' sparita non si cancella: quella e' una
    domanda sulla casa di oggi, non sul registro.

    Non e' un'eccezione alla regola «mai dati dell'utente», per la stessa
    ragione di `_migration_3`: sono righe che questo programma ha scritto su se
    stesso, sbagliando.
    """
    _drop_unrunnable_recipes(conn)


def _drop_unrunnable_recipes(conn) -> None:
    """Toglie le righe `ricetta` che la validazione di oggi rifiuta.

    Condivisa fra `_migration_4` e `_migration_5`: la seconda rifa' il lavoro
    della prima con un registro piu' severo, e due copie di questo ciclo
    avrebbero potuto divergere sul significato di «non eseguibile».
    """
    from .recipes import Recipe

    # Il nome del campo e' scritto qui e non importato da `recipe_turn`: quel
    # modulo importa questo, e una migrazione deve dire fra due anni la stessa
    # cosa che dice adesso -- anche se quella costante venisse rinominata.
    rows = conn.execute(
        "SELECT rowid, subject, value FROM knowledge WHERE field = 'ricetta'"
    ).fetchall()
    doomed = []
    for row in rows:
        try:
            data = json.loads(row["value"])
        except (TypeError, ValueError):
            doomed.append((row["rowid"], row["subject"], "non e' JSON"))
            continue
        recipe = Recipe(data)
        outcome = recipe.validate(entities=recipe.entities())
        if not outcome.valid:
            doomed.append((row["rowid"], row["subject"],
                           " \u00b7 ".join(outcome.problems)))
    for rowid, subject, why in doomed:
        conn.execute("DELETE FROM knowledge WHERE rowid = ?", (rowid,))
        logger.info(
            "sapere: ricetta di %s tolta -- il registro non sa eseguirla: %s",
            subject, why)


def _migration_5(conn) -> None:
    """v4 -> v5: si rifa' la pulizia della v4, con il controllo delle FORME.

    La v4 ha tolto le ricette che il registro non sapeva eseguire, e non
    bastava: controllava i nomi, i parametri e il numero di ingressi, non la
    **forma** di ciascuno. La casa vera, riaperta subito dopo, ha risposto

        riparazione: {"oggetti": "sollevata",
                      "perche": "AttributeError: 'list' object has no
                                 attribute 'windows'"}

    -- una ricetta che consegnava la serie di un'entita' a un'operazione che
    voleva un periodo. La v4 l'aveva lasciata li' perche' non sapeva vederla.

    **La stessa funzione, un registro piu' severo**: la validazione di oggi la
    rifiuta, quindi questa migrazione la trova. Rifarla non costa niente su un
    sapere gia' pulito, e una migrazione che si puo' ripetere senza danno e'
    preferibile a una che si deve indovinare.
    """
    _drop_unrunnable_recipes(conn)


def _migration_6(conn) -> None:
    """v5 -> v6: si rifa' la pulizia con le FORME separate al punto giusto.

    La v5 controllava gia' le forme, e non bastava: `serie` diceva **due cose
    diverse** -- le statistiche orarie di Home Assistant, dove ogni punto e' il
    cambio di quell'ora, e le letture cumulate di un contatore. Con una parola
    sola per due cose, una ricetta che dava le prime a `primo_ultimo_differenza`
    -- che vuole le seconde -- passava la validazione e calcolava la variazione
    della variazione.

    **Il numero sbagliato era gia' sulla casa vera**, misurato il 14/09/2026:
    `energia_consumata = -0,98 kWh` nel resoconto del 26/08. Energia consumata
    negativa.

    Separata la forma, quella ricetta e' rifiutata e questa migrazione la
    trova. (I numeri gia' archiviati li disinnesca `store._migration_8`: sono
    due archivi diversi, e ciascuno ripara il suo.)
    """
    _drop_unrunnable_recipes(conn)


def _migration_7(conn) -> None:
    """v6 -> v7: i rifiuti RAGIONATI escono da «non capito», col loro perche'.

    **La porta del sapere, aperta il 15/09/2026, ha mostrato per prima cosa
    una bugia scritta da noi.** Delle 21 righe marcate `non_capito` sulla casa
    vera, **18** portavano questa frase nostra -- «la ricetta non ha nessun
    passo: ... nessuno ha finito di scrivere» -- e le prove archiviate accanto
    la smentivano tutte e 18: il modello aveva risposto col contratto in mano,
    `steps: []` e un `why` pieno («*Una luce ha solo stato acceso/spento: non
    c'e' una misura di comfort o efficienza che valga la pena calcolare da
    un'unica entita' on/off*»). Aveva finito, e aveva detto di no.

    Il proprietario avrebbe letto **ventuno problemi da risolvere dove ce
    n'erano tre**.

    **Si recupera invece di ricomprare.** Il `why` e' gia' li', dentro le
    prove: leggerlo e spostarlo costa zero, cancellare le righe costerebbe 18
    giri del ponte per farsi ridire le stesse parole. Una riga le cui prove
    non si sanno rileggere si cancella -- non si indovina e non si tiene -- e
    il dispositivo torna una domanda aperta.

    Da qui in avanti la separazione e' alla fonte
    (`recipe_turn._is_declined`), e questa migrazione non ha piu' niente da
    fare: vale per cio' che era gia' scritto.
    """
    spostate = cancellate = 0
    rows = conn.execute(
        "SELECT subject, value, evidence FROM knowledge "
        "WHERE field = 'ricetta_non_capita' AND value LIKE '%nessun passo%'"
    ).fetchall()
    for row in rows:
        why = _why_from_evidence(row["evidence"])
        if why:
            conn.execute(
                "UPDATE knowledge SET field = ?, value = ?, verification = NULL "
                "WHERE subject_kind = 'dispositivo' AND subject = ? "
                "AND field = 'ricetta_non_capita'",
                ("ricetta_non_serve", why, row["subject"]))
            spostate += 1
        else:
            conn.execute(
                "DELETE FROM knowledge WHERE subject_kind = 'dispositivo' "
                "AND subject = ? AND field = 'ricetta_non_capita'",
                (row["subject"],))
            cancellate += 1
    if spostate or cancellate:
        logger.info(
            "sapere: %d rifiuti ragionati spostati in «ricetta_non_serve» col "
            "perche' del modello, %d righe illeggibili tolte -- dicevano «non "
            "capito» di un modello che aveva capito e risposto",
            spostate, cancellate)


def _why_from_evidence(evidence: str | None) -> str:
    """Il `why` del modello dentro le prove, o la stringa vuota.

    Le prove sono `il modello ha risposto: <la risposta>`, e la risposta e'
    il JSON del contratto -- eventualmente troncato a 1500 caratteri, che e'
    la ragione per cui **non si pretende che l'intero JSON sia valido**: si
    cerca il solo campo che serve. Se non c'e', non c'e': chi chiama cancella.
    """
    text = str(evidence or "")
    start = text.find('"why"')
    if start < 0:
        return ""
    try:
        # `raw_decode` da dove il valore comincia: legge UNA stringa JSON e si
        # ferma, senza chiedere che cio' che segue sia valido.
        quote = text.index('"', text.index(":", start) + 1)
        value, _ = json.JSONDecoder().raw_decode(text[quote:])
    except (ValueError, json.JSONDecodeError):
        return ""
    return value.strip() if isinstance(value, str) else ""


_SCHEMA_VERSION = 7

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
                    migrations={2: _migration_2, 3: _migration_3,
                                4: _migration_4, 5: _migration_5,
                                6: _migration_6,
                                7: _migration_7})

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

    def summary(self) -> dict:
        """Cosa contiene il sapere: `{"totale": n, "righe": [...]}`.

        Una riga per (specie, campo, provenienza), col suo conteggio.
        **Non tutto insieme**: «177 significati importati da Home Assistant» e
        «tre ricette dedotte dal modello» sono due fatti diversi, e chi legge
        deve poterli distinguere senza scorrere duemila righe.

        **La quarta fondamenta**: se un dato c'e' e nessuno puo' chiederlo,
        non esiste. Fino al 15/09/2026 il sapere si leggeva da tre punti del
        codice e da **nessuna pagina**.

        Ordine stabile, per specie e campo: due letture dello stesso sapere
        devono dare lo stesso ordine, o la pagina sembrerebbe cambiare quando
        non e' cambiato niente.
        """
        with self._lock:
            rows = self._conn.execute(
                # **Il campo si taglia ai due punti.** `direzione:power_importing`
                # e `direzione:energy_exporting_today` sono lo stesso campo con
                # dentro la cosa di cui parlano -- e' cosi' che
                # `by_field_prefix` li cerca. Senza il taglio il riassunto
                # sarebbe lungo quanto il dato: misurato il 15/09/2026, 14
                # righe da uno su 19 totali.
                "SELECT subject_kind, "
                "       CASE WHEN instr(field, ':') > 0 "
                "            THEN substr(field, 1, instr(field, ':') - 1) "
                "            ELSE field END AS campo, "
                "       provenance, COUNT(*) AS quante "
                "FROM knowledge GROUP BY subject_kind, campo, provenance "
                "ORDER BY subject_kind, campo, provenance").fetchall()
        counted = [{"specie": r["subject_kind"], "campo": r["campo"],
                    "provenienza": r["provenance"], "quante": r["quante"]}
                   for r in rows]
        return {"totale": sum(r["quante"] for r in counted), "righe": counted}

    def not_understood(self) -> list[Fact]:
        """Le righe che il modello **non ha capito**, dalla piu' recente.

        Sono precisamente cio' che il proprietario risolverebbe in dieci
        secondi -- «quello e' il contatore dell'acqua» -- e fino al
        15/09/2026 non gliele mostrava nessuno. Il caso vero: un dispositivo
        di cui il modello non ha saputo scrivere una ricetta **non viene
        richiesto mai piu'**, perche' un rifiuto vale come risposta data.

        Portano CHI e QUANDO: una riga di tre settimane fa puo' riguardare un
        dispositivo che nel frattempo e' cambiato, e chi legge deve poterlo
        dire senza indovinare.
        """
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM knowledge "
                "WHERE verification = 'non_capito' "
                # Niente `id`: questa tabella non ne ha uno (la chiave e'
                # soggetto+campo). A pari istante l'ordine si chiude sul
                # soggetto, che e' stabile e leggibile.
                "ORDER BY when_ts DESC, subject").fetchall()
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
