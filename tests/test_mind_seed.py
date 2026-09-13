"""Il seme del sapere: il repo, e poi cio' che l'installazione dichiara.

Spec `docs/design/2026-09-10-i-tre-attori.md` §2 e §8.

**Le misure che giustificano questa fetta** stanno in
`docs/design/2026-09-12-il-sapere-e-le-ricette.md`, prese sulla casa vera il
12/09/2026: il repo scriveva a mano il significato di **18 classi di `sensor`
su 62** e di **zero su 28** di `binary_sensor`, mentre l'installazione li
pubblica tutti, nella lingua dell'utente.
"""
import pytest

from hiris.app.mind import seed
from hiris.app.mind.knowledge import (
    KnowledgeStore,
    directions_by_translation_key,
    type_subject,
)


@pytest.fixture
def sapere(tmp_path):
    s = KnowledgeStore(str(tmp_path / "sapere.db"))
    yield s
    s.close()


def _risorse(*coppie):
    """Le risorse di `entity_component` come le manda Home Assistant."""
    return {f"component.{d}.entity_component.{c}.name": nome
            for d, c, nome in coppie}


# -- le direzioni dell'energia ---------------------------------------------

def test_le_direzioni_del_seme_sono_UNIVERSALI_e_portano_le_loro_prove():
    """Soggetto `integrazione`: valgono per chiunque abbia quell'inverter, non
    solo per questa casa -- ed e' il genere a dirlo, non una colonna in piu'
    che potrebbe divergere da lui."""
    righe = seed.direction_seed(1789000000.0)

    assert len(righe) == 14
    assert {r.subject for r in righe} == {"zcsazzurro"}
    assert {r.subject_kind for r in righe} == {"integrazione"}
    assert all(r.provenance == "dedotto" and r.evidence for r in righe)


def test_la_direzione_si_rilegge_come_mappa_per_il_lettore(sapere):
    sapere.seed(seed.direction_seed(1789000000.0))

    mappa = directions_by_translation_key(sapere)

    assert mappa["energy_generating_today"] == "produzione"
    assert mappa["power_autoconsuming"] == "autoconsumo"
    assert len(mappa) == 14


def test_una_casa_che_non_ha_MAI_seminato_ha_una_mappa_vuota_non_un_errore(sapere):
    """Un impianto con un altro inverter: nessuna riga, mappa vuota. Il
    lettore perde la meta' dedotta e lo fa in silenzio -- che e' giusto,
    perche' indovinare sarebbe peggio."""
    assert directions_by_translation_key(sapere) == {}


# -- i significati delle classi --------------------------------------------

def test_il_seme_del_repo_dichiara_da_dove_viene_SENZA_dirsi_confermato():
    """**Correzione della revisione indipendente, 13/09/2026.**

    Il FATTO viene dal sorgente di Home Assistant -- provenienza `importato`.
    Ma il VALORE e' una frase nostra, con la nostra enfasi: «la potenza
    ISTANTANEA (mW, W, kW...)» non e' scritta da nessuna parte in
    `homeassistant/components/sensor/const.py`. Dire `verifica = confermata`
    affermerebbe che Home Assistant la dice cosi', e non e' vero: e' la forma
    esatta della motivazione falsa, dentro il campo che esiste per impedirla.

    Da dove viene sta in `evidence` -- *«cosa e' stato letto»* -- col tag.

    Mutazione che la uccide: rimettere `verification="confermata"`.
    """
    righe = seed.meaning_seed(1789000000.0)

    assert righe, "il seme dei significati e' vuoto"
    assert all(r.provenance == "importato" for r in righe)
    assert all(r.verification is None for r in righe)
    assert all("2026.9.1" in r.evidence for r in righe)
    assert all(r.subject_kind == "tipo" for r in righe)


def test_il_soggetto_di_un_tipo_e_dominio_PUNTO_classe():
    """La forma dell'esempio della spec §8: `sensor` · `sensor.power`."""
    assert type_subject("sensor") == "sensor"
    assert type_subject("sensor", "power") == "sensor.power"


def test_la_casa_porta_i_significati_che_il_repo_non_ha_mai_scritto(sapere):
    """**Il buco misurato**: 44 classi di `sensor` e 28 di `binary_sensor` che
    il repo non nominava. Non erano «non importanti»: erano quelle di cui
    HIRIS non sapeva dire niente.

    Mutazione ESEGUITA: far tornare `meanings_from_translations` una lista
    vuota -- rossa, la classe resta senza significato.
    """
    risorse = _risorse(("binary_sensor", "gas", "Gas"),
                       ("sensor", "aqi", "Indice di qualita' dell'aria"))

    sapere.seed(seed.meanings_from_translations(
        risorse, ha_version="2026.9.1", language="it", when_ts=1789000000.0))

    assert sapere.get("tipo", "binary_sensor.gas", "significato").value == "Gas"
    assert sapere.get("tipo", "sensor.aqi", "significato").provenance == "importato"


def test_il_NOME_della_casa_non_schiaccia_la_FRASE_del_repo(sapere):
    """**La regola che rende utile tenerli tutti e due.** Home Assistant
    pubblica un NOME («Potenza»); il repo, dove ha guardato, porta una frase
    che dice cosa quel valore E' («la potenza ISTANTANEA, non un'energia»).

    Sono due cose diverse, e quella piu' ricca non si perde: le righe della
    casa si scrivono con `seed`, che tocca solo cio' che manca.

    Mutazione ESEGUITA: scrivere i significati della casa con `write` invece
    che con `seed` -- rossa, la frase del repo sparisce sostituita da una
    parola.
    """
    sapere.seed(seed.meaning_seed(1789000000.0))
    prima = sapere.get("tipo", "sensor.power", "significato").value

    sapere.seed(seed.meanings_from_translations(
        _risorse(("sensor", "power", "Potenza")),
        ha_version="2026.9.1", language="it", when_ts=1789000001.0))

    assert sapere.get("tipo", "sensor.power", "significato").value == prima
    assert len(prima) > len("Potenza"), "il repo qui ha una frase, non un nome"


def test_una_classe_senza_nome_pubblicato_NON_produce_una_riga_vuota(sapere):
    """Una riga con un significato vuoto sarebbe peggio di nessuna riga:
    direbbe «l'abbiamo guardata» su una classe che nessuno ha guardato."""
    risorse = {"component.sensor.entity_component.power.name": ""}

    righe = seed.meanings_from_translations(
        risorse, ha_version="2026.9.1", language="it", when_ts=1789000000.0)

    assert righe == []


def test_la_fonte_della_casa_dice_il_comando_la_lingua_e_la_versione():
    """Chi rilegge la riga fra sei mesi deve sapere da dove viene e in che
    lingua: la stessa riga in inglese direbbe un'altra parola, e senza la
    lingua non si distinguerebbero."""
    [riga] = seed.meanings_from_translations(
        _risorse(("sensor", "power", "Potenza")),
        ha_version="2026.9.1", language="it", when_ts=1789000000.0)

    assert "frontend/get_translations" in riga.source
    assert "it" in riga.source
    assert "2026.9.1" in riga.source
