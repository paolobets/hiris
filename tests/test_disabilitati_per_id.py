"""Un oggetto disabilitato si apre quando la chat lo nomina per id esatto
(Tappa 9, F6; scelta del proprietario del 12/10/2026, «Sì, per id esatto»).

La regola della porta resta (D7 della Tappa 3): le disabilitate sono fuori
da ogni insieme, e contate. Ma `riferimento` uguale all'id, senza altri
filtri, non chiede un insieme: chiede QUELLA cosa, e la scheda dice con
`fuori` perche' non e' fra le visibili -- e porta i suoi ricordi.
"""
import pytest

from hiris.app.home_space.tools import ToolDispatcher
from tests.test_knowledge_tools import _semina_casa


def _casa() -> dict:
    entita = [{"id": eid, "nome": nome, "area_id": "sala", "dispositivo_id": dev,
               "piattaforma": "x", "categoria": None, "classe": None, "unita": None,
               "disabilitata": spenta, "nascosta": 0}
              for eid, nome, dev, spenta in (
                  ("sensor.vecchio", "Sensore vecchio", None, 1),
                  ("sensor.nuovo", "Sensore nuovo", "dev_acceso", 0),
                  ("sensor.del_morto", "Sensore del morto", "dev_spento", 0))]
    return {"piani": [], "aree": [{"id": "sala", "nome": "Sala"}],
            "dispositivi": [{"id": "dev_spento", "nome": "Ponte spento", "area_id": "sala",
                             "disabilitato": 1},
                            {"id": "dev_acceso", "nome": "Ponte acceso", "area_id": "sala",
                             "disabilitato": 0}],
            "entita": entita}


def _porta(tmp_path) -> ToolDispatcher:
    return ToolDispatcher(_semina_casa(tmp_path, casa=_casa(), comportamento=[]), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("riferimento", ["sensor.vecchio", "dev_spento"])
async def test_per_id_esatto_si_apre_la_scheda_del_disabilitato(tmp_path, riferimento):
    """Rossa prima: `trovate: 0, escluse.disabilitate: 1`, nessuna scheda.
    Mutazione ESEGUITA: senza il ramo del disabilitato -- rossa."""
    risposta = await _porta(tmp_path).dispatch("search", {"riferimento": riferimento})
    assert risposta["trovate"] == 1, risposta
    voce, = risposta["voci"]
    assert voce["esiste"] is True and voce["id"] == riferimento
    # Non e' piu' un'esclusa: e' la cosa chiesta.
    assert risposta["escluse"]["disabilitate"] == 0 and "nota" not in risposta


@pytest.mark.asyncio
async def test_la_scheda_dice_che_e_disabilitato(tmp_path):
    voce, = (await _porta(tmp_path).dispatch(
        "search", {"riferimento": "sensor.vecchio"}))["voci"]
    assert voce["fuori"]


@pytest.mark.asyncio
@pytest.mark.parametrize("argomenti", [
    {"nome": "Sensore vecchio"},
    {"nome": "Ponte"},
    {"riferimento": "sensor.vecchio", "dominio": "sensor"},
])
async def test_per_nome_o_con_altri_filtri_resta_fuori(tmp_path, argomenti):
    """Solo l'id esatto, da solo, apre: un nome o un filtro in piu' chiedono
    un insieme, e nell'insieme le disabilitate restano fuori e contate.
    Mutazione ESEGUITA: aprire anche quando ci sono altri filtri -- rossa sul
    caso col dominio."""
    risposta = await _porta(tmp_path).dispatch("search", argomenti)
    ids = {v.get("id") for v in risposta["voci"]}
    assert "sensor.vecchio" not in ids and "dev_spento" not in ids, risposta
    assert risposta["escluse"]["disabilitate"] >= 1
