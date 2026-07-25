"""Slice 7 (Maggiordomo) Task 5: on-demand chat tool `daily_briefing`.

Unlike the scheduled `run_daily_briefing` (server.py Task 4), which gates
`allow_sensitive` on `LLMRouter.automatic_allows_sensitive()`, the dispatch()
call for `daily_briefing` gates `allow_sensitive` on the SAME two signals
`recall_knowledge` already uses: the per-agent `knowledge_allow_sensitive`
config and whether the current chat backend is `cloud`. Sensitive deadlines
are surfaced only when the agent config allows it AND the backend is local
(not cloud) -- fail-closed whenever either signal says otherwise (still
counted in bundle["counts"]["hidden_sensitive"] regardless of visibility).

The battery threshold uses the saved `detectors.battery.min_pct` policy when
the dispatcher was constructed with a `data_dir` (via watcher.policy.load_policy),
falling back to build_briefing_bundle's default when there is none.

It also returns the deterministic `render_briefing_template(bundle)` string
directly (no `compose_briefing`/LLM call): the chat model, already mid-reply,
narrates it itself. Read-only: no HA service call, no semaforo.
"""
from datetime import date, timedelta

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.watcher.policy import save_policy


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


@pytest.mark.asyncio
async def test_daily_briefing_shows_sensitive_when_allowed_and_local(tmp_path):
    """Fix A: sensitive deadlines are surfaced when BOTH the per-agent config
    allows them AND the chat backend is local (cloud=False) — mirrors
    recall_knowledge's allow_sensitive model."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=True, cloud=False,
    )

    assert "Cartella clinica riservata" in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_hides_sensitive_when_cloud_even_if_allowed(tmp_path):
    """Fix A: cloud=True fails closed even when the agent config allows
    sensitive content — locality gate wins."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=True, cloud=True,
    )

    assert "Cartella clinica riservata" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_hides_sensitive_when_not_allowed_even_if_local(tmp_path):
    """Fix A: local backend alone isn't enough — the agent config must also
    allow sensitive content, else it stays hidden."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=False, cloud=False,
    )

    assert "Cartella clinica riservata" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_honors_saved_battery_threshold(tmp_path):
    """Fix B: when the dispatcher has a data_dir, the saved
    detectors.battery.min_pct policy is loaded and used instead of the
    default threshold — a battery at 40% is only flagged once the saved
    threshold (50) is honored."""
    data_dir = str(tmp_path / "data")
    save_policy(data_dir, {"detectors": {"battery": {"min_pct": 50}}})
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    cache = _FakeEntityCache([
        {"id": "sensor.batteria_z", "state": "40", "name": "z", "unit": "%",
         "domain": "sensor", "device_class": "battery"},
    ])
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=cache,
                                 data_dir=data_dir)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert "z" in out
    assert "40" in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_without_data_dir_falls_back_to_default_threshold(tmp_path):
    """Fix B: with no data_dir configured, a battery at 40% must NOT be
    flagged against the default threshold (20) — same entity/state as the
    saved-threshold test above, opposite outcome, proving the policy is
    actually being loaded rather than always applied."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    cache = _FakeEntityCache([
        {"id": "sensor.batteria_z", "state": "40", "name": "z", "unit": "%",
         "domain": "sensor", "device_class": "battery"},
    ])
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=cache)

    out = await dispatcher.dispatch("daily_briefing", {})

    assert "40" not in out
    store.close()


@pytest.mark.asyncio
async def test_daily_briefing_shows_hidden_sensitive_count(tmp_path):
    """Fix C: when sensitive deadlines were withheld, the briefing text
    surfaces the hidden count as a trust signal."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="Cartella clinica riservata",
                    due_date=_due(1), sensitivity="sensitive")
    dispatcher = ToolDispatcher(_FakeHA(), notify_config={},
                                 knowledge_store=store, entity_cache=_FakeEntityCache())

    out = await dispatcher.dispatch(
        "daily_briefing", {}, knowledge_allow_sensitive=False, cloud=True,
    )

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
    """Read-only chat tool, same treatment as recall_knowledge/save_knowledge:
    not exposed to non-chat evaluation agents (no llm_router there either,
    and evaluation agents don't need an on-demand butler summary)."""
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS

    assert "daily_briefing" not in EVALUATION_ONLY_TOOLS
