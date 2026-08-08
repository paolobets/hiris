"""Test della definizione del tool di lettura sulla cronologia degli eventi.

fetta E2 Task 8 ("escono i trentaquattro"): `get_logbook`/`render_template`
(le funzioni esecutrici) e tutte le loro funzioni di supporto sono uscite --
orfane dal Task 7 (il `ToolDispatcher` che le chiamava e' uscito), nessun
chiamante di produzione le invocava piu': tutto cio' che questo file provava
sul loro comportamento (validazione degli input, troncamento, filtro di
perimetro) non ha piu' un soggetto -- cancellato, non spostato.
`RENDER_TEMPLATE_TOOL_DEF` e' uscita con loro (non serve a
`EVALUATION_ONLY_TOOLS`, esclusa di proposito -- vedi il commento sulla
definizione superstite in diagnostics_tools.py). `GET_LOGBOOK_TOOL_DEF`
resta (la usa `EVALUATION_ONLY_TOOLS`): le prove sulla sua forma e sulla sua
registrazione restano con lei.
"""
from hiris.app.tools.diagnostics_tools import GET_LOGBOOK_TOOL_DEF, MAX_LOGBOOK_HOURS


def test_la_definizione_e_valida_e_dichiara_i_limiti():
    assert GET_LOGBOOK_TOOL_DEF["name"] == "get_logbook"
    props = GET_LOGBOOK_TOOL_DEF["input_schema"]["properties"]
    assert props["hours"]["maximum"] == MAX_LOGBOOK_HOURS
    assert props["hours"]["minimum"] == 1
    # entity_id e' FACOLTATIVO: la domanda "cosa e' successo ieri sera?" non ha
    # un'entita'.
    assert GET_LOGBOOK_TOOL_DEF["input_schema"].get("required", []) == []


def test_la_descrizione_del_logbook_istruisce_sul_troncamento():
    # Il taglio esiste solo se il modello lo riferisce: senza questa istruzione
    # l'LLM conclude "non e' successo altro".
    assert "truncated" in GET_LOGBOOK_TOOL_DEF["description"]


# --- registrazione: dove il tool e' raggiungibile, e dove no ----------------
# Concesso agli agenti locali (EVALUATION_ONLY_TOOLS) e al gateway MCP, dove
# la denylist di lettura pota la sua risposta. Il catalogo della UI
# (static/config/templates.js) e' JS e vive in tests/js/tool-catalog.test.mjs.

def test_registrato_nel_runner_con_il_gating_giusto():
    from hiris.app.claude_runner import EVALUATION_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    nomi = {t["name"] for t in EVALUATION_TOOL_DEFS}
    assert "get_logbook" in nomi
    # Decisione di sicurezza (render_template, gia' uscita da questo catalogo,
    # la documentava per contrasto): il logbook e' una lettura utile a un
    # sorvegliante, un template puo' leggere QUALUNQUE stato di Home Assistant
    # ed e' il vettore di prompt injection perfetto per un agente reattivo.
    assert "get_logbook" in EVALUATION_ONLY_TOOLS
    assert "render_template" not in EVALUATION_ONLY_TOOLS


def test_solo_il_logbook_fra_i_read_tools_del_gateway():
    # Stessa ragione: derive_execute_policy concede SEMPRE i READ_TOOLS, senza
    # opt-in per singolo tool, e le letture partono con allowed_entities=None.
    from hiris.app.api.handlers_gateway_policy import READ_TOOLS
    assert "get_logbook" in READ_TOOLS
    assert "render_template" not in READ_TOOLS


# La potatura della risposta del logbook (api/read_denylist.py) e' uscita con
# la Fetta E2 Task 4 insieme a tutta la superficie /api/execute che la
# consumava: il suo soggetto (prune_read_result) non esiste piu' in nessun
# file, quindi il test che lo pinnava qui e' stato rimosso, non spostato.
