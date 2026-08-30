from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.casa.archivio import _MAIN_DASHBOARD_KEY as _ARCHIVE_KEY
from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.casa.comportamento import reread_dashboards
from hiris.app.proxy.ha_client import _CHIAVE_PLANCIA_PRINCIPALE as _HA_CLIENT_KEY
from hiris.app.proxy.ha_client import HAClient


def _client():
    return HAClient(base_url="http://ha.test", token="t")


def _msg(risultato):
    return {"id": 1, "type": "result", "success": True, "result": risultato}


def _finto_ws_batch(answers_per_command: dict) -> AsyncMock:
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
    a = HomeSpaceStore(str(tmp_path / "casa.db"))
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
        plance, unavailable = await _client().leggi_plance()
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
        plance, unavailable = await _client().leggi_plance()
    cucina = next(p for p in plance if p["url_path"] == "cucina")
    assert cucina["config"] is None
    assert "cucina" in unavailable


@pytest.mark.asyncio
async def test_dashboards_are_kept_and_reread(archivio):
    client = AsyncMock()
    client.leggi_plance = AsyncMock(return_value=(
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
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    await reread_dashboards(client, archivio)
    assert archivio.dashboards()[0]["entita"] == ["light.cucina"]


@pytest.mark.asyncio
async def test_a_completely_failed_read_does_not_delete_the_dashboards(archivio):
    """Stessa regola dell'anagrafe: una replica vecchia e dichiarata e' meglio
    di una vuota e falsa."""
    client = AsyncMock()
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}], []))
    await reread_dashboards(client, archivio)
    client.leggi_plance = AsyncMock(return_value=([], ["principale"]))
    await reread_dashboards(client, archivio)
    assert archivio.dashboards()[0]["titolo"] == "Principale"


def test_the_sentinel_key_is_not_derived_twice():
    """La chiave sentinella e' duplicata (non importata) fra archivio.py e
    ha_client.py per non far dipendere il client HA dallo storage — ma le due
    copie devono restare identiche, altrimenti la collisione che leggi_plance
    dovrebbe intercettare smetterebbe di essere riconosciuta."""
    assert _HA_CLIENT_KEY == _ARCHIVE_KEY


@pytest.mark.asyncio
async def test_two_dashboards_with_the_same_path_do_not_stop_the_update():
    """Prima: UNIQUE constraint failed -> l'aggiornamento delle plance
    smetteva finche' la condizione persisteva, indistinguibile da «tutto
    normale»."""
    duplicate_listing = [
        {"url_path": "cucina", "title": "Cucina", "mode": "storage"},
        {"url_path": "cucina", "title": "Cucina (di nuovo)", "mode": "storage"},
    ]
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(duplicate_listing),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        ("lovelace/config", "cucina"): _msg(_CONFIG_CUCINA),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, unavailable = await _client().leggi_plance()
    paths = [p["url_path"] for p in plance]
    assert paths.count("cucina") == 1
    assert any("cucina" in nd for nd in unavailable)


@pytest.mark.asyncio
async def test_a_dashboard_named_like_the_default_key_does_not_displace_it():
    """La chiave sentinella della predefinita non e' un percorso vietato in
    HA: una plancia puo' chiamarsi davvero cosi'."""
    listing = [{"url_path": _HA_CLIENT_KEY, "title": "Omonima", "mode": "storage"}]
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(listing),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, unavailable = await _client().leggi_plance()
    paths = [p["url_path"] for p in plance]
    assert paths == [None]  # solo la predefinita e' sopravvissuta
    assert plance[0]["config"] == _CONFIG_DEFAULT
    assert any(_HA_CLIENT_KEY in nd for nd in unavailable)


@pytest.mark.asyncio
async def test_a_dashboard_with_an_empty_path_does_not_disappear():
    """"" e' falsy ma non e' assente: prima non compariva ne' fra le plance
    ne' fra le non disponibili."""
    listing = [{"url_path": "", "title": "Vuota", "mode": "storage"}]
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(listing),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        ("lovelace/config", ""): _msg(_CONFIG_CUCINA),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, unavailable = await _client().leggi_plance()
    paths = [p["url_path"] for p in plance]
    assert "" in paths
    vuota = next(p for p in plance if p["url_path"] == "")
    assert vuota["config"] == _CONFIG_CUCINA
    assert unavailable == []


@pytest.mark.asyncio
async def test_a_listing_that_never_arrives_is_distinguished_from_an_empty_listing():
    """Important (4): `_ws_request` restituiva `None` sia se il comando falliva
    sia se riusciva con un risultato vuoto -- le due cose sono fatti diversi
    sulla casa (non lo so / non ce ne sono). Qui l'elenco non risponde
    affatto, ma la predefinita si legge lo stesso (un'ALTRA connessione)."""
    finto = _finto_ws_batch({
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        # "lovelace/dashboards/list" assente da risposte_per_comando: nessuna
        # risposta -> il comando risulta fallito, non vuoto-e-riuscito.
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, unavailable = await _client().leggi_plance()
    assert any(nd.startswith("elenco:") for nd in unavailable)
    paths = [p["url_path"] for p in plance]
    assert paths == [None]  # solo la predefinita, letta da un'altra connessione


@pytest.mark.asyncio
async def test_a_failed_listing_does_not_delete_the_additional_dashboards(archivio):
    """Important (4), riprodotto a livello di `rileggi_plance`: l'elenco va
    in timeout ma la config della predefinita si legge lo stesso -> senza
    distinguere i due casi, la guardia "nessuna leggibile" non scatterebbe
    (la predefinita E' leggibile) e la replica verrebbe sostituita con la
    sola predefinita: Cucina sparirebbe senza finire nemmeno fra i non
    disponibili, perche' l'elenco che l'avrebbe nominata non e' mai arrivato."""
    client = AsyncMock()
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT},
         {"url_path": "cucina", "title": "Cucina", "mode": "storage",
          "config": _CONFIG_CUCINA}],
        []))
    await reread_dashboards(client, archivio)
    assert {p["titolo"] for p in archivio.dashboards()} == {"Principale", "Cucina"}

    # Ora l'elenco va in timeout: solo la predefinita risulta leggibile.
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}],
        ["elenco: lovelace/dashboards/list non ha risposto"]))
    esito = await reread_dashboards(client, archivio)
    # La replica precedente resta INTATTA: Cucina non sparisce.
    assert {p["titolo"] for p in archivio.dashboards()} == {"Principale", "Cucina"}
    assert esito["conteggi"]["plance"] == 0
    assert any(nd.startswith("elenco:") for nd in esito["non_disponibili"])


def test_replace_dashboards_does_not_silently_overwrite_a_duplicate_key(archivio):
    """Difende la scelta di NON usare INSERT OR REPLACE: due voci con lo
    stesso percorso passate direttamente a sostituisci_plance (bypassando la
    deduplica di leggi_plance) devono sollevare, non sovrascriversi in
    silenzio. E' leggi_plance() il punto che dichiara gli scarti — l'archivio
    resta l'ultima linea di difesa, non la prima."""
    entries = [
        {"url_path": "cucina", "title": "Cucina", "mode": "storage",
         "config": _CONFIG_CUCINA},
        {"url_path": "cucina", "title": "Cucina (duplicata)", "mode": "storage",
         "config": _CONFIG_DEFAULT},
    ]
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        archivio.replace_dashboards(entries)
