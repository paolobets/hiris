from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_agentbot_editor_is_its_own_route_on_the_kit():
    js = (BASE / "config" / "agentbot-editor.js").read_text(encoding="utf-8")
    assert "HirisAgentbotEditor" in js and "HirisEditorKit" in js
    assert "HirisEntityPicker" in js, "trigger/condizione/target devono usare il picker istanziabile"
    assert "api/agentbots" in js
    main = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/agentbots/" in main


def test_sentinel_page_no_longer_owns_agentbot_crud():
    js = (BASE / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "api/sentinel/policy" in js
    assert "buildAgentbotRow" not in js and "emptyLens" not in js
    # Task 5: nessuna scrittura (POST/PUT/DELETE) su api/agentbots -- resta
    # solo la GET di sola lettura per l'elenco di navigazione (link a
    # #/agentbots/{id}, nessun form/salvataggio inline). Il file non deve
    # più contenere alcun metodo di scrittura HTTP da nessuna parte.
    assert "'PUT'" not in js and "'DELETE'" not in js
    assert js.count("api('api/agentbots'") == 1, "una sola chiamata (GET, elenco navigazione), non piu' CRUD"


def test_new_agentbot_routes_registered_before_generic_id_route():
    main = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/agentbots/new" in main
    new_idx = main.index(r"#\/agentbots\/new")
    generic_idx = main.index(r"#\/agentbots\/([^/]+)$")
    assert new_idx < generic_idx, "il pattern /new deve essere registrato PRIMA di quello generico [^/]+, altrimenti lo intercetta"


def test_config_html_includes_agentbot_editor_script():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/agentbot-editor.js" in html


def test_editor_kit_field_factories_reintroduced_with_a_real_consumer():
    kit = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "field:" in kit or "field :" in kit
    editor = (BASE / "config" / "agentbot-editor.js").read_text(encoding="utf-8")
    assert "HirisEditorKit.field." in editor, "agentbot-editor.js deve consumare HirisEditorKit.field.*, non ricostruirlo privatamente"


# ── Agenti v1.1 Fase 2 Task 6: modalità obiettivo nell'editor ────────────
# Guardie di WIRING (testo sul sorgente). La copertura COMPORTAMENTALE reale
# — che cosa vede l'utente scegliendo la modalità obiettivo e che cosa parte
# nel payload — vive in tests/js/agentbot-editor.test.mjs (node --test +
# jsdom), per la Global Constraint "TEST FE REALI" del piano.
import re


def _editor_js() -> str:
    return (BASE / "config" / "agentbot-editor.js").read_text(encoding="utf-8")


def _wizard_js() -> str:
    return (BASE / "config" / "create-wizard.js").read_text(encoding="utf-8")


def _strip_js_comments(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"//[^\n]*", "", js)


def test_editor_build_payload_carries_mode_objective_and_perimeter():
    """Trappola dichiarata del task: buildPayload() costruisce un payload
    whitelistato DA ZERO. Senza `mode`/`objective`/`perimeter` un salvataggio
    dalla SPA riconvertirebbe in silenzio un agente-obiettivo in regola."""
    code = _strip_js_comments(_editor_js())
    start = code.index("function buildPayload(")
    builder = code[start:code.index("window.saveAgentbot", start)]
    for key in ("mode", "objective", "perimeter"):
        assert key in builder, f"buildPayload deve portare `{key}` o il salvataggio lo perde"


def test_perimeter_empty_selection_is_null_never_an_empty_array():
    """Convenzione unica della catena (watcher/agentbots.py::
    _validate_str_list): null = nessuna restrizione, [] = nega tutto. Sono
    OPPOSTI. Il builder del perimetro deve avere un ramo esplicito verso
    `null`, non cadere sul `[]` che l'editor Chatbot usa per l'altra
    convenzione."""
    code = _strip_js_comments(_editor_js())
    start = code.index("function buildPerimeter(")
    builder = code[start:code.index("function buildPayload(", start)]
    assert builder.count(": null") >= 2, (
        "allowed_entities e allowed_services devono avere un ramo esplicito verso null "
        "(interruttore spento = nessuna restrizione dichiarata)"
    )
    assert "checked" in builder, "il ramo null/elenco deve dipendere da un interruttore esplicito dell'utente"


def test_ui_says_the_perimeter_limits_reading_too():
    """Decisione esplicita di questa fase: `allowed_entities` filtra anche
    le LETTURE del ragionatore (tools/dispatcher.py), non solo le azioni.
    L'utente deve leggerlo nell'interfaccia, non scoprirlo dopo."""
    for js in (_editor_js(), _wizard_js()):
        # Nel sorgente l'apostrofo è escapato (`l\'agente`, stringa JS fra
        # apici singoli): confronto sul testo che l'utente legge davvero.
        js = js.replace("\\'", "'")
        assert "sia ciò che l'agente può toccare sia ciò che può vedere" in js
        assert "non è nemmeno leggibile" in js
        assert "confinato dal solo semaforo" in js, (
            "non dichiarare nulla significa «confinato dal solo semaforo», non «bloccato»"
        )


def test_max_tier_is_not_exposed_in_the_ui():
    """`max_tier` è nello schema ma NESSUN runtime lo onora (debito noto
    dichiarato della fase). Esporlo sarebbe una promessa falsa: omesso, il
    validatore applica da sé il default più stretto ("green"). Questa
    guardia va rimossa insieme al debito, non prima."""
    for js in (_editor_js(), _wizard_js()):
        code = _strip_js_comments(js)
        assert "max_tier" not in code, (
            "max_tier non deve comparire nel CODICE della UI finché nessun runtime lo onora"
        )


def test_objective_mode_never_declares_an_action_nor_an_event_trigger():
    """validate_agentbot RIGETTA l'intero Agentbot se un objective porta una
    `action` o un trigger a evento. Il ramo objective di buildPayload deve
    uscire prima di toccare l'azione."""
    code = _strip_js_comments(_editor_js())
    start = code.index("function buildPayload(")
    builder = code[start:code.index("window.saveAgentbot", start)]
    objective_branch = builder[builder.index("if (mode === 'objective')"):]
    assert "return payload;" in objective_branch.split("payload.action")[0], (
        "il ramo objective deve uscire PRIMA di scrivere payload.action"
    )
