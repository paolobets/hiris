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
    assert corpo["aggiornata_il"] is not None
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
    assert corpo["aggiornata_il"] is None
