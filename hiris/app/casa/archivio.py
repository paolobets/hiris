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

from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS piani (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, livello INTEGER, icona TEXT
);
CREATE TABLE IF NOT EXISTS aree (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, piano_id TEXT, icona TEXT,
    alias TEXT NOT NULL DEFAULT '[]', etichette TEXT NOT NULL DEFAULT '[]'
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
    alias TEXT NOT NULL DEFAULT '[]', etichette TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS etichette (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, colore TEXT, icona TEXT
);
CREATE TABLE IF NOT EXISTS categorie (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, ambito TEXT
);
CREATE TABLE IF NOT EXISTS integrazioni (
    dominio TEXT NOT NULL, titolo TEXT, stato TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    chiave TEXT PRIMARY KEY, valore TEXT
);
CREATE TABLE IF NOT EXISTS comportamento (
    id TEXT PRIMARY KEY, tipo TEXT NOT NULL, nome TEXT,
    corpo TEXT, origine TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entita_area ON entita(area_id);
CREATE INDEX IF NOT EXISTS idx_entita_dispositivo ON entita(dispositivo_id);
CREATE INDEX IF NOT EXISTS idx_aree_piano ON aree(piano_id);
CREATE INDEX IF NOT EXISTS idx_comportamento_tipo ON comportamento(tipo);
"""

_TABELLE = ["piani", "aree", "dispositivi", "entita", "etichette",
            "categorie", "integrazioni"]


def _lista(valore) -> str:
    return json.dumps(valore if isinstance(valore, list) else [], ensure_ascii=False)


class ArchivioCasa:
    def __init__(self, db_path: str = "/data/casa.db") -> None:
        self._conn = connect(db_path)
        init_schema(self._conn, _SCHEMA, version=1)

    def chiudi(self) -> None:
        self._conn.close()

    def sostituisci(self, registri: dict[str, list[dict]],
                    non_disponibili: list[str] | None = None) -> None:
        """Rimpiazza l'intera anagrafe. O passa tutta, o non passa niente.

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
                          (p["floor_id"], p.get("name") or p["floor_id"],
                           p.get("level"), p.get("icon")))

            for a in registri.get("aree", []):
                c.execute("INSERT INTO aree (id, nome, piano_id, icona, alias, etichette) "
                          "VALUES (?,?,?,?,?,?)",
                          (a["area_id"], a.get("name") or a["area_id"], a.get("floor_id"),
                           a.get("icon"), _lista(a.get("aliases")), _lista(a.get("labels"))))

            for d in registri.get("dispositivi", []):
                c.execute("INSERT INTO dispositivi "
                          "(id, nome, produttore, modello, area_id, disabilitato, etichette) "
                          "VALUES (?,?,?,?,?,?,?)",
                          (d["id"], d.get("name_by_user") or d.get("name"),
                           d.get("manufacturer"), d.get("model"), d.get("area_id"),
                           1 if d.get("disabled_by") else 0, _lista(d.get("labels"))))

            for e in registri.get("entita", []):
                c.execute("INSERT INTO entita "
                          "(id, nome, area_id, dispositivo_id, piattaforma, categoria, "
                          " classe, unita, disabilitata, nascosta, alias, etichette) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (e["entity_id"],
                           # Il nome scelto dall'utente vince su quello che
                           # l'integrazione ha proposto: e' il primo posto in cui
                           # HIRIS deve chiamare le cose come le chiama lui.
                           e.get("name") or e.get("original_name"),
                           e.get("area_id"), e.get("device_id"), e.get("platform"),
                           e.get("entity_category"),
                           e.get("device_class") or e.get("original_device_class"),
                           e.get("unit_of_measurement"),
                           1 if e.get("disabled_by") else 0,
                           1 if e.get("hidden_by") else 0,
                           _lista(e.get("aliases")), _lista(e.get("labels"))))

            for et in registri.get("etichette", []):
                c.execute("INSERT INTO etichette (id, nome, colore, icona) VALUES (?,?,?,?)",
                          (et["label_id"], et.get("name") or et["label_id"],
                           et.get("color"), et.get("icon")))

            for ca in registri.get("categorie", []):
                # `ambito` lo mette leggi_registri: Home Assistant partiziona le
                # categorie per ambito e non lo riporta nelle righe, quindi due
                # categorie omonime in ambiti diversi sarebbero indistinguibili.
                c.execute("INSERT INTO categorie (id, nome, ambito) VALUES (?,?,?)",
                          (ca["category_id"], ca.get("name") or ca["category_id"],
                           ca.get("ambito")))

            for i in registri.get("integrazioni", []):
                c.execute("INSERT INTO integrazioni (dominio, titolo, stato) VALUES (?,?,?)",
                          (i.get("domain", ""), i.get("title"), i.get("state")))

            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) VALUES ('aggiornata_il', ?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('non_disponibili', ?)", (_lista(list(non_disponibili or [])),))
            c.commit()
        except Exception:
            c.rollback()
            raise

    def aggiornata_il(self) -> str | None:
        riga = self._conn.execute(
            "SELECT valore FROM meta WHERE chiave = 'aggiornata_il'").fetchone()
        return riga["valore"] if riga else None

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

    def sostituisci_comportamento(self, voci: list[dict]) -> None:
        """Rimpiazza cio' che la casa sa fare da sola. Tutto o niente.

        Separato da `sostituisci()` perche' cambia con una cadenza diversa
        (giorni contro mesi) e da una fonte diversa (i file di configurazione
        contro i registri): rileggere i registri perche' e' cambiata
        un'automazione sarebbe uno spreco, e viceversa.
        """
        c = self._conn
        try:
            c.execute("BEGIN")
            c.execute("DELETE FROM comportamento")
            for v in voci:
                corpo = v.get("corpo")
                c.execute("INSERT INTO comportamento (id, tipo, nome, corpo, origine) "
                          "VALUES (?,?,?,?,?)",
                          (v["id"], v["tipo"], v.get("nome"),
                           # `None` resta `None`: «non ho il corpo» e «il corpo
                           # e' vuoto» sono due cose diverse.
                           None if corpo is None else json.dumps(corpo, ensure_ascii=False),
                           v.get("origine", "file")))
            c.execute("INSERT OR REPLACE INTO meta (chiave, valore) "
                      "VALUES ('comportamento_letto_il', ?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
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
        return riga
