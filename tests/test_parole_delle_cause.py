"""Le cause di una misura che non si calcola, anche a parole (Fase B dello
sprint «il giro snello», 28/10/2026).

La pagina del Brain raggruppa le misure non calcolate per `causa` e dice il
gruppo con `causa_parole`, che la rotta manda accanto alla causa: la pagina
non ne tiene una copia. Qui si prova che ogni causa del vocabolario ha le sue
parole (l'elenco si CHIEDE a `CAUSES`, non si ricopia) e che le parole
arrivano dalle due porte del cervello, la rotta e lo strumento.
"""
import json

import pytest

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.handlers_mind import handle_report
from hiris.app.mind.operations import CAUSE_WORDS, CAUSES, COVERAGE_LOW
from hiris.app.mind.store import OBSERVATIONS_KEY, ObservationsStore
from hiris.app.startup import live_values
from tests.test_mind_tool import _AMMINISTRATORE, DAY, _Richiesta


def test_ogni_causa_del_vocabolario_ha_le_sue_parole():
    """Mutazione ESEGUITA il 28/10/2026: una causa nuova aggiunta a
    `MEASURE_CAUSES` senza parole -- rossa qui, col nome della causa, senza
    toccare la prova. Ripristinata, `git status` pulito."""
    assert len(CAUSES) >= 10, "il vocabolario delle cause e' improvvisamente piccolo"
    senza = sorted(CAUSES - set(CAUSE_WORDS))
    assert not senza, f"cause senza parole per chi legge: {senza}"
    fuori = sorted(set(CAUSE_WORDS) - CAUSES)
    assert not fuori, f"parole per cause che il vocabolario non ha: {fuori}"


def test_le_parole_sono_per_chi_legge():
    """Niente apostrofo al posto dell'accento, niente parola di Home
    Assistant fra apici: le parole finiscono in testa a un gruppo della
    pagina, davanti al proprietario."""
    for causa, parole in CAUSE_WORDS.items():
        assert "e'" not in parole and "`" not in parole, (causa, parole)
        assert parole and parole == parole.strip(), (causa, parole)


def _app(tmp_path) -> dict:
    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    store.replace_report(DAY, {"giorno": DAY, "cronaca": [], "misure": [
        {"soggetto": "dev_a", "misura": "consumo", "valore": 3.2},
        {"soggetto": "dev_b", "misura": "consumo",
         "non_calcolabile": "troppi pochi dati", "causa": COVERAGE_LOW}]})
    return {**live_values(), OBSERVATIONS_KEY: store}


@pytest.mark.asyncio
async def test_la_causa_arriva_a_parole_dalla_rotta_e_dallo_strumento(tmp_path):
    """Mutazione ESEGUITA il 28/10/2026: `_cause_worded` tolto da
    `MindView.report` -- rossa (`KeyError: 'causa_parole'`). Ripristinata,
    `git status` pulito."""
    app = _app(tmp_path)
    rotta = json.loads((await handle_report(_Richiesta(app, {"day": DAY}))).body)
    dispatcher = create_tool_dispatcher(app, soffitto=_AMMINISTRATORE)
    strumento = await dispatcher.dispatch("mind", {"cosa": "resoconti", "giorno": DAY})
    for risposta in (rotta, strumento):
        calcolata, ignota = risposta["resoconto"]["misure"]
        assert ignota["causa_parole"] == CAUSE_WORDS[COVERAGE_LOW]
        assert "causa_parole" not in calcolata, "una misura calcolata non ha una causa"


@pytest.mark.asyncio
async def test_la_causa_arriva_a_parole_anche_dall_ELENCO_dei_giorni(tmp_path):
    """Senza `day` la rotta e lo strumento danno le misure degli ultimi
    giorni (`MindView.reports`): la stessa misura ha la stessa forma da
    tutte le porte (fondamenta 3).

    Mutazione ESEGUITA il 28/10/2026 (R218-3, P5): `_cause_worded` tolto da
    `MindView.reports` -- rossa (`KeyError: 'causa_parole'`). Ripristinata."""
    app = _app(tmp_path)
    rotta = json.loads((await handle_report(_Richiesta(app, {}))).body)
    dispatcher = create_tool_dispatcher(app, soffitto=_AMMINISTRATORE)
    strumento = await dispatcher.dispatch("mind", {"cosa": "resoconti"})
    for risposta in (rotta, strumento):
        calcolata, ignota = risposta["resoconti"][0]["misure"]
        assert ignota["causa_parole"] == CAUSE_WORDS[COVERAGE_LOW]
        assert "causa_parole" not in calcolata


def test_ogni_novita_ha_le_sue_parole():
    """`novita` e' un vocabolario chiuso (`analyst.NOVELTY`): ogni parola ne
    ha una per chi legge, chiesta al vocabolario."""
    from hiris.app.mind.analyst import NOVELTY, NOVELTY_WORDS
    assert set(NOVELTY_WORDS) == set(NOVELTY)


@pytest.mark.asyncio
async def test_la_novita_arriva_a_parole_solo_dove_c_e(tmp_path):
    """Mutazione ESEGUITA il 28/10/2026: `novita_parole` tolto da `_worded` --
    rossa (`KeyError`). Ripristinata, `git status` pulito."""
    from hiris.app.api.handlers_mind import handle_analysis
    from hiris.app.mind.analyst import NOVELTY, NOVELTY_WORDS

    store = ObservationsStore(str(tmp_path / "osservazioni.db"))
    store.replace_analysis(DAY, {"giorno": DAY, "osservazioni": [
        {"soggetto": "dev_a", "misura": "consumo", "innesco": 1, "novita": NOVELTY[1]},
        {"soggetto": "dev_b", "misura": "consumo", "innesco": 2}]})
    app = {**live_values(), OBSERVATIONS_KEY: store}
    risposta = json.loads((await handle_analysis(_Richiesta(app, {"day": DAY}))).body)
    detta, vecchia = risposta["analisi"]["osservazioni"]
    assert detta["novita_parole"] == NOVELTY_WORDS[NOVELTY[1]]
    assert "novita_parole" not in vecchia
