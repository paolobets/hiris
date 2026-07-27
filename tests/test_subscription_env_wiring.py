import re, pathlib

RUN_SH = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "run.sh"


def test_run_sh_exports_oauth_token_and_config_dir():
    txt = RUN_SH.read_text(encoding="utf-8")
    assert re.search(r"export CLAUDE_CODE_OAUTH_TOKEN=\$\(bashio::config 'claude_code_oauth_token'", txt)
    assert "export CLAUDE_CONFIG_DIR=/data/claude" in txt
