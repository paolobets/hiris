from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_picker_present():
    js = (BASE / "config" / "sentinel-route.js").read_text(encoding="utf-8")
    assert "api/entities" in js and "device_class=temperature" in js
