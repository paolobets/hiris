# tests/test_coerenza_conferma.py — sprint coerenza, A5 + A6.
#
# Due difetti di SICUREZZA PERCEPITA: HIRIS dichiarava una rete di protezione
# piu' larga di quella che ha. Chi si fida agisce con meno cautela di quanta
# ne servirebbe, quindi una promessa non mantenuta e' peggio di nessuna
# promessa.
#
# A5 — l'opzione "richiedi conferma" di un Chatbot nominava il solo
# call_ha_service, mentre altri quattro strumenti attuano davvero. Il
# meccanismo e' una ISTRUZIONE nel system prompt (claude_runner.py e
# backends/openai_compat_runner.py la accodano ai system blocks): non c'e'
# alcun controllo nel codice che la faccia rispettare. Il controllo nel
# codice esiste, ma e' un altro meccanismo -- il semaforo
# (tools/dispatcher.py::_gate) -- e non copre create_ha_config, che scrive
# subito su Home Assistant. Le guardie qui sotto tengono allineati i due
# elenchi: cio' che il modello legge e cio' che il codice attua.
#
# A6 — mcp/tiers.py descriveva create_task e cancel_task come "richiede
# conferma", ma api/handlers_execute.py li dispaccia senza alcun gate. Il
# limite reale su create_task esiste ed e' un altro: le sue azioni
# call_ha_service devono essere verdi per-entita' (handlers_execute:224-246,
# gia' coperto da tests/test_execute_api.py). Le guardie qui sotto vietano
# che una descrizione MCP prometta una conferma a un tool che non la
# attraversa.
import re
from pathlib import Path

import pytest
from aiohttp import web

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app"


def _strip_js_comments(js: str) -> str:
    """Toglie i commenti /* */ e // prima di ogni assert: le guardie devono
    leggere il CODICE, non la prosa che lo descrive."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    js = re.sub(r"//[^\n]*", "", js)
    return js


# ---------------------------------------------------------------------------
# A5 — cio' che l'opzione "richiedi conferma" dice al modello
# ---------------------------------------------------------------------------

def test_prompt_conferma_nomina_ogni_strumento_coperto():
    from hiris.app.claude_runner import (
        CONFIRMATION_COVERED_TOOLS,
        REQUIRE_CONFIRMATION_PROMPT,
    )

    for tool in CONFIRMATION_COVERED_TOOLS:
        assert tool in REQUIRE_CONFIRMATION_PROMPT, (
            f"{tool} e' dichiarato coperto ma non compare nel testo che il "
            "modello riceve"
        )


def test_copertura_conferma_include_i_cinque_strumenti_che_attuano():
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    assert set(CONFIRMATION_COVERED_TOOLS) == {
        "call_ha_service",
        "trigger_automation",
        "toggle_automation",
        "set_input_helper",
        "create_ha_config",
    }


def _tool_con_gate_semaforo() -> set[str]:
    """Nomi dei tool che nel dispatcher attraversano il semaforo (_gate).

    Legge il sorgente invece di importarlo perche' i rami sono dentro una
    catena di `if name == "..."` in un'unica funzione: non esiste una tabella
    da interrogare a runtime.
    """
    src = (BASE / "tools" / "dispatcher.py").read_text(encoding="utf-8")
    corrente = None
    trovati: set[str] = set()
    for line in src.splitlines():
        m = re.search(r'if name == "([a-z_]+)"', line)
        if m:
            corrente = m.group(1)
        elif "self._gate(" in line and corrente:
            trovati.add(corrente)
    return trovati


def test_ogni_tool_gated_dal_semaforo_e_anche_coperto_dalla_conferma():
    """Anti-deriva: se domani un nuovo strumento passa dal semaforo, deve
    entrare anche nell'elenco che l'opzione dichiara di coprire."""
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    gated = _tool_con_gate_semaforo()
    assert gated, "nessun ramo con self._gate trovato: guardia da rivedere"
    mancanti = gated - set(CONFIRMATION_COVERED_TOOLS)
    assert not mancanti, f"strumenti che attuano ma fuori dalla conferma: {mancanti}"


def test_create_ha_config_e_coperto_pur_non_avendo_semaforo():
    """create_ha_config scrive script e scene su HA immediatamente
    (dispatcher: apply_ha_config, nessun _gate): e' proprio lo strumento per
    cui la conferma dell'utente e' l'unico passaggio prima dell'effetto."""
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    assert "create_ha_config" in CONFIRMATION_COVERED_TOOLS
    assert "create_ha_config" not in _tool_con_gate_semaforo()


def test_backend_openai_usa_lo_stesso_testo_di_conferma():
    """Un secondo runner con un testo proprio farebbe divergere la copertura
    a seconda del provider scelto."""
    src = (BASE / "backends" / "openai_compat_runner.py").read_text(encoding="utf-8")
    assert "REQUIRE_CONFIRMATION_PROMPT" in src
    assert "Proposta:" not in src, "testo di conferma duplicato nel backend OpenAI"


def test_editor_chatbot_dichiara_cosa_copre_la_conferma():
    """La descrizione che l'utente legge deve nominare gli stessi strumenti
    del prompt e dire che e' un'istruzione al modello, non un blocco."""
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    js = _strip_js_comments(
        (BASE / "static" / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    )
    for tool in CONFIRMATION_COVERED_TOOLS:
        assert tool in js, f"l'editor non dice all'utente che {tool} e' coperto"
    assert "istruzione al modello" in js, (
        "l'editor non dichiara che la conferma e' un'istruzione, non un blocco tecnico"
    )


# ---------------------------------------------------------------------------
# A6 — cio' che le descrizioni MCP promettono al modello
# ---------------------------------------------------------------------------

# L'UNICO tool del catalogo MCP che attraversa davvero un gate di conferma:
# api/handlers_execute.py instrada call_ha_service per tier e trattiene
# giallo/rosso in pending_approval. Ogni altra promessa di conferma in
# tiers.py sarebbe una rete dichiarata e assente.
_TOOL_MCP_CON_CONFERMA_VERA = {"call_service"}


def test_nessuna_descrizione_mcp_promette_una_conferma_inesistente():
    from hiris.app.mcp.tiers import TOOLS

    bugiardi = {
        t.name for t in TOOLS
        if "conferma" in t.description.lower()
    } - _TOOL_MCP_CON_CONFERMA_VERA
    assert not bugiardi, (
        f"promettono conferma senza attraversare alcun gate: {bugiardi}"
    )


def test_create_task_dichiara_il_vincolo_reale_del_semaforo():
    """Il limite su create_task esiste, ma e' il verde per-entita', non una
    conferma: la descrizione deve dire quello."""
    from hiris.app.mcp.tiers import get_tool

    desc = get_tool("create_task").description.lower()
    assert "verd" in desc


@pytest.mark.asyncio
async def test_cancel_task_viene_dispacciato_senza_gate(aiohttp_client):
    """Pin della realta' che la descrizione ora racconta: cancel_task va
    diritto al dispatcher. Se un domani gli si costruisce davvero un gate,
    questo test cade e la descrizione va riscritta insieme."""
    from hiris.app.api.handlers_execute import handle_execute

    class _FakeDispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, name, inputs, **kw):
            self.calls.append((name, inputs))
            return {"ok": True}

    app = web.Application()
    app["internal_token"] = "secret"
    app["execute_policy"] = {"tools": ["cancel_task"]}
    app["read_denylist"] = []
    app["tool_dispatcher"] = _FakeDispatcher()
    app.router.add_post("/api/execute", handle_execute)

    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "cancel_task", "input": {"task_id": "t1"}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["result"] == {"ok": True}
    assert app["tool_dispatcher"].calls == [("cancel_task", {"task_id": "t1"})]
