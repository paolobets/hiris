import pathlib
DF = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "Dockerfile"


def test_dockerfile_installs_node_and_claude_cli():
    txt = DF.read_text(encoding="utf-8")
    assert "nodejs" in txt and "npm" in txt
    assert "@anthropic-ai/claude-code" in txt
    for pkg in ("libgcc", "libstdc++", "ripgrep"):
        assert pkg in txt, pkg
    assert "USE_BUILTIN_RIPGREP=0" in txt
