from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

def test_sentinel_route_js_exists_and_exposes_mount():
    js = (BASE / "config" / "sentinel-route.js").read_text(encoding="utf-8")
    assert "HirisSentinelRoute" in js and "mount" in js
    assert "api/sentinel/policy" in js and "api/sentinel/timeline" in js

def test_config_html_includes_script_and_nav():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/sentinel-route.js" in html
    assert 'data-route="sentinel"' in html

def test_main_js_registers_route():
    js = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/sentinel" in js
