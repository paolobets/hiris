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
from .promessa import (
    CONSERVAZIONE_S, STATI_CONCLUSI, TETTO_IN_SOSPESO, serializza, valida,
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

_CONCLUSI = ",".join("'%s'" % s for s in STATI_CONCLUSI)


def _json(valore) -> str | None:
    return None if valore is None else json.dumps(valore)


class ArchivioPromesse:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- scrivere ------------------------------------------------------

    def crea(self, dati: dict, *, adesso: float) -> dict:
        motivo = valida(dati, adesso=adesso)
        if motivo is not None:
            return {"errore": motivo}
        with self._lock:
            self._pota(adesso)
            in_sospeso = self._conn.execute(
                "SELECT count(*) FROM promesse WHERE stato IN ('in_attesa','in_corso')"
            ).fetchone()[0]
            if in_sospeso >= TETTO_IN_SOSPESO:
                return {"errore": ("ho gia' %d promesse in sospeso, che e' il tetto "
                                   "che HIRIS si e' dato: disdicine una prima di "
                                   "farne un'altra." % TETTO_IN_SOSPESO)}
            ident = secrets.token_urlsafe(9)
            self._conn.execute(
                "INSERT INTO promesse(id,specie,frase,quando_ts,quando_detto,fuso,"
                "chiamata_json,domanda,istantanea_json,recapito,stato,nata_ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'in_attesa',?)",
                (ident, dati["specie"], dati["frase"].strip(), float(dati["quando_ts"]),
                 dati.get("quando_detto"), dati.get("fuso"),
                 _json(dati.get("chiamata")), dati.get("domanda"),
                 _json(dati.get("istantanea")), dati.get("recapito"),
                 adesso))
            self._conn.commit()
        return {"promessa": self.leggi(ident)}

    def prendi(self, promessa_id: str, *, adesso: float) -> bool:
        """`in_attesa` -> `in_corso`, atomica. `False` se qualcuno e' arrivato prima.

        E' QUI che vive «mai due volte»: non nel chiamante, che potrebbe
        dimenticarsene, ma in una `UPDATE ... WHERE stato='in_attesa'` che il
        database serializza per noi.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET stato='in_corso', risvegliata_ts=? "
                "WHERE id=? AND stato='in_attesa'", (adesso, promessa_id))
            self._conn.commit()
            return cur.rowcount == 1

    def concludi(self, promessa_id: str, *, stato: str, adesso: float,
                 motivo: str | None = None, esecuzione_id: str | None = None,
                 testo: str | None = None, avvisare: bool | None = None) -> None:
        if stato not in STATI_CONCLUSI:
            raise ValueError("«%s» non e' uno stato conclusivo" % stato)
        with self._lock:
            self._conn.execute(
                "UPDATE promesse SET stato=?, motivo=?, esecuzione_id=?, testo=?, "
                "avvisare=?, risvegliata_ts=COALESCE(risvegliata_ts, ?) WHERE id=?",
                (stato, motivo, esecuzione_id, testo,
                 None if avvisare is None else int(avvisare), adesso, promessa_id))
            self._conn.commit()

    def disdici(self, promessa_id: str, *, adesso: float) -> dict:
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
                "WHERE id=? AND stato='in_attesa'", (adesso, promessa_id))
            self._conn.commit()
            riuscita = cur.rowcount == 1
        if riuscita:
            return {"promessa": self.leggi(promessa_id)}
        riga = self.leggi(promessa_id)
        if riga is None:
            return {"errore": "non ho nessuna promessa con quell'identificatore."}
        return {"errore": "quella promessa e' gia' %s: non si disdice, si legge."
                          % riga["stato"]}

    def risana(self, *, adesso: float) -> int:
        """Le prese a meta' al riavvio: `fallita`, col motivo, e non ripartono.

        Una promessa `in_corso` all'avvio significa una cosa sola: l'add-on si
        e' fermato mentre la manteneva. Non si sa se l'azione sia partita --
        e proprio per questo non si riprova. Una luce accesa due volte e'
        innocua; una serranda no.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE promesse SET stato='fallita', motivo=? WHERE stato='in_corso'",
                ("l'add-on si e' fermato mentre la manteneva: non l'ho ripetuta, "
                 "perche' non so se fosse gia' partita.",))
            self._conn.commit()
            quante = cur.rowcount
        if quante:
            logger.warning("schedulatore: %d promesse erano in corso all'avvio, "
                           "dichiarate fallite (non ripetute)", quante)
        return quante

    # -- leggere -------------------------------------------------------

    def leggi(self, promessa_id: str) -> dict | None:
        with self._lock:
            riga = self._conn.execute(
                "SELECT * FROM promesse WHERE id=?", (promessa_id,)).fetchone()
        return None if riga is None else serializza(riga)

    def elenca(self, *, solo_in_sospeso: bool = False, limite: int = 50) -> list[dict]:
        with self._lock:
            if solo_in_sospeso:
                righe = self._conn.execute(
                    "SELECT * FROM promesse WHERE stato IN ('in_attesa','in_corso') "
                    "ORDER BY quando_ts ASC LIMIT ?", (int(limite),)).fetchall()
            else:
                righe = self._conn.execute(
                    "SELECT * FROM promesse ORDER BY quando_ts DESC LIMIT ?",
                    (int(limite),)).fetchall()
        return [serializza(r) for r in righe]

    def scadute(self, adesso: float) -> list[dict]:
        with self._lock:
            righe = self._conn.execute(
                "SELECT * FROM promesse WHERE stato='in_attesa' AND quando_ts<=? "
                "ORDER BY quando_ts ASC", (adesso,)).fetchall()
        return [serializza(r) for r in righe]

    # -- potare --------------------------------------------------------

    def _pota(self, adesso: float) -> None:
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
            "DELETE FROM promesse WHERE stato IN (%s) AND risvegliata_ts < ?"
            % _CONCLUSI, (adesso - CONSERVAZIONE_S,))
