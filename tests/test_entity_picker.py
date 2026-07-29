from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_entity_picker_module_exists_and_is_instance_scoped():
    js = (BASE / "config" / "entity-picker.js").read_text(encoding="utf-8")
    assert "HirisEntityPicker" in js
    assert "create" in js
    # nessun id hardcoded del vecchio singleton
    for legacy_id in ("entity-chips", "entity-search", "entity-suggestions", "f-entities"):
        assert "'" + legacy_id + "'" not in js and '"' + legacy_id + '"' not in js, \
            f"{legacy_id}: il picker deve generare i propri id, non riusare quelli globali"
    # deve esporre destroy (per staccare il listener documento)
    assert "destroy" in js
    assert "api/entities" in js and "entities" in js and "entity_id" in js


def test_permessi_no_longer_owns_the_entity_selector():
    js = (BASE / "config" / "permessi.js").read_text(encoding="utf-8")
    assert "_entitySelectionSet" not in js, "il selettore singleton deve essere rimosso"


def test_config_html_includes_entity_picker():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/entity-picker.js" in html
