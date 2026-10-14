"""Il giro delle ricette ruota fra i dispositivi da chiedere (N165-1).

`recipe_round` chiede a un dispositivo per giro, scelto da
`recipe_turn.who_to_ask` a partire dal cursore che l'app porta
(`RECIPE_CURSOR_KEY`). Se il cursore non avanzasse, ogni giro chiederebbe al
primo dispositivo, e uno che non risponde affamerebbe tutti gli altri.

Nessuna prova lo vedeva (giro 162 del revisore): togliere
`app[RECIPE_CURSOR_KEY].set(cursor)` lasciava la suite verde, e lo stesso
valeva per l'assegnazione di prima di X-31.

Mutazione ESEGUITA (14/10/2026): tolto `app[RECIPE_CURSOR_KEY].set(cursor)`
da `recipe_round` -- rossa (`['dev1', 'dev1']`).
"""
import pytest

from hiris.app.home_space.reader import HOME_SPACE_KEY
from hiris.app.llm_router import LLM_ROUTER_KEY
from hiris.app.mind import recipe_round, recipe_turn
from hiris.app.mind.knowledge import KNOWLEDGE_KEY, KnowledgeStore
from hiris.app.mind.store import OBSERVATIONS_KEY, ObservationsStore
from hiris.app.startup import live_values
from tests._anagrafe_finta import AnagrafeFinta
from tests._runner_finto import RunnerFinto

CASA = {
    "dispositivi": [{"id": "dev1", "nome": "Inverter"},
                    {"id": "dev2", "nome": "Pompa di calore"}],
    "entita": [],
    "aree": [],
}


@pytest.mark.asyncio
async def test_due_giri_chiedono_a_due_dispositivi(tmp_path, monkeypatch):
    sapere = KnowledgeStore(str(tmp_path / "sapere.db"))
    archivio = ObservationsStore(str(tmp_path / "osservazioni.db"))
    chiesti = []

    async def _ask(runner, sapere, house, device_id, **kwargs):
        chiesti.append(device_id)
        return "chiesto"

    monkeypatch.setattr(recipe_turn, "devices_to_ask",
                        lambda sapere, house, watched: ["dev1", "dev2"])
    monkeypatch.setattr(recipe_turn, "ask", _ask)
    app = {**live_values(), OBSERVATIONS_KEY: archivio, KNOWLEDGE_KEY: sapere,
           HOME_SPACE_KEY: AnagrafeFinta(CASA), LLM_ROUTER_KEY: RunnerFinto("{}")}
    try:
        assert await recipe_round.recipe_round(app) == "chiesto"
        assert await recipe_round.recipe_round(app) == "chiesto"
    finally:
        sapere.close()
        archivio.close()

    assert chiesti == ["dev1", "dev2"]
