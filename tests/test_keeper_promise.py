"""La forma di una promessa: cosa può nascere, e come si legge da tutte le porte."""
import re
from pathlib import Path

from hiris.app.keeper.promise import (
    CEILING_IN_SOSPESO,
    CONSERVAZIONE_S,
    ORIZZONTE_S,
    STATES_CONCLUSI,
    STATES_SOSPESO,
    TOLLERANZA_S,
    delay_reason,
    serializza,
    validate,
)

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

ADESSO = 1_755_600_000.0  # un istante fisso: nessun test di questo file legge l'orologio


def _fai(**extra):
    data = {
        "specie": "fai",
        "frase": "alle 17 accendi lo studio",
        "quando_ts": ADESSO + 3600,
        "quando_detto": "alle 17",
        "fuso": "Europe/Rome",
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
    }
    data.update(extra)
    return data


def _chiedi(**extra):
    data = {
        "specie": "chiedi",
        "frase": "fra un'ora verifica la temperatura della camera",
        "quando_ts": ADESSO + 3600,
        "quando_detto": "fra un'ora",
        "fuso": "Europe/Rome",
        "domanda": "la temperatura della camera e' aumentata?",
    }
    data.update(extra)
    return data


def test_una_promessa_valida_non_ha_motivi():
    assert validate(_fai(), now=ADESSO) is None
    assert validate(_chiedi(), now=ADESSO) is None


def test_una_specie_inventata_e_un_rifiuto():
    reason = validate(_fai(specie="ricorda"), now=ADESSO)
    assert reason is not None
    assert "fai" in reason and "chiedi" in reason


def test_un_istante_passato_porta_la_domanda_dentro_il_rifiuto():
    reason = validate(_fai(quando_ts=ADESSO - 60), now=ADESSO)
    assert reason is not None
    # Non basta rifiutare: il rifiuto deve dire cosa fare (spec §9.1.5).
    assert "passat" in reason.lower()
    assert "domani" in reason.lower()


def test_oltre_l_orizzonte_il_rifiuto_nomina_il_tetto():
    reason = validate(_fai(quando_ts=ADESSO + ORIZZONTE_S + 1), now=ADESSO)
    assert reason is not None
    assert "30 giorni" in reason


def test_un_fai_senza_chiamata_non_nasce():
    data = _fai()
    del data["chiamata"]
    assert validate(data, now=ADESSO) is not None


def test_un_chiedi_senza_domanda_non_nasce():
    data = _chiedi()
    del data["domanda"]
    assert validate(data, now=ADESSO) is not None


def test_una_frase_vuota_non_nasce():
    # `frase` e' cio' che rende la promessa leggibile da sola (fondamenta n.1).
    assert validate(_fai(frase="   "), now=ADESSO) is not None


def test_serializza_ha_sempre_le_stesse_chiavi_per_entrambe_le_specie():
    row_fai = {
        "id": "p1", "specie": "fai", "frase": "x", "quando_ts": 1.0,
        "quando_detto": "alle 17", "fuso": "Europe/Rome",
        "chiamata_json": '{"servizio": "light.turn_on"}', "domanda": None,
        "istantanea_json": None, "recapito": None, "stato": "in_attesa",
        "motivo": None, "esecuzione_id": None, "testo": None, "avvisare": None,
        "nata_ts": 0.5, "risvegliata_ts": None,
    }
    row_chiedi = dict(row_fai, id="p2", specie="chiedi", chiamata_json=None,
                       domanda="fa caldo?", istantanea_json='[{"entita": "sensor.t"}]')
    assert set(serializza(row_fai)) == set(serializza(row_chiedi))


def test_serializza_decodifica_il_json_e_non_lo_lascia_stringa():
    row = {
        "id": "p1", "specie": "fai", "frase": "x", "quando_ts": 1.0,
        "quando_detto": None, "fuso": None,
        "chiamata_json": '{"servizio": "light.turn_on"}', "domanda": None,
        "istantanea_json": None, "recapito": None, "stato": "in_attesa",
        "motivo": None, "esecuzione_id": None, "testo": None, "avvisare": None,
        "nata_ts": 0.5, "risvegliata_ts": None,
    }
    fuori = serializza(row)
    assert fuori["chiamata"] == {"servizio": "light.turn_on"}
    assert "chiamata_json" not in fuori


def test_il_motivo_del_ritardo_dice_i_minuti_misurati():
    phrase = delay_reason(41 * 60)
    assert "41" in phrase
    assert "non eseguita" in phrase


def test_le_costanti_sono_quelle_dichiarate_nella_spec():
    assert (TOLLERANZA_S, ORIZZONTE_S, CEILING_IN_SOSPESO, CONSERVAZIONE_S) == (
        120, 30 * 86400, 50, 90 * 86400)


# ---------------------------------------------------------------------------
# PENDING_STATES (JS, era STATI_SOSPESO) / STATI_CONCLUSI: lo stesso insieme di
# STATES_SOSPESO / STATES_CONCLUSI (Python) e nel
# JavaScript della pagina (review finale, rilievo ②). Il vocabolario di
# `agenda-route.js` esiste PRIMA di questo test -- qui non e' un doppione
# costruito apposta, e' quello LEGATO da una prova (`scripts/doppioni.py`,
# `_costanti_gia_legate`): la divergenza smette di essere silenziosa perche'
# questo test la vede.
#
# Un test gemello, dal lato JavaScript, vive in
# `tests/js/agenda-route-vocabulary.test.mjs` (stesso confronto, letto
# nell'altro verso): questo qui chiude specificamente il rilevatore
# meccanico del progetto, che sa leggere solo prove Python che nominano la
# costante e leggono un `.js`.
# ---------------------------------------------------------------------------

def _promesse_route_js() -> str:
    return (BASE / "config" / "agenda-route.js").read_text(encoding="utf-8")


def test_stati_sospeso_e_lo_stesso_insieme_nel_javascript_della_pagina():
    js = _promesse_route_js()
    # Il nome JS e' passato all'inglese il 02/09 (fetta del frontend); questo
    # test lega i due INSIEMI e non i due nomi, quindi sopravvive.
    m = re.search(r"var PENDING_STATES = \[([^\]]*)\];", js)
    assert m, "PENDING_STATES non trovata in agenda-route.js"
    dal_js = {s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()}
    assert dal_js == set(STATES_SOSPESO)


def test_ogni_stato_concluso_ha_una_voce_in_stato_label_e_stato_badge():
    js = _promesse_route_js()
    label = re.search(r"var STATE_LABEL = \{([\s\S]*?)\};", js)
    badge = re.search(r"var STATE_BADGE = \{([\s\S]*?)\};", js)
    assert label and badge, "STATE_LABEL / STATE_BADGE non trovati in agenda-route.js"
    chiavi_label = set(re.findall(r"(\w+):", label.group(1)))
    chiavi_badge = set(re.findall(r"(\w+):", badge.group(1)))
    for stato in STATES_CONCLUSI:
        assert stato in chiavi_label, f"STATE_LABEL non conosce «{stato}»"
        assert stato in chiavi_badge, f"STATE_BADGE non conosce «{stato}»"
