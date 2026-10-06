"""La memoria dell'analista, ricavata dagli archivi (D4 del piano degli
attori, 06/10/2026; Task 3.4).

**Il difetto** (voce D-33 del registro dei doppioni, spostata negli attori il
05/10/2026): l'analista diceva lo stesso tema ogni giorno, con parole diverse
-- coppie gia' presenti il giorno prima 2 su 7, 3 su 8, 4 su 8. Non aveva
nessuna memoria delle analisi precedenti.

**La cura scelta**: nessuna tabella nuova. La domanda porta le osservazioni
dei giorni della finestra, una per impronta (`observation_key`), con la prova
di allora (`evidence_of`) e l'esito della proposta che ne e' nata; il modello
dice «nuova» o «prova cambiata», e il codice rifiuta la stessa impronta con la
stessa prova.
"""
import json

import pytest

from hiris.app import server
from hiris.app.home_space import historian
from hiris.app.mind import actuator, analyst
from hiris.app.mind import analyst_turn as at
from hiris.app.mind.store import ObservationsStore


def _osservazione(**extra):
    base = {"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
            "chiave": None, "unita": "kWh", "innesco": 1,
            "cosa": "il prelievo e' salito", "spiegato": None,
            "cosa_cambierebbe": "meno spesa", "valore": 0.74, "copertura": 1.0,
            "quanti_scarti": 2.75, "mediana": 0.3, "base": 2}
    base.update(extra)
    return base


def _serie():
    return {"giorni": ["2026-09-12", "2026-09-13", "2026-09-14"], "obiettivi": [],
            "serie": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                       "chiave": None, "operazione": "somma_periodo", "unita": "kWh",
                       "valori": [0.3, 0.3, 0.74], "coperture": [1.0, 1.0, 1.0],
                       "perche": [],
                       "scostamento": {"ultimo": 0.74, "mediana": 0.3, "scarto": 0.16,
                                       "quanti_scarti": 2.75, "base": 2}}]}


def _risposta(**extra):
    riga = {"quale": 0, "innesco": 1, "cosa": "il prelievo e' salito",
            "spiegato": None, "cosa_cambierebbe": "meno spesa", "novita": "nuova"}
    riga.update(extra)
    return json.dumps({"osservazioni": [riga]})


def test_L_IMPRONTA_ha_una_casa_sola():
    """Fondamenta 2: l'impronta nasce nell'analista e l'attuatore la chiede."""
    assert actuator.observation_key is analyst.observation_key
    assert actuator.evidence_of is analyst.evidence_of


def test_la_memoria_e_UNA_VOCE_per_impronta_con_i_giorni_e_l_ESITO():
    """Due analisi archiviate con la stessa impronta fanno una voce sola, coi
    due giorni; la proposta nata da quell'impronta porta il suo esito; oggi
    non e' memoria."""
    vecchia = _osservazione(base=1, cosa="prima volta")
    analisi = [
        {"giorno": "2026-09-13", "osservazioni": [vecchia]},
        {"giorno": "2026-09-14", "osservazioni": [_osservazione(base=2)]},
        {"giorno": "2026-09-15", "osservazioni": [_osservazione(misura="oggi")]},
    ]
    proposte = [{"impronta": analyst.observation_key(vecchia), "stato": "rifiutata",
                 "esito_nota": "lo so gia'"}]

    memoria = analyst.previous_observations(analisi, proposte, today="2026-09-15",
                                            series=_serie())

    assert len(memoria) == 1
    voce = memoria[0]
    assert voce["giorni"] == ["2026-09-14", "2026-09-13"]
    assert voce["cosa"] == "il prelievo e' salito"
    assert voce["prova"] == {"base": 2, "quanti_scarti": 2.75, "spiegato": None}
    assert voce["esito"] == {"stato": "rifiutata", "nota": "lo so gia'"}
    assert voce["quale"] == 0


def test_la_domanda_porta_la_MEMORIA():
    memoria = analyst.previous_observations(
        [{"giorno": "2026-09-13", "osservazioni": [_osservazione()]}], [],
        today="2026-09-14", series=_serie())

    domanda = at.build_question(_serie(), memoria)

    assert "gia' detto nei giorni scorsi" in domanda
    assert '"giorni": ["2026-09-13"]' in domanda
    assert "novita" in domanda


def test_una_NUOVA_su_un_impronta_gia_detta_con_la_STESSA_prova_si_rifiuta():
    memoria = analyst.previous_observations(
        [{"giorno": "2026-09-13", "osservazioni": [_osservazione()]}], [],
        today="2026-09-14")

    esito = at.apply_analysis(_serie(), _risposta(), previous=memoria)

    assert esito["analisi"] is None
    assert any("stessa prova" in p for p in esito["problemi"]), esito["problemi"]


def test_con_la_PROVA_CAMBIATA_si_ridice():
    """Mutazione ESEGUITA (06/10/2026): in `novelty_problem` confrontare la
    sola impronta, senza la prova -- rossa (`stessa prova` fra i problemi)."""
    memoria = analyst.previous_observations(
        [{"giorno": "2026-09-13", "osservazioni": [_osservazione(base=1)]}], [],
        today="2026-09-14")

    esito = at.apply_analysis(_serie(), _risposta(novita="prova cambiata"),
                              previous=memoria)

    assert esito["problemi"] == []
    assert esito["analisi"]["osservazioni"][0]["novita"] == "prova cambiata"


def test_NOVITA_mancante_o_falsa_si_rifiuta():
    """Si rifiuta, non si corregge: come il numero scritto dal modello."""
    assert at.apply_analysis(_serie(), _risposta(novita=None))["analisi"] is None
    esito = at.apply_analysis(_serie(), _risposta(novita="prova cambiata"))
    assert any("mai stata detta" in p for p in esito["problemi"])


class _ModelloCheRipete:
    def __init__(self):
        self.domande = []

    async def chat(self, **kwargs):
        self.domande.append(kwargs["user_message"])
        return json.dumps({"osservazioni": [
            {"quale": 0, "innesco": 1, "cosa": "di nuovo il prelievo",
             "spiegato": None, "cosa_cambierebbe": "y", "novita": "nuova"}]})


def _resoconto(giorno):
    return {"giorno": giorno, "obiettivo": None,
            "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "operazione": "somma_periodo", "valore": 1.0,
                        "unita": "kWh", "copertura": 1.0}],
            "forme": [], "cronaca": []}


@pytest.mark.asyncio
async def test_il_GIRO_legge_la_memoria_dagli_archivi_e_rifiuta_la_ripetizione(tmp_path):
    """Dal giro intero: due analisi archiviate di ieri e l'altro ieri, la
    stessa osservazione detta con la stessa prova, e oggi non si scrive.

    Mutazione ESEGUITA (06/10/2026): il giro della catena che non passa la
    memoria ad `apply_analysis` -- rossa (l'analisi di oggi si scrive)."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        for giorno in ("2026-09-15", "2026-09-16", "2026-09-17"):
            store.replace_report(giorno, _resoconto(giorno))
        detta = _osservazione(base=2, quanti_scarti=None)
        store.replace_analysis("2026-09-16", {"osservazioni": [detta]})
        store.replace_analysis("2026-09-17", {"osservazioni": []})
        store.add_proposal(text="t", perche="p",
                           fingerprint=analyst.observation_key(detta),
                           prova=analyst.evidence_of(detta), chi_applica="tu",
                           now_ts=1.0)
        modello = _ModelloCheRipete()
        app = {"observations": store, "llm_router": modello, "bridge_active": False}

        await server.analyst_round(app)

        assert len(modello.domande) == 1
        assert '"giorni": ["2026-09-16"]' in modello.domande[0]
        assert '"stato": "attesa"' in modello.domande[0]
        oggi = historian.today(historian.house_timezone(None)).isoformat()
        assert store.analysis(oggi) is None
    finally:
        store.close()
