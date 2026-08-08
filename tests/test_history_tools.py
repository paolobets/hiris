"""Test della definizione del tool di lettura sullo storico numerico/temporale.

fetta E2 Task 8 ("escono i trentaquattro"): `get_history` e tutte le sue
funzioni di supporto (validazione, aggregazione, downsampling) sono uscite --
orfane dal Task 7 (il `ToolDispatcher` che le chiamava e' uscito), nessun
chiamante di produzione le invocava piu': tutto cio' che questo file provava
sul loro comportamento non ha piu' un soggetto -- cancellato, non spostato.
`GET_HISTORY_TOOL_DEF` resta (la usa `EVALUATION_ONLY_TOOLS`, claude_runner.py
-- la Sentinella): la prova sulla sua registrazione resta con lei.
"""


def test_get_history_registered_in_runner():
    from hiris.app.claude_runner import EVALUATION_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    names = {t["name"] for t in EVALUATION_TOOL_DEFS}
    assert "get_history" in names
    assert "get_history" in EVALUATION_ONLY_TOOLS    # read-only, injection-safe
