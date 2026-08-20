"""La forma di una promessa: cosa può nascere, e come si legge da tutte le porte."""
import re
from pathlib import Path

from hiris.app.schedulatore.promessa import (
    CONSERVAZIONE_S, ORIZZONTE_S, STATI_CONCLUSI, STATI_SOSPESO,
    TETTO_IN_SOSPESO, TOLLERANZA_S, motivo_ritardo, serializza, valida,
)

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

ADESSO = 1_755_600_000.0  # un istante fisso: nessun test di questo file legge l'orologio


def _fai(**extra):
    dati = {
        "specie": "fai",
        "frase": "alle 17 accendi lo studio",
        "quando_ts": ADESSO + 3600,
        "quando_detto": "alle 17",
        "fuso": "Europe/Rome",
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
    }
    dati.update(extra)
    return dati


def _chiedi(**extra):
    dati = {
        "specie": "chiedi",
        "frase": "fra un'ora verifica la temperatura della camera",
        "quando_ts": ADESSO + 3600,
        "quando_detto": "fra un'ora",
        "fuso": "Europe/Rome",
        "domanda": "la temperatura della camera e' aumentata?",
    }
    dati.update(extra)
    return dati


def test_una_promessa_valida_non_ha_motivi():
    assert valida(_fai(), adesso=ADESSO) is None
    assert valida(_chiedi(), adesso=ADESSO) is None


def test_una_specie_inventata_e_un_rifiuto():
    motivo = valida(_fai(specie="ricorda"), adesso=ADESSO)
    assert motivo is not None
    assert "fai" in motivo and "chiedi" in motivo


def test_un_istante_passato_porta_la_domanda_dentro_il_rifiuto():
    motivo = valida(_fai(quando_ts=ADESSO - 60), adesso=ADESSO)
    assert motivo is not None
    # Non basta rifiutare: il rifiuto deve dire cosa fare (spec §9.1.4).
    assert "passat" in motivo.lower()
    assert "domani" in motivo.lower()


def test_oltre_l_orizzonte_il_rifiuto_nomina_il_tetto():
    motivo = valida(_fai(quando_ts=ADESSO + ORIZZONTE_S + 1), adesso=ADESSO)
    assert motivo is not None
    assert "30 giorni" in motivo


def test_un_fai_senza_chiamata_non_nasce():
    dati = _fai()
    del dati["chiamata"]
    assert valida(dati, adesso=ADESSO) is not None


def test_un_chiedi_senza_domanda_non_nasce():
    dati = _chiedi()
    del dati["domanda"]
    assert valida(dati, adesso=ADESSO) is not None


def test_una_frase_vuota_non_nasce():
    # `frase` e' cio' che rende la promessa leggibile da sola (fondamenta n.1).
    assert valida(_fai(frase="   "), adesso=ADESSO) is not None


def test_serializza_ha_sempre_le_stesse_chiavi_per_entrambe_le_specie():
    riga_fai = {
        "id": "p1", "specie": "fai", "frase": "x", "quando_ts": 1.0,
        "quando_detto": "alle 17", "fuso": "Europe/Rome",
        "chiamata_json": '{"servizio": "light.turn_on"}', "domanda": None,
        "istantanea_json": None, "recapito": None, "stato": "in_attesa",
        "motivo": None, "esecuzione_id": None, "testo": None, "avvisare": None,
        "nata_ts": 0.5, "risvegliata_ts": None,
    }
    riga_chiedi = dict(riga_fai, id="p2", specie="chiedi", chiamata_json=None,
                       domanda="fa caldo?", istantanea_json='[{"entita": "sensor.t"}]')
    assert set(serializza(riga_fai)) == set(serializza(riga_chiedi))


def test_serializza_decodifica_il_json_e_non_lo_lascia_stringa():
    riga = {
        "id": "p1", "specie": "fai", "frase": "x", "quando_ts": 1.0,
        "quando_detto": None, "fuso": None,
        "chiamata_json": '{"servizio": "light.turn_on"}', "domanda": None,
        "istantanea_json": None, "recapito": None, "stato": "in_attesa",
        "motivo": None, "esecuzione_id": None, "testo": None, "avvisare": None,
        "nata_ts": 0.5, "risvegliata_ts": None,
    }
    fuori = serializza(riga)
    assert fuori["chiamata"] == {"servizio": "light.turn_on"}
    assert "chiamata_json" not in fuori


def test_il_motivo_del_ritardo_dice_i_minuti_misurati():
    frase = motivo_ritardo(41 * 60)
    assert "41" in frase
    assert "non eseguita" in frase


def test_le_costanti_sono_quelle_dichiarate_nella_spec():
    assert (TOLLERANZA_S, ORIZZONTE_S, TETTO_IN_SOSPESO, CONSERVAZIONE_S) == (
        120, 30 * 86400, 50, 90 * 86400)


# ---------------------------------------------------------------------------
# STATI_SOSPESO / STATI_CONCLUSI: lo stesso insieme in Python e nel
# JavaScript della pagina (review finale, rilievo ②). Il vocabolario di
# `promesse-route.js` esiste PRIMA di questo test -- qui non e' un doppione
# costruito apposta, e' quello LEGATO da una prova (`scripts/doppioni.py`,
# `_costanti_gia_legate`): la divergenza smette di essere silenziosa perche'
# questo test la vede.
#
# Un test gemello, dal lato JavaScript, vive in
# `tests/js/promesse-route-vocabolario.test.mjs` (stesso confronto, letto
# nell'altro verso): questo qui chiude specificamente il rilevatore
# meccanico del progetto, che sa leggere solo prove Python che nominano la
# costante e leggono un `.js`.
# ---------------------------------------------------------------------------

def _promesse_route_js() -> str:
    return (BASE / "config" / "promesse-route.js").read_text(encoding="utf-8")


def test_stati_sospeso_e_lo_stesso_insieme_nel_javascript_della_pagina():
    js = _promesse_route_js()
    m = re.search(r"var STATI_SOSPESO = \[([^\]]*)\];", js)
    assert m, "STATI_SOSPESO non trovata in promesse-route.js"
    dal_js = {s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()}
    assert dal_js == set(STATI_SOSPESO)


def test_ogni_stato_concluso_ha_una_voce_in_stato_label_e_stato_badge():
    js = _promesse_route_js()
    label = re.search(r"var STATO_LABEL = \{([\s\S]*?)\};", js)
    badge = re.search(r"var STATO_BADGE = \{([\s\S]*?)\};", js)
    assert label and badge, "STATO_LABEL / STATO_BADGE non trovati in promesse-route.js"
    chiavi_label = set(re.findall(r"(\w+):", label.group(1)))
    chiavi_badge = set(re.findall(r"(\w+):", badge.group(1)))
    for stato in STATI_CONCLUSI:
        assert stato in chiavi_label, "STATO_LABEL non conosce «%s»" % stato
        assert stato in chiavi_badge, "STATO_BADGE non conosce «%s»" % stato
