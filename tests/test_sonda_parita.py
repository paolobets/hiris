"""La sonda fa girare le copie VERE delle regole e conta dove non concordano.

Le prove usano la casa sintetica (`tests/_casa_sintetica.py`), che ha i casi
messi apposta.

Le domande `fuori`, `nomi` e `dove` e le loro prove (le mutazioni sulla casa
sintetica, sul confronto ricetta/osservatore e sul controllo degli id in testa
alle righe) sono uscite col Task 12 della Tappa 3 (04/10/2026): l'osservatore
e le ricette chiedono alla casa chi guardare, il nome e il posto, e non c'e'
piu' una seconda copia da confrontare. Le sorveglia
`tests/test_attori_compongono.py`.

`valore` e le sue prove sono uscite col Task 8 della Tappa 3 (04/10/2026,
B-08): il nucleo chiede al vocabolario, e non c'e' piu' una seconda copia.

Col Task 8 le porte di `fonte` dicono la causa da `House.source`, e sulla
casa sintetica non discordano piu'. Le prove qui sotto producono a comando lo
stato difettoso di prima (la verifica senza la casa, il motivo unico delle
ricette, una casa che dice «viva» di tutto) e verificano che la domanda lo
veda: e' cio' che le tiene discriminanti.

Le due domande della Tappa 3 (`fuori_con_causa`, `fonte`), mutazioni ESEGUITE
il 03/10/2026 e ripristinate (`git status` pulito; `fuori_con_causa` e le sue
prove sono uscite col Task 5, quando le sei copie sono diventate una):
- in `action/verification.py` il rifiuto di un'entita' senza stato dice «non
  ha uno stato» invece di «non esiste in questa casa» -- rossa
  (`test_la_fonte_vede_la_verifica_che_nega_un_entita_disabilitata`: nessun
  caso, attesa `sensor.sensore_d_spento`);
- in `mind/recipes.py` il motivo «senza statistiche» non incolpa piu' lo
  `state_class` -- rosse le due prove sul motivo delle ricette;
- in `sonda_parita._causes_by_device` tolte le disabilitate che la scheda
  conta e non elenca -- rossa (`_view_device` risponde per 9 entita', non 10).

"""
import sys
from pathlib import Path

import pytest

from hiris.app.mind.operations import NotComputable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import sonda_parita
from _casa_sintetica import synthetic_inputs

CLOCK = 1_790_000_000.0


@pytest.fixture(scope="module")
def result():
    return sonda_parita.run(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))


def test_ogni_domanda_gira_e_dichiara_le_copie_che_ha_chiamato(result):
    assert set(result) == set(sonda_parita.QUESTIONS)
    broken = {name: verdict.get("errore") for name, verdict in result.items()
              if verdict["disaccordi"] is None}
    assert not broken, broken
    silent = [name for name, verdict in result.items() if len(verdict["chiamate"]) < 2]
    assert not silent, f"domande che non confrontano due copie: {silent}"


def test_un_peggioramento_supera_l_atteso_e_un_miglioramento_no(result):
    expected = {name: verdict["disaccordi"] for name, verdict in result.items()}
    assert sonda_parita.worse_than_expected(result, expected) == []
    stricter = dict(expected, riferimenti=expected["riferimenti"] - 1)
    assert sonda_parita.worse_than_expected(result, stricter) == [
        (f"riferimenti: {expected['riferimenti']} disaccordi, attesi al massimo "
         f"{expected['riferimenti'] - 1}")]
    looser = dict(expected, riferimenti=expected["riferimenti"] + 5)
    assert sonda_parita.worse_than_expected(result, looser) == []


def test_una_domanda_senza_atteso_ferma_il_cancello(result):
    expected = {name: verdict["disaccordi"] for name, verdict in result.items()}
    del expected["oggi"]
    assert sonda_parita.worse_than_expected(result, expected) == [
        "oggi: nessun atteso scritto"]


def test_una_domanda_che_solleva_non_ferma_le_altre_e_si_dichiara(monkeypatch):
    def broken(inputs):
        raise RuntimeError("copia sparita")

    monkeypatch.setitem(sonda_parita.QUESTIONS, "riferimenti", broken)
    monkeypatch.setitem(sonda_parita.QUESTIONS, "oggi", lambda inputs: {
        "disaccordi": 0, "casi": [], "chiamate": ["a", "b"]})
    outcome = sonda_parita.run(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))
    assert outcome["riferimenti"]["disaccordi"] is None
    assert "copia sparita" in outcome["riferimenti"]["errore"]
    assert outcome["fonte"]["disaccordi"] == 0
    complaints = sonda_parita.worse_than_expected(outcome, {"riferimenti": 0})
    assert [line for line in complaints if line.startswith("riferimenti:")] == [
        "riferimenti: non eseguita (RuntimeError: copia sparita)"]


# ── le due domande della Tappa 3 (piano, Task 1) ────────────────────────────

def _with_universal_domain(inputs: dict) -> dict:
    """La casa sintetica col dominio universale di Home Assistant: senza, la
    verifica di un comando su un `sensor` non si puo' chiedere (nessun servizio
    lo nomina), e la porta che dice «non esiste» non si vedrebbe."""
    inputs["services"].append({"domain": "homeassistant", "services": {
        "update_entity": {"name": "Update entity", "fields": {},
                          "target": {"entity": [{}]}}}})
    return inputs


def test_la_fonte_sulla_casa_sintetica_non_discorda(result):
    """Dal Task 8 le tre porte e la casa dicono la stessa causa."""
    verdict = result["fonte"]
    assert verdict["disaccordi"] == 0, verdict["casi"]
    assert verdict["chieste"]["digesto"] == 12
    assert verdict["chieste"]["casa"] >= 12
    # Col dominio universale la verifica si chiede anche sui `sensor`, e la
    # disabilitata della casa sintetica arriva davvero alla porta.
    universal = sonda_parita.source(sonda_parita.build_inputs(
        _with_universal_domain(synthetic_inputs()), clock=CLOCK))
    assert universal["disaccordi"] == 0, universal["casi"]


def test_la_fonte_vede_il_motivo_delle_ricette_che_da_la_colpa_sbagliata(monkeypatch):
    """Lo stato di prima, prodotto a comando: un motivo solo per tutte, che
    incolpa lo `state_class` anche di una disabilitata
    (`sensor.sensore_d_spento`)."""
    monkeypatch.setattr(sonda_parita, "silent_entities", lambda house, keys: {
        key: NotComputable(f"{key} {sonda_parita.BLAMES_STATE_CLASS}",
                           cause="senza_statistiche") for key in keys})
    verdict = sonda_parita.source(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))
    blamed = [case for case in verdict["casi"] if case["porta"] == "ricette"]
    assert "sensor.sensore_d_spento" in {case["id"] for case in blamed}
    spenta = next(case for case in blamed if case["id"] == "sensor.sensore_d_spento")
    assert spenta["fatti"]["disabled_by"] == "user"


def test_la_fonte_vede_la_verifica_che_nega_un_entita_disabilitata(monkeypatch):
    """Il trovato 2 del piano (S-27), prodotto a comando: la verifica senza la
    casa dice «non esiste» di un'entita' che l'anagrafe conosce."""
    real = sonda_parita.verification
    monkeypatch.setattr(sonda_parita, "verification",
                        lambda call, registry, states, **_kw: real(call, registry, states))
    outcome = sonda_parita.source(sonda_parita.build_inputs(
        _with_universal_domain(synthetic_inputs()), clock=CLOCK))
    denied = [case for case in outcome["casi"] if case["porta"] == "verification"]
    assert [case["id"] for case in denied] == ["sensor.sensore_d_spento"]
    assert outcome["non_interrogabili_dalla_verifica"] == 0


def test_la_fonte_vede_una_casa_che_dice_viva_di_una_disabilitata(monkeypatch):
    monkeypatch.setattr(sonda_parita.House, "source",
                        lambda self, key: {"stato": "viva"})
    outcome = sonda_parita.source(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))
    assert "sensor.sensore_d_spento" in {case["id"] for case in outcome["casi"]
                                         if case["porta"] == "casa"}


def test_la_fonte_vede_il_digesto_che_tiene_dentro_un_entita_sparita():
    inputs = synthetic_inputs()
    inputs["states"] = [row for row in inputs["states"]
                        if row["entity_id"] != "light.luce_uno"]
    outcome = sonda_parita.source(sonda_parita.build_inputs(inputs, clock=CLOCK))
    assert [(case["id"], case["porta"]) for case in outcome["casi"]
            if case["porta"] == "digesto"] == [("light.luce_uno", "digesto")]


def test_un_sensore_che_dichiara_lo_state_class_non_e_incolpato():
    """Fuori da `statistic_ids` ma con `state_class: measurement`: fino al
    04/10/2026 il motivo diceva che le tiene «solo per le entita' che
    dichiarano uno `state_class`», ed era falso. Ora no."""
    inputs = synthetic_inputs()
    inputs["statistic_ids"].remove("sensor.sensore_b_segnale")
    outcome = sonda_parita.source(sonda_parita.build_inputs(inputs, clock=CLOCK))
    assert "sensor.sensore_b_segnale" not in {case["id"] for case in outcome["casi"]}


def test_la_fonte_senza_servizi_non_finge_di_aver_chiesto():
    inputs = synthetic_inputs()
    del inputs["services"]
    outcome = sonda_parita.run(sonda_parita.build_inputs(inputs, clock=CLOCK))
    assert outcome["fonte"]["disaccordi"] is None
    assert "servizi" in outcome["fonte"]["errore"]
