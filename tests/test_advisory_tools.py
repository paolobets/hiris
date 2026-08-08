"""Test della definizione del tool che espone all'LLM le segnalazioni del Brain.

fetta E2 Task 8 ("escono i trentaquattro"): `get_advisories` (la funzione
esecutrice) e tutte le sue funzioni di supporto sono uscite -- orfane dal Task
7 (il `ToolDispatcher` che le chiamava e' uscito), nessun chiamante di
produzione le invocava piu': tutto cio' che questo file provava sul loro
comportamento (troncamento, filtro di perimetro, evidenza) non ha piu' un
soggetto -- cancellato, non spostato. `GET_ADVISORIES_TOOL_DEF` resta (la usa
`EVALUATION_ONLY_TOOLS`, claude_runner.py -- la Sentinella): le due prove
sulla sua forma restano con lei.
"""
from hiris.app.tools.advisory_tools import GET_ADVISORIES_TOOL_DEF


def test_tool_def_ha_i_campi_richiesti():
    assert GET_ADVISORIES_TOOL_DEF["name"] == "get_advisories"
    assert "description" in GET_ADVISORIES_TOOL_DEF
    props = GET_ADVISORIES_TOOL_DEF["input_schema"]["properties"]
    assert "severity" in props
    assert set(props["severity"]["enum"]) == {"high", "warn", "info"}
    assert GET_ADVISORIES_TOOL_DEF["input_schema"]["required"] == []


def test_tool_def_dichiara_il_troncamento_al_modello():
    # Senza questa istruzione il modello riferisce la lista tagliata come se
    # fosse completa, e l'utente conclude che i problemi siano meno di quanti sono.
    assert "truncated" in GET_ADVISORIES_TOOL_DEF["description"]


def test_tool_def_dichiara_il_filtro_di_perimetro():
    assert "filtered" in GET_ADVISORIES_TOOL_DEF["description"]


def test_tool_def_dichiara_il_troncamento_dell_evidenza():
    assert "evidence_truncated" in GET_ADVISORIES_TOOL_DEF["description"]
