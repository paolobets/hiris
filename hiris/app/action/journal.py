"""Il registro delle esecuzioni -- una riga leggibile per ogni azione, e per
ogni origine.

La fetta «comandare» lo aveva promesso e non l'ha costruito: `actuator.py`
scriveva una riga di `logger.info` e basta. Per la fondamenta n.4 quel
registro NON esisteva -- nessuno poteva chiederlo.

Vive ACCANTO alla porta, e non dentro lo schedulatore, per una ragione sola:
un'azione eseguita e' lo stesso fatto qualunque sia l'origine. Un registro
delle sole promesse avrebbe dato allo stesso fatto due trattamenti a seconda
di chi l'ha chiesto -- fondamenta n.3 -- e i due registri sarebbero andati
fusi dopo.

**Il nome non e' `registry.py`**: in questa cartella quel nome e' gia' il
registro dei SERVIZI (cosa Home Assistant sa fare). Due cose diverse non
possono chiamarsi allo stesso modo in due file vicini.

Registra i tentativi che hanno superato la verifica -- riusciti o falliti. Un
rifiuto della verifica non e' un'esecuzione: e' un errore del modello, gia'
detto al modello, e riempirebbe il registro di cose che non sono successe.

Dalla fetta «costruire» registra due generi. Un comando (una chiamata di
servizio, dalla porta) e una costruzione (una scrittura di configurazione,
dall'officina). La tabella e' una sola perche' la domanda dell'utente e' una
sola -- «cosa hai fatto?» -- e due tabelle avrebbero costretto ogni lettore a
interrogarle entrambe e a fonderle a mano.
"""
from __future__ import annotations

import json
import secrets
import threading

from ..storage import connect, init_schema

# Quanto si conserva un'esecuzione (riuscita o fallita) in questo registro.
# E' una politica di QUESTO modulo, non presa in prestito da altrove: la
# cronaca vive ACCANTO alla porta (vedi il docstring del file) e deve reggersi
# da sola, come la porta stessa -- oggi `action/` non importa nulla da
# `keeper/`, e farlo per un solo numero invertirebbe gli strati per
# risparmiare una riga. Vale 90 giorni come la conservazione delle promesse
# concluse (`keeper/promise.py::CONSERVAZIONE_S`): sono due fatti
# distinti -- per quanto si conserva una PROMESSA conclusa, per quanto si
# conserva un'ESECUZIONE -- che oggi COINCIDONO, non uno che insegue l'altro.
# Si possono cambiare separatamente, in futuro, senza che l'altro se ne
# accorga.
EXECUTIONS_RETENTION_S = 90 * 86400

# Quante righe torna UNA interrogazione. La cronaca conserva 90 giorni: senza
# tetto, «cosa hai fatto» su una casa attiva restituirebbe l'intero trimestre
# dentro il contesto di un modello.
MAX_LIST_ROWS = 200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS esecuzioni (
    id TEXT PRIMARY KEY,
    quando_ts REAL NOT NULL,
    origine TEXT NOT NULL,
    servizio TEXT NOT NULL,
    entita_json TEXT NOT NULL,
    eseguito INTEGER NOT NULL,
    cambiato_json TEXT,
    errore TEXT,
    avviso TEXT,
    genere TEXT NOT NULL DEFAULT 'comando',
    oggetto TEXT
);
CREATE INDEX IF NOT EXISTS idx_esecuzioni_quando ON esecuzioni(quando_ts DESC);
"""


def _migration_2(conn) -> None:
    """v1 -> v2: la cronaca registra anche le costruzioni.

    Due colonne aggiunte, nessuna riscritta: le righe gia' scritte restano
    esattamente com'erano e diventano `genere='comando'`, che e' cio' che
    sono. Una migrazione che ricostruisce la tabella per due colonne
    rischierebbe di perdere una cronaca vera per un guadagno estetico.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(esecuzioni)")}
    if "genere" not in existing:
        conn.execute("ALTER TABLE esecuzioni ADD COLUMN genere TEXT NOT NULL "
                     "DEFAULT 'comando'")
    if "oggetto" not in existing:
        conn.execute("ALTER TABLE esecuzioni ADD COLUMN oggetto TEXT")


def _row(r) -> dict:
    return {
        "id": r["id"],
        "quando_ts": r["quando_ts"],
        "origine": r["origine"],
        "servizio": r["servizio"],
        "entita": json.loads(r["entita_json"]),
        "eseguito": bool(r["eseguito"]),
        "cambiato": None if r["cambiato_json"] is None else json.loads(r["cambiato_json"]),
        "errore": r["errore"],
        "avviso": r["avviso"],
        "genere": r["genere"],
        "oggetto": r["oggetto"],
    }


class Journal:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=2, migrations={2: _migration_2})

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def log(self, *, actor: str, service: str, entity: list[str],
                 executed: bool, now: float, changed: list[str] | None = None,
                 error: str | None = None, notice: str | None = None) -> str:
        ident = secrets.token_urlsafe(9)
        with self._lock:
            self._conn.execute(
                "DELETE FROM esecuzioni WHERE quando_ts < ?",
                (now - EXECUTIONS_RETENTION_S,))
            self._conn.execute(
                "INSERT INTO esecuzioni(id,quando_ts,origine,servizio,entita_json,"
                "eseguito,cambiato_json,errore,avviso,genere,oggetto) "
                "VALUES(?,?,?,?,?,?,?,?,?,'comando',NULL)",
                (ident, now, actor, service, json.dumps(list(entity)),
                 int(bool(executed)),
                 None if changed is None else json.dumps(list(changed)),
                 error, notice))
            self._conn.commit()
        return ident

    def log_construction(self, *, actor: str, operation: str, domain: str,
                             key: str, entity: list[str], executed: bool,
                             now: float, error: str | None = None,
                             notice: str | None = None) -> str:
        """Un atto di costruzione, nella STESSA tabella dei comandi.

        Un atto e' lo stesso fatto qualunque sia l'origine e qualunque sia il
        canale: due registri avrebbero dato allo stesso fatto due trattamenti,
        e sarebbero stati fusi dopo (fondamenta 3). `genere` dice come si legge
        la riga.

        **`servizio` per una costruzione porta `dominio.gesto`** -- per esempio
        `automation.create`. Non e' un servizio di Home Assistant e non va letto
        come tale: `genere` e' li' apposta per distinguerli. `entita` porta le
        entita' NATE o toccate dall'atto, che e' la stessa cosa che porta per
        un comando.
        """
        ident = secrets.token_urlsafe(9)
        with self._lock:
            self._conn.execute(
                "DELETE FROM esecuzioni WHERE quando_ts < ?",
                (now - EXECUTIONS_RETENTION_S,))
            self._conn.execute(
                "INSERT INTO esecuzioni(id,quando_ts,origine,servizio,entita_json,"
                "eseguito,cambiato_json,errore,avviso,genere,oggetto) "
                "VALUES(?,?,?,?,?,?,NULL,?,?,'costruzione',?)",
                (ident, now, actor, f"{domain}.{operation}",
                 json.dumps(list(entity)), int(bool(executed)), error, notice,
                 f"{domain}.{key}"))
            self._conn.commit()
        return ident

    def read(self, execution_id: str) -> dict | None:
        # Lettura, ma sulla stessa connessione condivisa (`check_same_thread=
        # False`) delle scritture: senza lock qui una `registra` in corso su
        # un altro thread potrebbe intrecciarsi con questa query. E' il
        # pattern appena consolidato in `keeper/store.py`.
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM esecuzioni WHERE id=?", (execution_id,)).fetchone()
        return None if r is None else _row(r)

    def list(self, *, from_ts: float, to_ts: float, entity: str | None = None,
               limit: int = MAX_LIST_ROWS) -> list[dict]:
        """Gli atti di HIRIS in una finestra, dal piu' recente.

        Fino a questa fetta la cronaca si poteva solo SCRIVERE e leggere per
        identificatore: nessuno poteva chiederle «cosa hai fatto ieri», e
        nessuno strumento la esponeva al modello. Era scritta e muta --
        fondamenta 4 -- e il dato per rispondere c'era gia' in tabella.

        `entita` filtra sulla lista DECODIFICATA, non sul JSON grezzo: un
        `LIKE '%light.cucina%'` prenderebbe anche `light.cucina_2`, che e'
        un'altra lampada. Il filtro costa una decodifica per riga sulle sole
        righe gia' ristrette dalla finestra, che l'indice `idx_esecuzioni_
        quando` copre. Il moltiplicatore per 10 sulla lettura da SQL non
        risolve il compromesso, lo sposta: se piu' di `limit*10` righe piu'
        recenti della finestra non appartengono all'entita' cercata, il
        risultato puo' essere vuoto o incompleto pur avendone nella finestra.

        La finestra rispetta il vincolo di conservazione: righe piu' vecchie
        di 90 giorni dalla data di oggi sono potate a ogni scrittura, quindi
        una finestra interamente oltre quel confine restituisce `[]`,
        indistinguibile da «non ho fatto niente in quel periodo».

        Il lock e' lo STESSO delle scritture, per la ragione scritta in
        `read`: connessione condivisa fra thread.
        """
        with self._lock:
            # Il LIMIT di SQL non puo' essere quello finale col filtro per
            # entita': leggiamo 10x il limite richiesto per avere piu' righe
            # su cui applicare il filtro Python. Questo MIGLIORA la probabilita'
            # di trovare righe dell'entita' cercata, ma non la garantisce se
            # la finestra contiene piu' di `limit*10` righe di altre entita'.
            rows = self._conn.execute(
                "SELECT * FROM esecuzioni WHERE quando_ts >= ? AND quando_ts <= ? "
                "ORDER BY quando_ts DESC LIMIT ?",
                (from_ts, to_ts, int(max(1, limit)) if entity is None
                 else int(max(1, limit)) * 10)).fetchall()
        occurrences = [_row(r) for r in rows]
        if entity is not None:
            occurrences = [e for e in occurrences if entity in e["entita"]]
        return occurrences[:int(max(1, limit))]
