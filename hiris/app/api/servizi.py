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
import threading

from ..storage import connect, init_schema

#: I ruoli, dal vocabolario di Home Assistant (spec 2026-09-21 §4). Insieme
#: CHIUSO: una parola nuova arriverebbe da una rotta e diventerebbe un permesso
#: che nessuna pagina sa disegnare.
RUOLI = ("amministratore", "utente", "lettore")

#: Che cosa e' chi chiede. Una macchina non sta in nessun posto, un pannello
#: si' -- e nella cronaca sono due fatti diversi.
SPECIE = ("integrazione", "luogo")

#: Gli stati di un servizio. `revocato` non e' la cancellazione: una riga
#: cancellata potrebbe ripresentarsi e tornare in coda, e allora revocare
#: sarebbe un fastidio invece che una decisione.
STATI = ("in_attesa", "autorizzato", "revocato")

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


def _row(r) -> dict:
    return {"chiave": r["chiave"], "nome": r["nome"], "indirizzo": r["indirizzo"],
            "stato": r["stato"], "ruolo": r["ruolo"], "specie": r["specie"],
            "visto_ts": r["visto_ts"], "deciso_ts": r["deciso_ts"],
            "codice": ServiziStore.codice(r["chiave"])}


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
        impronta = hashlib.sha256(str(chiave or "").encode("utf-8")).digest()
        return f"{int.from_bytes(impronta[:4], 'big') % 10000:04d}"

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
        if specie not in SPECIE:
            raise ValueError(f"specie {specie!r}: sono {', '.join(SPECIE)}")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE servizi SET stato='autorizzato', ruolo=?, specie=?, "
                "deciso_ts=? WHERE chiave=?", (ruolo, specie, now_ts, chiave))
            self._conn.commit()
        return cur.rowcount > 0

    def revoca(self, chiave: str, *, now_ts: float) -> bool:
        """Il no, o il ripensamento. Vale **subito**: revocare e poi aspettare
        sarebbe revocare domani."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE servizi SET stato='revocato', deciso_ts=? WHERE chiave=?",
                (now_ts, chiave))
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

    def elenco(self) -> list[dict]:
        """Tutti, dal più recente: la pagina mostra insieme chi aspetta, chi è
        vivo e chi hai revocato — perché sono la stessa domanda vista in tre
        momenti, e separarli in tre elenchi costringerebbe a cercare."""
        with self._lock:
            righe = self._conn.execute(
                "SELECT * FROM servizi ORDER BY visto_ts DESC").fetchall()
        return [_row(r) for r in righe]

    def pota(self, *, now_ts: float) -> int:
        """Toglie le presentazioni che nessuno ha guardato entro `ATTESA_S`."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM servizi WHERE stato='in_attesa' AND visto_ts < ?",
                (now_ts - self.ATTESA_S,))
            self._conn.commit()
        return cur.rowcount
