from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_kit_exists_with_shared_blocks():
    js = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "HirisEditorKit" in js
    for fn in ("modelSelect", "dirty", "saveBar", "checkGroup"):
        assert fn in js, f"il kit deve esporre {fn}"


def test_dirty_tracking_is_not_a_one_shot_snapshot():
    js = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "MutationObserver" in js or "addEventListener('change'" in js
    # il guard di navigazione deve esistere (perdita silenziosa di modifiche)
    assert "beforeunload" in js or "hashchange" in js


def test_models_fetch_is_cached_not_per_row():
    js = (BASE / "config" / "editor-kit.js").read_text(encoding="utf-8")
    assert "api/models" in js
    assert "cache" in js.lower() or "_modelsPromise" in js


def test_api_js_no_longer_owns_editor_code():
    """SP-4 Fase B Task 3 (C9): loadModels/_setModelValue sono codice editor
    dentro un file condiviso -- spostati nel kit, api.js resta utility pure."""
    js = (BASE / "config" / "api.js").read_text(encoding="utf-8")
    assert "function loadModels" not in js
    assert "function _setModelValue" not in js


def test_permessi_no_longer_owns_tool_action_checkboxes():
    """Assorbiti in HirisEditorKit.checkGroup (istanza-scoped, non piu'
    #tool-checks/#action-checks globali)."""
    js = (BASE / "config" / "permessi.js").read_text(encoding="utf-8")
    for fn in ("function buildToolChecks", "function buildActionChecks",
               "function getSelectedTools", "function getSelectedActions"):
        assert fn not in js, f"{fn} deve essere assorbita nel kit (checkGroup)"


def test_config_html_includes_editor_kit_before_consumers():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/editor-kit.js" in html
    consumers = ["config/permessi.js", "config/chatbot-form.js",
                 "config/chatbot-editor.js", "config/agentbot-route.js"]
    kit_pos = html.index("config/editor-kit.js")
    for c in consumers:
        assert kit_pos < html.index(c), f"editor-kit.js deve caricare prima di {c}"
