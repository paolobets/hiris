"""Cio' che resta di `casa.db`: il comportamento, le plance, e la cornice.

**L'anagrafe non e' piu' qui.** Piani, aree, dispositivi, entita', etichette,
categorie e integrazioni erano la copia dei registri di Home Assistant, e la
copia era piu' povera dell'originale -- buttava `translation_key`,
`unique_id`, `original_name`, e non poteva tenere la `classe`, che quel
comando non manda affatto. Si leggono dal vivo: `home_space/reader.py`.

Restano tre cose che dai registri non vengono:

- il **comportamento** (`automations.yaml`/`scripts.yaml`) e le **plance**,
  che hanno un'altra fonte e un altro ciclo di vita. **Escono con la Fetta
  1-bis**, e con loro questo file;
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
CREATE TABLE IF NOT EXISTS comportamento (
    id TEXT PRIMARY KEY, tipo TEXT NOT NULL, nome TEXT,
    corpo TEXT, origine TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plance (
    percorso TEXT PRIMARY KEY, titolo TEXT, modalita TEXT,
    config TEXT, entita TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_comportamento_tipo ON comportamento(tipo);
"""


#: Le sette tabelle della copia dei registri, uscite il 10/09/2026. Il nome
#: resta qui perche' la migrazione deve poterle CANCELLARE dagli archivi che
#: gia' esistono: toglierle dallo schema non le toglie da un file gia' creato,
#: e resterebbero a occupare spazio e a mentire a chi apre il database.
_REGISTRY_TABLES = ("piani", "aree", "dispositivi", "entita", "etichette",
                    "categorie", "integrazioni")


def _migration_8_registries_out(conn) -> None:
    """L'anagrafe esce da `casa.db`: si legge dal vivo (`home_space/reader.py`).

    `DROP TABLE IF EXISTS` e non un `DELETE`: non e' un travaso, e' una casa
    che cambia padrone. Gli indici cadono con le loro tabelle.

    Le migrazioni 2-7 non esistono piu': toccavano tutte e sole queste sette
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

    def replace_behavior(self, entries: list[dict], problems: list[str] | None = None,
                                  unloaded_files: dict[str, str] | None = None) -> None:
        """Rimpiazza cio' che la casa sa fare da sola. Tutto o niente.

        Separato da `replace()` perche' cambia con una cadenza diversa
        (giorni contro mesi) e da una fonte diversa (i file di configurazione
        contro i registri): rileggere i registri perche' e' cambiata
        un'automazione sarebbe uno spreco, e viceversa.

        `problems` e `unloaded_files` si archiviano ACCANTO ai dati, non solo
        nei log: sono costruiti con cura da `comportamento.compose()`/`reread()`
        proprio per dire a chi guarda perche' qualcosa manca o e' incerto —
        conservarli solo in una riga di log li rende invisibili a chiunque non
        stia leggendo il log in quel momento (vedi `non_disponibili` sopra,
        stesso principio).

        N2 (review indipendente 25/08/2026): `nome` e `corpo` hanno DUE fonti
        diverse e vanno trattati diversamente. `corpo` viene dal file YAML
        (`automations.yaml`/`scripts.yaml`) che il proprietario di casa
        scrive di persona -- resta cosi' com'e', nessuna sanificazione, come
        gia' deciso per `home_space/behavior.py` in generale. Ma `nome` NON
        viene dal file: e' il `friendly_name` letto da `get_states([])`
        (`comportamento.reread()`), una lettura di rete GREZZA che non
        passa da `entity_cache._to_minimal` -- lo stesso genere di testo
        controllabile da chi non e' il proprietario che C-2 sanifica
        ovunque arrivi cosi'. Sanificato qui con `_name()`, lo stesso
        pattern di `replace()` qui sopra: un punto solo per fonte, non
        un cablaggio dimenticato perche' "e' un file locale" -- quella
        ragione copre il corpo, non il nome.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM comportamento")
            for v in entries:
                body = v.get("corpo")
                c.execute("INSERT INTO comportamento (id, tipo, nome, corpo, origine) "
                          "VALUES (?,?,?,?,?)",
                          (v["id"], v["tipo"], _name(v.get("nome")),
                           # `None` resta `None`: «non ho il corpo» e «il corpo
                           # e' vuoto» sono due cose diverse.
                           None if body is None else json.dumps(body, ensure_ascii=False),
                           v.get("origine", "file")))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_letto_il', ?)",
                      (datetime.now(UTC).isoformat(timespec="seconds"),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_problemi', ?)",
                      (json.dumps(list(problems or []), ensure_ascii=False),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_file_non_letti', ?)",
                      (json.dumps(dict(unloaded_files or {}), ensure_ascii=False),))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def behavior(self) -> list[dict]:
        """Cio' che la casa sa fare da sola, coi corpi gia' sciolti."""
        entries = []
        for row in self._conn.execute("SELECT * FROM comportamento ORDER BY id").fetchall():
            v = dict(row)
            if v.get("corpo") is not None:
                try:
                    v["corpo"] = json.loads(v["corpo"])
                except (TypeError, ValueError):
                    v["corpo"] = None
            # Derivato da `origine`, non una colonna propria: le due cose
            # sono la STESSA informazione (solo `solo_file` genera un id
            # sintetico — vedi comportamento.compose()) e duplicarla in una
            # colonna aprirebbe la porta a farle disallineare. Dichiarato qui
            # comunque, cosi' chi legge /api/home-space non deve dedurlo da una
            # convenzione di prefisso sull'id.
            v["id_reale"] = v.get("origine") != "solo_file"
            entries.append(v)
        return entries

    def behavior_loaded_at(self) -> str | None:
        """Quando il comportamento e' stato riletto l'ultima volta -- data
        propria, diversa da `aggiornata_il()` (quella e' dell'anagrafe):
        cadenze e fonti diverse, vedi `replace_behavior`."""
        row = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'comportamento_letto_il'").fetchone()
        return row["valore"] if row else None

    def behavior_problems(self) -> list[str]:
        """Le frasi su cio' che l'ultima rilettura del comportamento NON ha
        potuto concludere con certezza (id duplicati, script vuoti, file mal
        formati). Vedi `comportamento.compose()`."""
        row = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'comportamento_problemi'").fetchone()
        if not row:
            return []
        try:
            value = json.loads(row["valore"])
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    def unloaded_files(self) -> dict[str, str]:
        """Il nome di ogni file di comportamento non letto, con la RAGIONE --
        tre forme, non due (`"assente"`, `"illeggibile: <motivo>"`, o
        `"cartella non raggiungibile"`), vedi `behavior.reread()` per il
        perche' sono tre e non vanno confuse fra loro."""
        row = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'comportamento_file_non_letti'").fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row["valore"])
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

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

