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

Le cause (Task 1.7, passo 1), mutazioni ESEGUITE il 03/10/2026, tutte rosse
per la ragione giusta:
- `_by_cause` che ignora `causa` -- rossa (`{"senza causa": 3}` invece di
  una causa per riga);
- `misure_ferme` sempre 0 -- rossa (0 invece di 1);
- i soggetti vivi contati fra i morti -- rossa (`soggetti_morti`: 4 invece di 3);
- le misure calcolate contate fra i rifiuti -- rossa (`sparita`: 3 invece di 2);
- una causa vuota tenuta come causa -- rossa (`""` accanto a «senza causa»).
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


# --- Le cause (piano degli strati 1-2 degli attori, Task 1.7, passo 1) ------
#
# Il campo `causa` accanto alla frase nasce col Task 1.2 (misure) e col Task
# 1.5 (soggetti). Finche' non c'e', cio' che non ha una causa si conta sotto
# «senza causa»: e' il numero che lo strato 1 deve portare a zero.


def test_i_soggetti_morti_si_contano_per_causa_e_senza_causa_finche_manca():
    watching = [{"soggetto": "sensor.vivo", "causa": "spenta"},
                {"soggetto": "sensor.sparito"},
                {"soggetto": "sensor.spento", "causa": "spenta"},
                {"soggetto": "sensor.ricreato", "causa": "ricreata"},
                {"soggetto": "log:qualcosa"}]
    result = _measure(watching=watching, live_ids={"sensor.vivo"})
    assert result["soggetti_morti"] == 3
    # Il vivo con una causa non e' morto: non entra nel conto per causa.
    assert result["soggetti_morti_per_causa"] == {
        batteria_attori.UNCAUSED: 1, "spenta": 1, "ricreata": 1}


def test_le_misure_non_calcolabili_si_contano_per_causa():
    reports = [
        {"giorno": "2026-09-29", "misure": [
            {"non_calcolabile": "manca lo state_class"},
            {"non_calcolabile": "x", "causa": "sparita"},
            {"valore": 3, "causa": "sparita"}]},
        {"giorno": "2026-09-30", "misure": [
            {"non_calcolabile": "ferma dal 30/09 00:00", "causa": batteria_attori.FROZEN},
            {"non_calcolabile": "x", "causa": "sparita"},
            {"non_calcolabile": "x", "causa": ""}]},
    ]
    result = _measure(reports=reports)
    assert result["misure_non_calcolabili"] == 5
    # Una misura calcolata che porta una causa non e' un rifiuto; una causa
    # vuota e' come nessuna causa.
    assert result["misure_non_calcolabili_per_causa"] == {
        batteria_attori.UNCAUSED: 2, "sparita": 2, batteria_attori.FROZEN: 1}
    assert result["misure_ferme"] == 1


def test_oggi_senza_il_campo_tutto_e_senza_causa_e_niente_e_fermo():
    reports = [{"giorno": "2026-09-30", "misure": [{"non_calcolabile": "x"},
                                                   {"non_calcolabile": "y"}]}]
    result = _measure(reports=reports, watching=[{"soggetto": "sensor.sparito"}])
    assert result["misure_non_calcolabili_per_causa"] == {batteria_attori.UNCAUSED: 2}
    assert result["soggetti_morti_per_causa"] == {batteria_attori.UNCAUSED: 1}
    assert result["misure_ferme"] == 0


def test_senza_morti_ne_rifiuti_i_conti_per_causa_sono_vuoti():
    result = _measure()
    assert result["soggetti_morti_per_causa"] == {}
    assert result["misure_non_calcolabili_per_causa"] == {}
    assert result["misure_ferme"] == 0


def test_dal_registro_il_troncato_si_legge_dall_ESITO_col_tetto_proprio():
    """Tappa 6, Task 3 (D-58): il registro scrive `troncato`, e la batteria
    lo conta qualunque sia il tetto del mestiere -- l'osservatore ha 16.000
    token, non 4.096. Un troncato non e' un fallito.

    Mutazione ESEGUITA: contare solo l'uguaglianza col tetto di fabbrica --
    rossa (`troncati`: 0 invece di 1 per l'osservatore)."""
    data = [(_turn("osservatore", 16000, outcome=batteria_attori.TRUNCATED),
             [_load(8000)]),
            (_turn("osservatore", 900), [_load(8000)])]

    observer = _measure(data=data)["attori"]["osservatore"]

    assert observer["troncati"] == 1
    assert observer["falliti"] == 0
