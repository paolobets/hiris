"""Regression guard for SP-4 Fase A Task 7 (front-end rename): every trace of
the pre-rename agent/sentinel/lens FE surface must be gone from
hiris/app/static/ -- routes, endpoints, globals, filenames. Mirrors the
task's Step 5 grep so a future edit that reintroduces a stray `api/agents`,
`#/sentinel`, etc. fails CI instead of silently 404ing the UI.

Deliberately NOT flagged (must stay, out of the SP-4 Fase A rename scope):
  - `api/sentinel/policy` / `api/sentinel/timeline` -- Sentinella detector
    config + timeline, distinct from the renamed user-defined Agentbots.
  - the `agent_id` wire key in the chat POST body / SSE "done" event --
    handlers_chat.py / claude_runner.py / openai_compat_runner.py still read
    and emit that literal key (unrelated to this FE-only task).
"""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

# Same shape as the task's regression grep:
#   grep -rnE "api/agents|api/lenses|#/agents|#/sentinel|HirisAgentEditor|
#               HirisAgentsList|HirisSentinelRoute|loadAgents\b" static/
#   | grep -viE "chatbots|agentbots"
_FORBIDDEN = re.compile(
    r"api/agents|api/lenses|#/agents|#/sentinel|"
    r"HirisAgentEditor|HirisAgentsList|HirisSentinelRoute|loadAgents\b"
)
_ALLOW_CONTEXT = re.compile(r"chatbots|agentbots", re.IGNORECASE)


def _iter_source_files():
    for ext in ("*.js", "*.html"):
        yield from STATIC.rglob(ext)


def test_no_pre_rename_agent_sentinel_traces_in_static():
    offenders = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN.search(line) and not _ALLOW_CONTEXT.search(line):
                offenders.append(f"{path.relative_to(STATIC)}:{lineno}: {line.strip()}")
    assert offenders == [], "stale pre-rename references found:\n" + "\n".join(offenders)


def test_renamed_fe_files_exist():
    cfg = STATIC / "config"
    for name in (
        "chatbot-editor.js", "chatbot-form.js", "chatbots-list.js", "agentbot-route.js",
    ):
        assert (cfg / name).is_file(), f"expected renamed file missing: {name}"
    for old in ("agent-editor.js", "agent-form.js", "agents-list.js", "sentinel-route.js"):
        assert not (cfg / old).exists(), f"pre-rename file still present: {old}"


def test_sentinel_config_timeline_routes_untouched():
    """Out-of-scope routes (Sentinella detector policy/timeline, not the
    renamed Agentbots) must still be reachable under their original path."""
    js = (STATIC / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "api/sentinel/policy" in js
    assert "api/sentinel/timeline" in js
