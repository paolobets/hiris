from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.casa.archivio import ArchivioCasa, _CHIAVE_PLANCIA_PRINCIPALE as _CHIAVE_ARCHIVIO
from hiris.app.casa.comportamento import rileggi_plance
from hiris.app.proxy.ha_client import HAClient, _CHIAVE_PLANCIA_PRINCIPALE as _CHIAVE_HA_CLIENT


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


def test_la_chiave_sentinella_non_e_derivata_due_volte():
    """La chiave sentinella e' duplicata (non importata) fra archivio.py e
    ha_client.py per non far dipendere il client HA dallo storage — ma le due
    copie devono restare identiche, altrimenti la collisione che leggi_plance
    dovrebbe intercettare smetterebbe di essere riconosciuta."""
    assert _CHIAVE_HA_CLIENT == _CHIAVE_ARCHIVIO


@pytest.mark.asyncio
async def test_due_plance_con_lo_stesso_percorso_non_fermano_l_aggiornamento():
    """Prima: UNIQUE constraint failed -> l'aggiornamento delle plance
    smetteva finche' la condizione persisteva, indistinguibile da «tutto
    normale»."""
    elenco_duplicato = [
        {"url_path": "cucina", "title": "Cucina", "mode": "storage"},
        {"url_path": "cucina", "title": "Cucina (di nuovo)", "mode": "storage"},
    ]
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(elenco_duplicato),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        ("lovelace/config", "cucina"): _msg(_CONFIG_CUCINA),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, non_disponibili = await _client().leggi_plance()
    percorsi = [p["url_path"] for p in plance]
    assert percorsi.count("cucina") == 1
    assert any("cucina" in nd for nd in non_disponibili)


@pytest.mark.asyncio
async def test_una_plancia_chiamata_come_la_chiave_della_predefinita_non_la_scalza():
    """La chiave sentinella della predefinita non e' un percorso vietato in
    HA: una plancia puo' chiamarsi davvero cosi'."""
    elenco = [{"url_path": _CHIAVE_HA_CLIENT, "title": "Omonima", "mode": "storage"}]
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(elenco),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, non_disponibili = await _client().leggi_plance()
    percorsi = [p["url_path"] for p in plance]
    assert percorsi == [None]  # solo la predefinita e' sopravvissuta
    assert plance[0]["config"] == _CONFIG_DEFAULT
    assert any(_CHIAVE_HA_CLIENT in nd for nd in non_disponibili)


@pytest.mark.asyncio
async def test_una_plancia_con_percorso_vuoto_non_sparisce():
    """"" e' falsy ma non e' assente: prima non compariva ne' fra le plance
    ne' fra le non disponibili."""
    elenco = [{"url_path": "", "title": "Vuota", "mode": "storage"}]
    finto = _finto_ws_batch({
        ("lovelace/dashboards/list", None): _msg(elenco),
        ("lovelace/config", None): _msg(_CONFIG_DEFAULT),
        ("lovelace/config", ""): _msg(_CONFIG_CUCINA),
    })
    with patch.object(HAClient, "_ws_batch", finto):
        plance, non_disponibili = await _client().leggi_plance()
    percorsi = [p["url_path"] for p in plance]
    assert "" in percorsi
    vuota = [p for p in plance if p["url_path"] == ""][0]
    assert vuota["config"] == _CONFIG_CUCINA
    assert non_disponibili == []


@pytest.mark.asyncio
async def test_l_elenco_non_arrivato_si_distingue_da_un_elenco_vuoto():
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
        plance, non_disponibili = await _client().leggi_plance()
    assert any(nd.startswith("elenco:") for nd in non_disponibili)
    percorsi = [p["url_path"] for p in plance]
    assert percorsi == [None]  # solo la predefinita, letta da un'altra connessione


@pytest.mark.asyncio
async def test_un_elenco_fallito_non_cancella_le_plance_aggiuntive(archivio):
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
    await rileggi_plance(client, archivio)
    assert {p["titolo"] for p in archivio.plance()} == {"Principale", "Cucina"}

    # Ora l'elenco va in timeout: solo la predefinita risulta leggibile.
    client.leggi_plance = AsyncMock(return_value=(
        [{"url_path": None, "title": "Principale", "mode": "storage",
          "config": _CONFIG_DEFAULT}],
        ["elenco: lovelace/dashboards/list non ha risposto"]))
    esito = await rileggi_plance(client, archivio)
    # La replica precedente resta INTATTA: Cucina non sparisce.
    assert {p["titolo"] for p in archivio.plance()} == {"Principale", "Cucina"}
    assert esito["conteggi"]["plance"] == 0
    assert any(nd.startswith("elenco:") for nd in esito["non_disponibili"])


def test_sostituisci_plance_non_sovrascrive_in_silenzio_una_chiave_duplicata(archivio):
    """Difende la scelta di NON usare INSERT OR REPLACE: due voci con lo
    stesso percorso passate direttamente a sostituisci_plance (bypassando la
    deduplica di leggi_plance) devono sollevare, non sovrascriversi in
    silenzio. E' leggi_plance() il punto che dichiara gli scarti — l'archivio
    resta l'ultima linea di difesa, non la prima."""
    voci = [
        {"url_path": "cucina", "title": "Cucina", "mode": "storage",
         "config": _CONFIG_CUCINA},
        {"url_path": "cucina", "title": "Cucina (duplicata)", "mode": "storage",
         "config": _CONFIG_DEFAULT},
    ]
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        archivio.sostituisci_plance(voci)
