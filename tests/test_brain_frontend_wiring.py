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


def test_dashboard_renders_advisory_severity_and_real_proposal_type():
    js = (BASE / "config" / "dashboard.js").read_text(encoding="utf-8")
    assert "severity" in js, "la home non distingue le segnalazioni per gravita'"
    assert "adv-card" in js, "le advisory devono avere una classe propria (non .prop-card)"
    assert "automazione HA" not in js or "TYPE_LABELS" in js or "p.type" in js, \
        "l'etichetta della proposta non deve essere hardcodata"
