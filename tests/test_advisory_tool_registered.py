"""Il tool esiste solo se e' registrato: un punto mancante lo rende invisibile.

`get_advisories` va dichiarato in otto punti diversi (runner, dispatcher, UI,
gateway...). Asserire il NOME in ciascuno e' l'unica difesa contro il difetto
silenzioso: un catalogo pinnato solo sul conteggio resta verde se qualcuno
toglie questo tool e ne aggiunge un altro.

Il nono punto era il catalogo MCP (mcp/tiers.py), uscito con la Fetta E2 Task
3 insieme al server che lo esponeva -- MCP non e' piu' servito a Claude.

L'ottavo punto -- il catalogo della UI (static/config/templates.js) -- e' JS e
vive in tests/js/tool-catalog.test.mjs.
"""


def test_get_advisories_registered_in_runner():
    from hiris.app.claude_runner import EVALUATION_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    names = {t["name"] for t in EVALUATION_TOOL_DEFS}
    assert "get_advisories" in names
    assert "get_advisories" in EVALUATION_ONLY_TOOLS


def test_get_advisories_fra_i_read_tools_del_gateway():
    # READ_TOOLS e' la lista sempre concessa al gateway perche' non distruttiva.
    from hiris.app.api.handlers_gateway_policy import READ_TOOLS

    assert "get_advisories" in READ_TOOLS
