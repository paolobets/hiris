"""La chat risponde in un modo solo: chi chiede lo streaming riceve la risposta normale.

Fino alla 3.72.2 `POST /api/chat` aveva un secondo ramo, in Server-Sent
Events, attivato da `Accept: text/event-stream` o da `"stream": true`. Nessuna
pagina lo chiedeva (la chat disegna una risposta per turno), e il ramo portava
con se' un secondo ciclo del modello in ogni runner (`chat_stream`), libero di
divergere dal primo. E' uscito con la Tappa 0 dello sprint «Una fonte sola di
verita'» (dichiarazione D2 del piano, voce M-04 del registro).

Mutazione ESEGUITA: rimesso in `handle_chat` il ramo `wants_stream` che
risponde `text/event-stream` -- rossa (`text/event-stream` nel Content-Type).
"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio

from hiris.app.api.handlers_config import THEME_KEY
from hiris.app.chat_settings import CHAT_SETTINGS_KEY, ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.claude_runner import CLAUDE_RUNNER_KEY
from hiris.app.llm_router import LLM_ROUTER_KEY
from hiris.app.proxy.ha_client import HA_CLIENT_KEY
from hiris.app.server import create_app
from hiris.app.storage import DATA_DIR_KEY
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

from tests._runner_finto import RunnerFinto


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    mock_runner = RunnerFinto("risposta di prova")
    app[HA_CLIENT_KEY] = CasaFinta(synthetic_inputs())
    app[CHAT_SETTINGS_KEY].set(ChatSettings())
    app[CLAUDE_RUNNER_KEY] = mock_runner
    app[LLM_ROUTER_KEY] = mock_runner
    app[THEME_KEY] = "auto"
    app[DATA_DIR_KEY] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


async def _answered_as_json(response) -> None:
    assert response.status == 200
    assert response.headers.get("Content-Type", "").startswith("application/json")
    assert (await response.json())["response"] == "risposta di prova"


@pytest.mark.asyncio
async def test_chi_chiede_lo_streaming_col_corpo_riceve_la_risposta_normale(client):
    await _answered_as_json(
        await client.post("/api/chat", json={"message": "Prova", "stream": True}))


@pytest.mark.asyncio
async def test_chi_chiede_lo_streaming_con_l_intestazione_riceve_la_risposta_normale(client):
    await _answered_as_json(await client.post(
        "/api/chat", json={"message": "Prova"}, headers={"Accept": "text/event-stream"}))


@pytest.mark.asyncio
async def test_la_risposta_normale_resta_quella(client):
    await _answered_as_json(await client.post("/api/chat", json={"message": "Ciao"}))
