from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

def test_models_route_js_exists_and_exposes_mount():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "HirisModelsRoute" in js and "mount" in js
    assert "api/models/config" in js

def test_config_html_includes_script_and_nav():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/models-route.js" in html
    assert 'data-route="models"' in html

def test_main_js_registers_route():
    js = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/models" in js
    assert "'models'" in js  # updateNavActive branch

def test_models_route_has_four_sections():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "Provider attivi" in js
    assert "Catena automatica" in js
    assert "Assegnazione per entità" in js
    assert "Embeddings" in js

def test_models_route_puts_full_config_object():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    # Every write to /api/models/config must send the full {chain_order,
    # brain_model, provider_models} object (never a partial patch) --
    # the backend replaces the whole file on PUT.
    assert "JSON.stringify(state.cfg)" in js
    assert "api/agents/" in js  # per-Chatbot model uses a separate endpoint
