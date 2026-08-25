"""L'archivio della casa — la REPLICA di cio' che Home Assistant dichiara.

Non contiene niente di irripetibile: si cancella e si ricostruisce da HA in
pochi secondi. Per questo non si aggiorna per pezzi, si SOSTITUISCE per intero
dentro una transazione — rattoppare per id aprirebbe una classe di derive
silenziose in cambio di un risparmio di qualche decimo di secondo.

La memoria, che invece non si ricostruisce da nessuna parte, vive in un altro
archivio: vedi docs/design/2026-08-05-la-conoscenza-di-hiris.md, §1.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..proxy._sanitize import sanitize_ha_value, sanitize_ha_free_text
from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS piani (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, livello INTEGER, icona TEXT
);
CREATE TABLE IF NOT EXISTS aree (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, piano_id TEXT, icona TEXT,
    alias TEXT NOT NULL DEFAULT '[]', etichette TEXT NOT NULL DEFAULT '[]',
    entita_temperatura TEXT, entita_umidita TEXT
);
CREATE TABLE IF NOT EXISTS dispositivi (
    id TEXT PRIMARY KEY, nome TEXT, produttore TEXT, modello TEXT,
    area_id TEXT, disabilitato INTEGER NOT NULL DEFAULT 0,
    etichette TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS entita (
    id TEXT PRIMARY KEY, nome TEXT, area_id TEXT, dispositivo_id TEXT,
    piattaforma TEXT, categoria TEXT, classe TEXT, unita TEXT,
    disabilitata INTEGER NOT NULL DEFAULT 0, nascosta INTEGER NOT NULL DEFAULT 0,
    alias TEXT NOT NULL DEFAULT '[]', etichette TEXT NOT NULL DEFAULT '[]',
    categorie TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS etichette (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, colore TEXT, icona TEXT
);
-- L'identita' di una categoria e' la COPPIA (ambito, id), non l'id.
-- Home Assistant tiene il registro come `dict[scope, dict[category_id, ...]]`
-- (`helpers/category_registry.py`, verificato): l'unicita' che garantisce e'
-- DENTRO l'ambito, e la stessa verifica vale per i nomi
-- (`_async_ensure_name_is_available(scope, name)`) -- due categorie omonime in
-- ambiti diversi sono esplicitamente ammesse. Un `id TEXT PRIMARY KEY`
-- affermava un'unicita' globale che la fonte non promette, e siccome
-- `sostituisci` e' tutto-o-niente il primo id ripetuto avrebbe fatto rotolare
-- indietro la ricostruzione INTERA della casa, non solo la riga.
CREATE TABLE IF NOT EXISTS categorie (
    id TEXT NOT NULL, nome TEXT NOT NULL, ambito TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (ambito, id)
);
CREATE TABLE IF NOT EXISTS integrazioni (
    dominio TEXT NOT NULL, titolo TEXT, stato TEXT, motivo TEXT
);
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
CREATE INDEX IF NOT EXISTS idx_entita_area ON entita(area_id);
CREATE INDEX IF NOT EXISTS idx_entita_dispositivo ON entita(dispositivo_id);
CREATE INDEX IF NOT EXISTS idx_aree_piano ON aree(piano_id);
CREATE INDEX IF NOT EXISTS idx_comportamento_tipo ON comportamento(tipo);
"""

_TABELLE = ["piani", "aree", "dispositivi", "entita", "etichette",
            "categorie", "integrazioni"]

# La plancia predefinita di Home Assistant ha `url_path` nullo. SQLite non
# considera due NULL uguali (NULL != NULL): usarlo come chiave primaria non
# la protegge da duplicati, quindi la si archivia sotto una chiave esplicita
# e la si ritraduce a `None` in lettura — vedi plance()/sostituisci_plance().
_CHIAVE_PLANCIA_PRINCIPALE = "__principale__"


def _lista(valore) -> str:
    return json.dumps(valore if isinstance(valore, list) else [], ensure_ascii=False)


def _nome(valore) -> str | None:
    """Un nome/alias/titolo destinato all'anagrafe, sanificato al confine.

    C-2 (L1-sicurezza.md): `sostituisci` e' l'UNICO scrittore dell'anagrafe --
    ogni riga che entra qui viene da un registro di Home Assistant, e un
    nome/alias/titolo e' testo che HIRIS non controlla (un dispositivo
    di rete ostile, un'integrazione compromessa, un ospite che rinomina
    qualcosa). Sanificare QUI, e non a valle, significa che ogni lettore
    dell'anagrafe (`leggi()`, il nucleo, `guarda`, `cerca`, la pagina) eredita
    la difesa senza doverla ripetere -- un punto solo, non cinque.

    `None`/non-stringa passano invariati: un campo assente non deve
    diventare una stringa vuota che afferma "questo nome c'e' ed e' vuoto".

    Usa `sanitize_ha_value` (tetto 255): ogni campo che passa di qui e'
    `state`-shaped (friendly_name, titolo, alias) -- per `motivo`, che non lo
    e', vedi `_motivo()` sotto (M2, audit-2026-08-25, minori)."""
    return sanitize_ha_value(valore) if isinstance(valore, str) else valore


def _motivo(valore) -> str | None:
    """Il `motivo` per cui un'integrazione non e' partita, sanificato al
    confine come `_nome()` -- stessa fonte (un registro di HA), stesso
    rischio -- ma con un tetto DIVERSO.

    M2 (audit-2026-08-25, minori): prima usava `_nome()`/`sanitize_ha_value`
    (255, il tetto vero di uno `state`). `motivo` non e' uno `state`: e' la
    spiegazione di un guasto (`error_reason_translation_key`/`reason` di HA),
    HA non gli impone nessun tetto, e un motivo vero -- il riassunto di
    un'eccezione -- puo' onestamente superare 255 senza essere un attacco.
    Usa `sanitize_ha_free_text` (tetto 500): vedi il suo docstring in
    `_sanitize.py` per il perche' del numero."""
    return sanitize_ha_free_text(valore) if isinstance(valore, str) else valore


def _lista_sanificata(valore) -> str:
    """Come `_lista`, ma ogni voce stringa passa dal sanitizzatore -- per gli
    ALIAS (testo scelto dall'utente o dall'integrazione), MAI per le liste di
    id (`labels`, slug che Home Assistant genera e che l'anagrafe risolve
    altrove, dalla tabella `etichette` -- gia' sanificata alla propria
    sorgente)."""
    if not isinstance(valore, list):
        return "[]"
    return json.dumps([_nome(v) for v in valore], ensure_ascii=False)


def _dizionario(valore) -> str:
    """Come `_lista`, per i campi che Home Assistant manda come dizionario.

    L'assegnazione delle categorie e' `{ambito: category_id}` -- non una lista
    -- perche' un'entita' puo' stare in UNA categoria per ambito
    (`RegistryEntry.categories: dict[str, str]`, verificato in
    `helpers/entity_registry.py`). Appiattirla in una lista di id avrebbe
    buttato via l'ambito, che fa parte dell'identita' della categoria: due
    categorie omonime in ambiti diversi sono due cose diverse.

    Chiavi e valori si costringono a stringa e le voci vuote cadono: cio' che
    entra qui viene dalla rete, e una chiave non-stringa renderebbe la riga
    illeggibile a `json.loads` dall'altro capo.
    """
    if not isinstance(valore, dict):
        return "{}"
    pulito = {str(k).strip(): str(v).strip() for k, v in valore.items()
              if str(k).strip() and str(v).strip()}
    return json.dumps(pulito, ensure_ascii=False)


def _migrazione_2_motivo_integrazione(conn) -> None:
    """`integrazioni.motivo`: il perche' un'integrazione non e' partita.

    Serve una migrazione e non basta il `CREATE TABLE IF NOT EXISTS`: quello
    non tocca una tabella che esiste gia', quindi su un'installazione
    aggiornata la colonna non comparirebbe e il primo `sostituisci` fallirebbe
    -- cioe' la casa smetterebbe di ricostruirsi, in silenzio, dal momento
    dell'aggiornamento.

    Idempotente per costruzione: `init_schema` la chiama una volta sola, alla
    transizione 1 -> 2. Il `try` copre il caso di un archivio gia' ritoccato a
    mano, dove la colonna c'e' gia'.
    """
    try:
        conn.execute("ALTER TABLE integrazioni ADD COLUMN motivo TEXT")
    except Exception:
        pass


def _migrazione_3_entita_di_riferimento_dell_area(conn) -> None:
    """`aree.entita_temperatura` / `aree.entita_umidita`.

    Stessa ragione della migrazione 2: `CREATE TABLE IF NOT EXISTS` non tocca
    una tabella che esiste gia', e senza queste colonne il primo `sostituisci`
    dopo l'aggiornamento fallirebbe -- la casa smetterebbe di ricostruirsi, in
    silenzio.
    """
    for colonna in ("entita_temperatura", "entita_umidita"):
        try:
            conn.execute(f"ALTER TABLE aree ADD COLUMN {colonna} TEXT")
        except Exception:
            pass


def _migrazione_4_categorie_delle_entita(conn) -> None:
    """`entita.categorie`: in quale categoria l'utente ha messo questa cosa.

    Stessa ragione delle migrazioni 2 e 3: `CREATE TABLE IF NOT EXISTS` non
    tocca una tabella che esiste gia', e senza questa colonna il primo
    `sostituisci` dopo l'aggiornamento fallirebbe -- la casa smetterebbe di
    ricostruirsi, in silenzio.

    Il predefinito e' `'{}'` e non `'[]'`: e' un dizionario ambito -> id, non
    una lista (vedi `_dizionario`). Una riga vecchia che non ha mai visto le
    categorie dice cosi' «nessuna categoria», che e' vero.
    """
    try:
        conn.execute("ALTER TABLE entita ADD COLUMN categorie TEXT NOT NULL DEFAULT '{}'")
    except Exception:
        pass


def _migrazione_5_identita_della_categoria(conn) -> None:
    """La chiave di `categorie` diventa la coppia (ambito, id).

    Non si puo' cambiare una PRIMARY KEY con un `ALTER TABLE`: si ricostruisce
    la tabella e ci si ricopia dentro cio' che c'era. `INSERT OR IGNORE`
    perche' un archivio vecchio, se anche avesse due righe che collidono sulla
    nuova chiave, non deve poter impedire l'aggiornamento: la tabella e' una
    replica che il primo `sostituisci` riscrive per intero.

    `ambito` diventa NOT NULL con predefinito vuoto: NULL non e' uguale a
    NULL in SQLite, quindi lasciarlo nullabile dentro una chiave primaria
    avrebbe rimesso in piedi il buco che la chiave serve a chiudere.
    """
    try:
        conn.executescript(
            "CREATE TABLE categorie_nuova ("
            " id TEXT NOT NULL, nome TEXT NOT NULL, ambito TEXT NOT NULL DEFAULT '',"
            " PRIMARY KEY (ambito, id));"
            "INSERT OR IGNORE INTO categorie_nuova (id, nome, ambito)"
            " SELECT id, nome, COALESCE(ambito, '') FROM categorie;"
            "DROP TABLE categorie;"
            "ALTER TABLE categorie_nuova RENAME TO categorie;")
    except Exception:
        pass


_MIGRAZIONI = {
    2: _migrazione_2_motivo_integrazione,
    3: _migrazione_3_entita_di_riferimento_dell_area,
    4: _migrazione_4_categorie_delle_entita,
    5: _migrazione_5_identita_della_categoria,
}


class ArchivioCasa:
    def __init__(self, db_path: str = "/data/casa.db") -> None:
        self._conn = connect(db_path)
        init_schema(self._conn, _SCHEMA, version=5, migrations=_MIGRAZIONI)

    def chiudi(self) -> None:
        self._conn.close()

    def sostituisci(self, registri: dict[str, list[dict]],
                    non_disponibili: list[str] | None = None,
                    sistema_di_riferimento: dict | None = None) -> None:
        """Rimpiazza l'intera anagrafe. O passa tutta, o non passa niente.

        `riferimento` e' il sistema di riferimento della casa (unita', fuso,
        valuta, lingua, versione di HA) distillato da
        `anagrafe.sistema_di_riferimento`. Sta qui e non in una tabella o in
        un file suo perche' e' una proprieta' della CASA come le sue aree: un
        secondo posto da tenere aggiornato sarebbe un secondo posto da cui
        leggere una versione diversa della stessa verita'.

        Vuoto o assente NON cancella quello di prima: e' la stessa dottrina
        con cui `anagrafe.ricostruisci` non sostituisce la casa quando tutti i
        registri sono caduti. Il fuso di ieri e' ancora il fuso giusto; un
        riferimento cancellato farebbe leggere ogni temperatura senza sapere
        in che scala.

        `non_disponibili` sono i registri che non hanno risposto: si conservano
        accanto ai dati perche' una casa senza piani e un registro dei piani
        caduto producono la stessa lista vuota, e chi guarda l'anagrafe deve
        poterli distinguere anche a ore di distanza dalla lettura.

        Il `BEGIN` esplicito e' quello che rende vera la promessa: se una riga
        malformata solleva a meta' strada, la casa vecchia resta intatta invece
        di restare monca — e una casa monca e' peggio di una vecchia, perche'
        non si distingue da una casa che e' davvero cambiata.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            for tabella in _TABELLE:
                c.execute(f"DELETE FROM {tabella}")

            for p in registri.get("piani", []):
                c.execute("INSERT INTO piani (id, nome, livello, icona) VALUES (?,?,?,?)",
                          (p["floor_id"], _nome(p.get("name")) or p["floor_id"],
                           p.get("level"), p.get("icon")))

            for a in registri.get("aree", []):
                # `temperature_entity_id`/`humidity_entity_id`: QUALE entita' e'
                # LA temperatura di quella stanza, dichiarata dall'utente in
                # Home Assistant. Arrivavano gia' dentro questa risposta e si
                # buttavano, e senza di esse HIRIS deve INDOVINARE fra tutti i
                # sensori dell'area quale intende chi chiede se fa caldo in
                # soggiorno. E' il significato piu' dichiarato che esista, e
                # costava zero chiamate.
                c.execute("INSERT INTO aree (id, nome, piano_id, icona, alias, etichette, "
                          " entita_temperatura, entita_umidita) VALUES (?,?,?,?,?,?,?,?)",
                          (a["area_id"], _nome(a.get("name")) or a["area_id"], a.get("floor_id"),
                           a.get("icon"), _lista_sanificata(a.get("aliases")),
                           _lista(a.get("labels")),
                           a.get("temperature_entity_id"), a.get("humidity_entity_id")))

            for d in registri.get("dispositivi", []):
                c.execute("INSERT INTO dispositivi "
                          "(id, nome, produttore, modello, area_id, disabilitato, etichette) "
                          "VALUES (?,?,?,?,?,?,?)",
                          (d["id"], _nome(d.get("name_by_user") or d.get("name")),
                           _nome(d.get("manufacturer")), _nome(d.get("model")), d.get("area_id"),
                           1 if d.get("disabled_by") else 0, _lista(d.get("labels"))))

            for e in registri.get("entita", []):
                # `categories` -- IN QUALE CATEGORIA l'utente ha messo questa
                # cosa -- arrivava gia' dentro questa stessa risposta
                # (`RegistryEntry.as_partial_dict`, verificato sul sorgente di
                # HA) e si buttava. E' la stessa tassonomia scritta a mano
                # delle etichette, dall'altro capo: il registro delle
                # categorie era letto con quattro comandi WS a ogni
                # ricostruzione e l'assegnazione, che costa zero, no.
                #
                # ATTENZIONE alla vicinanza dei nomi: `categoria` (singolare)
                # e' l'`entity_category` di Home Assistant -- `config` o
                # `diagnostic`, deciso dall'INTEGRAZIONE -- e non c'entra
                # niente con `categorie` (plurale), che e' la tassonomia
                # dell'UTENTE. Due fatti diversi, due colonne diverse.
                c.execute("INSERT INTO entita "
                          "(id, nome, area_id, dispositivo_id, piattaforma, categoria, "
                          " classe, unita, disabilitata, nascosta, alias, etichette, "
                          " categorie) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (e["entity_id"],
                           # Il nome scelto dall'utente vince su quello che
                           # l'integrazione ha proposto: e' il primo posto in cui
                           # HIRIS deve chiamare le cose come le chiama lui.
                           _nome(e.get("name") or e.get("original_name")),
                           e.get("area_id"), e.get("device_id"), e.get("platform"),
                           e.get("entity_category"),
                           e.get("device_class") or e.get("original_device_class"),
                           e.get("unit_of_measurement"),
                           1 if e.get("disabled_by") else 0,
                           1 if e.get("hidden_by") else 0,
                           _lista_sanificata(e.get("aliases")), _lista(e.get("labels")),
                           _dizionario(e.get("categories"))))

            for et in registri.get("etichette", []):
                c.execute("INSERT INTO etichette (id, nome, colore, icona) VALUES (?,?,?,?)",
                          (et["label_id"], _nome(et.get("name")) or et["label_id"],
                           et.get("color"), et.get("icon")))

            for ca in registri.get("categorie", []):
                # `ambito` lo mette leggi_registri: Home Assistant partiziona le
                # categorie per ambito e non lo riporta nelle righe, quindi due
                # categorie omonime in ambiti diversi sarebbero indistinguibili.
                # `ambito` a stringa vuota e mai NULL: e' meta' della chiave
                # primaria, e in SQLite NULL non e' uguale a NULL -- due righe
                # con ambito nullo non sarebbero considerate doppie.
                c.execute("INSERT INTO categorie (id, nome, ambito) VALUES (?,?,?)",
                          (ca["category_id"], _nome(ca.get("name")) or ca["category_id"],
                           ca.get("ambito") or ""))

            for i in registri.get("integrazioni", []):
                # `reason` -- il MOTIVO per cui un'integrazione non e' partita
                # -- arrivava dentro la stessa risposta e si buttava. E' la
                # risposta a «perche' la telecamera del giardino non risponde?»,
                # che HIRIS poteva solo non sapere.
                c.execute("INSERT INTO integrazioni (dominio, titolo, stato, motivo) "
                          "VALUES (?,?,?,?)",
                          (i.get("domain", ""), _nome(i.get("title")), i.get("state"),
                           _motivo(i.get("reason") or i.get("error_reason_translation_key"))))

            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) VALUES ('aggiornata_il', ?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('non_disponibili', ?)", (_lista(list(non_disponibili or [])),))
            if sistema_di_riferimento:
                c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                          "VALUES ('sistema_di_riferimento', ?)",
                          (json.dumps(sistema_di_riferimento, ensure_ascii=False),))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def aggiornata_il(self) -> str | None:
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'aggiornata_il'").fetchone()
        return riga["valore"] if riga else None

    def sistema_di_riferimento(self) -> dict:
        """Il sistema di riferimento della casa: `{fuso, valuta, lingua,
        paese, nome, versione_ha, unita}` -- `{}` se non e' mai stato letto.

        `{}` e non `None`: chi legge deve poter fare `.get("fuso")` senza
        sapere prima se la casa e' stata mai letta. Il "non lo so" non si
        dichiara con un tipo diverso ma con la chiave che manca -- che e'
        anche cio' che dice il nucleo, tacendo invece di inventare un fuso.
        """
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'sistema_di_riferimento'").fetchone()
        if not riga:
            return {}
        try:
            valore = json.loads(riga["valore"])
        except (TypeError, ValueError):
            return {}
        return valore if isinstance(valore, dict) else {}

    def non_disponibili(self) -> list[str]:
        """I registri che non avevano risposto all'ultima ricostruzione."""
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'non_disponibili'").fetchone()
        if not riga:
            return []
        try:
            valore = json.loads(riga["valore"])
        except (TypeError, ValueError):
            return []
        return valore if isinstance(valore, list) else []

    def sostituisci_comportamento(self, voci: list[dict], problemi: list[str] | None = None,
                                  file_non_letti: dict[str, str] | None = None) -> None:
        """Rimpiazza cio' che la casa sa fare da sola. Tutto o niente.

        Separato da `sostituisci()` perche' cambia con una cadenza diversa
        (giorni contro mesi) e da una fonte diversa (i file di configurazione
        contro i registri): rileggere i registri perche' e' cambiata
        un'automazione sarebbe uno spreco, e viceversa.

        `problemi` e `file_non_letti` si archiviano ACCANTO ai dati, non solo
        nei log: sono costruiti con cura da `comportamento.componi()`/`rileggi()`
        proprio per dire a chi guarda perche' qualcosa manca o e' incerto —
        conservarli solo in una riga di log li rende invisibili a chiunque non
        stia leggendo il log in quel momento (vedi `non_disponibili` sopra,
        stesso principio).

        N2 (review indipendente 25/08/2026): `nome` e `corpo` hanno DUE fonti
        diverse e vanno trattati diversamente. `corpo` viene dal file YAML
        (`automations.yaml`/`scripts.yaml`) che il proprietario di casa
        scrive di persona -- resta cosi' com'e', nessuna sanificazione, come
        gia' deciso per `casa/comportamento.py` in generale. Ma `nome` NON
        viene dal file: e' il `friendly_name` letto da `get_states([])`
        (`comportamento.rileggi()`), una lettura di rete GREZZA che non
        passa da `entity_cache._to_minimal` -- lo stesso genere di testo
        controllabile da chi non e' il proprietario che C-2 sanifica
        ovunque arrivi cosi'. Sanificato qui con `_nome()`, lo stesso
        pattern di `sostituisci()` qui sopra: un punto solo per fonte, non
        un cablaggio dimenticato perche' "e' un file locale" -- quella
        ragione copre il corpo, non il nome.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM comportamento")
            for v in voci:
                corpo = v.get("corpo")
                c.execute("INSERT INTO comportamento (id, tipo, nome, corpo, origine) "
                          "VALUES (?,?,?,?,?)",
                          (v["id"], v["tipo"], _nome(v.get("nome")),
                           # `None` resta `None`: «non ho il corpo» e «il corpo
                           # e' vuoto» sono due cose diverse.
                           None if corpo is None else json.dumps(corpo, ensure_ascii=False),
                           v.get("origine", "file")))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_letto_il', ?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_problemi', ?)",
                      (json.dumps(list(problemi or []), ensure_ascii=False),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_file_non_letti', ?)",
                      (json.dumps(dict(file_non_letti or {}), ensure_ascii=False),))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def comportamento(self) -> list[dict]:
        """Cio' che la casa sa fare da sola, coi corpi gia' sciolti."""
        voci = []
        for riga in self._conn.execute("SELECT * FROM comportamento ORDER BY id").fetchall():
            v = dict(riga)
            if v.get("corpo") is not None:
                try:
                    v["corpo"] = json.loads(v["corpo"])
                except (TypeError, ValueError):
                    v["corpo"] = None
            # Derivato da `origine`, non una colonna propria: le due cose
            # sono la STESSA informazione (solo `solo_file` genera un id
            # sintetico — vedi comportamento.componi()) e duplicarla in una
            # colonna aprirebbe la porta a farle disallineare. Dichiarato qui
            # comunque, cosi' chi legge /api/casa non deve dedurlo da una
            # convenzione di prefisso sull'id.
            v["id_reale"] = v.get("origine") != "solo_file"
            voci.append(v)
        return voci

    def comportamento_letto_il(self) -> str | None:
        """Quando il comportamento e' stato riletto l'ultima volta -- data
        propria, diversa da `aggiornata_il()` (quella e' dell'anagrafe):
        cadenze e fonti diverse, vedi `sostituisci_comportamento`."""
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'comportamento_letto_il'").fetchone()
        return riga["valore"] if riga else None

    def problemi_comportamento(self) -> list[str]:
        """Le frasi su cio' che l'ultima rilettura del comportamento NON ha
        potuto concludere con certezza (id duplicati, script vuoti, file mal
        formati). Vedi `comportamento.componi()`."""
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'comportamento_problemi'").fetchone()
        if not riga:
            return []
        try:
            valore = json.loads(riga["valore"])
        except (TypeError, ValueError):
            return []
        return valore if isinstance(valore, list) else []

    def file_non_letti(self) -> dict[str, str]:
        """Il nome di ogni file di comportamento non letto, con la RAGIONE
        (`"assente"` o `"illeggibile: <motivo>"`). Vedi `comportamento.rileggi()`."""
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'comportamento_file_non_letti'").fetchone()
        if not riga:
            return {}
        try:
            valore = json.loads(riga["valore"])
        except (TypeError, ValueError):
            return {}
        return valore if isinstance(valore, dict) else {}

    def sostituisci_plance(self, voci: list[dict],
                           non_disponibili: list[str] | None = None) -> None:
        """Rimpiazza le plance. Tutto o niente, stessa forma di
        sostituisci_comportamento(): stesso BEGIN/rollback, stesso
        scioglimento del JSON, `config` a `None` che resta `None`.

        NON sta in _TABELLE ne' in sostituisci(): le plance hanno una
        cadenza propria (l'evento EVENTO_PLANCE), diversa da quella
        dell'anagrafe — ci finirebbero cancellate a ogni ricostruzione dei
        registri.

        `non_disponibili` si archivia accanto ai dati, stesso principio di
        `non_disponibili` dell'anagrafe: senza conservarlo, /api/casa non
        potrebbe dire perche' una plancia manca.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM plance")
            for v in voci:
                percorso = v.get("url_path")
                chiave = percorso if percorso is not None else _CHIAVE_PLANCIA_PRINCIPALE
                config = v.get("config")
                c.execute(
                    "INSERT INTO plance (percorso, titolo, modalita, config, entita) "
                    "VALUES (?,?,?,?,?)",
                    (chiave, v.get("title"), v.get("mode"),
                     # `None` resta `None`: «plancia illeggibile» e «plancia
                     # senza viste» sono due cose diverse (vedi leggi_plance).
                     None if config is None else json.dumps(config, ensure_ascii=False),
                     _lista(v.get("entita"))))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('plance_lette_il', ?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('plance_non_disponibili', ?)",
                      (json.dumps(list(non_disponibili or []), ensure_ascii=False),))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def plance_lette_il(self) -> str | None:
        """Quando le plance sono state rilette l'ultima volta -- data propria,
        diversa da `aggiornata_il()` (anagrafe) e da `comportamento_letto_il()`."""
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'plance_lette_il'").fetchone()
        return riga["valore"] if riga else None

    def non_disponibili_plance(self) -> list[str]:
        """Le plance/percorsi che l'ultima lettura non e' riuscita a
        risolvere (elenco non arrivato, config illeggibile, percorso
        duplicato). Vedi `comportamento.rileggi_plance()`."""
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'plance_non_disponibili'").fetchone()
        if not riga:
            return []
        try:
            valore = json.loads(riga["valore"])
        except (TypeError, ValueError):
            return []
        return valore if isinstance(valore, list) else []

    def plance(self) -> list[dict]:
        """Le plance con la loro configurazione, coi campi JSON gia' sciolti.

        La predefinita torna con `percorso` a `None`, come l'ha data
        `leggi_plance()`: la chiave esplicita usata per archiviarla e' un
        dettaglio di storage, non deve trapelare verso l'esterno.
        """
        voci = []
        for riga in self._conn.execute("SELECT * FROM plance ORDER BY percorso").fetchall():
            v = dict(riga)
            if v.get("percorso") == _CHIAVE_PLANCIA_PRINCIPALE:
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
            voci.append(v)
        return voci

    def leggi(self) -> dict[str, list[dict]]:
        """L'anagrafe intera, con le liste JSON gia' sciolte."""
        casa: dict[str, list[dict]] = {}
        for tabella in _TABELLE:
            righe = self._conn.execute(f"SELECT * FROM {tabella}").fetchall()
            casa[tabella] = [self._sciogli(dict(r)) for r in righe]
        return casa

    @staticmethod
    def _sciogli(riga: dict) -> dict:
        for campo in ("alias", "etichette"):
            if campo in riga:
                try:
                    riga[campo] = json.loads(riga[campo])
                except (TypeError, ValueError):
                    riga[campo] = []
        # `categorie` e' un DIZIONARIO ambito -> category_id, non una lista:
        # ripiegare su `[]` come sopra darebbe a chi legge una forma che il
        # campo non ha mai (`.items()` su una lista solleva), e il ripiego
        # deve avere la stessa forma del valore buono.
        if "categorie" in riga:
            try:
                sciolto = json.loads(riga["categorie"])
            except (TypeError, ValueError):
                sciolto = None
            riga["categorie"] = sciolto if isinstance(sciolto, dict) else {}
        return riga
