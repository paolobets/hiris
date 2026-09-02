"""«Perche' la telecamera del giardino non risponde?»

Home Assistant lo diagnostica gia' da se': manda lo stato di ogni
integrazione E il motivo del guasto, dentro la stessa risposta che l'anagrafe
legge a ogni ricostruzione. HIRIS salvava lo stato, buttava il motivo, e non
leggeva ne' l'uno ne' l'altro: poteva solo contare le entita' non disponibili
e non sapere perche'.
"""
from hiris.app.home_space.briefing import compose
from hiris.app.home_space.store import HomeSpaceStore


def _nucleo(integrazioni):
    testo, riepilogo = compose({"entita": [], "integrazioni": integrazioni}, [], [], {})
    return testo, riepilogo


def test_il_motivo_del_guasto_si_conserva(tmp_path):
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        a.replace({"integrazioni": [
            {"domain": "reolink", "title": "Reolink", "state": "setup_retry",
             "reason": "timeout durante la connessione"},
        ]}, [])
        voce = a.read()["integrazioni"][0]
        assert voce["stato"] == "setup_retry"
        assert voce["motivo"] == "timeout durante la connessione"
    finally:
        a.close()


def test_un_integrazione_caduta_si_dichiara_col_motivo():
    testo, riepilogo = _nucleo([
        {"dominio": "reolink", "titolo": "Reolink", "stato": "setup_retry",
         "motivo": "timeout durante la connessione"},
    ])
    assert "Reolink" in testo
    assert "timeout durante la connessione" in testo
    # Fra i GUASTI, non fra gli avvisi: sono un fatto sulla casa, non un
    # limite di cio' che HIRIS sa.
    assert any("Reolink" in g for g in riepilogo["faults"])
    assert "## Cosa non va in casa" in testo


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
    primo `replace` sarebbe fallito e la casa avrebbe smesso di
    ricostruirsi, in silenzio."""
    import sqlite3

    percorso = str(tmp_path / "vecchio.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE integrazioni (dominio TEXT NOT NULL, titolo TEXT, stato TEXT);")
    vecchio.commit()
    vecchio.close()

    a = HomeSpaceStore(percorso)
    try:
        a.replace({"integrazioni": [
            {"domain": "reolink", "title": "Reolink", "state": "setup_error",
             "reason": "credenziali rifiutate"},
        ]}, [])
        assert a.read()["integrazioni"][0]["motivo"] == "credenziali rifiutate"
    finally:
        a.close()


def test_due_voci_con_lo_stesso_nome_non_si_ripetono():
    """Sull'impianto vero uscivano nove voci per sei cose: «Fritz-esterno
    (not_loaded), Fritz-studio (not_loaded), FRITZ!Repeater (not_loaded)» e
    poi di nuovo tutte e tre. Home Assistant permette piu' voci di
    configurazione con lo stesso titolo, e ripetere il nome non aggiunge un
    fatto: consuma l'attenzione di chi legge e fa sembrare il guasto piu'
    grande di quello che e'.

    Ma quante sono si DICE. Due cose giu' con lo stesso nome sono due cose, e
    tacerlo sarebbe l'errore opposto."""
    testo, _ = _nucleo([
        {"dominio": "fritz", "titolo": "Fritz-esterno", "stato": "not_loaded"},
        {"dominio": "fritz", "titolo": "Fritz-esterno", "stato": "not_loaded"},
        {"dominio": "lifx", "titolo": "Abat-jour", "stato": "not_loaded"},
    ])
    assert testo.count("Fritz-esterno") == 1, "il nome non deve ripetersi"
    assert "Fritz-esterno x2" in testo, "ma quante sono deve dirlo"
    assert "3 integrazioni" in testo, "il totale conta le voci vere, non le righe"


def test_il_titolo_si_ripulisce_dagli_spazi():
    """Sull'impianto vero c'e' un «Abat-jour » con lo spazio in coda, e usciva
    cosi' nel testo che il modello legge."""
    testo, _ = _nucleo([
        {"dominio": "lifx", "titolo": "Abat-jour ", "stato": "setup_retry",
         "motivo": "timeout"},
    ])
    assert "Abat-jour (setup_retry" in testo
