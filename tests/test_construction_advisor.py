"""Il mestiere: quale struttura serve, e perche'. La Legge I che diventa codice."""
import pytest

from hiris.app.action.construction.advisor import STRUCTURES, consiglia


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


# ── `richiesto` e' un vocabolario chiuso, non una frase ─────────────────────

def test_le_tre_strutture_sono_quelle_che_il_consiglio_puo_produrre():
    """`STRUCTURES` e' l'UNICA casa di «quali sono le tre strutture».

    Il confronto del dissenso e' un'appartenenza a questo insieme: se qui
    dentro comparisse una parola che `consiglia` non produce mai -- o ne
    sparisse una che produce -- il dissenso direbbe il falso su un caso vero,
    ed e' esattamente com'e' nato il rilievo."""
    prodotte = set()
    for intento in (
        _intento(innesco=[{"trigger": "sun"}], passi=[{"action": "a"}]),
        _intento(passi=[{"action": "a"}]),
        _intento(stati=[{"entity_id": "light.x", "state": "on"}]),
    ):
        prodotte.update(consiglia(intento)["strutture"])
    assert prodotte == set(STRUCTURES)


@pytest.mark.parametrize("scritto", [
    "Automazione",
    "un'automazione",
    "automation",
    "correzione errori di configurazione dell'automazione esistente",
])
def test_una_frase_al_posto_della_struttura_NON_e_un_dissenso(scritto):
    """Il difetto misurato sulla casa vera (audit delle fondamenta, rilievo 5).

    `GET /api/constructions`, costruzione APPLICATA
    `automation.1784125482111029`: «hai chiesto "correzione errori di
    configurazione dell'automazione esistente", e secondo me qui serve
    automazione; dimmi tu». Il consigliere dissentiva da se stesso, il
    proprietario ha approvato un'anteprima che si contraddiceva, e la cronaca
    -- che serve a MISURARE quanto il mestiere sbaglia -- ha registrato un
    dissenso falso.

    La cura sta alla fonte (`richiesto` e' un vocabolario chiuso, e la porta
    lo impone): qui si prova che il consigliere, davanti a una parola che non
    e' una delle tre, non inventa un disaccordo. Se la cura fosse una
    normalizzazione di stringhe piu' furba, il quarto caso di questa lista --
    una frase intera che CONTIENE la parola «automazione» -- la smentirebbe.
    """
    esito = consiglia(_intento(richiesto=scritto,
                               innesco=[{"trigger": "sun", "event": "sunrise"}],
                               passi=[{"action": "cover.open_cover"}]))
    assert esito["strutture"] == ["automazione"]
    assert esito["dissenso"] is False, (
        f"«{scritto}» non nomina una delle tre strutture: non c'e' niente da "
        "cui dissentire")
    assert "hai chiesto" not in esito["motivo"]
