"""Test della definizione del tool di lettura sulla salute di Home Assistant.

fetta E2 Task 8 ("escono i trentaquattro"): `get_ha_health` (la funzione
esecutrice) e' uscita -- orfana dal Task 7 (il `ToolDispatcher` che la
chiamava e' uscito), nessun chiamante di produzione la invocava piu': i test
sul suo comportamento (inoltro delle sezioni al monitor, guasto senza
monitor) non hanno piu' un soggetto -- cancellati, non spostati.
`GET_HA_HEALTH_TOOL_DEF` resta (la usa `EVALUATION_ONLY_TOOLS`,
claude_runner.py -- la Sentinella): le prove sulla sua forma restano con lei.
"""
from hiris.app.tools.health_tools import GET_HA_HEALTH_TOOL_DEF


def test_tool_def_has_required_fields():
    assert GET_HA_HEALTH_TOOL_DEF["name"] == "get_ha_health"
    assert "sections" in GET_HA_HEALTH_TOOL_DEF["input_schema"]["properties"]


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
