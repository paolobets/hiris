"""«Perche' la telecamera del giardino non risponde?»

Home Assistant lo diagnostica gia' da se': manda lo stato di ogni
integrazione E il motivo del guasto, dentro la stessa risposta che l'anagrafe
legge a ogni ricostruzione. HIRIS salvava lo stato, buttava il motivo, e non
leggeva ne' l'uno ne' l'altro: poteva solo contare le entita' non disponibili
e non sapere perche'.
"""
from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.nucleo import componi


def _nucleo(integrazioni):
    testo, riepilogo = componi({"entita": [], "integrazioni": integrazioni}, [], [], {})
    return testo, riepilogo


def test_il_motivo_del_guasto_si_conserva(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    try:
        a.sostituisci({"integrazioni": [
            {"domain": "reolink", "title": "Reolink", "state": "setup_retry",
             "reason": "timeout durante la connessione"},
        ]}, [])
        voce = a.leggi()["integrazioni"][0]
        assert voce["stato"] == "setup_retry"
        assert voce["motivo"] == "timeout durante la connessione"
    finally:
        a.chiudi()


def test_un_integrazione_caduta_si_dichiara_col_motivo():
    testo, riepilogo = _nucleo([
        {"dominio": "reolink", "titolo": "Reolink", "stato": "setup_retry",
         "motivo": "timeout durante la connessione"},
    ])
    assert "Reolink" in testo
    assert "timeout durante la connessione" in testo
    assert any("Reolink" in a for a in riepilogo["avvisi"])


def test_un_integrazione_sana_non_si_annuncia():
    """Il contrario, e serve quanto l'altra: un avviso su ogni integrazione
    caricata sarebbe rumore in ogni prompt, e renderebbe invisibile quella
    rotta -- il difetto opposto e altrettanto grave."""
    testo, _ = _nucleo([
        {"dominio": "hue", "titolo": "Philips Hue", "stato": "loaded"},
        {"dominio": "mqtt", "titolo": "MQTT", "stato": "setup_in_progress"},
    ])
    assert "Philips Hue" not in testo
    assert "MQTT" not in testo


def test_senza_motivo_non_se_ne_inventa_uno():
    """HA riempie `reason` per `setup_error` e `setup_retry`, non sempre per
    `not_loaded`. Una causa inventata manderebbe l'utente a riparare la cosa
    sbagliata."""
    testo, _ = _nucleo([
        {"dominio": "zwave_js", "titolo": "Z-Wave", "stato": "not_loaded"},
    ])
    assert "Z-Wave" in testo
    assert "not_loaded" in testo
    assert ":" not in testo.split("Z-Wave")[1].split(")")[0]


def test_un_archivio_gia_esistente_guadagna_la_colonna(tmp_path):
    """La migrazione, e non e' una formalita': `CREATE TABLE IF NOT EXISTS` non
    tocca una tabella che esiste gia'. Senza, dal momento dell'aggiornamento il
    primo `sostituisci` sarebbe fallito e la casa avrebbe smesso di
    ricostruirsi, in silenzio."""
    import sqlite3

    percorso = str(tmp_path / "vecchio.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE integrazioni (dominio TEXT NOT NULL, titolo TEXT, stato TEXT);")
    vecchio.commit()
    vecchio.close()

    a = ArchivioCasa(percorso)
    try:
        a.sostituisci({"integrazioni": [
            {"domain": "reolink", "title": "Reolink", "state": "setup_error",
             "reason": "credenziali rifiutate"},
        ]}, [])
        assert a.leggi()["integrazioni"][0]["motivo"] == "credenziali rifiutate"
    finally:
        a.chiudi()
