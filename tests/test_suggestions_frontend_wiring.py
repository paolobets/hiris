from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_suggestions_section_present():
    js = (BASE / "config" / "sentinel-route.js").read_text(encoding="utf-8")
    assert "api/suggestions" in js
    assert "undo" in js
    assert "Suggerimenti del Brain" in js
