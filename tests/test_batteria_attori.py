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
  una causa per riga) [la prova dei soggetti e' stata riscritta col Task 1.5:
  la riga porta `fonte`, non `causa`; le sue mutazioni sono sotto];
- `misure_ferme` sempre 0 -- rossa (0 invece di 1);
- i soggetti vivi contati fra i morti -- rossa (`soggetti_morti`: 4 invece di 3);
- le misure calcolate contate fra i rifiuti -- rossa (`sparita`: 3 invece di 2);
- una causa vuota tenuta come causa -- rossa (`""` accanto a «senza causa»).

Marcati e non marcati (Task 1.5, passo 4), mutazione ESEGUITA il 05/10/2026:
`soggetti_morti_marcati` sempre 0 -- rossa (0 invece di 3).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import batteria_attori

from hiris.app import steering
from hiris.app.mind import analyst

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


def _source(state):
    """La `fonte` di una riga di `GET /api/mind/watching`: la forma di
    `House.source` (Tappa 3, Task 8), ridotta a cio' che la batteria legge."""
    return {"stato": state, "causa": None}


def test_i_soggetti_morti_si_contano_marcati_e_non_marcati_e_per_stato_della_fonte():
    """Task 1.5, passo 4: «soggetti morti» diventa «marcati / non marcati».
    Marcato e' chi porta la `fonte` (anche `None`: nessuno lo conosce)."""
    watching = [{"soggetto": "sensor.vivo", "fonte": _source("viva")},
                {"soggetto": "sensor.sparito"},
                {"soggetto": "sensor.spento", "fonte": _source("spenta_dal_proprietario")},
                {"soggetto": "sensor.altro_spento",
                 "fonte": _source("spenta_dal_proprietario")},
                {"soggetto": "sensor.rimosso", "fonte": None},
                {"soggetto": "log:qualcosa"}]
    result = _measure(watching=watching, live_ids={"sensor.vivo"})
    assert result["soggetti_morti"] == 4
    assert result["soggetti_morti_marcati"] == 3
    assert result["soggetti_morti_non_marcati"] == 1
    # Il vivo marcato non e' morto: non entra nel conto per causa.
    assert result["soggetti_morti_per_causa"] == {
        batteria_attori.UNCAUSED: 1, "spenta_dal_proprietario": 2,
        batteria_attori.NOT_IN_HA: 1}


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


def test_le_misure_ferme_si_contano_con_la_causa_del_prodotto():
    """La batteria conta «ferme» le misure che il PRODOTTO rifiuta per dato
    fermo: la parola si chiede al vocabolario delle cause, non si ricopia.

    Mutazione ESEGUITA il 06/10/2026: in `mind/operations.py`,
    `FROZEN = "ferma"` -> `FROZEN = "dato_fermo"`, con la copia di prima
    (`FROZEN = "ferma"` scritta nella batteria) -> rossa, 0 misure ferme;
    con la batteria che la importa -> verde senza toccare la prova.
    """
    from hiris.app.mind.operations import FROZEN

    reports = [{"giorno": "2026-09-30", "misure": [
        {"non_calcolabile": "ferma dalle 00:00", "causa": FROZEN}]}]
    assert _measure(reports=reports)["misure_ferme"] == 1


def test_le_etichette_della_batteria_non_sono_cause_del_prodotto():
    """«senza causa» e l'etichetta di chi Home Assistant non conosce sono della
    batteria: se il vocabolario del prodotto ne adottasse una, la batteria
    conterebbe come «senza causa» rifiuti che una causa ce l'hanno."""
    from hiris.app.mind.operations import CAUSES

    assert batteria_attori.UNCAUSED not in CAUSES
    assert batteria_attori.NOT_IN_HA not in CAUSES


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


# --- L'analista (piano degli attori, strati 3-4, Task 3.8) ------------------
#
# Mutazioni ESEGUITE il 06/10/2026 (la regola di prima col giro 49), ognuna
# rossa per la ragione giusta e col ripristino verificato (`git status`):
# - `osservazioni_con_letture` contate su tutte le analisi, con o senza
#   `letture` -- rossa (3 invece di 2);
# - la novita' decisa dalla sola impronta, senza la prova -- rossa (la prova
#   cambiata contata «stessa prova»: 4 invece di 2);
# - la memoria presa da TUTTE le analisi, non dalle precedenti -- rossa (nessuna
#   «nuova»);
# - la forma del rifiuto senza coprire i numeri -- rossa (due forme invece di
#   una);
# - i tetti propri ignorati -- rossa (`tetto` 4096 invece di 8000);
# - la regola di prima col tetto di oggi invece che con quello di fabbrica
#   (G49-1, giro 49) -- rossa (`troncati`: 2 invece di 3);
# - un rifiutato contato fra i falliti -- rossa (`falliti`: 3 invece di 0).
# Mutazione ESEGUITA sulla fonte: `steering.ANALYST_SPECIES = "analista_x"` --
# le prove qui sotto restano verdi senza toccarle, perche' il nome si chiede.

ANALYST = steering.ANALYST_SPECIES


def _observation(soggetto, *, base=10, scarti=2.0, novita=None):
    out = {"soggetto": soggetto, "misura": "consumo", "chiave": "kwh",
           "innesco": 1, "cosa": "sale", "base": base, "quanti_scarti": scarti,
           "spiegato": None}
    if novita is not None:
        out["novita"] = novita
    return out


def _analysis(day, observations, readings=None):
    out = {"giorno": day, "osservazioni": observations}
    if readings is not None:
        out["letture"] = readings
    return out


def test_le_specie_si_chiedono_al_registro_e_la_derivazione_non_e_vuota():
    assert ANALYST in steering.SPECIE
    assert len(steering.SPECIE) >= 2
    data = [(_turn("attuatore", 100), [_load(10)]),
            (_turn(ANALYST, 100), [_load(10)])]
    assert _measure(data=data)["specie_fuori_registro"] == ["attuatore"]


def test_le_osservazioni_con_letture_sono_quelle_delle_analisi_che_ne_portano():
    readings = [{"tool": "history", "input": {"id": "sensor.a"}},
                {"tool": "history", "input": {"id": "sensor.b"}},
                {"tool": "search", "input": {"q": "x"}}]
    analyses = [
        _analysis("2026-10-01", [_observation("vecchio")], readings),
        _analysis("2026-10-05", [_observation("a"), _observation("b")], readings),
        _analysis("2026-10-06", [_observation("c")]),
    ]
    result = _measure(analyses=analyses, since_day="2026-10-05")["analista"]
    assert result["analisi"] == 2
    assert result["osservazioni"] == 3
    assert result["osservazioni_con_letture"] == 2
    assert result["analisi_con_letture"] == 1
    # Per nome, senza gli ingressi: un ingresso puo' portare un dato della casa.
    assert result["letture_per_strumento"] == {"history": 2, "search": 1}


def test_le_ripetizioni_si_giudicano_con_la_regola_del_prodotto_sulla_memoria_precedente():
    analyses = [
        # Fuori finestra, ma memoria: ci sono gia' «a» e «b».
        _analysis("2026-10-03", [_observation("a"), _observation("b")]),
        _analysis("2026-10-04", [
            _observation("a"),                    # stessa prova
            _observation("b", base=11),           # prova cambiata
            _observation("c", novita="nuova")]),  # nuova
        _analysis("2026-10-05", [
            _observation("c"),                    # stessa prova di ieri
            _observation("b", base=11, scarti=3.0)]),  # prova cambiata ancora
    ]
    result = _measure(analyses=analyses, since_day="2026-10-04")["analista"]
    assert result["osservazioni_per_novita"] == {
        batteria_attori.SAME_EVIDENCE: 2, analyst.NOVELTY[1]: 2,
        analyst.NOVELTY[0]: 1}
    # Cio' che il prodotto ha scritto, accanto: le analisi di prima del D4 non
    # lo portano.
    assert result["novita_scritta_dal_prodotto"] == {
        "nuova": 1, batteria_attori.UNCAUSED: 4}


def test_l_etichetta_della_stessa_prova_non_e_una_parola_del_prodotto():
    assert batteria_attori.SAME_EVIDENCE not in analyst.NOVELTY


def test_le_risposte_rifiutate_si_contano_per_forma_del_motivo():
    trigger = ("l'osservazione {n} dice innesco «{w}», ma la misura [{q}] e' "
               "candidata a [1, 3]: gli inneschi li marca il codice")
    data = [
        (dict(_turn(ANALYST, 900, outcome=steering.REFUSED),
              problems=[trigger.format(n=1, w="2", q=4),
                        "l'osservazione 2 non dice COSA ha visto"]),
         [_load(30000)]),
        (dict(_turn(ANALYST, 900, outcome=steering.REFUSED),
              problems=[trigger.format(n=3, w="1.0", q=17)]), [_load(30000)]),
        (_turn(ANALYST, 900, outcome=steering.REFUSED), [_load(30000)]),
        # Non contano: un'altra specie, e un turno riuscito.
        (dict(_turn("ricette", 900, outcome=steering.REFUSED),
              problems=["altro"]), [_load(1000)]),
        (dict(_turn(ANALYST, 900), problems=["vecchio"]), [_load(30000)]),
    ]
    result = _measure(data=data)
    shape = ("l'osservazione N dice innesco «…», ma la misura […] e' "
             "candidata a […]: gli inneschi li marca il codice")
    assert result["analista"]["rifiuti_per_motivo"] == {
        shape: 2, "l'osservazione N non dice COSA ha visto": 1,
        batteria_attori.UNCAUSED: 1}
    row = result["attori"][ANALYST]
    assert row["rifiutati"] == 3
    # Un rifiutato ha risposto: non e' un fallito.
    assert row["falliti"] == 0


def test_l_analista_porta_il_suo_tetto_ma_la_regola_di_prima_usa_quello_di_allora():
    """Il troncato si legge dall'esito, col tetto che il turno ha dichiarato;
    la riga porta accanto il tetto del mestiere. I turni registrati prima
    dell'esito hanno girato col tetto di fabbrica, e la regola di prima usa
    quello: un `riuscito` lungo quanto il tetto di OGGI non e' troncato
    (G49-1)."""
    data = [(_turn(ANALYST, 8000), [_load(30000)]),
            (_turn(ANALYST, CEILING), [_load(30000)]),
            (_turn(ANALYST, CEILING), [_load(30000)]),
            (_turn(ANALYST, 300, outcome=steering.TRUNCATED), [_load(30000)])]
    row = _measure(data=data, ceilings={ANALYST: 8000})["attori"][ANALYST]
    assert row["troncati"] == 3
    assert row["tetto"] == 8000
    assert row["token_ingresso_per_giro"] == 30000


def test_i_token_per_giro_non_contano_i_giri_senza_token():
    observer = _measure()["attori"]["osservatore"]
    assert observer["token_ingresso_per_giro"] == round((8000 + 9000) / 2)


def test_la_batteria_intera_su_una_casa_finta(monkeypatch, capsys):
    """Dal comando all'uscita: le rotte che chiede, e i conti dell'analista
    nel JSON stampato. La casa e' finta: `casa.hiris_get` e `casa.ha_read`
    rispondono con le forme delle rotte vere."""
    import json as _json
    from datetime import datetime

    import casa

    today = datetime.now().astimezone().date().isoformat()
    turn = dict(_turn(ANALYST, 900), id="t1", ts=1.0)
    answers = {
        "/api/misure?giorni=1": {"turni": [turn], "carichi": {"t1": [_load(30000)]}},
        "/api/mind/watching": {"watching": [{"soggetto": "sensor.vivo"}]},
        "/api/mind/report": {"resoconti": []},
        "/api/mind/analysis": {"analisi": [_analysis(
            today, [_observation("a")], [{"tool": "history", "input": {}}])]},
    }
    asked = []

    def fake_get(path):
        asked.append(path)
        return _json.dumps(answers[path]).encode()

    async def fake_read(method, *args):
        assert method == "get_states"
        return [{"entity_id": "sensor.vivo"}]

    monkeypatch.setattr(casa, "hiris_get", fake_get)
    monkeypatch.setattr(casa, "ha_read", fake_read)
    monkeypatch.setattr(sys, "argv", ["batteria_attori.py", "--giorni", "1"])

    batteria_attori.main()

    assert sorted(asked) == sorted(answers)
    printed = _json.loads(capsys.readouterr().out)
    assert printed["attori"][ANALYST]["tetto"] == _analyst_ceiling()
    assert printed["analista"]["osservazioni_con_letture"] == 1
    assert printed["analista"]["osservazioni_per_novita"] == {analyst.NOVELTY[0]: 1}
    assert printed["soggetti_morti"] == 0


def _analyst_ceiling():
    from hiris.app.mind.analyst_turn import MAX_ANSWER_TOKENS

    return MAX_ANSWER_TOKENS
