from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.comportamento import rileggi_plance
from hiris.app.proxy.ha_client import HAClient


def _client():
    return HAClient(base_url="http://ha.test", token="t")


def _msg(risultato):
    return {"id": 1, "type": "result", "success": True, "result": risultato}


def _finto_ws_batch(risposte_per_comando: dict) -> AsyncMock:
    """Fake di `_ws_batch` che risponde in base al TIPO di comando e
    all'url_path (non alla posizione nella lista o al numero di chiamate).

    `leggi_plance()` legge prima l'elenco e SOLO DOPO — perche' i percorsi
    delle plance aggiuntive li scopre li' — sa quali comandi `lovelace/config`
    interrogare: sono due chiamate a `_ws_batch` in sequenza, non una sola. Un
    fake che restituisce sempre la STESSA lista fissa (`AsyncMock(return_value=...)`)
    la' dove servirebbe una risposta diversa ad ogni chiamata produrrebbe
    accoppiamenti sbagliati fra percorso e config — il fake deve rispondere
    in base a COSA si chiede, non a QUANTE volte lo si chiede.
    """
    async def _finto(comandi, timeout=10.0):
        risposte = []
        for tipo, extra in comandi:
            percorso = (extra or {}).get("url_path")
            risposte.append(risposte_per_comando.get((tipo, percorso)))
        return risposte
    return AsyncMock(side_effect=_finto)


_ELENCO = [{"url_path": "cucina", "title": "Cucina", "mode": "storage",
            "icon": "mdi:chef-hat", "show_in_sidebar": True}]
_CONFIG_DEFAULT = {"views": [{"title": "Casa", "path": "casa",
                              "cards": [{"type": "light", "entity": "light.cucina"}]}]}
_CONFIG_CUCINA = {"views": [{"title": "Fornelli", "cards": []}]}


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


@pytest.mark.asyncio
async def test_la_plancia_predefinita_non_si_perde():
    """`lovelace/dashboards/list` NON la restituisce: ha url_path nullo e va
    chiesta a parte. E' quella che l'utente guarda tutti i giorni."""
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(_ELENCO),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        ("lovelace/config", "cucina"): _msg(_CONFIG_CUCINA),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, non_disponibili = await _client().leggi_plance()
    percorsi = [p["url_path"] for p in plance]
    assert None in percorsi          # la predefinita
    assert "cucina" in percorsi
    assert non_disponibili == []


@pytest.mark.asyncio
async def test_una_plancia_illeggibile_si_dichiara():
    """Le plance in modalita' YAML non stanno nell'archivio interno: la
    richiesta fallisce, e non deve diventare «plancia senza viste»."""
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(_ELENCO),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        # "cucina" assente: nessuna risposta -> richiesta fallita.
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, non_disponibili = await _client().leggi_plance()
    cucina = [p for p in plance if p["url_path"] == "cucina"][0]
    assert cucina["config"] is None
    assert "cucina" in non_disponibili


@pytest.mark.asyncio
async def test_le_plance_si_conservano_e_si_rileggono(archivio):
    client = AsyncMock()
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    esito = await rileggi_plance(client, archivio)
    voci = archivio.plance()
    assert voci[0]["titolo"] == "Principale"
    assert voci[0]["config"]["views"][0]["title"] == "Casa"
    assert esito["conteggi"]["plance"] == 1


@pytest.mark.asyncio
async def test_le_entita_mostrate_si_estraggono(archivio):
    """A cosa serve davvero: sapere QUALI entita' una plancia mostra, per
    poter dire «questa la vedi gia' in Cucina» invece di riproporla."""
    client = AsyncMock()
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    await rileggi_plance(client, archivio)
    assert archivio.plance()[0]["entita"] == ["light.cucina"]


@pytest.mark.asyncio
async def test_una_lettura_del_tutto_fallita_non_cancella_le_plance(archivio):
    """Stessa regola dell'anagrafe: una replica vecchia e dichiarata e' meglio
    di una vuota e falsa."""
    client = AsyncMock()
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    await rileggi_plance(client, archivio)
    client.leggi_plance = AsyncMock(return_value=([], ["principale"]))
    await rileggi_plance(client, archivio)
    assert archivio.plance()[0]["titolo"] == "Principale"
