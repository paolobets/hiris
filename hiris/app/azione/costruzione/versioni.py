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

# L'insieme «in sospeso» -- stessa forma di `STATI_SOSPESO` in
# `schedulatore/promessa.py`, per lo stesso motivo: una proposta rivendicata
# (`in_corso`) non e' ancora conclusa, e non deve sparire dall'elenco delle
# pendenti ne' smettere di contare contro il tetto nella finestra fra
# `rivendica` e la transizione finale (`applicata`/`rifiutata`).
STATI_SOSPESO = ("in_attesa", "in_corso")
_SOSPESI_SQL = ",".join(f"'{s}'" for s in STATI_SOSPESO)

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
            # `stato IN (STATI_SOSPESO)`, non solo `in_attesa`: una proposta
            # rivendicata (`in_corso`) e' ancora in sospeso, e deve continuare
            # a occupare un posto sotto il tetto -- se contasse solo
            # `in_attesa`, due `applica` in corsa potrebbero far salire il
            # numero vero di proposte in volo oltre il tetto nella finestra
            # fra `rivendica` e la transizione finale.
            aperte = self._conn.execute(
                f"SELECT count(*) FROM costruzioni WHERE stato IN ({_SOSPESI_SQL})").fetchone()[0]
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
        """`solo_in_attesa=True` elenca le pendenti -- `stato IN
        (STATI_SOSPESO)`, non solo `in_attesa`: una proposta rivendicata
        (`in_corso`) non e' ancora conclusa, e non deve sparire dall'elenco
        nella finestra fra `rivendica` e la transizione finale."""
        sql = "SELECT * FROM costruzioni"
        if solo_in_attesa:
            sql += f" WHERE stato IN ({_SOSPESI_SQL})"
        sql += " ORDER BY creata_ts DESC LIMIT ?"
        with self._lock:
            righe = self._conn.execute(sql, (int(limite),)).fetchall()
        return [_riga(r) for r in righe]

    def rivendica(self, ident: str, *, adesso: float) -> dict:
        """Prende in carico una proposta PRIMA di scrivere su Home Assistant
        (spec §7).

        E' la stessa guardia gia' usata per le promesse in
        `schedulatore/archivio.py`: una UPDATE atomica `WHERE stato=
        'in_attesa'` e' l'UNICO punto in cui due conferme quasi simultanee
        della stessa proposta si possono distinguere. Chi la chiama per primo
        vince e la proposta passa a `in_corso`; l'altro trova `rowcount == 0`
        e deve fermarsi PRIMA di scrivere -- un controllo fatto leggendo lo
        stato con `leggi()` non basta, perche' quella lettura e' gia' stantia
        nel momento stesso in cui la si confronta con una richiesta
        concorrente.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato='in_corso', aggiornata_ts=? "
                "WHERE id=? AND stato='in_attesa'",
                (adesso, ident))
            self._conn.commit()
        if cur.rowcount == 0:
            return {"errore": "quella proposta non e' piu' in attesa"}
        return {"id": ident, "stato": "in_corso"}

    def risana(self, *, adesso: float) -> int:
        """Le proposte rimaste `in_corso` al riavvio: chiuse, non ripescate.

        Stessa forma di `AgendaStore.risana` (`schedulatore/archivio.py`):
        una riga `in_corso` all'avvio significa una cosa sola, l'add-on si e'
        fermato fra `rivendica` e la transizione finale (`applica` non ha
        fatto in tempo a chiamare `segna_applicata` o `segna_rifiutata`).

        **Senza questa chiusura la riga resterebbe un fantasma per sempre**:
        con `rivendica` a farla uscire da `in_attesa`, nessun altro percorso
        del modulo la riporta a uno stato terminale -- non `_scadi` (filtra
        su `stato='in_attesa'`), non un secondo `rivendica` (la sua UPDATE e'
        anch'essa `WHERE stato='in_attesa'`), non l'utente (ogni `applica`
        successiva la troverebbe gia' "in corso" e rifiuterebbe). Invisibile
        a `elenca(solo_in_attesa=True)` PRIMA di questa correzione, non piu'
        adesso che quella query legge `STATI_SOSPESO` -- ma restare `in_corso`
        per sempre resterebbe comunque un fantasma: mai scaduta, sempre
        contata contro il tetto, cancellata in silenzio dalla potatura dopo
        novanta giorni senza che nessuno abbia mai saputo com'e' andata.

        **Non si riprova a scrivere.** Dopo un riavvio a meta' non sappiamo
        se Home Assistant abbia gia' ricevuto la scrittura: ripeterla
        rischierebbe un doppione, non ripeterla rischierebbe di perdere una
        modifica riuscita -- e indovinare in una direzione o nell'altra
        sarebbe peggio che dirlo. Si dichiara **l'incertezza**, non un esito.

        Va chiamata all'avvio (dal Task 8, che monta l'officina), PRIMA che
        una nuova `applica` possa rivendicare qualcosa.

        Restituisce quante righe ha chiuso.
        """
        motivo = ("l'add-on si e' riavviato mentre la stavo applicando: non so "
                  "se la scrittura sia arrivata a Home Assistant.")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato='rifiutata', aggiornata_ts=?, motivo=? "
                "WHERE stato='in_corso'",
                (adesso, motivo))
            self._conn.commit()
            quante = cur.rowcount
        if quante:
            logger.warning("costruzioni: %d proposte erano in_corso all'avvio, "
                           "risanate a rifiutata (non riprovate)", quante)
        return quante

    def segna_applicata(self, ident: str, *, adesso: float,
                        esecuzione_id: str | None) -> dict:
        return self._cambia_stato(ident, "applicata", adesso, esecuzione_id, None)

    def segna_rifiutata(self, ident: str, *, adesso: float, motivo: str) -> dict:
        return self._cambia_stato(ident, "rifiutata", adesso, None, motivo)

    def segna_disdetta(self, ident: str, *, adesso: float) -> dict:
        """Il «no» del proprietario -- che NON e' un fallimento.

        `rifiutata` vuol dire «ho provato e non ci sono riuscito»: validazione
        caduta, Home Assistant che rifiuta, riavvio a meta'. Questo e' l'altro
        caso, ed e' quello che vogliamo sia facile: l'utente ha guardato la
        proposta e ha detto di no. Tenerli separati e' cio' che permette alla
        pagina di non colorare di rosso l'esercizio del controllo per cui
        l'intero giro in due tempi esiste. Stessa distinzione che lo
        schedulatore fa gia' fra `fallita` e `disdetta`, e stessa parola.

        **Transita SOLO da `in_attesa`** -- una `WHERE` dedicata, non quella
        (`IN ('in_attesa','in_corso')`) condivisa da `_cambia_stato` (ondata
        finale, punto 2). L'invariante della potatura (`_pota`, sopra) fu
        dimostrato quando la transizione `in_attesa -> applicata` era a senso
        unico: aggiungere `disdetta` sopra la `WHERE` di `_cambia_stato`
        l'ha rotto in silenzio. La corsa che apriva: una conferma dalla chat
        rivendica la riga (`in_corso`) e comincia a scrivere su Home
        Assistant; nella stessa finestra un Rifiuta dalla pagina la porta a
        `disdetta` PRIMA che la scrittura torni. La scrittura arriva
        comunque a Home Assistant, `segna_applicata` trova la riga gia'
        `disdetta` e fallisce -- ma l'automazione E' stata scritta davvero, e
        la riga che la descrive resta `disdetta`: FUORI dall'insieme protetto
        dalla potatura, quindi il suo «prima» -- l'unica copia esistente al
        mondo di com'era quell'oggetto -- diventa cancellabile a 90 giorni.
        Impedire la disdetta di una riga gia' rivendicata chiude la corsa
        alla radice: chi ha vinto la rivendicazione porta la transizione
        finale fino in fondo (`applicata` o `rifiutata`), e solo allora la
        riga torna leggibile come non piu' in sospeso.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato='disdetta', aggiornata_ts=?, motivo=? "
                "WHERE id=? AND stato='in_attesa'",
                (adesso, "rifiutata dal proprietario", ident))
            self._conn.commit()
        if cur.rowcount == 0:
            return {"errore": "quella proposta non e' piu' in attesa"}
        return {"id": ident, "stato": "disdetta"}

    def _cambia_stato(self, ident: str, stato: str, adesso: float,
                      esecuzione_id: str | None, motivo: str | None) -> dict:
        with self._lock:
            # `IN ('in_attesa','in_corso')`: la transizione finale arriva
            # quasi sempre da `in_corso` (dopo `rivendica`), ma resta valida
            # anche direttamente da `in_attesa` -- i chiamanti che non passano
            # da `rivendica` (i test di questo modulo, per esempio) devono
            # continuare a funzionare esattamente come prima. La UPDATE resta
            # atomica: e' cosi' che due conferme simultanee non applicano due
            # volte la stessa proposta. Stessa forma della presa in carico di
            # una promessa (`schedulatore/archivio.py`).
            cur = self._conn.execute(
                "UPDATE costruzioni SET stato=?, aggiornata_ts=?, esecuzione_id=?, motivo=? "
                "WHERE id=? AND stato IN ('in_attesa','in_corso')",
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
