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


def test_ronda_option_exited_with_the_ronda():
    """fetta E3 Task 4: `sentinel_ronda_min`/SENTINEL_RONDA_MINUTES lost their
    only Python reader here -- the job `hiris_sentinel_ronda`
    (`SituationEvaluator.run_evaluation`) that this option's interval fed is
    deleted along with the ronda itself. Same "un'opzione e' il suo percorso
    puntato" discipline applied to `bridge_fallback` in this task
    (test_bridge_options_wiring.py): a knob pointing at deleted code is a
    silent orphan, not a harmless leftover, so it exits config.yaml/run.sh/
    translations too, not just server.py's job registration. This test used
    to pin the option's presence; it now pins its absence."""
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    assert "sentinel_ronda_min" not in cfg["options"]
    assert "sentinel_ronda_min" not in cfg["schema"]
    sh = (BASE / "run.sh").read_text(encoding="utf-8")
    assert "SENTINEL_RONDA_MINUTES" not in sh
    for f in ("it.yaml", "en.yaml"):
        t = (BASE / "translations" / f).read_text(encoding="utf-8")
        assert "sentinel_ronda_min" not in t
