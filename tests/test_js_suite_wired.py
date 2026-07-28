from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_js_test_suite_exists_and_is_ci_wired():
    assert (ROOT / "package.json").exists()
    assert list((ROOT / "tests" / "js").glob("*.test.mjs")), "nessun test JS comportamentale"
    ci = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "npm test" in ci, "i test JS devono girare in CI"


def test_js_deps_are_not_shipped_in_the_image():
    df = (ROOT / "hiris" / "Dockerfile").read_text(encoding="utf-8")
    assert "package.json" not in df and "node_modules" not in df
