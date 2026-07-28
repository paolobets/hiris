from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_dashboard_wires_brain_endpoints():
    js = (BASE / "config" / "dashboard.js").read_text(encoding="utf-8")
    assert "api/brain/feed" in js
    assert "api/brain/advisories" in js
    assert "Stream ragionamenti" in js or "Ragionamenti" in js
    assert "/ack" in js and "/dismiss" in js
    assert "X-Requested-With" in js


def test_dashboard_keeps_proposals_and_onboarding():
    js = (BASE / "config" / "dashboard.js").read_text(encoding="utf-8")
    assert "api/proposals?status=pending" in js
    assert "renderEmpty" in js  # first-run onboarding preserved
