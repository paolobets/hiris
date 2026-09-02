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
    `migration_error` e `failed_unload`. Una causa inventata manderebbe
    l'utente a riparare la cosa sbagliata.

    **La finta portava `not_loaded` fino al 02/09**, quando `not_loaded` era
    ancora (per errore) uno stato rotto: cambiata in `failed_unload`, che e'
    un guasto vero e a cui HA non sempre allega un motivo."""
    testo, _ = _nucleo([
        {"dominio": "zwave_js", "titolo": "Z-Wave", "stato": "failed_unload"},
    ])
    assert "Z-Wave" in testo
    assert "failed_unload" in testo
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
        {"dominio": "fritz", "titolo": "Fritz-esterno", "stato": "setup_retry"},
        {"dominio": "fritz", "titolo": "Fritz-esterno", "stato": "setup_retry"},
        {"dominio": "lifx", "titolo": "Abat-jour", "stato": "setup_retry"},
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


# ── Il difetto del 02/09: «non e' loaded» non vuol dire «e' rotto» ──────────
#
# Trovato dal proprietario leggendo il briefing della sua casa: il nucleo
# annunciava «9 integrazioni non stanno funzionando» e quella vera era UNA.
# Otto falsi allarmi su nove, ogni giorno.
#
# L'elenco degli stati era GIUSTO come elenco di «non e' `loaded`» e SBAGLIATO
# come elenco di «e' rotto»: la domanda a cui rispondeva non era quella che
# serviva. E c'era un secondo discriminante che il codice non guardava
# affatto, `source`.


def test_not_loaded_NON_e_un_guasto():
    """«NOT_LOADED: The config entry has not been loaded. **This is the
    initial state when a config entry is created or when Home Assistant is
    restarted.**» (developers.home-assistant.io/docs/config_entries_index/)

    Non e' uno stato di errore: e' lo stato iniziale. Dopo ogni riavvio di
    Home Assistant ci passano TUTTE le integrazioni della casa.

    Mutazione: rimettere `not_loaded` in `_BROKEN_INTEGRATION_STATES` --
    questo test torna rosso e il nucleo ricomincia a chiamare guasto lo stato
    normale di ogni integrazione appena riavviata."""
    testo, riepilogo = _nucleo([
        {"dominio": "fritz", "titolo": "Fritz-esterno", "stato": "not_loaded",
         "origine": "user"},
    ])
    assert "Fritz-esterno" not in testo
    assert not any("Fritz-esterno" in g for g in riepilogo["faults"])


def test_una_voce_IGNORATA_dal_proprietario_non_e_un_guasto():
    """«Users will have the option to **ignore** the discovery of your config
    entry, so they won't be bothered about it anymore»
    (developers.home-assistant.io/docs/config_entries_config_flow_handler/).

    Sulla casa vera tutte e otto le voci `not_loaded` portavano
    `source: "ignore"`: non si caricheranno mai, per scelta del proprietario.
    Dirgli che sono rotte significa dirgli che e' guasto cio' che lui ha
    spento.

    **Si scarta in QUALUNQUE stato**, e per questo la finta manda un
    `setup_error`: se il filtro guardasse solo `not_loaded` questo test
    sarebbe verde per la ragione sbagliata."""
    testo, riepilogo = _nucleo([
        {"dominio": "fritz", "titolo": "Fritz-ignorato", "stato": "setup_error",
         "motivo": "credenziali rifiutate", "origine": "ignore"},
    ])
    assert "Fritz-ignorato" not in testo
    assert not any("Fritz-ignorato" in g for g in riepilogo["faults"])


def test_lo_STESSO_stato_rotto_compare_se_NON_e_ignorato():
    """Il gemello del test sopra, e senza di lui quello non prova niente: la
    differenza dev'essere l'ORIGINE, non lo stato.

    Mutazione: togliere il filtro su `origine` -- il test sopra torna rosso e
    questo resta verde, che e' esattamente la coppia che serve."""
    testo, riepilogo = _nucleo([
        {"dominio": "fritz", "titolo": "Fritz-rotto", "stato": "setup_error",
         "motivo": "credenziali rifiutate", "origine": "user"},
    ])
    assert "Fritz-rotto (setup_error: credenziali rifiutate)" in testo
    assert any("Fritz-rotto" in g for g in riepilogo["faults"])


def test_la_casa_vera_del_02_09_nove_voci_una_sola_rotta():
    """La misura che ha fatto nascere la correzione, rifatta come prova.

    Otto voci `not_loaded` con `source: "ignore"` piu' un `setup_retry` vero.
    Prima: «9 integrazioni non stanno funzionando». Dopo: una, col suo
    motivo."""
    ignorate = [
        {"dominio": "fritz", "titolo": f"Voce {n}", "stato": "not_loaded",
         "origine": "ignore"} for n in range(8)
    ]
    testo, riepilogo = _nucleo(ignorate + [
        {"dominio": "lifx", "titolo": "Abat-jour", "stato": "setup_retry",
         "motivo": "timeout durante la connessione"},
    ])
    assert "9 integrazioni" not in testo
    assert "Un'integrazione di Home Assistant non sta funzionando" in testo
    assert "Abat-jour (setup_retry: timeout durante la connessione)" in testo
    assert len([g for g in riepilogo["faults"] if "integrazion" in g]) == 1


def test_l_origine_si_conserva_nell_anagrafe(tmp_path):
    """Il filtro puo' esistere solo se il dato arriva: `source` si buttava
    esattamente come si buttava `reason` prima della fetta di agosto."""
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        a.replace({"integrazioni": [
            {"domain": "fritz", "title": "Fritz-esterno", "state": "not_loaded",
             "source": "ignore"},
        ]}, [])
        voce = a.read()["integrazioni"][0]
        assert voce["origine"] == "ignore"
    finally:
        a.close()


def test_un_archivio_gia_esistente_guadagna_la_colonna_origine(tmp_path):
    """La migrazione 6, gemella della 2: senza, dal momento dell'aggiornamento
    il primo `replace` fallirebbe e la casa smetterebbe di ricostruirsi in
    silenzio."""
    import sqlite3

    percorso = str(tmp_path / "vecchio.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE integrazioni (dominio TEXT NOT NULL, titolo TEXT,"
        " stato TEXT, motivo TEXT);")
    vecchio.commit()
    vecchio.close()

    a = HomeSpaceStore(percorso)
    try:
        a.replace({"integrazioni": [
            {"domain": "fritz", "title": "Fritz", "state": "not_loaded",
             "source": "ignore"},
        ]}, [])
        assert a.read()["integrazioni"][0]["origine"] == "ignore"
    finally:
        a.close()
