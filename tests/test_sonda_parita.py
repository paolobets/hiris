"""La sonda fa girare le copie VERE delle regole e conta dove non concordano.

Le prove usano la casa sintetica (`tests/_casa_sintetica.py`), che ha i casi
messi apposta: tre entita' che ereditano l'area dal dispositivo, quattro che
la ricetta vede e l'osservatore no, i nomi vivi col prefisso del dispositivo.

Mutazione ESEGUITA: in `tests/_casa_sintetica.py` data l'area propria alle tre
entita' che la ereditano -- rossa (`dove`: 0 disaccordi, attesi 3).
Mutazione ESEGUITA: in `sonda_parita.excluded` tolto il confronto fra ricetta
e osservatore -- rossa (`fuori`: 0 disaccordi, attesi 4).
Mutazione ESEGUITA: in `sonda_parita._entity_ids` tolto il controllo sugli id
-- rossa (`dove` torna 0 disaccordi con un separatore sbagliato, invece di
dichiararsi non eseguita: era il rilievo I6 della revisione del 01/10/2026).
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


def test_la_sonda_vede_l_area_ereditata_che_l_osservatore_perde(result):
    lost = {case["id"] for case in result["dove"]["casi"]}
    assert lost == {"sensor.sensore_a_temperatura", "sensor.sensore_a_umidita",
                    "sensor.sensore_b_potenza"}
    assert all(case["area_emessa"] is None and case["area_vera"]
               for case in result["dove"]["casi"])


def test_la_sonda_vede_le_righe_che_la_ricetta_manda_e_l_osservatore_no(result):
    leaked = {case["id"] for case in result["fuori"]["casi"]
              if case["solo_in"] == "recipe_turn.device_lines"}
    assert leaked == {"sensor.sensore_b_segnale", "number.sensore_b_soglia",
                      "sensor.sensore_c_riserva", "sensor.sensore_d_spento"}


def test_la_sonda_vede_il_nome_col_prefisso_del_dispositivo(result):
    renamed = {case["id"]: case for case in result["nomi"]["casi"]}
    assert renamed["sensor.sensore_a_temperatura"]["scheda"] == "Temperatura"
    assert renamed["sensor.sensore_a_temperatura"]["riga"] == "Sensore A Temperatura"
    assert "light.luce_uno" not in renamed, "stesso nome dalle due porte: non e' un disaccordo"


def test_un_peggioramento_supera_l_atteso_e_un_miglioramento_no(result):
    expected = {name: verdict["disaccordi"] for name, verdict in result.items()}
    assert sonda_parita.worse_than_expected(result, expected) == []
    stricter = dict(expected, dove=expected["dove"] - 1)
    assert sonda_parita.worse_than_expected(result, stricter) == [
        f"dove: {expected['dove']} disaccordi, attesi al massimo {expected['dove'] - 1}"]
    looser = dict(expected, dove=expected["dove"] + 5)
    assert sonda_parita.worse_than_expected(result, looser) == []


def test_una_domanda_senza_atteso_ferma_il_cancello(result):
    expected = {name: verdict["disaccordi"] for name, verdict in result.items()}
    del expected["nomi"]
    assert sonda_parita.worse_than_expected(result, expected) == [
        "nomi: nessun atteso scritto"]


def test_una_domanda_che_solleva_non_ferma_le_altre_e_si_dichiara(monkeypatch):
    def broken(inputs):
        raise RuntimeError("copia sparita")

    monkeypatch.setitem(sonda_parita.QUESTIONS, "nomi", broken)
    monkeypatch.setitem(sonda_parita.QUESTIONS, "oggi", lambda inputs: {
        "disaccordi": 0, "casi": [], "chiamate": ["a", "b"]})
    outcome = sonda_parita.run(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))
    assert outcome["nomi"]["disaccordi"] is None
    assert "copia sparita" in outcome["nomi"]["errore"]
    assert outcome["dove"]["disaccordi"] == 3
    complaints = sonda_parita.worse_than_expected(outcome, {"nomi": 0})
    assert [line for line in complaints if line.startswith("nomi:")] == [
        "nomi: non eseguita (RuntimeError: copia sparita)"]


def test_il_valore_si_chiede_alla_copia_vera_del_nucleo(result):
    # `binary_sensor.porta_uno` e' `unavailable`: il nucleo lo legge come un
    # valore, il vocabolario no.
    assert [case["id"] for case in result["valore"]["casi"]] == ["binary_sensor.porta_uno"]


def test_una_riga_che_cambia_forma_ferma_la_domanda_invece_di_darle_ragione(monkeypatch):
    """Se le righe dell'osservatore non si spezzano piu' dove la sonda crede,
    gli id letti non sono id. Senza guardia `dove` darebbe ZERO disaccordi:
    «parita' raggiunta», e falso."""
    monkeypatch.setattr(sonda_parita, "LINE_SEPARATOR", " | ")
    outcome = sonda_parita.run(sonda_parita.build_inputs(synthetic_inputs(), clock=CLOCK))
    for question in ("dove", "fuori"):
        assert outcome[question]["disaccordi"] is None, outcome[question]
        assert "forma della riga" in outcome[question]["errore"]
    assert any(line.startswith("dove: non eseguita")
               for line in sonda_parita.worse_than_expected(outcome, {"dove": 3}))

