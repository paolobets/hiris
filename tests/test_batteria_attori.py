"""I numeri degli attori si calcolano da cio' che HIRIS ha registrato.

La batteria degli attori NON innesca nessun turno: legge i turni che gli
attori hanno fatto da soli (`GET /api/misure`), cio' che l'osservatore guarda
(`GET /api/mind/watching`) e i resoconti (`GET /api/mind/report`). I nomi dei
campi qui sotto sono quelli che le rotte restituiscono, letti dalla casa il
01/10/2026.

Mutazione ESEGUITA: in `measure` contato come troncato ogni turno con
`output_tokens > 0` -- rossa (`troncati`: 2 invece di 1).
Mutazione ESEGUITA: in `measure` contati morti solo i soggetti senza punto nel
nome -- rossa (`soggetti_morti`: 0 invece di 1).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import batteria_attori

CEILING = 4096


def _turn(species, output_tokens, *, duration_ms=1000, outcome="riuscito", iterations=1):
    return {"species": species, "channel": "catena", "output_tokens": output_tokens,
            "duration_ms": duration_ms, "outcome": outcome, "iterations": iterations}


def _load(input_tokens, cached=0):
    return {"input_tokens": input_tokens, "cache_read_tokens": cached,
            "cache_write_tokens": 0}


DATA = [
    (_turn("analista", 4096, duration_ms=41000), [_load(36000)]),
    (_turn("analista", 900, duration_ms=12000), [_load(30000, cached=5000)]),
    (_turn("osservatore", 21096, duration_ms=90000, iterations=2),
     [_load(8000), _load(9000)]),
    (_turn("osservatore", 500, outcome="fallito"), [_load(None)]),
]


def _measure(**changes):
    arguments = {"data": DATA, "watching": [], "reports": [], "live_ids": set(),
                 "output_ceiling": CEILING}
    return batteria_attori.measure(**{**arguments, **changes})


def test_un_turno_fermato_dal_tetto_e_contato_troncato():
    analyst = _measure()["attori"]["analista"]
    assert analyst["turni"] == 2
    assert analyst["troncati"] == 1
    assert analyst["token_ingresso"] == 36000 + 30000 + 5000
    assert analyst["token_uscita"] == 4096 + 900
    assert analyst["secondi_mediani"] == 26.5


def test_il_tetto_vale_per_chi_non_ne_dichiara_un_altro():
    # L'osservatore scrive 21.096 token: il suo tetto e' un altro, e superare
    # QUESTO tetto non e' una troncatura. Vale solo l'uguaglianza esatta.
    observer = _measure()["attori"]["osservatore"]
    assert observer["troncati"] == 0
    assert observer["falliti"] == 1
    assert observer["giri"] == 3
    assert observer["giri_senza_token"] == 1


def test_un_soggetto_guardato_che_non_ha_piu_uno_stato_e_contato_morto():
    watching = [{"soggetto": "sensor.vivo"}, {"soggetto": "sensor.sparito"},
                {"soggetto": "log:qualcosa"}, {"soggetto": "integrazione:marca"}]
    result = _measure(watching=watching, live_ids={"sensor.vivo"})
    assert result["soggetti_guardati"] == 4
    assert result["soggetti_entita"] == 2
    assert result["soggetti_morti"] == 1


def test_le_misure_non_calcolabili_si_contano_sul_giorno_piu_recente_e_su_tutti():
    reports = [
        {"giorno": "2026-09-29", "misure": [{"non_calcolabile": "x"}, {"non_calcolabile": None}]},
        {"giorno": "2026-09-30", "misure": [{"non_calcolabile": "x"}, {"non_calcolabile": "y"},
                                            {"non_calcolabile": None}]},
    ]
    result = _measure(reports=reports)
    assert result["resoconti"] == 2
    assert result["misure_totali"] == 5 and result["misure_non_calcolabili"] == 3
    assert result["ultimo_giorno"] == {"giorno": "2026-09-30", "misure": 3,
                                       "non_calcolabili": 2}


def test_senza_turni_la_batteria_lo_dice_invece_di_dare_zeri():
    result = _measure(data=[])
    assert result["attori"] == {}
    assert result["turni_letti"] == 0
