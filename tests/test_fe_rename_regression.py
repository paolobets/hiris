"""Regression guard for SP-4 Fase A Task 7 (front-end rename): every trace of
the pre-rename agent/sentinel/lens FE surface must be gone from
hiris/app/static/ -- routes, endpoints, globals, filenames. Mirrors the
task's Step 5 grep so a future edit that reintroduces a stray `api/agents`,
`#/sentinel`, etc. fails CI instead of silently 404ing the UI.

Deliberately NOT flagged (must stay, out of the SP-4 Fase A rename scope):
  - the `agent_id` wire key in the chat POST body / SSE "done" event --
    handlers_chat.py / claude_runner.py / openai_compat_runner.py still read
    and emit that literal key (unrelated to this FE-only task).

Boundary moved for v1.1 (Fase 1, Task 5, 2026-07-29): this guard was written
in the 1.0 rename to keep the codebase from drifting *back* to the
pre-rename "agent" naming. Agenti v1.1 now moves the naming *forward* onto
"agent" on purpose -- it unifies Chatbot + Agentbot into a single "Agente"
entity with two modes (rule/objective) -- so a guard that still forbade the
bare "agent editor" name would fight the new architecture instead of
protecting it. `HirisAgentEditor` / `agent-editor.js` were released below
for that reason. No FE file is renamed in this task (Fase 1 is
schema/wire-only); this only removes the future roadblock. Everything else
here still names a genuinely retired concept (the pre-rename raw "agents"
list/route, the separate "lenses" surface, the absorbed Sentinel route) and
stays forbidden.
"""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

# Same shape as the task's regression grep:
#   grep -rnE "api/agents|api/lenses|#/agents|#/sentinel|
#               HirisAgentsList|HirisSentinelRoute|loadAgents\b" static/
#   | grep -viE "chatbots|agentbots"
#
# `HirisAgentEditor` was removed from this list in v1.1 Fase 1 Task 5: the
# rename direction reversed on purpose (unified "Agente" entity, two modes)
# and this token is the JS global name of the editor v1.1 will reuse -- see
# the module docstring. It is not a typo or an oversight; do not re-add it.
_FORBIDDEN = re.compile(
    r"api/agents|api/lenses|#/agents|#/sentinel|"
    r"HirisAgentsList|HirisSentinelRoute|loadAgents\b"
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


# fetta E5 Task 6: gli altri due casi di questo file sono usciti col loro
# soggetto. `test_renamed_fe_files_exist` elencava chatbot-editor.js /
# chatbots-list.js / agentbot-route.js, cancellati insieme alle rotte che
# chiamavano; `test_sentinel_config_timeline_routes_untouched` leggeva
# agentbot-route.js per verificare che `api/sentinel/policy` e
# `api/sentinel/timeline` restassero raggiungibili -- entrambe uscite dal
# backend fra la E3 e la E4, e il file che le chiamava e' uscito qui.
# La guardia sopra resta, e diventa piu' forte: il suo soggetto e' TUTTO
# static/, che ora e' piu' piccolo e non deve riacquisire nessuno di quei nomi.
