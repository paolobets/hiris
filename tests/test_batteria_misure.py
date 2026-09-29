"""La batteria: nessun nome della casa nel repo, e il riassunto contato bene."""
import importlib.util
import json
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "batteria_misure.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("batteria_misure", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_le_domande_vengono_da_FUORI(tmp_path):
    """Mutazione ESEGUITA: una lista DOMANDE scritta nello script -- rossa."""
    sorgente = SCRIPT.read_text(encoding="utf-8")
    assert "DOMANDE = [" not in sorgente
    f = tmp_path / "d.json"
    f.write_text(json.dumps([{"n": 1, "aspetto": "a", "domanda": "q",
                              "atteso": "x", "effetto": None,
                              "giudice": "hiris"}]), encoding="utf-8")
    assert _modulo().carica_domande(str(f))[0]["domanda"] == "q"


def test_un_file_di_domande_senza_criterio_si_rifiuta(tmp_path):
    """Il criterio si scrive PRIMA (spec §6): una domanda senza `atteso` non parte."""
    f = tmp_path / "d.json"
    f.write_text(json.dumps([{"n": 1, "aspetto": "a", "domanda": "q",
                              "effetto": None, "giudice": "hiris"}]),
                 encoding="utf-8")
    with pytest.raises(SystemExit):
        _modulo().carica_domande(str(f))


def test_il_riassunto_conta_giudizi_e_tempi_solo_sui_riusciti():
    """Mutazione ESEGUITA: mediana anche sugli scaduti -- rossa."""
    esiti = [{"stato": "ok", "secondi": 10, "giudizio": "giusta"},
             {"stato": "ok", "secondi": 20, "giudizio": "incompleta"},
             {"stato": "ok", "secondi": 30, "giudizio": None},
             {"stato": "scaduto", "secondi": 900, "giudizio": None}]
    r = _modulo().riassunto(esiti)
    assert r["riusciti"] == 3 and r["mediana_s"] == 20
    assert r["giudizi"] == {"giusta": 1, "incompleta": 1, "sbagliata": 0,
                            "da_giudicare": 1}


def test_senza_conferme_le_domande_con_effetto_non_partono():
    """Senza nessuno alla tastiera, una promessa, un ricordo o una luce
    accesa non si fanno: quelle domande restano al proprietario.

    Mutazione ESEGUITA: `domande_ammesse` che restituisce tutto -- rossa."""
    domande = [{"n": 1, "effetto": None}, {"n": 21, "effetto": "promessa"},
               {"n": 27, "effetto": "azione"}]
    m = _modulo()
    assert [d["n"] for d in m.domande_ammesse(domande, conferme=False)] == [1]
    assert len(m.domande_ammesse(domande, conferme=True)) == 3
