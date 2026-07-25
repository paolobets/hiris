"""Slice 7 (Maggiordomo) Task 5: on-demand chat tool `daily_briefing`.

Unlike the scheduled `run_daily_briefing` (server.py Task 4), which gates
`allow_sensitive` on `LLMRouter.automatic_allows_sensitive()`, the
ToolDispatcher has no llm_router/data_dir (see __init__). The tool result
here lands in the CHAT model's context, not the automatic backend chain
that gate measures, so `daily_briefing` builds the bundle FAIL-CLOSED
(`allow_sensitive=False`) unconditionally: sensitive deadlines are never
surfaced on-demand in chat (still counted in bundle["counts"]["hidden_sensitive"]).

It also returns the deterministic `render_briefing_template(bundle)` string
directly (no `compose_briefing`/LLM call): the chat model, already mid-reply,
narrates it itself. Read-only: no HA service call, no semaforo.
"""
from datetime import date, timedelta

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    pass


class _FakeEntityCache:
    """Minimal stand-in for EntityCache.all_states() — a LIST of flat dicts,
    same shape used by tests/test_briefing_bundle.py."""

    def __init__(self, states: list[dict] | None = None) -> None:
        self._states = states or []

    def all_states(self) -> list[dict]:
        return list(self._states)


def _due(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_daily_briefing_returns_nonempty_text_with_obligation(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI in scadenza",
                    due_date=_due(2), sensitivity="normal")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert out.strip() != ""
    assert "TARI in scadenza" in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_hides_sensitive_obligation_fail_closed(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert "Cartella clinica riservata" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_no_knowledge_store_returns_friendly_fallback():
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=None, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert out.strip() != ""


@pytest.mark.asyncio
async def test_daily_briefing_never_raises_when_entity_cache_broken(tmp_path):
    class _BrokenCache:
        def all_states(self):
            raise RuntimeError("boom")

    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Bolletta", due_date=_due(1),
                    sensitivity="normal")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_BrokenCache())

    out = await dispatcher.dispatch("daily_briefing", {})

    assert isinstance(out, str)
    assert "Bolletta" in out  # deadlines still surfaced despite home-status failure
    store.close()


def test_daily_briefing_tool_declared_in_chat_tool_schema():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, DAILY_BRIEFING_TOOL_DEF

    names = [t["name"] for t in ALL_TOOL_DEFS]
    assert "daily_briefing" in names
    assert DAILY_BRIEFING_TOOL_DEF in ALL_TOOL_DEFS
    # No required inputs — invocable with an empty/optional object.
    assert DAILY_BRIEFING_TOOL_DEF["input_schema"].get("required", []) == []


def test_daily_briefing_not_in_evaluation_only_tools():
    """Read-only chat tool, same treatment as recall_knowledge/save_knowledge:
    not exposed to non-chat evaluation agents (no llm_router there either,
    and evaluation agents don't need an on-demand butler summary)."""
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS

    assert "daily_briefing" not in EVALUATION_ONLY_TOOLS
