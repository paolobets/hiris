"""Il tool esiste solo se e' registrato: un punto mancante lo rende invisibile.

`get_advisories` va dichiarato in nove punti diversi (runner, dispatcher, UI,
gateway, MCP...). Asserire il NOME in ciascuno e' l'unica difesa contro il
difetto silenzioso: un catalogo pinnato solo sul conteggio resta verde se
qualcuno toglie questo tool e ne aggiunge un altro.

Il nono punto -- il catalogo della UI (static/config/templates.js) -- e' JS e
vive in tests/js/tool-catalog.test.mjs.
"""


def test_get_advisories_registered_in_runner():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    names = {t["name"] for t in ALL_TOOL_DEFS}
    assert "get_advisories" in names
    assert "get_advisories" in EVALUATION_ONLY_TOOLS


def test_get_advisories_nel_registro_mcp():
    # tiers.py e' il catalogo esposto al gateway: qui il nome, il tool HIRIS
    # instradato e il tier di sola lettura.
    from hiris.app.mcp.tiers import TOOLS, Tier

    voci = {t.name: t for t in TOOLS}
    assert "get_advisories" in voci
    assert voci["get_advisories"].hiris_tool == "get_advisories"
    assert voci["get_advisories"].tier is Tier.READ


def test_get_advisories_fra_i_read_tools_del_gateway():
    # READ_TOOLS e' la lista sempre concessa al gateway perche' non distruttiva.
    from hiris.app.api.handlers_gateway_policy import READ_TOOLS

    assert "get_advisories" in READ_TOOLS
