"""L'archivio dei SERVIZI accoppiati (decisione del proprietario, 22/09/2026).

Fino al 22/09 i servizi esterni si dichiaravano in un campo di testo nelle
opzioni dell'add-on. Il proprietario l'ha respinto per tre ragioni che quel
campo non puo' risolvere:

- **ogni modifica riavvia l'add-on** -- aggiungere un servizio spegne la casa
  per dieci secondi;
- **revocare significa editare un blob di testo**, invece di un gesto;
- e soprattutto **non si vede mai quando un servizio si presenta la prima
  volta**: l'autorizzazione e' gia' data prima che il servizio esista.

Il terzo punto e' quello che rende «by design» questo disegno, e non e' la
crittografia: e' che **il primo contatto e' un evento che il proprietario vede
e approva**.

**La chiave privata non viaggia mai.** La genera il servizio, sulla sua
macchina, e non esce da li'; qui arriva solo la pubblica. Cio' che il
proprietario approva non e' una chiave, e' un **codice breve** che HIRIS gli
mostra e che il servizio mostra a sua volta: se coincidono, sta accoppiando
QUEL servizio e non qualcun altro che si e' messo in mezzo.

**Il codice si deriva dalla chiave**, e non e' casuale: e' cosi' che il servizio
puo' mostrarlo senza scambiare nient'altro con HIRIS. Un codice casuale
richiederebbe un secondo scambio, e quel secondo scambio sarebbe esattamente il
punto in cui qualcuno si mette in mezzo.

**Qui non vive nessun segreto.** Una chiave pubblica non e' un segreto, e un
codice derivato da essa nemmeno: questo archivio si puo' leggere per intero
senza che ne esca niente di utile a nessuno.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable

from ..storage import connect, init_schema

# I ruoli e le specie si chiedono al vocabolario del confine (F-02): fino al
# 07/10/2026 `RUOLI` era scritto due volte, qui e in `canali.py`.
from .canali import RUOLI, SERVICE_SPECIES, SPECIE_IGNOTA

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS servizi (
    chiave TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    indirizzo TEXT NOT NULL,
    stato TEXT NOT NULL,
    ruolo TEXT,
    specie TEXT,
    visto_ts REAL NOT NULL,
    deciso_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_servizi_stato ON servizi(stato, visto_ts DESC);
"""


#: Una presentazione che nessuno ha guardato entro `ServiziStore.ATTESA_S`.
#: Una condizione sola per chi la cancella (`_prune`) e per chi la salta
#: (`elenco`, `approva`, `revoca`): fra la scadenza e la prossima scrittura la
#: riga sta ancora su disco, e nessuna porta la deve vedere.
_EXPIRED_SQL = "(stato='in_attesa' AND visto_ts < ?)"


def _row(r) -> dict:
    return {"chiave": r["chiave"], "nome": r["nome"], "indirizzo": r["indirizzo"],
            "stato": r["stato"], "ruolo": r["ruolo"], "specie": r["specie"],
            "visto_ts": r["visto_ts"], "deciso_ts": r["deciso_ts"],
            "codice": ServiziStore.codice(r["chiave"]),
            "impronta": ServiziStore.fingerprint(r["chiave"])}


class ServiziStore:
    """Chi ha chiesto di parlare con HIRIS, e cosa gli hai risposto."""

    #: Per quanto resta in pagina una presentazione che nessuno ha guardato.
    #:
    #: Chiunque possa raggiungere HIRIS puo' presentarsi: senza scadenza la
    #: pagina si riempie di rumore, e una pagina piena di rumore e' una pagina
    #: che non si guarda piu'. Le AUTORIZZATE non scadono -- quelle le hai
    #: decise tu, e sparire da sole sarebbe un servizio vivo che muore in
    #: silenzio.
    ATTESA_S = 24 * 3600.0

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def codice(chiave: str) -> str:
        """Le quattro cifre da confrontare, derivate dalla chiave pubblica.

        Quattro cifre non sono un segreto e non devono esserlo: non difendono
        da chi indovina, difendono da **chi si è messo in mezzo**. Chi
        intercetta l'accoppiamento non può far coincidere il proprio codice con
        quello che il servizio vero mostra sul suo schermo, e il proprietario
        vede due numeri diversi.
        """
        return f"{int(ServiziStore.fingerprint(chiave)[:8], 16) % 10000:04d}"

    @staticmethod
    def fingerprint(chiave: str) -> str:
        """**L'identita' di un servizio** (S-16, D7 della Tappa 7): l'impronta
        SHA-256 della sua chiave pubblica, in esadecimale. E' l'`id` del suo
        soggetto (`canali.riconosci`) e quindi del suo filo (`specie:id`); il
        nome e' un'etichetta, e due servizi con lo stesso nome restano due.

        L'impronta e non la chiave perche' la chiave in base64 porta `/` e
        `+`, e l'id finisce in chiavi, registri e URL. Il codice di
        accoppiamento (`codice`) si deriva dalla stessa impronta: un fatto,
        una funzione."""
        return hashlib.sha256(str(chiave or "").encode("utf-8")).hexdigest()

    def presenta(self, *, nome: str, chiave: str, indirizzo: str,
                 now_ts: float) -> dict:
        """Un servizio si fa vivo. **Non lo autorizza**: lo mette in coda.

        Presentarsi due volte non crea due righe -- è lo stesso servizio, e la
        pagina deve restare leggibile. E un servizio **revocato** che si
        ripresenta resta revocato: altrimenti basterebbe ribussare per tornare
        in coda, e la revoca non servirebbe a niente.
        """
        if not str(chiave or "").strip():
            raise ValueError("un servizio senza chiave pubblica non si presenta")
        with self._lock:
            # La potatura vive nella scrittura che fa crescere l'archivio, non
            # nella lettura (Tappa 7, Task 0b): una `GET` non scrive.
            self._prune(now_ts)
            esistente = self._conn.execute(
                "SELECT * FROM servizi WHERE chiave=?", (chiave,)).fetchone()
            if esistente is None:
                self._conn.execute(
                    "INSERT INTO servizi(chiave,nome,indirizzo,stato,visto_ts) "
                    "VALUES(?,?,?,'in_attesa',?)",
                    (chiave, str(nome or "senza nome"), str(indirizzo or "?"), now_ts))
            elif esistente["stato"] != "revocato":
                self._conn.execute(
                    "UPDATE servizi SET nome=?, indirizzo=?, visto_ts=? WHERE chiave=?",
                    (str(nome or "senza nome"), str(indirizzo or "?"), now_ts, chiave))
            self._conn.commit()
            riga = self._conn.execute(
                "SELECT * FROM servizi WHERE chiave=?", (chiave,)).fetchone()
        return _row(riga)

    def approva(self, chiave: str, *, ruolo: str, specie: str,
                now_ts: float) -> bool:
        """Il sì del proprietario, col ruolo e la specie che decide lui."""
        if ruolo not in RUOLI:
            raise ValueError(f"ruolo {ruolo!r}: sono {', '.join(RUOLI)}")
        if specie not in SERVICE_SPECIES:
            raise ValueError(f"specie {specie!r}: sono {', '.join(SERVICE_SPECIES)}")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE servizi SET stato='autorizzato', ruolo=?, specie=?, "
                f"deciso_ts=? WHERE chiave=? AND NOT {_EXPIRED_SQL}",
                (ruolo, specie, now_ts, chiave, self._expiry(now_ts)))
            self._conn.commit()
        return cur.rowcount > 0

    def revoca(self, chiave: str, *, now_ts: float) -> bool:
        """Il no, o il ripensamento. Vale **subito**: revocare e poi aspettare
        sarebbe revocare domani."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE servizi SET stato='revocato', deciso_ts=? "
                f"WHERE chiave=? AND NOT {_EXPIRED_SQL}",
                (now_ts, chiave, self._expiry(now_ts)))
            self._conn.commit()
        return cur.rowcount > 0

    def autorizzato(self, chiave: str) -> dict | None:
        """Il servizio dietro questa chiave, **solo se è autorizzato**.

        Finché non l'hai approvato la sua firma non apre niente: se bastasse
        presentarsi, il primo contatto sarebbe l'autorizzazione e non ci
        sarebbe niente da approvare.
        """
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM servizi WHERE chiave=? AND stato='autorizzato'",
                (chiave,)).fetchone()
        return None if r is None else _row(r)

    def elenco(self, *, now_ts: float) -> list[dict]:
        """Tutti, dal più recente: la pagina mostra insieme chi aspetta, chi è
        vivo e chi hai revocato — perché sono la stessa domanda vista in tre
        momenti, e separarli in tre elenchi costringerebbe a cercare.

        Le presentazioni scadute non ci sono, anche se nessuno le ha ancora
        tolte dal disco: una lettura non scrive."""
        with self._lock:
            righe = self._conn.execute(
                f"SELECT * FROM servizi WHERE NOT {_EXPIRED_SQL} "
                "ORDER BY visto_ts DESC", (self._expiry(now_ts),)).fetchall()
        return [_row(r) for r in righe]

    def _expiry(self, now_ts: float) -> float:
        return now_ts - self.ATTESA_S

    def _prune(self, now_ts: float) -> None:
        """Toglie dal disco le presentazioni che nessuno ha guardato entro
        `ATTESA_S`. La chiama `presenta`, che tiene il lucchetto: e' l'unica
        scrittura che fa crescere l'archivio."""
        self._conn.execute(f"DELETE FROM servizi WHERE {_EXPIRED_SQL}",
                           (self._expiry(now_ts),))


#: Quanto resta aperta la finestra di accoppiamento. **Dieci minuti**, decisione
#: del proprietario del 22/09/2026, e sta scritta dove si applica. Non e' lo
#: scarto ammesso sul momento di una firma (`canali.SCARTO_MOMENTO_S`): fino al
#: 07/10/2026 i due fatti avevano lo stesso nome (F-21).
#:
#: La rotta di presentazione e' l'unica superficie che questo prodotto non puo'
#: autenticare: un servizio che non hai ancora approvato **non ha modo** di
#: autenticarsi, ed e' tutto il punto dell'accoppiamento. Invece di difenderla
#: -- tetti sul numero di righe, limiti di ritmo, scadenze -- si e' scelto di
#: **non farla esistere**: c'e' solo nei dieci minuti in cui l'hai aperta tu.
#:
#: Una difesa permanente invecchia. Una porta chiusa no.
ACCOPPIAMENTO_S = 600.0


def service_thread_renames(rows: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Le chiavi dei fili dei servizi, dal nome all'impronta (S-16, D7 della
    Tappa 7): `({vecchia: nuova}, [chiavi ambigue])`.

    Una chiave vecchia e' `specie:nome`, com'era fino al 07/10/2026; la nuova
    `specie:impronta` (`chat_thread.subject_key_for` sul soggetto di
    `canali.riconosci`). Contano i servizi autorizzati e revocati -- quelli
    che hanno potuto parlare. **Due servizi con lo stesso nome e la stessa
    specie non si separano**: il filo era uno, e non c'e' modo di sapere di
    chi fosse ogni sessione. Restano alla chiave vecchia, cioe' a nessuno, e
    si nominano nel registro: dare a uno dei due la cronologia dell'altro
    sarebbe peggio."""
    owners: dict[str, set[str]] = {}
    for row in rows:
        if row.get("stato") not in ("autorizzato", "revocato"):
            continue
        old = f"{row.get('specie') or SPECIE_IGNOTA}:{row.get('nome')}"
        new = f"{row.get('specie') or SPECIE_IGNOTA}:{row.get('impronta')}"
        owners.setdefault(old, set()).add(new)
    renames = {old: next(iter(new)) for old, new in owners.items()
               if len(new) == 1 and old not in new}
    return renames, sorted(old for old, new in owners.items() if len(new) > 1)


def open_services(app, path: str) -> ServiziStore:
    """All'avvio: apre l'archivio dei servizi accoppiati e porta i fili dei
    servizi all'impronta della chiave (`migrate_service_threads`). Vive qui e
    non in `server.py` (regola del 06/10/2026: `server.py` registra e avvia,
    non ospita); l'avvio la chiama al posto del costruttore, DOPO aver aperto
    gli archivi che la migrazione tocca."""
    app["servizi"] = store = ServiziStore(path)
    migrate_service_threads(app)
    return store


def _service_thread_archives(app) -> list[tuple[str, Callable[[dict[str, str]], int]]]:
    """Gli archivi che portano il soggetto di chi ha parlato in una colonna,
    con la funzione che lo rinomina: `(nome per il registro, rekey)`. Un
    archivio che l'avvio non ha aperto (il sapere puo' restare `None`) non
    c'e', e il registro lo tace.

    Fino al 07/10/2026 migravano solo i fili della chat (T8); il soggetto
    vive anche qui, e con la chiave vecchia un servizio perdeva le sue
    promesse in agenda (G83-3, scelta di Paolo: «Migra tutto»)."""
    from .. import chat_store

    archives: list[tuple[str, Callable[[dict[str, str]], int]]] = [
        ("sessioni di chat",
         lambda renames: chat_store.rekey_subjects(app["data_dir"], renames)),
    ]
    named = (("promesse", "agenda"), ("costruzioni", "constructions"),
             ("ricordi", "memory_store"))
    for label, key in named:
        archive = app.get(key)
        if archive is not None:
            archives.append((label, archive.rekey_subjects))
    return archives


def migrate_service_threads(app) -> dict[str, int]:
    """All'avvio: il soggetto dei servizi passa dal nome all'impronta della
    chiave in ogni archivio che lo porta (`_service_thread_archives`), con la
    stessa mappa (`service_thread_renames`), e il registro dice quante righe
    per archivio (la misura dal vivo di D7). Torna `{archivio: righe}`.

    Non solleva: un archivio che non riesce lascia le sue righe dov'erano,
    lo dice, e gli altri migrano lo stesso. Si rifa' a ogni avvio, e dal
    secondo non trova niente: le chiavi vecchie non esistono piu'."""
    store = app.get("servizi")
    if store is None:
        return {}
    try:
        renames, ambiguous = service_thread_renames(store.elenco(now_ts=time.time()))
    except Exception as exc:
        logger.warning("servizi: i fili non sono migrati all'impronta della chiave "
                       "(%s: %s)", type(exc).__name__, exc)
        return {}
    moved: dict[str, int] = {}
    for label, rekey in _service_thread_archives(app):
        try:
            moved[label] = rekey(renames)
        except Exception as exc:
            logger.warning("servizi: %s non migrate all'impronta della chiave "
                           "(%s: %s)", label, type(exc).__name__, exc)
    logger.info("servizi: dal nome all'impronta della chiave (%d servizi) -- %s",
                len(renames),
                ", ".join(f"{n} {label}" for label, n in moved.items()) or "niente")
    if ambiguous:
        logger.warning("servizi: %d nomi portati da piu' servizi, i loro fili restano "
                       "senza padrone: %s", len(ambiguous), ", ".join(ambiguous))
    return moved


def apri_finestra(finestra: dict, *, adesso: float) -> float:
    """Apre l'accoppiamento per `ACCOPPIAMENTO_S` secondi. Torna quando si chiude."""
    finestra["scade"] = adesso + ACCOPPIAMENTO_S
    return finestra["scade"]


def chiudi_finestra(finestra: dict) -> None:
    """La chiude subito: il gesto a mano del proprietario
    (`handlers_servizi.handle_close_window`).

    L'approvazione di un servizio NON la chiama: senza quel gesto la finestra
    resta aperta fino allo scadere.
    """
    finestra.pop("scade", None)


def finestra_aperta(finestra: dict | None, *, adesso: float) -> bool:
    """Se adesso si accetta una presentazione.

    **Nasce chiusa**: se nascesse aperta, «si apre quando lo dici tu» sarebbe
    falso a ogni avvio dell'add-on — e l'add-on riparte spesso.
    """
    return bool((finestra or {}).get("scade", 0) > adesso)


def finestra_resta(finestra: dict | None, *, adesso: float) -> float:
    """Quanti secondi mancano alla chiusura — `0` se è già chiusa.

    Serve alla pagina: una finestra che si apre senza dire quanto dura
    costringe chi la guarda a indovinare.
    """
    return max(0.0, float((finestra or {}).get("scade", 0)) - adesso)


def prepara_finestra(app) -> None:
    """Il contenitore nasce quando l'app si compone, non alla prima apertura.

    E vive **in memoria**, non nell'archivio: una finestra che sopravvive a un
    riavvio è una finestra che ti sei dimenticato aperta.
    """
    app["finestra_servizi"] = {}
