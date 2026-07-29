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
