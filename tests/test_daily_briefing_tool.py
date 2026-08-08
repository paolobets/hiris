"""Slice 7 (Maggiordomo) Task 5: on-demand chat tool `daily_briefing`.

fetta E2 Task 7 ("esce il dispatcher"): this file used to drive its
assertions through `ToolDispatcher.dispatch("daily_briefing", ...)`, which
is gone. Verifying what actually died for construction (checked by running
each test against the deleted class) showed the wrapper contributed exactly
two things of its own:

  1. `if self._knowledge_store is None: return "Il maggiordomo non ha
     accesso alla memoria..."` -- a pre-check with its own friendly text,
     bypassed entirely once the tool itself is unreachable. No successor
     reproduces this exact message; `build_briefing_bundle(None, ...)`
     already degrades to an empty bundle without raising on its own (see
     `test_none_store_and_cache_never_crash`,
     tests/test_briefing_bundle.py), so the underlying "never crashes on a
     missing store" guarantee survives there, just without this specific
     text.
  2. `allow_sensitive = bool(knowledge_allow_sensitive) and not bool(cloud)`
     -- a two-signal-to-one-bool translation specific to the on-demand chat
     tool. No other caller reproduces it (the scheduled `run_daily_briefing`
     gates on `LLMRouter.automatic_allows_sensitive()` instead), so it dies
     with the tool.

Everything else these tests exercised (deadline collection/horizon/owner
scoping, sensitive-obligation exclusion + counting, batteries sourced ONLY
from `advisory_store` -- never recalculated from the entity cache, dismissed
advisories never resurfacing, never-raises robustness, template rendering of
deadlines/home-status/sanitization) is `build_briefing_bundle` and
`render_briefing_template`'s OWN behaviour, already fully covered directly
against those two functions in tests/test_briefing_bundle.py and
tests/test_briefing_compose.py -- untouched by this task. Re-deriving the
same coverage a second time through a dead access path would be pure
duplication, so those tests were deleted rather than moved.

One assertion had no duplicate anywhere: `render_briefing_template`'s
rendering of a non-zero `hidden_sensitive` count into the butler's text
("Ci sono anche N scadenze riservate non mostrate qui.") was reached only
through this file. That one is kept below, calling
`build_briefing_bundle`/`render_briefing_template` directly instead of
through the dead dispatcher.

The two catalog-membership tests at the bottom never depended on
`ToolDispatcher` at all (module-level import aside) and are unchanged.
"""
from datetime import date, timedelta

from hiris.app.brain.briefing import build_briefing_bundle, render_briefing_template
from hiris.app.brain.knowledge_store import KnowledgeStore


def _due(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


def test_daily_briefing_shows_hidden_sensitive_count(tmp_path):
    """Fix C: when sensitive deadlines were withheld, the briefing text
    surfaces the hidden count as a trust signal."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")

    bundle = build_briefing_bundle(
        store, None, today=date.today(), allow_sensitive=False,
    )
    out = render_briefing_template(bundle)

    assert "1" in out
    assert "riservat" in out.lower()
    store.close()


def test_daily_briefing_tool_declared_in_chat_tool_schema():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, DAILY_BRIEFING_TOOL_DEF

    names = [t["name"] for t in ALL_TOOL_DEFS]
    assert "daily_briefing" in names
    assert DAILY_BRIEFING_TOOL_DEF in ALL_TOOL_DEFS
    # No required inputs — invocable with an empty/optional object.
    assert DAILY_BRIEFING_TOOL_DEF["input_schema"].get("required", []) == []


def test_daily_briefing_not_in_evaluation_only_tools():
    """Read-only chat tool, same treatment as recall_memory/save_memory:
    not exposed to non-chat evaluation agents (no llm_router there either,
    and evaluation agents don't need an on-demand butler summary)."""
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS

    assert "daily_briefing" not in EVALUATION_ONLY_TOOLS
