"""L'archivio delle promesse: l'UNICA casa di «cosa e quando».

Non esiste un timer per promessa. Un timer in memoria muore al riavvio e
diventa un secondo posto che sa quando: qui la verita' e' la tabella, e
l'orologio (`orologio.py`) non fa che chiederle chi e' scaduto.

Non solleva mai verso il chiamante per un ingresso sbagliato: `crea` e
`disdici` rispondono con un dizionario che porta `errore`, perche' chi li
chiama e' uno strumento che parla a un modello. Solleva soltanto cio' che
sollevano SQLite e il filesystem, che non sono errori d'ingresso.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading

from ..storage import connect, init_schema
from .promise import (
    CEILING_IN_SOSPESO,
    CONSERVAZIONE_S,
    STATES_CONCLUSI,
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
    recapito TEXT,
    stato TEXT NOT NULL DEFAULT 'in_attesa',
    motivo TEXT,
    esecuzione_id TEXT,
    testo TEXT,
    avvisare INTEGER,
    nata_ts REAL NOT NULL,
    risvegliata_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_promesse_scadenza ON promesse(stato, quando_ts);
"""

_CONCLUSI = ",".join(f"'{s}'" for s in STATES_CONCLUSI)
# Stessa forma di `_CONCLUSI` qui sopra, per lo stesso motivo: composta UNA
# volta dal vocabolario di `promessa.py`, mai riscritta a mano nelle due
# query sotto (review finale, rilievo ②).
_SOSPESI = ",".join(f"'{s}'" for s in STATES_SOSPESO)


def _json(value) -> str | None:
    return None if value is None else json.dumps(value)


class AgendaStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- scrivere ------------------------------------------------------

    def create(self, data: dict, *, now: float) -> dict:
        reason = validate(data, now=now)
        if reason is not None:
            return {"errore": reason}
        with self._lock:
            self._prune(now)
            in_sospeso = self._conn.execute(
                f"SELECT count(*) FROM promesse WHERE stato IN ({_SOSPESI})"
            ).fetchone()[0]
            if in_sospeso >= CEILING_IN_SOSPESO:
                return {"errore": (
                    f"ho gia' {CEILING_IN_SOSPESO} promesse in sospeso, che e' il tetto "
                    "che HIRIS si e' dato: disdicine una prima di "
                    "farne un'altra."
                )}
            ident = secrets.token_urlsafe(9)
            self._conn.execute(
                "INSERT INTO promesse(id,specie,frase,quando_ts,quando_detto,fuso,"
                "chiamata_json,domanda,istantanea_json,recapito,stato,nata_ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'in_attesa',?)",
                (ident, data["specie"], data["frase"].strip(), float(data["quando_ts"]),
                 data.get("quando_detto"), data.get("fuso"),
                 _json(data.get("chiamata")), data.get("domanda"),
                 _json(data.get("istantanea")), data.get("recapito"),
                 now))
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

    def cancel(self, promise_id: str, *, now: float) -> dict:
        """`in_attesa` -> `disdetta`, atomica sullo stesso modello di `prendi`.

        Non si legge lo stato per DECIDERE: si scrive con una
        `UPDATE ... WHERE stato='in_attesa'` e si guarda il `rowcount`. Se si
        leggesse prima e si scrivesse dopo, l'orologio potrebbe infilare un
        `prendi` (e l'azione vera) nella finestra fra le due mosse: l'azione
        sarebbe avvenuta e l'archivio direbbe comunque «disdetta». La lettura
        resta -- serve a dire ALL'UTENTE perche' non si e' disdetta -- ma
        arriva dopo, per costruire il messaggio, mai per arbitrare.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET stato='disdetta', "
                "risvegliata_ts=COALESCE(risvegliata_ts, ?) "
                "WHERE id=? AND stato='in_attesa'", (now, promise_id))
            self._conn.commit()
            riuscita = cur.rowcount == 1
        if riuscita:
            return {"promessa": self.read(promise_id)}
        row = self.read(promise_id)
        if row is None:
            return {"errore": "non ho nessuna promessa con quell'identificatore."}
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
            "l'add-on si e' fermato mentre la manteneva: non l'ho ripetuta, "
            "perche' non so se fosse gia' partita.")
        _REASON_CHIEDI = (
            "l'add-on si e' fermato mentre guardavo: non ho toccato niente in "
            "casa, ma non so se la notifica fosse gia' partita. Non l'ho "
            "ripetuta: l'ora che mi avevi dato e' passata, e una risposta "
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

    def list(self, *, solo_in_sospeso: bool = False, limit: int = 50) -> list[dict]:
        with self._lock:
            if solo_in_sospeso:
                righe = self._conn.execute(
                    f"SELECT * FROM promesse WHERE stato IN ({_SOSPESI}) "
                    "ORDER BY quando_ts ASC LIMIT ?",
                    (int(limit),)).fetchall()
            else:
                righe = self._conn.execute(
                    "SELECT * FROM promesse ORDER BY quando_ts DESC LIMIT ?",
                    (int(limit),)).fetchall()
        return [serializza(r) for r in righe]

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
        `concludi()` sia `disdici()` lo scrivono con
        `COALESCE(risvegliata_ts, adesso)`, quindi non serve un ripiego su
        `nata_ts` per le righe che non sono mai passate da `prendi()`.

        Chiamata con il lock gia' preso.
        """
        self._conn.execute(
            f"DELETE FROM promesse WHERE stato IN ({_CONCLUSI}) AND risvegliata_ts < ?",
            (now - CONSERVAZIONE_S,),
        )
