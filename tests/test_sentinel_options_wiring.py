from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parents[1] / "hiris"


def test_config_yaml_has_sentinel_options():
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    assert "sentinel_daily_cap" in cfg["options"]
    assert "sentinel_daily_cap" in cfg["schema"]


def test_run_sh_exports_env():
    sh = (BASE / "run.sh").read_text(encoding="utf-8")
    assert "SENTINEL_DAILY_CAP" in sh and "SENTINEL_COOLDOWN_SEC" in sh


def test_translations_present():
    for f in ("it.yaml", "en.yaml"):
        t = (BASE / "translations" / f).read_text(encoding="utf-8")
        assert "sentinel_daily_cap" in t


def test_ronda_option_wired():
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    assert "sentinel_ronda_min" in cfg["options"] and "sentinel_ronda_min" in cfg["schema"]
    sh = (BASE / "run.sh").read_text(encoding="utf-8")
    assert "SENTINEL_RONDA_MINUTES" in sh
