import pytest
from unittest.mock import MagicMock
from hiris.app.tools.health_tools import get_ha_health, GET_HA_HEALTH_TOOL_DEF


@pytest.fixture
def mock_monitor():
    m = MagicMock()
    m.get_snapshot = MagicMock(return_value={
        "system": {"ha_version": "2025.1.0"},
        "logs": {"errors": 0, "warnings": 1, "top_errors": []},
        "last_updated": "2026-04-30T08:00:00Z",
    })
    return m


def test_tool_def_has_required_fields():
    assert GET_HA_HEALTH_TOOL_DEF["name"] == "get_ha_health"
    assert "sections" in GET_HA_HEALTH_TOOL_DEF["input_schema"]["properties"]


def test_get_ha_health_passes_sections_to_monitor(mock_monitor):
    result = get_ha_health(mock_monitor, sections=["system", "logs"])
    mock_monitor.get_snapshot.assert_called_once_with(["system", "logs"])
    assert result["system"]["ha_version"] == "2025.1.0"


def test_get_ha_health_defaults_to_all(mock_monitor):
    result = get_ha_health(mock_monitor, sections=None)
    mock_monitor.get_snapshot.assert_called_once_with(["all"])


def test_tool_def_enum_include_le_sezioni_nuove():
    enum = GET_HA_HEALTH_TOOL_DEF["input_schema"]["properties"]["sections"]["items"]["enum"]
    assert "system_health" in enum
    assert "supervisor" in enum
    descrizione = GET_HA_HEALTH_TOOL_DEF["description"]
    assert "system_health" in descrizione
    assert "supervisor" in descrizione
    # Il troncamento va dichiarato all'LLM, altrimenti conclude che i problemi
    # siano meno di quanti sono.
    assert "truncated" in descrizione


def test_la_descrizione_non_promette_il_sottoinsieme_come_invariante():
    # Le segnalazioni del Brain e la sezione 'unavailable' derivano dallo stesso
    # fatto, ma sono lette in momenti diversi e le segnalazioni sono persistite:
    # un'entita' rientrata esce subito dall'elenco in tempo reale e resta
    # segnalata fino alla scansione successiva. In quella finestra il
    # sottoinsieme non vale, e un "always" scritto da noi fa riferire al modello
    # una cosa falsa con sicurezza. La relazione va descritta, non promessa.
    descrizione = GET_HA_HEALTH_TOOL_DEF["description"]
    assert "always a subset" not in descrizione
    # ...ma la relazione resta detta, altrimenti si e' solo tolta informazione.
    assert "subset" in descrizione
    # ...e la finestra in cui non vale e' dichiarata, con il rimedio: guardare
    # la sezione in tempo reale prima di dire all'utente che e' ancora giu'.
    assert "next scan" in descrizione


def test_get_ha_health_no_monitor_returns_error():
    result = get_ha_health(None, sections=["all"])
    assert "error" in result
