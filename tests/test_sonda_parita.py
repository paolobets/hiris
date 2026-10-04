"""La sonda fa girare le copie VERE delle regole e conta dove non concordano.

Le prove usano la casa sintetica (`tests/_casa_sintetica.py`), che ha i casi
messi apposta.

Le domande `fuori`, `nomi` e `dove` e le loro prove (le mutazioni sulla casa
sintetica, sul confronto ricetta/osservatore e sul controllo degli id in testa
alle righe) sono uscite col Task 12 della Tappa 3 (04/10/2026): l'osservatore
e le ricette chiedono alla casa chi guardare, il nome e il posto, e non c'e'
piu' una seconda copia da confrontare. Le sorveglia
`tests/test_attori_compongono.py`.

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
    stricter = dict(expected, valore=expected["valore"] - 1)
    assert sonda_parita.worse_than_expected(result, stricter) == [
        f"valore: {expected['valore']} disaccordi, attesi al massimo {expected['valore'] - 1}"]
    looser = dict(expected, valore=expected["valore"] + 5)
    assert sonda_parita.worse_than_expected(result, looser) == []


def test_una_domanda_senza_atteso_ferma_il_cancello(result):
    expected = {name: verdict["disaccordi"] for name, verdict in result.items()}
    del expected["valore"]
    assert sonda_parita.worse_than_expected(result, expected) == [
        "valore: nessun atteso scritto"]


def test_una_domanda_che_solleva_non_ferma_le_altre_e_si_dichiara(monkeypatch):
    def broken(inputs):
        raise RuntimeError("copia sparita")

    monkeypatch.setitem(sonda_parita.QUESTIONS, "riferimenti", broken)
    monkeypatch.setitem(sonda_parita.QUESTIONS, "oggi", lambda inputs: {
        "disaccordi": 0, "casi": [], "chiamate": ["a", "b"]})
    outcome = sonda_parita.run(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))
    assert outcome["riferimenti"]["disaccordi"] is None
    assert "copia sparita" in outcome["riferimenti"]["errore"]
    assert outcome["valore"]["disaccordi"] == 1
    complaints = sonda_parita.worse_than_expected(outcome, {"riferimenti": 0})
    assert [line for line in complaints if line.startswith("riferimenti:")] == [
        "riferimenti: non eseguita (RuntimeError: copia sparita)"]


def test_il_valore_si_chiede_alla_copia_vera_del_nucleo(result):
    # `binary_sensor.porta_uno` e' `unavailable`: il nucleo lo legge come un
    # valore, il vocabolario no.
    assert [case["id"] for case in result["valore"]["casi"]] == ["binary_sensor.porta_uno"]


# ── le due domande della Tappa 3 (piano, Task 1) ────────────────────────────

def _with_universal_domain(inputs: dict) -> dict:
    """La casa sintetica col dominio universale di Home Assistant: senza, la
    verifica di un comando su un `sensor` non si puo' chiedere (nessun servizio
    lo nomina), e la porta che dice «non esiste» non si vedrebbe."""
    inputs["services"].append({"domain": "homeassistant", "services": {
        "update_entity": {"name": "Update entity", "fields": {},
                          "target": {"entity": [{}]}}}})
    return inputs


def test_la_fonte_vede_il_motivo_delle_ricette_che_da_la_colpa_sbagliata(result):
    """`sensor.sensore_d_spento` e' disabilitata e negli stati non c'e': il
    motivo delle ricette dice che le manca uno `state_class`."""
    verdict = result["fonte"]
    assert [(case["id"], case["porta"]) for case in verdict["casi"]] == [
        ("sensor.sensore_d_spento", "ricette")]
    assert verdict["casi"][0]["fatti"]["disabled_by"] == "user"
    assert verdict["chieste"]["digesto"] == 12


def test_la_fonte_vede_la_verifica_che_nega_un_entita_disabilitata():
    """Il trovato 2 del piano (S-27): l'anagrafe conosce l'entita', la
    verifica del comando dice che non esiste."""
    outcome = sonda_parita.source(sonda_parita.build_inputs(
        _with_universal_domain(synthetic_inputs()), clock=CLOCK))
    denied = [case for case in outcome["casi"] if case["porta"] == "verification"]
    assert [case["id"] for case in denied] == ["sensor.sensore_d_spento"]
    assert outcome["non_interrogabili_dalla_verifica"] == 0


def test_la_fonte_vede_il_digesto_che_tiene_dentro_un_entita_sparita():
    inputs = synthetic_inputs()
    inputs["states"] = [row for row in inputs["states"]
                        if row["entity_id"] != "light.luce_uno"]
    outcome = sonda_parita.source(sonda_parita.build_inputs(inputs, clock=CLOCK))
    assert [(case["id"], case["porta"]) for case in outcome["casi"]
            if case["porta"] == "digesto"] == [("light.luce_uno", "digesto")]


def test_la_fonte_vede_il_motivo_falso_su_un_sensore_che_dichiara_lo_state_class():
    """Fuori da `statistic_ids` ma con `state_class: measurement`: «le tiene
    solo per le entita' che dichiarano uno `state_class`» e' falso."""
    inputs = synthetic_inputs()
    inputs["statistic_ids"].remove("sensor.sensore_b_segnale")
    outcome = sonda_parita.source(sonda_parita.build_inputs(inputs, clock=CLOCK))
    assert "sensor.sensore_b_segnale" in {case["id"] for case in outcome["casi"]
                                          if case["porta"] == "ricette"}


def test_la_fonte_senza_servizi_non_finge_di_aver_chiesto():
    inputs = synthetic_inputs()
    del inputs["services"]
    outcome = sonda_parita.run(sonda_parita.build_inputs(inputs, clock=CLOCK))
    assert outcome["fonte"]["disaccordi"] is None
    assert "servizi" in outcome["fonte"]["errore"]
