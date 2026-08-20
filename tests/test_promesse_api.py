"""Le due rotte -- e la prova che dalla porta HTTP esce la STESSA promessa.

Fixture `client`: l'app VERA (`create_app`), non un'app costruita a mano con
le sole due rotte in prova -- vedi lo stesso ragionamento in
`test_impostazioni_api.py`. La rotta nuova deve passare dagli stessi
middleware di ogni altra (`internal_auth_middleware`, `csrf_middleware`): un
test che li scavalcasse non direbbe niente su cio' che accade in produzione.
Il CSRF resta silenzioso qui perche' `conftest.py` mette
`HIRIS_ALLOW_NO_CSRF=1` per l'intera suite -- la stessa valvola che ogni
altro test di API con questa fixture usa (vedi `test_api.py`,
`test_impostazioni_api.py`): nessuna eccezione dedicata a questa rotta.
"""
import os

import pytest
import pytest_asyncio

from hiris.app.chat_store import close_all_stores
from hiris.app.schedulatore.archivio import ArchivioPromesse
from hiris.app.server import create_app


@pytest.fixture(autouse=True)
def reset_chat_stores():
    """Chiude le connessioni SQLite dopo ogni test (file-lock su Windows)."""
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app["promesse"] = ArchivioPromesse(os.path.join(str(tmp_path), "promesse.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app["promesse"].close()


@pytest.mark.asyncio
async def test_get_promesse_torna_le_in_sospeso(client):
    archivio = client.app["promesse"]
    archivio.crea({"specie": "chiedi", "frase": "x", "quando_ts": 3601.0,
                   "domanda": "e' aumentata?"}, adesso=1.0)

    risposta = await client.get("/api/promesse")
    assert risposta.status == 200
    corpo = await risposta.json()
    assert len(corpo["promesse"]) == 1


@pytest.mark.asyncio
async def test_get_promesse_tutte_include_le_concluse(client):
    archivio = client.app["promesse"]
    ident = archivio.crea({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          adesso=1.0)["promessa"]["id"]
    archivio.concludi(ident, stato="mantenuta", adesso=2.0)

    corpo = await (await client.get("/api/promesse?tutte=1")).json()
    assert len(corpo["promesse"]) == 1
    corpo = await (await client.get("/api/promesse")).json()
    assert corpo["promesse"] == []


@pytest.mark.asyncio
async def test_delete_disdice_e_una_gia_conclusa_da_409(client):
    archivio = client.app["promesse"]
    ident = archivio.crea({"specie": "chiedi", "frase": "x",
                           "quando_ts": 3601.0, "domanda": "?"},
                          adesso=1.0)["promessa"]["id"]

    assert (await client.delete("/api/promesse/%s" % ident)).status == 200
    assert archivio.leggi(ident)["stato"] == "disdetta"

    secondo = await client.delete("/api/promesse/%s" % ident)
    assert secondo.status == 409
    assert "errore" in await secondo.json()


@pytest.mark.asyncio
async def test_delete_di_un_id_inesistente_da_404(client):
    assert (await client.delete("/api/promesse/mai-esistita")).status == 404


@pytest.mark.asyncio
async def test_la_rotta_e_lo_strumento_danno_la_STESSA_forma(client):
    """Fondamenta n.3: una promessa vista dalla chat e dalla pagina e' la stessa."""
    from hiris.app.casa.strumenti import DispatcherStrumenti

    archivio = client.app["promesse"]
    archivio.crea({"specie": "chiedi", "frase": "x", "quando_ts": 3601.0,
                   "domanda": "?"}, adesso=1.0)

    da_http = (await (await client.get("/api/promesse")).json())["promesse"][0]
    d = DispatcherStrumenti(None, None, promesse=archivio)
    da_strumento = (await d.dispatch("promesse", {}))["promesse"][0]

    assert da_http == da_strumento
    # La lista non deve essere vuota: un confronto fra due liste vuote
    # passerebbe a vuoto e non proverebbe niente sulla forma.
    assert da_http
