"""Cio' che resta di `casa.db`: il comportamento, le plance, e la cornice.

**Ne' l'anagrafe ne' il comportamento sono piu' qui.** Piani, aree, dispositivi, entita', etichette,
categorie e integrazioni erano la copia dei registri di Home Assistant, e la
copia era piu' povera dell'originale -- buttava `translation_key`,
`unique_id`, `original_name`, e non poteva tenere la `classe`, che quel
comando non manda affatto. Si leggono dal vivo: `home_space/reader.py`. Il comportamento
(automazioni e script) e' uscito lo stesso giorno per la stessa ragione: il
file diceva cosa c'e' SCRITTO, Home Assistant dice cosa ESISTE.

Restano tre cose che dai registri non vengono:

- le **plance**, che hanno un'altra fonte e un altro ciclo di vita -- e che
  gia' si leggono dal vivo: qui c'e' solo dove si tengono. **Escono con la
  fetta in corso**, e con loro questo file;
- il **sistema di riferimento** (`remember_reference_frame`), che non e' una
  copia di un fatto di HA ma la cornice in cui e' scritto il nostro archivio.

La memoria, che non si ricostruisce da nessuna parte, vive in un altro
archivio: vedi docs/design/2026-08-05-la-conoscenza-di-hiris.md, §1.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from ..proxy._sanitize import sanitize_ha_value
from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    chiave TEXT PRIMARY KEY, valore TEXT
);
CREATE TABLE IF NOT EXISTS plance (
    percorso TEXT PRIMARY KEY, titolo TEXT, modalita TEXT,
    config TEXT, entita TEXT NOT NULL DEFAULT '[]'
);
"""


#: Le sette tabelle della copia dei registri, uscite il 10/09/2026. Il nome
#: resta qui perche' la migrazione deve poterle CANCELLARE dagli archivi che
#: gia' esistono: toglierle dallo schema non le toglie da un file gia' creato,
#: e resterebbero a occupare spazio e a mentire a chi apre il database.
_REGISTRY_TABLES = ("piani", "aree", "dispositivi", "entita", "etichette",
                    "categorie", "integrazioni", "comportamento")


def _migration_8_registries_out(conn) -> None:
    """L'anagrafe e il comportamento escono da `casa.db`: si leggono dal vivo
    (`home_space/reader.py`, `home_space/behavior.py`).

    `DROP TABLE IF EXISTS` e non un `DELETE`: non e' un travaso, e' una casa
    che cambia padrone. Gli indici cadono con le loro tabelle.

    Le migrazioni 2-7 non esistono piu': toccavano tutte e sole queste otto
    tabelle (una colonna `motivo`, le entita' di riferimento di un'area, le
    categorie, l'identita' di una categoria, l'origine di un'integrazione,
    l'appartenenza a un'istanza). Un archivio fermo a una versione vecchia le
    salta e arriva qui, dove le tabelle che quelle migrazioni riparavano
    vengono cancellate: riparare una tabella per poi cancellarla sarebbe
    lavoro per nessuno.
    """
    for table in _REGISTRY_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


_MIGRATIONS = {8: _migration_8_registries_out}



# La plancia predefinita di Home Assistant ha `url_path` nullo. SQLite non
# considera due NULL uguali (NULL != NULL): usarlo come chiave primaria non
# la protegge da duplicati, quindi la si archivia sotto una chiave esplicita
# e la si ritraduce a `None` in lettura — vedi dashboards()/replace_dashboards().
_MAIN_DASHBOARD_KEY = "__principale__"


def _list(value) -> str:
    return json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)


def _name(value) -> str | None:
    """Un nome/alias/titolo destinato all'anagrafe, sanificato al confine.

    C-2 (L1-sicurezza.md): il `nome` di un'automazione e' il `friendly_name`
    letto da Home Assistant, cioe' testo che HIRIS non controlla. Sanificare
    al confine, e non a valle, significa che ogni lettore eredita la difesa
    senza doverla ripetere -- un punto solo, non cinque. Il gemello per
    l'anagrafe vive ora in `reader.clean_name`, che e' la stessa decisione
    nello stesso punto del flusso: la costruzione.

    `None`/non-stringa passano invariati: un campo assente non deve
    diventare una stringa vuota che afferma "questo nome c'e' ed e' vuoto".

    Usa `sanitize_ha_value` (tetto 255): ogni campo che passa di qui e'
    `state`-shaped (friendly_name, titolo, alias) -- per `motivo`, che non lo
    e', vedi `_motivo()` sotto (M2, audit-2026-08-25, minori)."""
    return sanitize_ha_value(value) if isinstance(value, str) else value



class HomeSpaceStore:
    def __init__(self, db_path: str = "/data/casa.db") -> None:
        self._conn = connect(db_path)
        init_schema(self._conn, _SCHEMA, version=8, migrations=_MIGRATIONS)

    def close(self) -> None:
        self._conn.close()

    def reference_frame(self) -> dict:
        """Il sistema di riferimento della casa: `{fuso, valuta, lingua,
        paese, nome, versione_ha, unita}` -- `{}` se non e' mai stato letto.

        `{}` e non `None`: chi legge deve poter fare `.get("fuso")` senza
        sapere prima se la casa e' stata mai letta. Il "non lo so" non si
        dichiara con un tipo diverso ma con la chiave che manca -- che e'
        anche cio' che dice il nucleo, tacendo invece di inventare un fuso.
        """
        row = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'sistema_di_riferimento'").fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row["valore"])
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def remember_reference_frame(self, frame: dict | None) -> None:
        """Scrive il sistema di riferimento, e **solo quello**.

        E' l'unica cosa dell'anagrafe che sopravvive ai riavvii da quando la
        casa si legge dal vivo (`reader.HomeSpace`), e non e' un'eccezione
        arbitraria: il fuso non e' una copia di un fatto di Home Assistant, e'
        **la cornice in cui e' scritto il nostro archivio**. I 22 giorni di
        grezzo sono istanti; senza il fuso non si sanno nemmeno dividere in
        giorni, e la riparazione d'avvio -- che gira prima che HA abbia
        risposto -- attribuirebbe gli episodi notturni al giorno sbagliato.
        Misurato: e' il difetto per cui esiste
        `test_mind_wiring.py::test_le_due_porte_sullo_stesso_grezzo_producono_
        gli_stessi_oggetti`.

        Vuoto o assente NON cancella quello di prima: il fuso di ieri e'
        ancora il fuso giusto, e un riferimento cancellato farebbe leggere
        ogni temperatura senza sapere in che scala.
        """
        if not frame:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (chiave, valore) "
            "VALUES ('sistema_di_riferimento', ?)",
            (json.dumps(frame, ensure_ascii=False),))
        self._conn.commit()

    def replace_dashboards(self, entries: list[dict],
                           unavailable: list[str] | None = None) -> None:
        """Rimpiazza le plance. Tutto o niente, stessa forma di
        replace_behavior(): stesso BEGIN/rollback, stesso
        scioglimento del JSON, `config` a `None` che resta `None`.

        NON sta in _TABELLE ne' in replace(): le plance hanno una
        cadenza propria (l'evento DASHBOARD_EVENT), diversa da quella
        dell'anagrafe — ci finirebbero cancellate a ogni ricostruzione dei
        registri.

        `non_disponibili` si archivia accanto ai dati, stesso principio di
        `non_disponibili` dell'anagrafe: senza conservarlo, /api/home-space non
        potrebbe dire perche' una plancia manca.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM plance")
            for v in entries:
                path = v.get("url_path")
                key = path if path is not None else _MAIN_DASHBOARD_KEY
                config = v.get("config")
                c.execute(
                    "INSERT INTO plance (percorso, titolo, modalita, config, entita) "
                    "VALUES (?,?,?,?,?)",
                    (key, v.get("title"), v.get("mode"),
                     # `None` resta `None`: «plancia illeggibile» e «plancia
                     # senza viste» sono due cose diverse (vedi leggi_plance).
                     None if config is None else json.dumps(config, ensure_ascii=False),
                     _list(v.get("entita"))))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('plance_lette_il', ?)",
                      (datetime.now(UTC).isoformat(timespec="seconds"),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('plance_non_disponibili', ?)",
                      (json.dumps(list(unavailable or []), ensure_ascii=False),))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def dashboards_loaded_at(self) -> str | None:
        """Quando le plance sono state rilette l'ultima volta -- data propria,
        diversa da `aggiornata_il()` (anagrafe) e da `comportamento_letto_il()`."""
        row = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'plance_lette_il'").fetchone()
        return row["valore"] if row else None

    def unavailable_dashboards(self) -> list[str]:
        """Le plance/percorsi che l'ultima lettura non e' riuscita a
        risolvere (elenco non arrivato, config illeggibile, percorso
        duplicato). Vedi `comportamento.reread_dashboards()`."""
        row = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'plance_non_disponibili'").fetchone()
        if not row:
            return []
        try:
            value = json.loads(row["valore"])
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    def dashboards(self) -> list[dict]:
        """Le plance con la loro configurazione, coi campi JSON gia' sciolti.

        La predefinita torna con `percorso` a `None`, come l'ha data
        `read_dashboards()`: la chiave esplicita usata per archiviarla e' un
        dettaglio di storage, non deve trapelare verso l'esterno.
        """
        entries = []
        for row in self._conn.execute("SELECT * FROM plance ORDER BY percorso").fetchall():
            v = dict(row)
            if v.get("percorso") == _MAIN_DASHBOARD_KEY:
                v["percorso"] = None
            if v.get("config") is not None:
                try:
                    v["config"] = json.loads(v["config"])
                except (TypeError, ValueError):
                    v["config"] = None
            try:
                v["entita"] = json.loads(v["entita"])
            except (TypeError, ValueError):
                v["entita"] = []
            entries.append(v)
        return entries

