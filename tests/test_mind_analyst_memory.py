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
from hiris.app.mind import analyst
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
                       # L'ultima copertura scende: la riga e' candidata agli
                       # inneschi 1 e 3 (`analyst.trigger_facts`).
                       "valori": [0.3, 0.3, 0.74], "coperture": [1.0, 1.0, 0.5],
                       "perche": [],
                       "scostamento": {"ultimo": 0.74, "mediana": 0.3, "scarto": 0.16,
                                       "quanti_scarti": 2.75, "base": 2}}]}


def _riga(**extra):
    riga = {"quale": 0, "innesco": 1, "cosa": "il prelievo e' salito",
            "spiegato": None, "cosa_cambierebbe": "meno spesa"}
    riga.update(extra)
    return riga


def _risposta(*righe):
    return json.dumps({"osservazioni": list(righe) or [_riga()]})


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
    assert "novita" not in domanda, "lo scrive il codice, non il modello"


def test_la_RIPETIZIONE_con_la_stessa_prova_si_TOGLIE_e_le_altre_restano():
    """G12-2 del revisore (giro 12, 06/10/2026), eseguito: rifiutare l'analisi
    intera per una ripetizione perdeva le altre osservazioni del giorno, e la
    domanda dopo era identica -- su una misura che non varia mai, fino a
    ventiquattro turni a vuoto. Si toglie solo lei, come `to_handle`.

    Mutazione ESEGUITA (06/10/2026): `novelty` che torna «nuova» anche con la
    stessa prova -- rossa (la ripetizione resta nell'analisi)."""
    memoria = analyst.previous_observations(
        [{"giorno": "2026-09-13", "osservazioni": [_osservazione()]}], [],
        today="2026-09-14")

    esito = at.apply_analysis(_serie(), _risposta(_riga(), _riga(innesco=3)),
                              previous=memoria)

    assert esito["problemi"] == []
    rimaste = esito["analisi"]["osservazioni"]
    assert [o["innesco"] for o in rimaste] == [3]
    assert rimaste[0]["novita"] == "nuova"
    assert esito["ripetute"] == [analyst.observation_key(_osservazione())]


def test_con_la_PROVA_CAMBIATA_si_ridice_e_lo_scrive_il_CODICE():
    """Mutazione ESEGUITA (06/10/2026): in `novelty` confrontare la sola
    impronta, senza la prova -- rossa (l'osservazione sparisce)."""
    memoria = analyst.previous_observations(
        [{"giorno": "2026-09-13", "osservazioni": [_osservazione(base=1)]}], [],
        today="2026-09-14")

    esito = at.apply_analysis(_serie(), _risposta(_riga(novita="nuova")),
                              previous=memoria)

    assert esito["problemi"] == []
    assert esito["analisi"]["osservazioni"][0]["novita"] == "prova cambiata"


def test_senza_memoria_ogni_osservazione_e_NUOVA():
    esito = at.apply_analysis(_serie(), _risposta())
    assert esito["analisi"]["osservazioni"][0]["novita"] == "nuova"


class _ModelloCheRipete:
    def __init__(self):
        self.domande = []

    async def chat(self, **kwargs):
        self.domande.append(kwargs["user_message"])
        return json.dumps({"osservazioni": [
            {"quale": 0, "cosa": "di nuovo il prelievo", "spiegato": None}]})


def _resoconto(giorno, copertura=1.0):
    return {"giorno": giorno, "obiettivo": None,
            "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "operazione": "somma_periodo", "valore": 1.0,
                        "unita": "kWh", "copertura": copertura}],
            "forme": [], "cronaca": []}


@pytest.mark.asyncio
async def test_il_GIRO_legge_la_memoria_dagli_archivi_e_toglie_la_ripetizione(tmp_path):
    """Dal giro intero: due analisi archiviate, la stessa osservazione detta
    con la stessa prova. L'analisi di oggi si scrive -- il giro non richiede
    ogni ora -- e la ripetizione non c'e'.

    Mutazione ESEGUITA (06/10/2026): il giro della catena che non passa la
    memoria ad `apply_analysis` -- rossa (la ripetizione si scrive)."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        # La copertura scende l'ultimo giorno: un solo innesco, il 3, che il
        # codice attacca senza che il modello lo scriva.
        for giorno, copertura in (("2026-09-15", 1.0), ("2026-09-16", 1.0),
                                  ("2026-09-17", 0.5)):
            store.replace_report(giorno, _resoconto(giorno, copertura))
        detta = _osservazione(base=2, quanti_scarti=None, innesco=3)
        store.replace_analysis("2026-09-16", {"osservazioni": [detta]})
        store.replace_analysis("2026-09-17", {"osservazioni": []})
        # L'esito di una proposta nella memoria lo prova
        # `test_la_memoria_e_UNA_VOCE_per_impronta_con_i_giorni_e_l_ESITO`, sui
        # dizionari di `proposals()`: la firma di `add_proposal` cambia con lo
        # strato 4 (`stakes`), e questa prova non deve legarsi a lei.
        modello = _ModelloCheRipete()
        app = {"observations": store, "llm_router": modello, "bridge_active": False}

        await server.analyst_round(app)

        assert len(modello.domande) == 1
        assert '"giorni": ["2026-09-16"]' in modello.domande[0]
        oggi = historian.today(historian.house_timezone(None)).isoformat()
        assert store.analysis(oggi)["osservazioni"] == []
    finally:
        store.close()
