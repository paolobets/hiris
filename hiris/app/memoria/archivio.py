"""L'archivio della memoria -- l'unica cosa di HIRIS che non si ricostruisce.

Tutto il resto (`hiris/app/casa/archivio.py`) e' una REPLICA di cio' che Home
Assistant dichiara: si cancella e si rifa' in pochi secondi. Questo archivio
no: e' cio' che l'utente ha detto e cio' che HIRIS ne ha capito. Per questo
vive nel suo file (`/data/memoria.db`), separato da `casa.db` -- non si mette
una cosa usa-e-getta accanto a una irripetibile.

Vedi docs/design/2026-08-05-la-conoscenza-di-hiris.md, §1, per il contratto
completo. Tre regole guidano questo modulo:

1. **Il testo e' la verita'.** `ricorda()` archivia la frase cosi' com'e'
   stata detta; tutto il resto (`forza`, `grandezza`, le ancore, le
   condizioni) e' un'INTERPRETAZIONE di quella frase, e puo' essere rifatta
   senza toccare il testo.
2. **Si corregge l'interpretazione, non il ricordo.** `correggi()` non tocca
   mai `testo`: alza `corretto_da_utente` per dire alla pagina "questo
   l'ha aggiustato l'utente", cosa utile a capire quanto spesso HIRIS
   interpreta male.
3. **Un ricordo a meta' e' peggio di nessun ricordo**, perche' non si
   distingue da uno interpretato male. Ogni scrittura multi-riga (`ricorda`,
   `correggi`, `dimentica`) usa `BEGIN`/`rollback`, stessa forma di
   `ArchivioCasa.sostituisci`.

**Questo archivio e' nudo di proposito.** Niente `status`, niente
`chatbot_id`, niente `sensitivity`, niente scadenza, niente ambito per
proprietario: quelle difese, nella 1.x, proteggevano confini che la 2.0 non
ha ancora. "Prima le strutture, poi le sicurezze" (CLAUDE.md) -- le
difese vere si derivano dai rischi della 2.0, in una fase dedicata, non si
ereditano da un prodotto diverso. In particolare: **niente colonna di
scadenza**. Nella 1.x c'era (`valid_until`), e ha fatto sparire in silenzio
ricordi veri dell'utente dopo novanta giorni. Qui la memoria non evapora.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ricordi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    testo TEXT NOT NULL,
    detto_da TEXT,
    detto_il TEXT NOT NULL,
    forza TEXT,
    grandezza TEXT,
    minimo REAL,
    massimo REAL,
    unita TEXT,
    corretto_da_utente INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ancore (
    ricordo_id INTEGER NOT NULL REFERENCES ricordi(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    riferimento TEXT NOT NULL,
    nome_visto TEXT
);
CREATE TABLE IF NOT EXISTS condizioni (
    ricordo_id INTEGER NOT NULL REFERENCES ricordi(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    valore TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ancore_rif ON ancore(riferimento);
CREATE INDEX IF NOT EXISTS idx_ancore_ricordo ON ancore(ricordo_id);
CREATE INDEX IF NOT EXISTS idx_condizioni_ricordo ON condizioni(ricordo_id);
"""

# Le uniche colonne di `ricordi` che `correggi()` puo' toccare -- MAI
# `testo` (regola 2: si corregge l'interpretazione, non il ricordo) e MAI
# `id`/`detto_il`/`corretto_da_utente`, che il codice gestisce da solo.
# La whitelist tiene anche la SQL dinamica di `correggi()` al riparo da nomi
# di colonna che non esistono: un `**campi` sbagliato solleva subito, invece
# di fallire dentro la INSERT con un messaggio SQLite poco chiaro.
_CAMPI_MODIFICABILI = {"detto_da", "forza", "grandezza", "minimo", "massimo", "unita"}


class ArchivioMemoria:
    def __init__(self, db_path: str = "/data/memoria.db") -> None:
        self._conn = connect(db_path)
        init_schema(self._conn, _SCHEMA, version=1)

    def chiudi(self) -> None:
        self._conn.close()

    def ricorda(self, testo: str, detto_da: str | None, ancore=(), condizioni=(),
                forza: str | None = None, grandezza: str | None = None,
                minimo: float | None = None, massimo: float | None = None,
                unita: str | None = None) -> int:
        """Archivia un ricordo nuovo, con le sue ancore e condizioni.

        Un ricordo nudo (nessuna ancora, nessuna condizione, nessuna forza)
        e' un ricordo intero, non un ricordo a meta': la struttura e'
        un'aggiunta opzionale sopra il testo, mai una sua precondizione.

        Tutto in una transazione: se un'ancora e' malformata (manca
        `riferimento`, per esempio) l'intera scrittura si annulla, cosi' non
        resta un ricordo senza le ancore che avrebbe dovuto avere -- che
        sarebbe indistinguibile da un ricordo interpretato male.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            cursore = c.execute(
                "INSERT INTO ricordi "
                "(testo, detto_da, detto_il, forza, grandezza, minimo, massimo, unita) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (testo, detto_da, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 forza, grandezza, minimo, massimo, unita))
            ricordo_id = cursore.lastrowid
            self._scrivi_ancore(ricordo_id, ancore)
            self._scrivi_condizioni(ricordo_id, condizioni)
            c.commit()
            return ricordo_id
        except Exception:
            c.rollback()
            raise

    def richiama(self, limite: int = 20) -> list[dict]:
        """Gli ultimi `limite` ricordi, i piu' recenti prima, con ancore e
        condizioni gia' risolte."""
        righe = self._conn.execute(
            "SELECT * FROM ricordi ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [self._componi(dict(r)) for r in righe]

    def per_ancora(self, tipo: str, riferimento: str) -> list[dict]:
        """I ricordi ancorati a `riferimento` con quel `tipo` (un'area,
        un'entita', un dispositivo), i piu' recenti prima.

        Il contratto di un'ancora e' la COPPIA tipo+riferimento (stessa
        forma di `Indice.verifica()` in riconoscitore.py): un `riferimento`
        da solo non basta, o un'entita' e un'area con lo stesso id
        letterale (capita raramente, ma capita) si mescolerebbero.

        E' il punto per cui le ancore esistono: senza un modo per chiedere
        "quali preferenze riguardano la sala da pranzo?", un'ancora sarebbe
        solo un campo scritto e mai riletto.
        """
        righe = self._conn.execute(
            "SELECT DISTINCT r.* FROM ricordi r "
            "JOIN ancore a ON a.ricordo_id = r.id "
            "WHERE a.tipo = ? AND a.riferimento = ? ORDER BY r.id DESC",
            (tipo, riferimento)).fetchall()
        return [self._componi(dict(r)) for r in righe]

    def ottieni(self, id: int) -> dict | None:
        """Un ricordo per id, con ancore e condizioni gia' risolte, o
        `None` se non esiste.

        Serve a chi deve leggere lo stato ARCHIVIATO prima di scrivere una
        correzione parziale -- handlers_memoria.py verifica la coerenza di
        un intervallo (minimo/massimo) contro il valore gia' archiviato
        quando la richiesta ne tocca solo meta', non contro `None`.
        """
        riga = self._conn.execute("SELECT * FROM ricordi WHERE id = ?", (id,)).fetchone()
        return self._componi(dict(riga)) if riga else None

    def conta(self) -> int:
        """Quanti ricordi ci sono in tutto -- non solo i `limite` che
        `richiama()` restituisce. La memoria non evapora (regola del
        modulo): oltre `limite` voci restano vere e proprio invisibili
        senza questo numero, e un ricordo invisibile e' indistinguibile
        da uno cancellato."""
        riga = self._conn.execute("SELECT COUNT(*) AS n FROM ricordi").fetchone()
        return riga["n"]

    def correggi(self, id: int, **campi) -> bool:
        """Corregge l'interpretazione di un ricordo -- mai il testo.

        `campi` puo' contenere colonne scalari di `ricordi` (`forza`,
        `grandezza`, `minimo`, `massimo`, `unita`, `detto_da`) e/o le liste
        `ancore`/`condizioni`, che vengono SOSTITUITE per intero (stessa
        logica di `ArchivioCasa.sostituisci`: rattoppare per singola riga
        aprirebbe una classe di derive silenziose). Alza sempre
        `corretto_da_utente`, anche se si corregge solo `ancore` o
        `condizioni`: e' comunque HIRIS che aveva interpretato male.

        Restituisce `True` se `id` esisteva ed e' stato corretto, `False`
        se non esisteva -- il chiamante DEVE poterlo distinguere da un
        successo (handlers_memoria.py risponde 404, non 200 `ok: true`:
        un `PATCH` su un id sparito non e' andato a buon fine solo perche'
        la UPDATE non ha sollevato). L'UPDATE su `ricordi` gira SEMPRE,
        anche quando `campi` e' vuoto (il ramo `else` sotto), proprio
        perche' e' l'unico punto che tocca la tabella genitrice e puo'
        quindi controllare `rowcount` prima di scrivere ancore/condizioni:
        se `id` non esiste, la INSERT in `ancore` violerebbe la chiave
        esterna con un `IntegrityError` non gestito invece di un rifiuto
        pulito -- controllare qui prima evita anche quello.
        """
        ancore = campi.pop("ancore", None)
        condizioni = campi.pop("condizioni", None)
        ignoti = set(campi) - _CAMPI_MODIFICABILI
        if ignoti:
            raise ValueError(f"correggi(): campi non modificabili: {sorted(ignoti)}")

        c = self._conn
        try:
            c.execute("BEGIN")
            assegnazioni = ", ".join(f"{colonna} = ?" for colonna in campi)
            if assegnazioni:
                cursore = c.execute(f"UPDATE ricordi SET {assegnazioni}, corretto_da_utente = 1 "
                                     f"WHERE id = ?", (*campi.values(), id))
            else:
                cursore = c.execute(
                    "UPDATE ricordi SET corretto_da_utente = 1 WHERE id = ?", (id,))
            if cursore.rowcount == 0:
                c.rollback()
                return False
            if ancore is not None:
                c.execute("DELETE FROM ancore WHERE ricordo_id = ?", (id,))
                self._scrivi_ancore(id, ancore)
            if condizioni is not None:
                c.execute("DELETE FROM condizioni WHERE ricordo_id = ?", (id,))
                self._scrivi_condizioni(id, condizioni)
            c.commit()
            return True
        except Exception:
            c.rollback()
            raise

    def dimentica(self, id: int) -> None:
        """Cancella un ricordo, con le sue ancore e condizioni.

        Le tabelle figlie hanno `ON DELETE CASCADE`, ma quel vincolo conta
        solo perche' `storage.connect()` attiva `PRAGMA foreign_keys=ON` --
        senza, questa singola DELETE lascerebbe ancore e condizioni orfane
        e nessun test se ne accorgerebbe finche' non si contano le righe
        avanzate. Il `BEGIN`/`rollback` resta comunque: la CASCADE e' un
        meccanismo di SQLite dentro la stessa transazione, non un sostituto
        della transazione.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM ricordi WHERE id = ?", (id,))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def _scrivi_ancore(self, ricordo_id: int, ancore) -> None:
        for a in ancore:
            self._conn.execute(
                "INSERT INTO ancore (ricordo_id, tipo, riferimento, nome_visto) "
                "VALUES (?,?,?,?)",
                (ricordo_id, a["tipo"], a["riferimento"], a.get("nome_visto")))

    def _scrivi_condizioni(self, ricordo_id: int, condizioni) -> None:
        for cond in condizioni:
            self._conn.execute(
                "INSERT INTO condizioni (ricordo_id, tipo, valore) VALUES (?,?,?)",
                (ricordo_id, cond["tipo"], cond["valore"]))

    def _componi(self, riga: dict) -> dict:
        """Un ricordo con le sue ancore e condizioni gia' sciolte -- stessa
        idea di `ArchivioCasa._sciogli`, ma qui la lista viene da tabelle
        proprie, non da una colonna JSON."""
        ricordo_id = riga["id"]
        riga["ancore"] = [dict(a) for a in self._conn.execute(
            "SELECT tipo, riferimento, nome_visto FROM ancore WHERE ricordo_id = ? "
            "ORDER BY rowid", (ricordo_id,)).fetchall()]
        riga["condizioni"] = [dict(c) for c in self._conn.execute(
            "SELECT tipo, valore FROM condizioni WHERE ricordo_id = ? ORDER BY rowid",
            (ricordo_id,)).fetchall()]
        return riga
