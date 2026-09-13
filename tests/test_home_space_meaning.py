"""Il dettaglio di un'entita' dice **cosa significa la sua classe**.

E' il lettore del sapere importato dalla fetta 4 (spec §2): finche' il
significato di una classe viveva solo in una tabella a mano di 27 voci, HIRIS
non sapeva dire niente delle altre. Misurato il 12/09/2026 sulla casa vera: 44
classi di `sensor` su 62 e 28 su 28 di `binary_sensor` senza una parola
(`docs/design/2026-09-12-il-sapere-e-le-ricette.md`, misura 2).

**Il sapere e' la fonte, non le traduzioni.** Le due cose non sono la stessa:
Home Assistant pubblica un NOME («Potenza»), il repo dove ha guardato porta una
frase che dice cosa quel valore E' («la potenza ISTANTANEA, non un'energia»).
Il sapere li tiene insieme, con la frase piu' ricca che vince -- e leggere le
traduzioni direttamente da qui perderebbe proprio quella meta'.
"""
import pytest

from hiris.app.home_space import queries
from hiris.app.mind.knowledge import Fact, KnowledgeStore


@pytest.fixture
def sapere(tmp_path):
    s = KnowledgeStore(str(tmp_path / "sapere.db"))
    s.write(Fact(subject_kind="tipo", subject="sensor.aqi", field="significato",
                 value="Indice di qualita' dell'aria", provenance="importato",
                 verification="confermata",
                 source="frontend/get_translations (Home Assistant 2026.9.1)",
                 who="prova", when_ts=1789000000.0))
    yield s
    s.close()


def _casa():
    return {"entita": [{"id": "sensor.salotto_aqi", "nome": "Qualita' aria salotto",
                        "area_id": None, "dispositivo_id": None}],
            "aree": [], "dispositivi": []}


def _dettaglio(sapere, *, classe="aqi"):
    return queries.view(
        _casa(), [], [], {"sensor.salotto_aqi": "42"},
        "entita", "sensor.salotto_aqi",
        reported_classes={"sensor.salotto_aqi": classe} if classe else None,
        knowledge=sapere)


def test_il_dettaglio_DICE_cosa_significa_la_classe(sapere):
    """**Il lettore che rende vero il sapere importato.** Senza di lui quelle
    righe sarebbero un archivio che nessuno interroga -- e un dato che nessuno
    puo' chiedere, dice la quarta fondamenta, non esiste.

    Mutazione ESEGUITA: togliere il blocco che scrive `significato` in
    `_view_entity` -- rossa.
    """
    dettaglio = _dettaglio(sapere)

    assert dettaglio["significato"] == "Indice di qualita' dell'aria"


def test_una_classe_di_cui_il_sapere_TACE_non_inventa_un_significato(sapere):
    """Nessuna chiave, non una stringa vuota: «non lo so» si dichiara
    tacendo, come fa gia' `regola` qui accanto."""
    dettaglio = _dettaglio(sapere, classe="mai_vista")

    assert "significato" not in dettaglio


class _SapereSpiato:
    """Il sapere, con le domande contate. Serve perche' la proprieta' da
    difendere e' che una domanda NON venga fatta, e il suo esito e' identico
    in tutti e due i casi."""

    def __init__(self, vero):
        self._vero = vero
        self.domande = []

    def get(self, subject_kind, subject, field):
        self.domande.append((subject_kind, subject, field))
        return self._vero.get(subject_kind, subject, field)


def test_un_entita_SENZA_classe_non_chiede_niente_al_sapere(sapere):
    """Una chiave composta su una classe assente (`sensor.None`) chiederebbe
    una riga che non puo' esistere, a ogni dettaglio di ogni entita' senza
    classe -- che su questa casa sono la maggioranza.

    **Questa prova e' nata verde e non poteva fallire.** La prima stesura
    asseriva `"significato" not in dettaglio`: vero anche togliendo la
    guardia, perche' l'archivio risponde `None` a una chiave inventata
    esattamente come tace su una classe che non conosce. La mutazione
    `if knowledge is None:` al posto di `if knowledge is None or not
    device_class:`, eseguita il 13/09/2026, la lasciava verde.

    Riscritta sul fatto vero -- la domanda non si fa -- la stessa mutazione
    arrossisce.

    Mutazione che la uccide: togliere `or not device_class` dalla guardia.
    """
    spia = _SapereSpiato(sapere)

    dettaglio = _dettaglio(spia, classe=None)

    assert spia.domande == [], "ha interrogato il sapere su una classe che non c'e'"
    assert "significato" not in dettaglio


def test_SENZA_sapere_il_dettaglio_esce_come_prima():
    """Il dettaglio non dipende dal sapere per esistere: senza, tace e basta.
    Un componente che si rompe quando un altro manca non e' autonomo."""
    dettaglio = queries.view(
        _casa(), [], [], {"sensor.salotto_aqi": "42"},
        "entita", "sensor.salotto_aqi",
        reported_classes={"sensor.salotto_aqi": "aqi"})

    assert "significato" not in dettaglio
    assert dettaglio["id"] == "sensor.salotto_aqi"
