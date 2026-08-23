"""Il mestiere: quale struttura serve, e perche'. La Legge I che diventa codice."""
from hiris.app.azione.costruzione.mestiere import consiglia


def _intento(**kw):
    base = {"richiesto": None, "innesco": None, "passi": [], "stati": [],
            "parametri": [], "riuso": False, "ricorrente": False}
    base.update(kw)
    return base


def test_un_innesco_fa_un_automazione():
    esito = consiglia(_intento(innesco=[{"trigger": "state"}], passi=[{"action": "light.turn_on"}]))
    assert esito["strutture"] == ["automazione"]
    assert esito["dissenso"] is False


def test_una_sequenza_senza_innesco_fa_uno_script():
    esito = consiglia(_intento(passi=[{"action": "light.turn_off"}, {"delay": 5}]))
    assert esito["strutture"] == ["script"]


def test_soli_stati_da_ristabilire_fanno_una_scena():
    esito = consiglia(_intento(stati=[{"entity_id": "light.salotto", "state": "on"}]))
    assert esito["strutture"] == ["scena"]


def test_un_innesco_piu_una_sequenza_riusata_fa_tutti_e_due():
    esito = consiglia(_intento(innesco=[{"trigger": "time"}],
                               passi=[{"action": "light.turn_off"}], riuso=True))
    assert esito["strutture"] == ["automazione", "script"]
    assert "riusa" in esito["motivo"] or "altrove" in esito["motivo"]


def test_un_parametro_in_ingresso_impone_lo_script():
    """Le automazioni non prendono parametri; gli script si', con `fields`."""
    esito = consiglia(_intento(innesco=[{"trigger": "state"}],
                               passi=[{"action": "light.turn_on"}],
                               parametri=["stanza"]))
    assert "script" in esito["strutture"]


def test_una_ricorrenza_e_un_automazione_non_una_promessa():
    """Lo schedulatore serve per «fra un'ora, una volta». «Ogni giorno alle 7»
    e' un'automazione di Home Assistant -- Legge I, e il doppione che questa
    riga previene."""
    esito = consiglia(_intento(ricorrente=True, passi=[{"action": "cover.open_cover"}]))
    assert esito["strutture"] == ["automazione"]
    assert "ricorrenza" in esito["motivo"]


def test_il_dissenso_si_dichiara_quando_l_utente_ha_chiesto_altro():
    esito = consiglia(_intento(richiesto="automazione",
                               passi=[{"action": "light.turn_off"}]))
    assert esito["strutture"] == ["script"]
    assert esito["dissenso"] is True
    assert "automazione" in esito["motivo"]


def test_un_intento_vuoto_non_consiglia_niente_e_lo_dice():
    """Un ingresso vuoto non deve produrre una frase falsa detta con sicurezza."""
    esito = consiglia(_intento())
    assert esito["strutture"] == []
    assert esito["motivo"]
    assert esito["dissenso"] is False


def test_una_ricorrenza_con_soli_stati_fa_automazione_piu_scena():
    """Gli stati non vengono mai consumati da automazione né da script.
    Una ricorrenza (che fa automazione) con stati da ristabilire richiede anche una scena.
    L'automazione oraria accende la scena."""
    esito = consiglia(_intento(ricorrente=True,
                               stati=[{"entity_id": "light.salotto", "state": "on"}]))
    assert esito["strutture"] == ["automazione", "scena"]
    assert "accende" in esito["motivo"] or "scena" in esito["motivo"]


def test_un_innesco_con_stati_senza_passi_fa_automazione_piu_scena():
    """Un innesco senza passi è un'automazione che accende una scena con gli stati."""
    esito = consiglia(_intento(innesco=[{"trigger": "state"}],
                               stati=[{"entity_id": "light.salotto", "state": "on"}]))
    assert esito["strutture"] == ["automazione", "scena"]
    assert "accende" in esito["motivo"] or "scena" in esito["motivo"]


def test_soli_stati_rimangono_solo_scena():
    """Quando l'unica cosa è ristabilire stati, la struttura è solo una scena.
    Non deve diventare automazione + scena."""
    esito = consiglia(_intento(stati=[{"entity_id": "light.salotto", "state": "on"}]))
    assert esito["strutture"] == ["scena"]
    assert "scena" in esito["motivo"]
