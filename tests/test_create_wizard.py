"""Wiring guard for SP-4 Fase B Task 6 (creazione goal-first).

Text-only guardia sul sorgente FE (il comportamento reale -- derivazione
del tipo, override, niente chiamate LLM, linea rossa E.2 sul payload
Agentbot -- è coperto dai test comportamentali reali in
tests/js/create-wizard.test.mjs, node --test + jsdom, per la Global
Constraint "TEST FE REALI" del piano). Qui si verifica solo il WIRING:
il modulo esiste ed è deterministico, config.html lo carica, main.js
registra #/nuovo, e le CTA di creazione puntano al wizard invece che
direttamente a #/chatbots/new.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"
CONFIG = BASE / "config"


def _read(name: str) -> str:
    return (CONFIG / name).read_text(encoding="utf-8")


def test_create_wizard_module_exists_and_exposes_deriveType():
    js = _read("create-wizard.js")
    assert "window.HirisCreateWizard" in js
    assert "mount" in js
    assert "deriveType" in js


def test_create_wizard_never_calls_an_llm_endpoint():
    """Deterministica, nessun LLM: l'unico vocabolario di endpoint nel file
    è la CRUD verso le entità (chatbots/agentbots) e la ricerca entità --
    mai un endpoint di reasoning/chat/modello.

    NB: "api/chat" è un prefisso di "api/chatbots" -- il controllo esclude
    esplicitamente quel caso, altrimenti si autofallirebbe sul nome
    dell'endpoint legittimo."""
    import re
    js = _read("create-wizard.js")
    assert not re.search(r"api/chat(?!bots)", js), "nessun endpoint di conversazione/reasoning (api/chat) -- solo CRUD entità"
    for token in ("api/reasoning", "api/brain", "/anthropic", "/openrouter"):
        assert token not in js, f"il wizard non deve mai referenziare un endpoint LLM/reasoning: {token}"
    # Endpoint effettivamente usati -- tutti CRUD entità o ricerca, nessun ragionamento.
    assert "api/chatbots" in js
    assert "api/agentbots" in js


def test_create_wizard_agentbot_payload_never_references_allowed_tools():
    """Enforcement strutturale della linea rossa E.2: il builder del payload
    Agentbot non deve MAI referenziare la chiave allowed_tools -- non deve
    esistere il vocabolario per introdurre tool liberi in un Agentbot."""
    js = _read("create-wizard.js")
    build_start = js.index("function buildAgentbotPayload")
    build_end = js.index("function", build_start + 1)
    agentbot_builder_src = js[build_start:build_end]
    assert "allowed_tools" not in agentbot_builder_src


def test_config_html_includes_create_wizard():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/create-wizard.js" in html
    # Deve caricare dopo i suoi prerequisiti dichiarati.
    assert html.index("config/editor-kit.js") < html.index("config/create-wizard.js")
    assert html.index("config/entity-picker.js") < html.index("config/create-wizard.js")
    assert html.index("config/templates.js") < html.index("config/create-wizard.js")


def test_main_js_registers_nuovo_route():
    js = _read("main.js")
    assert "#\\/nuovo" in js or "#/nuovo" in js
    assert "HirisCreateWizard.mount" in js


def test_main_js_keeps_chatbots_new_as_direct_advanced_path():
    """#/chatbots/new resta un ingresso valido e distinto (percorso diretto/
    avanzato), non un redirect verso il wizard."""
    js = _read("main.js")
    assert "chatbots\\/new" in js
    assert "HirisChatbotEditor.mount(null)" in js


def test_creation_ctas_point_at_the_wizard():
    dashboard = _read("dashboard.js")
    chatbots_list = _read("chatbots-list.js")
    assert "#/chatbots/new" not in dashboard, "le CTA di creazione in dashboard.js devono puntare al wizard (#/nuovo), non più direttamente a #/chatbots/new"
    assert "#/chatbots/new" not in chatbots_list, "le CTA di creazione in chatbots-list.js devono puntare al wizard (#/nuovo), non più direttamente a #/chatbots/new"
    assert "#/nuovo" in dashboard
    assert "#/nuovo" in chatbots_list


def test_guard_hoisted_to_main_js_and_removed_from_chatbot_editor():
    """T5 review (Minor): il guard di navigazione era installato dal
    top-level IIFE di chatbot-editor.js -- accoppiamento strutturale
    fragile. Task 6 lo hoista in main.js, comune a ogni route."""
    main_js = _read("main.js")
    chatbot_editor_js = _read("chatbot-editor.js")
    agentbot_editor_js = _read("agentbot-editor.js")
    assert "HirisEditorKit.dirty.guard(" in main_js
    assert "HirisEditorKit.dirty.guard(" not in chatbot_editor_js
    assert "HirisEditorKit.dirty.guard(" not in agentbot_editor_js


# ── Agenti v1.1 Fase 2 Task 6: modalità obiettivo nel wizard ────────────
def test_wizard_agentbot_payload_has_a_mode_branch():
    """Il wizard è il posto naturale per «obiettivo»: la missione scritta al
    passo 1 in linguaggio naturale È l'obiettivo. Il builder deve avere il
    ramo, altrimenti dal wizard si può creare solo una regola."""
    import re
    js = _read("create-wizard.js")
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    build_start = code.index("function buildAgentbotPayload")
    builder = code[build_start:code.index("function renderStep4", build_start)]
    for key in ("mode", "objective", "perimeter"):
        assert key in builder, f"buildAgentbotPayload deve saper produrre `{key}`"
    assert "allowed_tools" not in builder, (
        "LINEA ROSSA E.2: nemmeno il ramo obiettivo introduce il vocabolario dei tool liberi"
    )


def test_wizard_perimeter_empty_selection_is_null_never_an_empty_array():
    """buildChatbotPayload() manda `[]` per "nessuna selezione" — è la
    convenzione OPPOSTA a quella del perimetro (null = nessuna restrizione,
    [] = nega tutto). Ricopiarla qui farebbe nascere paralizzato ogni agente
    creato senza selezione."""
    import re
    js = _read("create-wizard.js")
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    build_start = code.index("function buildAgentbotPayload")
    builder = code[build_start:code.index("function renderStep4", build_start)]
    perimeter = builder[builder.index("payload.perimeter"):]
    assert "allowed_entities: state.agentbotPerimeterLimitEntities" in perimeter, (
        "il ramo null/elenco deve dipendere da un interruttore esplicito dell'utente"
    )
    assert ": null" in perimeter
    assert "allowed_entities: []" not in perimeter and "allowed_services: []" not in perimeter
