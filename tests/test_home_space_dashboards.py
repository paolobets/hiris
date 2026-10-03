"""Le plance, lette dal client vero sulla casa finta.

Fino alla Tappa 2 (Task 12) `read_dashboards` si provava sostituendo
`HAClient._ws_send` con una finta che rispondeva per (comando, percorso), e
`reread_dashboards` con un `AsyncMock` che rendeva una tupla scritta a mano --
anche una che il client vero non rende mai (`([], ["principale"])`: la
principale c'e' sempre). Ora tutte girano su
`scripts/casa_finta.py::CasaFinta`, che ricostruisce dall'ingresso
`dashboards` (la forma che `read_dashboards` restituisce) i messaggi grezzi di
`lovelace/dashboards/list` e `lovelace/config`: una plancia senza corpo vi
riceve il rifiuto vero di Home Assistant, `config_not_found`.
"""
import sys
from pathlib import Path

import pytest

from hiris.app.home_space.behavior import reread_dashboards
from hiris.app.home_space.reader import HomeSpace
from tests._casa_sintetica import synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

_ELENCO = [{"url_path": "cucina", "title": "Cucina", "mode": "storage",
            "icon": "mdi:chef-hat", "show_in_sidebar": True}]
_CONFIG_DEFAULT = {"views": [{"title": "Casa", "path": "casa",
                              "cards": [{"type": "light", "entity": "light.cucina"}]}]}
_CONFIG_CUCINA = {"views": [{"title": "Fornelli", "cards": []}]}


def _house(main_config, extra=(), unavailable=(), **kwargs) -> CasaFinta:
    """Una casa con la principale (`main_config`, `None` = senza corpo) e le
    plance aggiuntive `extra` (righe dell'elenco piu' la loro `config`)."""
    inputs = synthetic_inputs()
    inputs["dashboards"] = {
        "entries": [{"url_path": None, "title": "Principale", "config": main_config},
                    *extra],
        "unavailable": list(unavailable)}
    return CasaFinta(inputs, **kwargs)


@pytest.fixture
def archivio(tmp_path):
    a = HomeSpace(str(tmp_path / "casa.db"))
    yield a
    a.close()


@pytest.mark.asyncio
async def test_the_default_dashboard_is_not_lost():
    """`lovelace/dashboards/list` NON la restituisce: ha url_path nullo e va
    chiesta a parte. E' quella che l'utente guarda tutti i giorni."""
    house = _house(_CONFIG_DEFAULT, [{**_ELENCO[0], "config": _CONFIG_CUCINA}])
    plance, unavailable = await house.read_dashboards()
    by_path = {p["url_path"]: p for p in plance}
    assert by_path[None]["config"] == _CONFIG_DEFAULT        # la predefinita
    assert by_path["cucina"]["config"] == _CONFIG_CUCINA
    assert unavailable == []
    # La principale si chiede SENZA percorso: e' cosi' che Home Assistant la
    # riconosce.
    assert ("lovelace/config", {}) in house.calls


@pytest.mark.asyncio
async def test_an_unreadable_dashboard_is_declared():
    """Le plance senza corpo nell'archivio interno: la richiesta e' rifiutata,
    e non deve diventare «plancia senza viste»."""
    house = _house(_CONFIG_DEFAULT, [{**_ELENCO[0], "config": None}],
                   unavailable=["cucina"])
    plance, unavailable = await house.read_dashboards()
    cucina = next(p for p in plance if p["url_path"] == "cucina")
    assert cucina["config"] is None
    assert unavailable == ["cucina"]


@pytest.mark.asyncio
async def test_dashboards_are_kept_and_reread(archivio):
    esito = await reread_dashboards(_house(_CONFIG_DEFAULT), archivio)
    entries = archivio.dashboards()
    assert entries[0]["titolo"] == "Principale"
    assert entries[0]["config"]["views"][0]["title"] == "Casa"
    assert esito["conteggi"]["plance"] == 1


@pytest.mark.asyncio
async def test_the_shown_entities_are_extracted(archivio):
    """A cosa serve davvero: sapere QUALI entita' una plancia mostra, per
    poter dire «questa la vedi gia' in Cucina» invece di riproporla."""
    await reread_dashboards(_house(_CONFIG_DEFAULT), archivio)
    assert archivio.dashboards()[0]["entita"] == ["light.cucina"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [
    # Home Assistant non risponde a niente: l'elenco non arriva.
    lambda: _house(_CONFIG_DEFAULT,
                   silence={"lovelace/dashboards/list", "lovelace/config"}),
    # Risponde, ma nessuna plancia ha un corpo leggibile.
    lambda: _house(None, unavailable=["principale"]),
], ids=["silenzio", "nessuna_leggibile"])
async def test_a_completely_failed_read_does_not_delete_the_dashboards(archivio, failed):
    """Stessa regola dell'anagrafe: una replica vecchia e dichiarata e' meglio
    di una vuota e falsa."""
    await reread_dashboards(_house(_CONFIG_DEFAULT), archivio)
    esito = await reread_dashboards(failed(), archivio)
    assert esito["conteggi"]["plance"] == 0
    assert archivio.dashboards()[0]["titolo"] == "Principale"
    assert archivio.dashboards()[0]["config"] == _CONFIG_DEFAULT
