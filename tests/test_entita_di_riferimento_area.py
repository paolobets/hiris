"""«Fa caldo in soggiorno?»

Home Assistant lascia dichiarare, per ogni area, QUALE entita' e' la
temperatura di quella stanza (`temperature_entity_id`) e quale l'umidita'.
E' il significato piu' dichiarato che esista -- non dedotto, scritto a mano
dall'utente -- e arrivava gia' dentro la risposta che l'anagrafe legge a ogni
ricostruzione (`AreaEntry.json_fragment`, verificato sul sorgente di HA).

HIRIS lo buttava. Senza, davanti a «fa caldo in soggiorno?» deve indovinare
fra tutti i sensori dell'area quale intende chi chiede -- e su una stanza con
il termostato, la valvola e il sensore della finestra puo' benissimo scegliere
quello sbagliato e rispondere con sicurezza.
"""
from hiris.app.casa.anagrafe import hierarchy
from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.casa.domande import view

_REGISTRI = {
    "aree": [
        {"area_id": "soggiorno", "name": "Soggiorno",
         "temperature_entity_id": "sensor.soggiorno_temp",
         "humidity_entity_id": "sensor.soggiorno_umid"},
        {"area_id": "ripostiglio", "name": "Ripostiglio"},
    ],
    "entita": [],
}


def _casa(tmp_path):
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        a.replace(_REGISTRI, [])
        return a.read()
    finally:
        a.close()


def test_l_archivio_conserva_le_entita_di_riferimento(tmp_path):
    area = next(a for a in _casa(tmp_path)["aree"] if a["id"] == "soggiorno")
    assert area["entita_temperatura"] == "sensor.soggiorno_temp"
    assert area["entita_umidita"] == "sensor.soggiorno_umid"


def test_l_albero_le_porta(tmp_path):
    piani = hierarchy(_casa(tmp_path), ())
    aree = [a for p in piani for a in p["aree"]]
    soggiorno = next(a for a in aree if a["id"] == "soggiorno")
    assert soggiorno["entita_temperatura"] == "sensor.soggiorno_temp"


def test_guarda_un_area_le_dice(tmp_path):
    d = view(_casa(tmp_path), [], [], {}, "area", "soggiorno")
    assert d["entita_temperatura"] == "sensor.soggiorno_temp"
    assert d["entita_umidita"] == "sensor.soggiorno_umid"


def test_un_area_senza_dichiarazione_non_ne_inventa_una(tmp_path):
    """Il contrario, e serve quanto l'altra: una chiave `null` su ogni area
    sarebbe rumore, e per giunta indistinguibile da un registro caduto."""
    d = view(_casa(tmp_path), [], [], {}, "area", "ripostiglio")
    assert "entita_temperatura" not in d
    assert "entita_umidita" not in d


def test_un_archivio_gia_esistente_guadagna_le_colonne(tmp_path):
    """La migrazione: `CREATE TABLE IF NOT EXISTS` non tocca una tabella che
    esiste gia', quindi senza di essa il primo `replace` dopo
    l'aggiornamento sarebbe fallito e la casa avrebbe smesso di ricostruirsi,
    in silenzio."""
    import sqlite3

    percorso = str(tmp_path / "vecchio.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE aree (id TEXT PRIMARY KEY, nome TEXT NOT NULL, piano_id TEXT, "
        "icona TEXT, alias TEXT NOT NULL DEFAULT '[]', "
        "etichette TEXT NOT NULL DEFAULT '[]');")
    vecchio.commit()
    vecchio.close()

    a = HomeSpaceStore(percorso)
    try:
        a.replace(_REGISTRI, [])
        area = next(x for x in a.read()["aree"] if x["id"] == "soggiorno")
        assert area["entita_temperatura"] == "sensor.soggiorno_temp"
    finally:
        a.close()
