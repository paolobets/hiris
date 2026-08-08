"""Consolidamento 1.2 — una proposta deve contenere cio' che il suo tipo dichiara.

Due percorsi autonomi (Sentinella e coverage-review del Brain) creavano proposte
di tipo `ha_automation` con dentro tutt'altro: un'azione suggerita, o il
suggerimento grezzo del modello. All'approvazione `create_automation` accettava
qualunque dizionario non vuoto e scriveva in Home Assistant un'automazione senza
trigger ne' azione. Stesso schema del bug di luglio: sembra applicata, non fa
nulla.

La difesa era su entrambi i lati:
  - chi applica: `create_automation` rifiuta cio' che non ha la forma minima di
    un'automazione HA;
  - chi propone: la Sentinella proponeva uno script (che era cio' che aveva
    davvero in mano) e la coverage-review un'automazione solo quando il
    suggerimento portava davvero una config di automazione.

fetta E3 Task 5 + Task 7: entrambi i "chi propone" sono usciti per intero --
la coverage-review del Brain (Task 5, brain.coverage_review) e la Sentinella
(Task 7, watcher/sentinel_proposal.py + watcher/executor.py, cancellati
insieme al resto del guardiano/ragionatore/esecutore). Resta solo "chi
applica": `create_automation`/`is_automation_config` (proxy/ha_client.py) non
hanno nulla a che fare con la Sentinella -- sono la difesa che vale per
QUALUNQUE proposta futura, non solo per quelle che la Sentinella creava.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app.proxy.ha_client import HAClient, is_automation_config


# ---------------------------------------------------------------------------
# Chi applica — forma minima di un'automazione Home Assistant
# ---------------------------------------------------------------------------

def _post_mock(status=200):
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value="OK")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _client_with_post_spy():
    client = HAClient(base_url="http://supervisor/core", token="t")
    client.call_service = AsyncMock(return_value=True)   # niente reload reale
    client.get_automations = AsyncMock(return_value=[])  # niente match per alias
    post = MagicMock(return_value=_post_mock(200))
    client._session = MagicMock()
    client._session.post = post
    return client, post


NON_AUTOMATION_CONFIGS = [
    {"suggested_action": {"domain": "switch", "service": "turn_off",
                          "entity_id": "switch.stufa", "data": {}}},   # Sentinella
    {"detector": "power", "entity": "sensor.presa", "max_watt": 2000},  # coverage-review
    {"alias": "Solo un nome"},                                          # niente trigger/azioni
    {"alias": "X", "trigger": [{"platform": "state"}]},                 # niente azioni
    {"alias": "X", "action": [{"service": "light.turn_on"}]},           # niente trigger
    {"alias": "X", "trigger": None, "action": None},                    # chiavi svuotate
    {"title": "Idea di gestione", "rationale": "perche' si'"},          # suggerimento grezzo
]


@pytest.mark.asyncio
@pytest.mark.parametrize("config", NON_AUTOMATION_CONFIGS)
async def test_create_automation_rejects_non_automation_config(config):
    client, post = _client_with_post_spy()
    res = await client.create_automation(config)
    assert "error" in res, res
    post.assert_not_called()   # niente scrittura in HA, nemmeno tentata


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [None, {}, [], "trigger"])
async def test_create_automation_still_rejects_empty_or_non_dict(config):
    client, post = _client_with_post_spy()
    res = await client.create_automation(config)
    assert "error" in res
    post.assert_not_called()


ACCEPTED_CONFIGS = [
    # forma storica (singolare) — l'unica esistente fino a HA 2024.10
    {"alias": "X", "trigger": [], "action": []},
    # forma canonica attuale (plurale), retro-compatibile con la precedente
    {"alias": "X", "triggers": [{"trigger": "state", "entity_id": "light.x"}],
     "actions": [{"service": "light.turn_off", "target": {"entity_id": "light.x"}}]},
    # un solo trigger/azione scritti come mapping invece che come lista
    {"alias": "X", "trigger": {"platform": "state", "entity_id": "light.x"},
     "action": {"service": "light.turn_off"}},
    # forme miste (HA accetta le chiavi indipendentemente l'una dall'altra)
    {"alias": "X", "triggers": [], "action": []},
    # automazione da blueprint: non ha trigger ne' azioni proprie
    {"alias": "X", "use_blueprint": {"path": "motion.yaml", "input": {"a": "b"}}},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("config", ACCEPTED_CONFIGS)
async def test_create_automation_accepts_every_legitimate_form(config):
    client, post = _client_with_post_spy()
    res = await client.create_automation(config)
    assert res.get("ok") is True, res
    post.assert_called_once()


def test_is_automation_config_predicate():
    assert is_automation_config({"trigger": [], "action": []}) is True
    assert is_automation_config({"triggers": [], "actions": []}) is True
    assert is_automation_config({"use_blueprint": {"path": "x.yaml"}}) is True
    assert is_automation_config({"suggested_action": {}}) is False
    assert is_automation_config({"use_blueprint": "x.yaml"}) is False
    assert is_automation_config({}) is False
    assert is_automation_config(None) is False


# ---------------------------------------------------------------------------
# fetta E3 Task 5 + Task 7: le sezioni "Chi propone" che vivevano qui sono
# uscite per intero, entrambe insieme al loro soggetto:
#
# - "Chi propone (1) — la Sentinella propone uno script" (Task 7):
#   `build_sentinel_script_proposal`/`propose_sentinel_script`
#   (watcher/sentinel_proposal.py) e `execute` (watcher/executor.py) sono
#   cancellati insieme al resto della Sentinella (guardiano/ragionatore/
#   esecutore) -- nessuna proposta automatica resta da confezionare.
# - "Chi propone (2) — la coverage-review propone solo cio' che e'
#   applicabile" (Task 5): `brain.suggestions.apply_suggestions`/
#   `SuggestionStore`/`brain.coverage_review.COVERAGE_REVIEW_SYSTEM` sono
#   cancellati insieme al Brain auto-proponente.
#
# Nessun successore per nessuna delle due -- resta solo "chi applica" sopra
# (`create_automation`/`is_automation_config`), la difesa che vale per
# qualunque proposta futura, non solo per quelle che questi due percorsi
# creavano.
