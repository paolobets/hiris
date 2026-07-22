"""Test bridge options wiring: config.yaml, run.sh, translations."""
from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parents[1] / "hiris"


def test_bridge_options():
    """Verify bridge options are properly wired end-to-end."""
    # Test 1: config.yaml has bridge options and schema
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    assert "bridge_enabled" in cfg["options"], "bridge_enabled not in config.yaml options"
    assert "bridge_deadline_min" in cfg["options"], "bridge_deadline_min not in config.yaml options"
    assert "bridge_fallback" in cfg["options"], "bridge_fallback not in config.yaml options"

    assert "bridge_enabled" in cfg["schema"], "bridge_enabled not in config.yaml schema"
    assert "bridge_deadline_min" in cfg["schema"], "bridge_deadline_min not in config.yaml schema"
    assert "bridge_fallback" in cfg["schema"], "bridge_fallback not in config.yaml schema"

    # Test 2: run.sh exports bridge env vars
    sh = (BASE / "run.sh").read_text(encoding="utf-8")
    assert "BRIDGE_ENABLED" in sh, "BRIDGE_ENABLED not exported in run.sh"
    assert "BRIDGE_DEADLINE_MIN" in sh, "BRIDGE_DEADLINE_MIN not exported in run.sh"
    assert "BRIDGE_FALLBACK" in sh, "BRIDGE_FALLBACK not exported in run.sh"

    # Test 3: translations contain bridge_enabled
    it_content = (BASE / "translations" / "it.yaml").read_text(encoding="utf-8")
    en_content = (BASE / "translations" / "en.yaml").read_text(encoding="utf-8")
    assert "bridge_enabled" in it_content, "bridge_enabled not in it.yaml"
    assert "bridge_enabled" in en_content, "bridge_enabled not in en.yaml"
