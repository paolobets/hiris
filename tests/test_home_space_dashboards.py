from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.home_space.behavior import reread_dashboards
from hiris.app.home_space.reader import HomeSpace
from hiris.app.proxy.ha_client import HAClient


def _client():
    return HAClient(base_url="http://ha.test", token="t")


def _msg(risultato):
    return {"id": 1, "type": "result", "success": True, "result": risultato}


def _finto_ws_batch(answers_per_command: dict) -> AsyncMock:
    """Fake di `_ws_batch` che risponde in base al TIPO di comando e
    all'url_path (non alla posizione nella lista o al numero di chiamate).

    `read_dashboards()` legge prima l'elenco e SOLO DOPO — perche' i percorsi
    delle plance aggiuntive li scopre li' — sa quali comandi `lovelace/config`
    interrogare: sono due chiamate a `_ws_batch` in sequenza, non una sola. Un
    fake che restituisce sempre la STESSA lista fissa (`AsyncMock(return_value=...)`)
    la' dove servirebbe una risposta diversa ad ogni chiamata produrrebbe
    accoppiamenti sbagliati fra percorso e config — il fake deve rispondere
    in base a COSA si chiede, non a QUANTE volte lo si chiede.
    """
    async def _finto(commands, timeout=10.0):
        answers = []
        for kind, extra in commands:
            percorso = (extra or {}).get("url_path")
            answers.append(answers_per_command.get((kind, percorso)))
        return answers
    return AsyncMock(side_effect=_finto)


_ELENCO = [{"url_path": "cucina", "title": "Cucina", "mode": "storage",
            "icon": "mdi:chef-hat", "show_in_sidebar": True}]
_CONFIG_DEFAULT = {"views": [{"title": "Casa", "path": "casa",
                              "cards": [{"type": "light", "entity": "light.cucina"}]}]}
_CONFIG_CUCINA = {"views": [{"title": "Fornelli", "cards": []}]}


@pytest.fixture
def archivio(tmp_path):
    a = HomeSpace(str(tmp_path / "casa.db"))
    yield a
    a.close()


@pytest.mark.asyncio
async def test_the_default_dashboard_is_not_lost():
    """`lovelace/dashboards/list` NON la restituisce: ha url_path nullo e va
    chiesta a parte. E' quella che l'utente guarda tutti i giorni."""
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(_ELENCO),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        ("lovelace/config", "cucina"): _msg(_CONFIG_CUCINA),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, unavailable = await _client().read_dashboards()
    paths = [p["url_path"] for p in plance]
    assert None in paths          # la predefinita
    assert "cucina" in paths
    assert unavailable == []


@pytest.mark.asyncio
async def test_an_unreadable_dashboard_is_declared():
    """Le plance in modalita' YAML non stanno nell'archivio interno: la
    richiesta fallisce, e non deve diventare «plancia senza viste»."""
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(_ELENCO),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        # "cucina" assente: nessuna risposta -> richiesta fallita.
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, unavailable = await _client().read_dashboards()
    cucina = next(p for p in plance if p["url_path"] == "cucina")
    assert cucina["config"] is None
    assert "cucina" in unavailable


@pytest.mark.asyncio
async def test_dashboards_are_kept_and_reread(archivio):
    client = AsyncMock()
    client.read_dashboards = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    esito = await reread_dashboards(client, archivio)
    entries = archivio.dashboards()
    assert entries[0]["titolo"] == "Principale"
    assert entries[0]["config"]["views"][0]["title"] == "Casa"
    assert esito["conteggi"]["plance"] == 1


@pytest.mark.asyncio
async def test_the_shown_entities_are_extracted(archivio):
    """A cosa serve davvero: sapere QUALI entita' una plancia mostra, per
    poter dire «questa la vedi gia' in Cucina» invece di riproporla."""
    client = AsyncMock()
    client.read_dashboards = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    await reread_dashboards(client, archivio)
    assert archivio.dashboards()[0]["entita"] == ["light.cucina"]


@pytest.mark.asyncio
async def test_a_completely_failed_read_does_not_delete_the_dashboards(archivio):
    """Stessa regola dell'anagrafe: una replica vecchia e dichiarata e' meglio
    di una vuota e falsa."""
    client = AsyncMock()
    client.read_dashboards = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    await reread_dashboards(client, archivio)
    client.read_dashboards = AsyncMock(return_value=([], ["principale"]))
    await reread_dashboards(client, archivio)
    assert archivio.dashboards()[0]["titolo"] == "Principale"


