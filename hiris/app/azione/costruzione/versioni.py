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

from ...storage import connect, init_schema

logger = logging.getLogger(__name__)

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
    motivo TEXT
);
CREATE INDEX IF NOT EXISTS idx_costruzioni_stato ON costruzioni(stato, creata_ts DESC);
CREATE INDEX IF NOT EXISTS idx_costruzioni_oggetto ON costruzioni(dominio, chiave, creata_ts DESC);
"""


def _carica(testo):
    return None if testo is None else json.loads(testo)


def _riga(r) -> dict:
    return {
        "id": r["id"],
        "creata_ts": r["creata_ts"],
        "aggiornata_ts": r["aggiornata_ts"],
        "stato": r["stato"],
        "gesto": r["gesto"],
        "dominio": r["dominio"],
        "chiave": r["chiave"],
        "origine": r["origine"],
        "turno": r["turno"],
        "frase": r["frase"],
        "prima": _carica(r["prima_json"]),
        "dopo": _carica(r["dopo_json"]),
        "helper": _carica(r["helper_json"]) or [],
        "anteprima": r["anteprima"],
        "esecuzione_id": r["esecuzione_id"],
        "motivo": r["motivo"],
    }


class ArchivioCostruzioni:
    """L'unica casa delle proposte e delle versioni. Non parla con Home Assistant."""

    # Tetti dichiarati (spec §7). Non sono opzioni: un numero che l'utente puo'
    # cambiare e' un secondo comportamento da mantenere.
    MAX_IN_ATTESA = 20
    SCADENZA_S = 7 * 86400
    CONSERVAZIONE_S = 90 * 86400

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def proponi(self, *, gesto: str, dominio: str, chiave: str, origine: str,
                turno: str | None, frase: str | None, prima: dict | None,
                dopo: dict | None, helper: list, anteprima: str,
                adesso: float) -> dict:
        ident = secrets.token_urlsafe(9)
        with self._lock:
            self._pota(adesso)
            # Le scadute si contano fuori dal tetto, e questa e' l'unica
            # ragione per cui `scadi` viene chiamata in produzione: senza
            # questa riga la scadenza sarebbe scritta e mai eseguita -- una
            # regola vera solo nei test.
            self._scadi(adesso)
            aperte = self._conn.execute(
                "SELECT count(*) FROM costruzioni WHERE stato='in_attesa'").fetchone()[0]
            if aperte >= self.MAX_IN_ATTESA:
                return {"errore": (f"ci sono gia' {aperte} proposte in attesa (il tetto e' "
                                   f"{self.MAX_IN_ATTESA}): decidi quelle prima di farne altre.")}
            self._conn.execute(
                "INSERT INTO costruzioni(id,creata_ts,aggiornata_ts,stato,gesto,dominio,"
                "chiave,origine,turno,frase,prima_json,dopo_json,helper_json,anteprima,"
                "esecuzione_id,motivo) VALUES(?,?,?,'in_attesa',?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                (ident, adesso, adesso, gesto, dominio, chiave, origine, turno, frase,
                 None if prima is None else json.dumps(prima),
                 None if dopo is None else json.dumps(dopo),
                 json.dumps(list(helper)), anteprima))
            self._conn.commit()
        return {"id": ident}

    def leggi(self, ident: str) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM costruzioni WHERE id=?", (ident,)).fetchone()
        return None if r is None else _riga(r)

    def elenca(self, *, solo_in_attesa: bool = False, limite: int = 200) -> list[dict]:
        sql = "SELECT * FROM costruzioni"
        if solo_in_attesa:
            sql += " WHERE stato='in_attesa'"
        sql += " ORDER BY creata_ts DESC LIMIT ?"
        with self._lock:
            righe = self._conn.execute(sql, (int(limite),)).fetchall()
        return [_riga(r) for r in righe]

    def segna_applicata(self, ident: str, *, adesso: float,
                        esecuzione_id: str | None) -> dict:
        return self._cambia_stato(ident, "applicata", adesso, esecuzione_id, None)

    def segna_rifiutata(self, ident: str, *, adesso: float, motivo: str) -> dict:
        return self._cambia_stato(ident, "rifiutata", adesso, None, motivo)

    def _cambia_stato(self, ident: str, stato: str, adesso: float,
                      esecuzione_id: str | None, motivo: str | None) -> dict:
        with self._lock:
            # Il `WHERE stato='in_attesa'` sta nella UPDATE e non in un
            # controllo del chiamante: e' cosi' che due conferme simultanee
            # non applicano due volte la stessa proposta. Stessa forma della
            # presa in carico di una promessa (`schedulatore/archivio.py`).
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato=?, aggiornata_ts=?, esecuzione_id=?, motivo=? "
                "WHERE id=? AND stato='in_attesa'",
                (stato, adesso, esecuzione_id, motivo, ident))
            self._conn.commit()
        if cur.rowcount == 0:
            return {"errore": "quella proposta non e' piu' in attesa"}
        return {"id": ident, "stato": stato}

    def scadi(self, adesso: float) -> int:
        """Le proposte troppo vecchie diventano `scaduta`. Restituisce quante.

        Non si cancellano: sparire in silenzio renderebbe indistinguibile «e'
        scaduta» da «non l'ho mai proposta».
        """
        with self._lock:
            return self._scadi(adesso)

    def _scadi(self, adesso: float) -> int:
        """Il corpo, **senza lock**: lo chiama `proponi`, che il lock ce l'ha
        gia' in mano. `threading.Lock` non e' rientrante -- prenderlo due volte
        bloccherebbe il processo, non solleverebbe."""
        cur = self._conn.execute(
            "UPDATE costruzioni SET stato='scaduta', aggiornata_ts=?, "
            "motivo='scaduta senza risposta' "
            "WHERE stato='in_attesa' AND creata_ts < ?",
            (adesso, adesso - self.SCADENZA_S))
        self._conn.commit()
        return cur.rowcount

    def ultima_applicata(self, dominio: str, chiave: str) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM costruzioni WHERE dominio=? AND chiave=? AND stato='applicata' "
                "ORDER BY creata_ts DESC LIMIT 1", (dominio, chiave)).fetchone()
        return None if r is None else _riga(r)

    def _pota(self, adesso: float) -> int:
        """Le righe vecchie se ne vanno -- tranne l'ultima applicata di ogni
        oggetto, che e' l'unica copia del «prima» rimasta al mondo.

        E' l'unica operazione irreversibile del modulo: restituisce quante
        righe ha tolto e lo scrive nel log quando ne toglie almeno una, cosi'
        una regressione nella soglia o nella chiave di partizione lascia una
        traccia invece di sparire in silenzio. Committa da sola: la sua
        durabilita' non puo' dipendere dal commit di un metodo chiamato dopo.

        Va chiamata con il lock gia' preso.
        """
        soglia = adesso - self.CONSERVAZIONE_S
        cur = self._conn.execute(
            "DELETE FROM costruzioni WHERE creata_ts < ? AND id NOT IN ("
            "  SELECT id FROM ("
            "    SELECT id, ROW_NUMBER() OVER ("
            "      PARTITION BY dominio, chiave ORDER BY creata_ts DESC) AS rn"
            "    FROM costruzioni WHERE stato='applicata'"
            "  ) WHERE rn = 1)",
            (soglia,))
        self._conn.commit()
        quante = cur.rowcount
        if quante:
            logger.info("costruzioni: potate %d righe piu' vecchie della soglia %s "
                        "(l'ultima applicata di ogni oggetto e' esclusa)", quante, soglia)
        return quante
