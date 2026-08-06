"""GET /api/casa: la casa si vede in sola lettura, anche quando l'archivio manca.

Convenzione seguita: quella vera del repo (vedi `hiris/app/server.py`,
`create_app()`) -- un handler `async def` semplice, registrato con
`app.router.add_get(...)` dentro `create_app()`. Nessun `registra_rotte_*`:
il repo non lo usa da nessun'altra parte, e introdurlo qui sarebbe esattamente
il secondo modo di fare la stessa cosa che questo refactor vuole eliminare.
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_casa import handle_get_casa
from hiris.app.casa.archivio import ArchivioCasa


@pytest.mark.asyncio
async def test_api_casa_restituisce_la_gerarchia(aiohttp_client, tmp_path):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
        "integrazioni": [{"domain": "mqtt", "title": "MQTT", "state": "loaded"}],
    })
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["piani"][0]["nome"] == "Piano terra"
    assert corpo["piani"][0]["aree"][0]["nome"] == "Cucina"
    assert corpo["conteggi"]["aree"] == 1
    assert corpo["anagrafe_letta_il"] is not None
    assert corpo["non_disponibili"] == []
    archivio.chiudi()


@pytest.mark.asyncio
async def test_api_casa_senza_anagrafe_risponde_lo_stesso(aiohttp_client):
    """L'anagrafe puo' essere vuota se HA non era pronto all'avvio: 200 e vuota,
    non 500 -- chi guarda deve poter distinguere «vuota» da «rotta»."""
    app = web.Application()
    app["archivio_casa"] = None
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["piani"] == []
    assert corpo["anagrafe_letta_il"] is None
    # Stesso principio applicato al comportamento: senza archivio, un
    # "senza_corpo" a zero affermerebbe "conosco tutto" -- resta `None`,
    # non un fatto finto. `conteggi`/`voci` sono contenitori naturali.
    assert corpo["comportamento"] == {
        "letto_il": None, "conteggi": {}, "senza_corpo": None,
        "problemi": None, "file_non_letti": None, "voci": [],
    }
    assert corpo["plance"] == {"lette_il": None, "non_disponibili": None, "voci": []}


@pytest.mark.asyncio
async def test_api_casa_mostra_il_comportamento_e_quanto_non_sa(aiohttp_client, tmp_path):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci_comportamento(
        [
            {"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
             "corpo": {"trigger": []}, "origine": "file"},
            {"id": "automation.a_mano", "tipo": "automazione", "nome": "A mano",
             "corpo": None, "origine": "solo_stato"},
            {"id": "script.vuoto", "tipo": "script", "nome": "Vuoto",
             "corpo": {}, "origine": "file"},
        ],
        problemi=["automations.yaml: id 42 usato da 2 voci"],
        file_non_letti={"scripts.yaml": "assente"},
    )
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    comportamento = corpo["comportamento"]
    # Data propria della sezione, diversa da `anagrafe_letta_il`.
    assert comportamento["letto_il"] is not None
    assert comportamento["conteggi"] == {"automazione": 2, "script": 1}
    # Solo "a_mano" e' senza corpo: "vuoto" un corpo ce l'ha, e' solo vuoto --
    # le due cose non sono la stessa cosa e non vanno confuse.
    assert comportamento["senza_corpo"] == 1
    assert len(comportamento["voci"]) == 3
    # Le dichiarazioni costruite da comportamento.componi()/rileggi() devono
    # arrivare fin qui, non morire in un log (Important 3).
    assert comportamento["problemi"] == ["automations.yaml: id 42 usato da 2 voci"]
    assert comportamento["file_non_letti"] == {"scripts.yaml": "assente"}
    per_id = {v["id"]: v for v in comportamento["voci"]}
    assert per_id["automation.a_mano"]["corpo"] is None
    assert per_id["script.vuoto"]["corpo"] == {}
    archivio.chiudi()


@pytest.mark.asyncio
async def test_api_casa_mostra_le_plance_compresa_la_predefinita(aiohttp_client, tmp_path):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    archivio.sostituisci_plance([
        {"url_path": None, "title": "Principale", "mode": "storage",
         "config": {"views": []}, "entita": ["light.cucina"]},
        {"url_path": "cucina", "title": "Cucina", "mode": "storage",
         "config": None, "entita": []},
    ])
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_casa)
    client = await aiohttp_client(app)

    resp = await client.get("/api/casa")
    assert resp.status == 200
    corpo = await resp.json()
    sezione = corpo["plance"]
    # Data propria della sezione: `sostituisci_plance` l'ha appena scritta,
    # non e' `aggiornata_il`/`anagrafe_letta_il`.
    assert sezione["lette_il"] is not None
    assert sezione["non_disponibili"] == []
    plance = sezione["voci"]
    assert len(plance) == 2
    principale = next(p for p in plance if p["percorso"] is None)
    assert principale["titolo"] == "Principale"
    assert principale["entita"] == ["light.cucina"]
    cucina = next(p for p in plance if p["percorso"] == "cucina")
    # Una plancia in modalita' YAML non si legge: `config: None` e' un fatto
    # diverso da "plancia senza viste" e non va appiattito.
    assert cucina["config"] is None
    archivio.chiudi()
