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
#
# Fix wave 1 -- la correzione stessa sovra-affermava in due punti, la stessa
# classe di difetto in scala minore: la descrizione di create_task prometteva
# un filtro piu' stretto del reale (vale sulle azioni di PRIMO LIVELLO) e i
# documenti descrivevano il semaforo come rete completa, mentre
# create_ha_config e' proprio cio' che non copre. Le guardie qui sotto ora
# coprono anche i documenti, che nessun test leggeva.
import re
from pathlib import Path

import pytest
from aiohttp import web

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app"
DOCS = Path(__file__).resolve().parents[1] / "docs"


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

    LIMITE DICHIARATO del parsing: riconosce il semaforo solo dalla chiamata
    letterale `self._gate(` dentro il ramo. Un gate futuro raggiunto per via
    indiretta -- un helper che chiama _gate al posto del ramo, un decoratore,
    un dispatch a tabella -- sfuggirebbe IN SILENZIO: l'insieme resterebbe non
    vuoto grazie ai rami attuali, quindi nemmeno l'assert `gated` sotto se ne
    accorgerebbe, e lo strumento nuovo risulterebbe "non gated" senza che
    nessuno lo dica. Chi introduce un percorso del genere deve aggiornare
    anche questa lettura.
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

# I soli tool del catalogo MCP la cui descrizione PUO' nominare un passaggio
# di conferma, perche' sul loro percorso ne esiste davvero uno:
#
#   call_service   -- api/handlers_execute.py instrada call_ha_service per
#                     tier e trattiene giallo/rosso in pending_approval.
#   create_task    -- non ha un gate sul proprio dispatch, ma allo scatto ogni
#                     sua azione call_ha_service ripassa dal semaforo e un
#                     tier giallo/rosso diventa step-up all'owner (task_engine
#                     478-497, pinnato da tests/test_task_engine.py::
#                     test_confirm_tier_task_action_requests_stepup_and_holds).
#   save_knowledge -- l'elemento nasce in stato `pending` e resta invisibile
#                     alle ricerche finche' l'utente non lo approva
#                     (tools/knowledge_tools.py::handle_save_knowledge).
#
# Ogni altra promessa di conferma in tiers.py sarebbe una rete dichiarata e
# assente.
_TOOL_MCP_CON_CONFERMA_VERA = {"call_service", "create_task", "save_knowledge"}

# La sola parola "conferma" non basta: la stessa promessa si scrive "richiede
# approvazione", "gate di sicurezza", "step-up", "autorizzazione". Un elenco
# piccolo di formulazioni copre i modi in cui una ToolDef puo' millantare una
# rete.
_FORMULAZIONI_DI_CONFERMA = (
    "conferma", "approva", "autorizzazione", "autorizza",
    "gate", "step-up", "stepup", "via libera", "benestare",
)

# Le stesse formulazioni in NEGATIVO sono affermazioni oneste -- "non richiede
# conferma", "senza approvazione", "nessun gate" -- ed e' proprio il testo che
# questo sprint vuole incoraggiare: vanno tolte prima di cercare, altrimenti
# la guardia boccerebbe la formulazione corretta.
_NEGAZIONE_RE = re.compile(
    r"\b(?:non|senza|nessun[aeio]?|niente|mai|priva di)\b"
    r"(?:\s+\w+){0,3}?\s+"
    r"(?:conferma\w*|approva\w*|autorizza\w*|gate\w*|step-?up|via libera|benestare)"
)


def _promette_conferma(descrizione: str) -> bool:
    """Vero se la descrizione promette al modello un passaggio di conferma."""
    testo = _NEGAZIONE_RE.sub(" ", descrizione.lower())
    return any(f in testo for f in _FORMULAZIONI_DI_CONFERMA)


def test_la_guardia_riconosce_le_formulazioni_equivalenti():
    """La guardia sotto vale quanto vale questo riconoscitore: se cercasse la
    sola parola "conferma", una promessa scritta altrimenti passerebbe."""
    for promessa in (
        "Richiede conferma (gate di sicurezza).",
        "Richiede approvazione dell'utente.",
        "Passa da un gate di sicurezza.",
        "Attiva uno step-up sull'owner.",
        "Serve l'autorizzazione del proprietario.",
    ):
        assert _promette_conferma(promessa), f"promessa non riconosciuta: {promessa!r}"
    for onesto in (
        "Non richiede conferma: e' il semaforo il limite.",
        "Viene eseguito senza approvazione umana.",
        "Nessun gate di sicurezza fra la chiamata e l'effetto.",
        "Elenca i task HIRIS pianificati.",
    ):
        assert not _promette_conferma(onesto), f"falso allarme su: {onesto!r}"


def test_nessuna_descrizione_mcp_promette_una_conferma_inesistente():
    from hiris.app.mcp.tiers import TOOLS

    bugiardi = {
        t.name for t in TOOLS
        if _promette_conferma(t.description)
    } - _TOOL_MCP_CON_CONFERMA_VERA
    assert not bugiardi, (
        f"promettono conferma senza attraversare alcun gate: {bugiardi}"
    )


def test_create_task_dichiara_il_perimetro_reale_del_filtro():
    """La vecchia asserzione ("verd" nella descrizione) era verde anche prima
    della correzione: la descrizione difettosa gia' nominava le entita' verdi,
    quindi non esercitava alcuna pressione. Qui si chiede cio' che PRIMA
    mancava -- che il filtro sia dichiarato valido sulle azioni di primo
    livello, che l'annidamento sia nominato, e che non si prometta l'assenza
    di passaggi umani (smentita allo scatto dallo step-up del task_engine)."""
    from hiris.app.mcp.tiers import get_tool

    desc = get_tool("create_task").description.lower()
    assert "verd" in desc
    assert "primo livello" in desc, "il filtro e' dichiarato piu' largo di quanto sia"
    assert "annidat" in desc, "l'annidamento sfugge al filtro e va detto"
    assert "nessun passaggio umano" not in desc, (
        "allo scatto un'azione non verde produce uno step-up: promessa smentita"
    )


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


class _DispatcherTask:
    """Dispatcher finto: registra le chiamate che superano il filtro."""

    def __init__(self):
        self.calls = []

    async def dispatch(self, name, inputs, **kw):
        self.calls.append((name, inputs))
        return {"task_id": "t9"}


def _app_create_task(tmp_path) -> web.Application:
    """App minima per /api/execute con create_task esposto e light.rosso rosso."""
    from hiris.app.api.handlers_execute import handle_execute

    app = web.Application()
    app["internal_token"] = "secret"
    app["data_dir"] = str(tmp_path)
    app["execute_policy"] = {
        "tools": ["create_task"],
        "tiers": {"light": "green"},
        "entity_tiers": {"light.rosso": "red"},
    }
    app["read_denylist"] = []
    app["tool_dispatcher"] = _DispatcherTask()
    app.router.add_post("/api/execute", handle_execute)
    return app


def _azione_rossa() -> dict:
    return {"type": "call_ha_service", "domain": "light", "service": "turn_on",
            "data": {"entity_id": "light.rosso"}}


@pytest.mark.asyncio
async def test_create_task_filtra_solo_le_azioni_di_primo_livello(aiohttp_client, tmp_path):
    """Pin della realta' che la descrizione ora racconta.

    Il filtro verde di handlers_execute (224-246) ispeziona le azioni di PRIMO
    LIVELLO. Un'azione non verde nascosta dentro un task annidato
    (create_task dentro create_task, ammesso da tools/dispatcher.py::
    _ALLOWED_TASK_ACTIONS e attuato da task_engine 513-521) non viene vista
    qui: e' fermata allo scatto dal semaforo del task_engine, che per un tier
    giallo/rosso chiede uno step-up all'owner. Non e' un varco sul semaforo,
    e' un messaggio d'errore peggiore -- lo stesso compromesso gia' accettato
    per allowed_entities in tools/dispatcher.py.

    Se un domani il filtro scendera' nell'annidamento, questo test cade e la
    descrizione MCP va riscritta insieme.
    """
    app = _app_create_task(tmp_path)
    client = await aiohttp_client(app)

    # Primo livello: l'azione rossa fa rifiutare il task, senza dispatch.
    resp = await client.post(
        "/api/execute",
        json={"tool": "create_task", "input": {
            "label": "diretto", "trigger": {"type": "delay", "minutes": 1},
            "actions": [_azione_rossa()]}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    assert (await resp.json())["result"]["ok"] is False
    assert app["tool_dispatcher"].calls == []

    # Stessa azione, annidata: passa il filtro e arriva al dispatcher.
    resp = await client.post(
        "/api/execute",
        json={"tool": "create_task", "input": {
            "label": "annidato", "trigger": {"type": "delay", "minutes": 1},
            "actions": [{"type": "create_task", "task": {
                "label": "figlio", "trigger": {"type": "delay", "minutes": 2},
                "actions": [_azione_rossa()]}}]}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    assert (await resp.json())["result"] == {"task_id": "t9"}
    assert len(app["tool_dispatcher"].calls) == 1


# ---------------------------------------------------------------------------
# Fix wave 1 -- cio' che i documenti dichiarano
# ---------------------------------------------------------------------------

# I quattro documenti che descrivono require_confirmation all'utente. Nessun
# test li leggeva, quindi il testo poteva derivare senza che nulla cadesse:
# e' successo proprio qui, con il semaforo presentato come rete completa.
_DOC_CONFERMA = ("come-funziona.md", "how-it-works.md", "casi-duso.md", "use-cases.md")

# Marcatori con cui un testo dichiara che la copertura ha un buco. Ne basta
# uno: la guardia verifica che l'eccezione sia DETTA, non come sia scritta.
_MARCATORI_ECCEZIONE = (
    "eccezione", "tranne", "salvo", "non copre", "non tocca",
    "except", "does not cover", "outside",
)


def _blocchi_su_require_confirmation(testo: str) -> list[str]:
    """Paragrafi (o righe di tabella) che parlano di require_confirmation."""
    return [b for b in re.split(r"\n\s*\n", testo) if "require_confirmation" in b]


def test_i_documenti_non_dichiarano_un_semaforo_piu_largo_del_vero():
    """create_ha_config e' esattamente cio' che il semaforo NON copre: dalla
    chat crea script e scene su Home Assistant subito. Un documento che
    presenta il semaforo come l'argine che regge da solo promette una rete
    piu' larga di quella che c'e'. Dove si nomina il semaforo, l'eccezione va
    nominata insieme."""
    for nome in _DOC_CONFERMA:
        testo = (DOCS / nome).read_text(encoding="utf-8")
        blocchi = _blocchi_su_require_confirmation(testo)
        assert blocchi, f"docs/{nome}: nessun blocco su require_confirmation, guardia da rivedere"
        for blocco in blocchi:
            basso = blocco.lower()
            if "semaforo" not in basso and "semaphore" not in basso:
                continue
            assert "create_ha_config" in basso and any(
                m in basso for m in _MARCATORI_ECCEZIONE
            ), (
                f"docs/{nome}: il semaforo e' presentato come rete completa senza "
                "dichiarare che create_ha_config ne resta fuori"
            )
