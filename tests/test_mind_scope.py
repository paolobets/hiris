"""Lo scope: cosa l'osservatore guarda, da quando, perche' — e **chi l'ha
deciso**.

**Perche' l'autore e' una colonna e non un dettaglio.** La spec prevedeva un
movimento solo: dalla pagina si puo' togliere qualcosa a cio' che l'osservatore
ha scelto (§11). Il proprietario ha aggiunto il secondo (11/09/2026):
**l'osservatore toglie, ma l'analista puo' far rientrare**. Senza sapere CHI ha
deciso, la seconda decisione non saprebbe di essere una revisione della prima —
e l'osservatore, al giro dopo, ricancellerebbe cio' che l'analista aveva
rimesso dentro, per sempre, senza che nessuno se ne accorgesse.

**L'ordine di autorita' non e' una gerarchia di importanza: e' una gerarchia di
INFORMAZIONE.** L'osservatore decide guardando l'anagrafe e l'obiettivo;
l'analista decide dopo aver letto i resoconti, cioe' con in mano una cosa che
l'osservatore non aveva -- come la casa si e' comportata davvero. Il
proprietario decide sapendo perche' ha quella casa. Chi sa di piu' non viene
scavalcato da chi sa di meno.
"""
import os

import pytest

from hiris.app.mind.scope import ANALYST, OBSERVER, OWNER
from hiris.app.mind.store import ObservationsStore


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


def test_prima_di_qualunque_decisione_non_si_guarda_niente(archivio):
    """`{}` e non «tutta la casa»: prima che l'osservatore abbia deciso, HIRIS
    non ha scelto niente, e fingere il contrario direbbe al proprietario che
    sta osservando 833 entita' che invece non guarda."""
    assert archivio.scope() == {}


def test_una_decisione_porta_il_perche_e_chi_l_ha_presa(archivio):
    archivio.decide_scope("sensor.solare", inside=True, reason="pesa sull'energia",
                          author=OBSERVER, when_ts=1000.0)

    voce = archivio.scope()["sensor.solare"]
    assert voce["dentro"] is True
    assert voce["motivo"] == "pesa sull'energia"
    assert voce["autore"] == OBSERVER
    assert voce["deciso_ts"] == 1000.0


def test_l_analista_puo_far_rientrare_cio_che_l_osservatore_ha_tolto(archivio):
    """**L'emendamento del proprietario, provato.** L'osservatore decide al
    momento dello scope, guardando l'anagrafe; l'analista decide dopo aver
    letto i resoconti. Un'esclusione sbagliata dal primo sguardo e' esattamente
    l'errore che solo il secondo puo' vedere.

    Mutazione che la uccide: far vincere sempre la decisione piu' recente --
    funzionerebbe qui, e si romperebbe al test dopo.
    """
    archivio.decide_scope("sensor.pioggia", inside=False, reason="non pesa",
                          author=OBSERVER, when_ts=1000.0)
    archivio.decide_scope("sensor.pioggia", inside=True,
                          reason="spiega il crollo dell'autosufficienza",
                          author=ANALYST, when_ts=2000.0)

    voce = archivio.scope()["sensor.pioggia"]
    assert voce["dentro"] is True
    assert voce["autore"] == ANALYST


def test_l_osservatore_non_scavalca_chi_ha_deciso_prima_di_lui(archivio):
    """**La difesa che rende vero l'emendamento.** Senza di essa l'analista
    rimette dentro, l'osservatore al giro successivo ritoglie, e la casa
    oscilla per sempre senza che nessuno lo veda: la decisione dell'analista
    verrebbe cancellata da chi ha meno informazione, non da chi ne ha di piu'.

    Mutazione che la uccide: lasciare che l'osservatore sovrascriva qualunque
    autore.
    """
    archivio.decide_scope("sensor.pioggia", inside=True, reason="spiega il crollo",
                          author=ANALYST, when_ts=1000.0)

    assert archivio.decide_scope("sensor.pioggia", inside=False, reason="non pesa",
                                 author=OBSERVER, when_ts=2000.0) is False

    voce = archivio.scope()["sensor.pioggia"]
    assert voce["dentro"] is True
    assert voce["autore"] == ANALYST


def test_il_proprietario_scavalca_tutti_e_due(archivio):
    """L'unica manopola resta sua: se toglie qualcosa dalla pagina, non c'e'
    nessun attore che gliela rimetta dentro alle spalle."""
    archivio.decide_scope("light.salotto", inside=True, reason="pesa",
                          author=ANALYST, when_ts=1000.0)

    assert archivio.decide_scope("light.salotto", inside=False, reason="non mi interessa",
                                 author=OWNER, when_ts=2000.0) is True
    assert archivio.scope()["light.salotto"]["autore"] == OWNER

    assert archivio.decide_scope("light.salotto", inside=True, reason="ci ripenso",
                                 author=ANALYST, when_ts=3000.0) is False
    assert archivio.scope()["light.salotto"]["dentro"] is False


def test_lo_stesso_autore_puo_sempre_cambiare_idea(archivio):
    """L'autorita' protegge da CHI SA MENO, non da se stessi: un osservatore
    che riconsidera la casa deve poter correggere la propria decisione, o la
    cadenza di riconsiderazione non servirebbe a niente."""
    archivio.decide_scope("sensor.x", inside=True, reason="prima", author=OBSERVER,
                          when_ts=1000.0)

    assert archivio.decide_scope("sensor.x", inside=False, reason="ci ho ripensato",
                                 author=OBSERVER, when_ts=2000.0) is True
    assert archivio.scope()["sensor.x"]["motivo"] == "ci ho ripensato"


def test_cio_che_si_guarda_davvero_e_solo_quello_dentro(archivio):
    """La domanda che il rubinetto pone a ogni evento: «questo soggetto lo
    guardo?». Chi e' stato escluso resta NELLA pagina con la sua ragione -- e'
    la trasparenza -- ma non nel filtro."""
    archivio.decide_scope("sensor.dentro", inside=True, reason="pesa", author=OBSERVER)
    archivio.decide_scope("sensor.fuori", inside=False, reason="non pesa", author=OBSERVER)

    assert archivio.is_watched("sensor.dentro") is True
    assert archivio.is_watched("sensor.fuori") is False
    assert set(archivio.scope()) == {"sensor.dentro", "sensor.fuori"}


def test_un_soggetto_su_cui_nessuno_ha_deciso_e_fuori(archivio):
    """**Il default e' «no», e non e' un dettaglio.** Fra l'esser stati
    esclusi e il non esser mai stati considerati non c'e' differenza per il
    rubinetto: in nessuno dei due casi qualcuno ha deciso che quel soggetto
    pesa. Un default «si'» rimetterebbe dentro tutte le 833 entita' della casa
    il giorno in cui lo scope fosse vuoto -- cioe' **al primo avvio**, prima
    che l'osservatore abbia parlato -- e la promessa del -83% cadrebbe li'.

    Mutazione che la uccide: tornare `True` per un soggetto sconosciuto.
    """
    assert archivio.is_watched("sensor.mai_visto") is False


def test_la_domanda_del_rubinetto_costa_una_riga_sola(archivio):
    """Misurato l'11/09/2026 su uno scope di 833 righe (381 dentro): chiedere
    **un** soggetto costa **24 us**, chiedere l'insieme intero ne costava
    **1.084** -- quarantacinque volte tanto, per ogni evento della casa, cioe'
    32 secondi di lavoro al giorno contro 0,7.

    La prima stesura dello scope tornava l'insieme (`watched_subjects()`), e
    il suo docstring prometteva gia' «una lettura sola»: era vero, ed era la
    lettura sbagliata. Qui si guarda che la promessa sia diventata quella
    giusta -- una RIGA, per chiave primaria.
    """
    for i in range(50):
        archivio.decide_scope(f"sensor.s{i}", inside=True, reason="pesa", author=OBSERVER)

    piano = archivio._conn.execute(
        "EXPLAIN QUERY PLAN SELECT inside FROM scope WHERE subject = ?",
        ("sensor.s1",)).fetchall()

    testo = " ".join(str(r["detail"]) for r in piano)
    assert "SCAN" not in testo, testo
    assert "SEARCH" in testo, testo


def test_una_decisione_senza_motivo_non_si_scrive(archivio):
    """Stessa disciplina di `type_vocabulary.Field`, che non si puo' costruire
    senza provenienza: una scelta senza ragione non e' rivedibile da nessuno --
    ne' dall'analista ne' dal proprietario -- e la pagina esiste per farle
    vedere, le ragioni."""
    assert archivio.decide_scope("sensor.muto", inside=True, reason="  ",
                                 author=OBSERVER) is False
    assert archivio.scope() == {}
