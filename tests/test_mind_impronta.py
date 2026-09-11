"""L'impronta: **accorgersi che in casa è comparso qualcosa di nuovo**.

Non e' una domanda a cui Home Assistant sappia rispondere: «è nuova?» si sa
solo confrontando la casa di adesso con com'era (spec §4). Serve dunque
un'impronta di com'era -- e il piano di questa fetta ne prevedeva una da
costruire.

**Non serve costruirla: c'e' gia', ed e' lo SCOPE.** Un'entita' e' nuova per
l'osservatore esattamente quando **nessuno ha ancora deciso niente su di lei**
-- ne' dentro ne' fuori. Una seconda struttura che tenesse «com'era la casa»
sarebbe un doppione della stessa verita', e divergerebbe al primo disallineamento
fra le due scritture (la fondamenta 2 del progetto). Ed e' anche piu' esatta:
l'anagrafe direbbe «questa entita' esisteva gia' ieri» anche di una su cui
l'osservatore non ha mai aperto bocca, per esempio perche' il giro precedente
si era interrotto a meta'.

**Ed e' l'innesco dell'anello**: l'osservatore gira al primo avvio, quando
cambia l'obiettivo, quando compare qualcosa di nuovo, e alla cadenza di
riconsiderazione (spec §5.1). Le quattro cause sono una domanda sola --
*«è ora, e perché?»* -- e la risposta porta sempre il perché con sé, perché
finisce in una pagina che il proprietario legge.
"""
import os

import pytest

from hiris.app.mind import cadence
from hiris.app.mind.scope import ANALYST, OBSERVER
from hiris.app.mind.store import ObservationsStore

GIORNO = 86400.0
ORA = 1_000_000.0
CADENZA = 3.5 * GIORNO


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


# -- l'impronta --------------------------------------------------------

def test_su_una_casa_mai_guardata_e_tutto_nuovo(archivio):
    """Al primo avvio lo scope e' vuoto, e ogni entita' della casa e' una su
    cui nessuno ha deciso. Non e' un caso limite: e' il giorno uno di ogni
    installazione."""
    assert archivio.undecided(["sensor.a", "sensor.b"]) == ["sensor.a", "sensor.b"]


def test_cio_su_cui_si_e_gia_deciso_non_e_nuovo_nemmeno_se_ESCLUSO(archivio):
    """**Il punto della prova.** Un'entita' lasciata FUORI e' stata guardata e
    giudicata: ripresentarla come nuova a ogni giro farebbe girare
    l'osservatore per sempre sulle stesse 452 entita' di servizio, e ogni giro
    costa una lettura dell'intera casa al modello.

    Mutazione che la uccide: cercare solo fra i soggetti `dentro`.
    """
    archivio.decide_scope("sensor.dentro", inside=True, reason="pesa", author=OBSERVER)
    archivio.decide_scope("sensor.fuori", inside=False, reason="non pesa", author=OBSERVER)

    assert archivio.undecided(["sensor.dentro", "sensor.fuori", "sensor.nuovo"]) == \
        ["sensor.nuovo"]


def test_cio_che_e_SPARITO_dalla_casa_non_diventa_nuovo(archivio):
    """Lo scope conserva le decisioni su entita' che non esistono piu' -- e'
    giusto, sono la cronaca di cosa si e' deciso e perche'. Ma la domanda qui
    e' sulla casa di ADESSO: si chiede fra cio' che c'e', non fra cio' che e'
    stato deciso.

    Mutazione che la uccide: tornare le chiavi dello scope invece dei soggetti
    chiesti.
    """
    archivio.decide_scope("sensor.smontato", inside=True, reason="pesava", author=OBSERVER)

    assert archivio.undecided(["sensor.rimasto"]) == ["sensor.rimasto"]


def test_l_ordine_e_quello_chiesto_e_non_si_ripete(archivio):
    """L'elenco finisce in un prompt e in una pagina: un ordine che cambia a
    ogni giro renderebbe due risposte identiche impossibili da confrontare."""
    assert archivio.undecided(["sensor.b", "sensor.a", "sensor.b"]) == \
        ["sensor.b", "sensor.a"]


def test_una_casa_senza_entita_non_ha_niente_di_nuovo(archivio):
    assert archivio.undecided([]) == []


# -- l'innesco ---------------------------------------------------------

def test_al_primo_avvio_si_riconsidera_e_si_dice_perche():
    """Non «True»: una **ragione**, perche' finisce nella pagina accanto alla
    riconsiderazione. `True` costringerebbe la pagina a reinventare la frase,
    e la reinventerebbe diversa."""
    perche = cadence.reason_to_reconsider(
        last=None, cadence_s=CADENZA, objective_ts=None, undecided=[], now=ORA)

    assert perche is not None
    assert "mai" in perche


def test_se_l_obiettivo_e_cambiato_DOPO_l_ultima_volta_si_rifa():
    """**La ragione piu' forte delle quattro, e per questo la prima che si
    guarda.** Lo scope e' una risposta a una domanda: cambiata la domanda,
    ogni risposta data prima e' sospetta, comprese quelle che escludevano.

    Mutazione che la uccide: confrontare l'obiettivo con `now` invece che con
    l'istante dell'ultima riconsiderazione.
    """
    ultima = {"quando_ts": ORA - GIORNO, "finestra_s": 7 * GIORNO, "cadenza_s": CADENZA}

    assert cadence.reason_to_reconsider(
        last=ultima, cadence_s=CADENZA, objective_ts=ORA - 2 * GIORNO,
        undecided=[], now=ORA) is None

    perche = cadence.reason_to_reconsider(
        last=ultima, cadence_s=CADENZA, objective_ts=ORA - 3600.0,
        undecided=[], now=ORA)
    assert perche is not None
    assert "obiettivo" in perche


def test_qualcosa_di_nuovo_in_casa_non_aspetta_la_cadenza():
    """Una lampadina installata stamattina non deve restare invisibile fino a
    giovedi': cio' che non e' osservato non esiste piu', e i tre giorni
    mancanti non tornano.

    La ragione **dice quante** sono e **ne nomina qualcuna**: «ci sono cose
    nuove» non e' una frase su cui il proprietario possa fare niente.

    Mutazione che la uccide: guardare solo la cadenza.
    """
    ultima = {"quando_ts": ORA - 3600.0, "finestra_s": 7 * GIORNO, "cadenza_s": CADENZA}

    perche = cadence.reason_to_reconsider(
        last=ultima, cadence_s=CADENZA, objective_ts=None,
        undecided=["light.nuova", "sensor.nuovo"], now=ORA)

    assert perche is not None
    assert "2" in perche
    assert "light.nuova" in perche


def test_e_senza_cadenza_misurata_una_cosa_nuova_fa_girare_lo_stesso():
    """**La misura della memoria puo' fallire, la casa intanto cambia.** Se
    l'unico innesco fosse la cadenza, un Home Assistant che non risponde alla
    sonda lascerebbe l'osservatore fermo per sempre su una casa che cresce.

    Mutazione che la uccide: pretendere `cadence_s` prima di guardare le
    quattro cause.
    """
    ultima = {"quando_ts": ORA - 3600.0, "finestra_s": None, "cadenza_s": None}

    perche = cadence.reason_to_reconsider(
        last=ultima, cadence_s=None, objective_ts=None,
        undecided=["light.nuova"], now=ORA)

    assert perche is not None
    assert "light.nuova" in perche


def test_passata_la_cadenza_si_rifa_e_la_ragione_porta_i_numeri():
    """«Sono passate 84 ore» non basta: quel numero viene dalla memoria
    misurata di Home Assistant, e la ragione lo dice -- altrimenti il
    proprietario dovrebbe crederci sulla parola."""
    ultima = {"quando_ts": ORA - 4 * GIORNO, "finestra_s": 7 * GIORNO,
              "cadenza_s": CADENZA}

    perche = cadence.reason_to_reconsider(
        last=ultima, cadence_s=CADENZA, objective_ts=None, undecided=[], now=ORA)

    assert perche is not None
    assert "84" in perche
    assert "7" in perche


def test_niente_di_cambiato_e_niente_da_fare():
    """**La quinta risposta, e la piu' importante da non sbagliare.** Girare
    quando non serve costa una lettura dell'intera casa al modello (≈26.600
    token) per non cambiare niente."""
    ultima = {"quando_ts": ORA - 3600.0, "finestra_s": 7 * GIORNO, "cadenza_s": CADENZA}

    assert cadence.reason_to_reconsider(
        last=ultima, cadence_s=CADENZA, objective_ts=ORA - 10 * GIORNO,
        undecided=[], now=ORA) is None


def test_senza_cadenza_misurata_e_senza_novita_non_si_gira_a_caso():
    """La domanda «è ora?» non ha risposta se la finestra non si e' potuta
    misurare. Delle due bugie possibili si sceglie quella che si vede: fermarsi
    e dirlo, invece di rileggere la casa a ogni giro del lavoro periodico."""
    ultima = {"quando_ts": ORA - 30 * GIORNO, "finestra_s": None, "cadenza_s": None}

    assert cadence.reason_to_reconsider(
        last=ultima, cadence_s=None, objective_ts=None, undecided=[], now=ORA) is None


# -- il perche' si scrive accanto a cio' che ha provocato ---------------

def test_la_riconsiderazione_conserva_la_ragione_che_l_ha_provocata(archivio):
    """La pagina mostra «l'ultima volta è stata il 9, perché era comparso un
    termostato nuovo». Senza la ragione scritta accanto, di quella
    riconsiderazione resterebbe solo una data."""
    archivio.record_reconsideration(when_ts=ORA, window_s=7 * GIORNO,
                                    cadence_s=CADENZA,
                                    reason="e' comparso light.nuova")

    assert archivio.last_reconsideration()["motivo"] == "e' comparso light.nuova"


def test_l_impronta_e_lo_scope_anche_quando_a_decidere_e_stato_l_analista(archivio):
    """L'emendamento del proprietario (11/09/2026) lascia decidere anche
    all'analista. Una sua decisione e' una decisione: il soggetto smette di
    essere nuovo, o l'osservatore glielo ripresenterebbe a ogni giro
    cancellandogliela."""
    archivio.decide_scope("sensor.pioggia", inside=True,
                          reason="spiega il crollo dell'autosufficienza", author=ANALYST)

    assert archivio.undecided(["sensor.pioggia"]) == []
