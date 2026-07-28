from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

def test_agentbot_route_js_exists_and_exposes_mount():
    js = (BASE / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "HirisAgentbotRoute" in js and "mount" in js
    # api/sentinel/policy and api/sentinel/timeline are OUT of the SP-4 Fase A
    # rename (Sentinella config/timeline, not the user-defined Agentbots) --
    # they must stay unchanged.
    assert "api/sentinel/policy" in js and "api/sentinel/timeline" in js

def test_config_html_includes_script_and_nav():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/agentbot-route.js" in html
    assert 'data-route="agentbots"' in html

def test_main_js_registers_route():
    js = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/agentbots" in js

def test_agentbot_route_has_situations_section():
    js = (BASE / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "situations" in js
    assert "hot_and_away" in js and "away_alarm_off" in js

def test_agentbot_route_has_preparation_section():
    js = (BASE / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "preparation" in js and "evening_arrival" in js
