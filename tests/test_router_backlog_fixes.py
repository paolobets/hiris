"""Slice 4 final-review backlog, closed out in Slice 4b Task 5.

1. ``LLMRouter.run_with_actions``'s all-backends-fail fallback (and the
   explicit-model/no-runner-configured branch) used to return a 3-tuple
   (``"", None, None``), but the real runners (``claude_runner.run_with_actions``,
   ``openai_compat_runner.run_with_actions``) return a 2-tuple
   (``clean_text, structured``), and every real caller unpacks 2 values --
   e.g. ``agent_engine.py``'s ``result, structured = await
   self._claude_runner.run_with_actions(...)``. When every backend raised,
   the router's own fallback didn't match that contract and the 2-value
   unpack would raise ``ValueError: too many values to unpack``.
2. ``_norm_policy``: a non-empty policy list that filters down to nothing
   (all names unknown) used to return ``[]`` instead of falling back to the
   strategy's default order, silently leaving the router with an empty
   backend chain.

Real APIs verified before writing this test:
- ``hiris/app/claude_runner.py``'s ``run_with_actions`` returns
  ``clean_text, structured`` (grep: ``return clean_text, structured``).
- ``hiris/app/agent_engine.py`` (~line 899): ``result, structured = await
  asyncio.wait_for(self._claude_runner.run_with_actions(...), ...)``.
- ``hiris/app/llm_router.py``'s ``_norm_policy(policy, strategy)`` and
  ``_STRATEGY_ORDER`` module-level dict.
"""
import pytest

from hiris.app.llm_router import LLMRouter, _norm_policy, _STRATEGY_ORDER


class _AllFail:
    """Fake backend whose run_with_actions always raises -- exercises the
    router's own fallback return, not a real runner's."""

    async def run_with_actions(self, **kw):
        raise RuntimeError("backend down")


# ---------------------------------------------------------------------------
# (a) run_with_actions fallback / explicit-model-no-runner: 2-tuple contract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_with_actions_all_backends_fail_returns_2_tuple():
    router = LLMRouter(claude=_AllFail(), strategy="balanced")
    result, structured = await router.run_with_actions(
        user_message="hi", system_prompt="sys", model="auto",
    )
    assert isinstance(result, str) and "non disponibili" in result
    assert structured == {}


@pytest.mark.asyncio
async def test_run_with_actions_agent_engine_style_unpack_does_not_crash_when_all_backends_raise():
    """Mirrors agent_engine.py's real call shape: `result, structured = await
    self._claude_runner.run_with_actions(...)` with self._claude_runner being
    an LLMRouter whose only backend raises on every attempt."""
    router = LLMRouter(claude=_AllFail(), ollama=_AllFail(), strategy="balanced")
    # Must not raise ValueError: too many/not enough values to unpack.
    result, structured = await router.run_with_actions(
        user_message="[Agent trigger: test]", system_prompt="sys",
        model="auto", max_tokens=100,
        agent_type="agent",
    )
    assert isinstance(result, str) and result
    assert structured == {}


@pytest.mark.asyncio
async def test_run_with_actions_explicit_model_no_runner_returns_2_tuple():
    """model != 'auto' routes to a specific backend slot; when that slot is
    unconfigured (None), the router must still return a 2-tuple."""
    router = LLMRouter()  # no backends configured at all
    result, structured = await router.run_with_actions(
        user_message="hi", system_prompt="sys", model="claude-sonnet-4-6",
    )
    assert isinstance(result, str) and result
    assert structured == {}


# ---------------------------------------------------------------------------
# (b) _norm_policy: all-invalid non-empty list falls back to strategy order
# ---------------------------------------------------------------------------

def test_norm_policy_all_invalid_falls_back_to_strategy_order():
    assert _norm_policy(["bogus"], "balanced") == _STRATEGY_ORDER["balanced"]


def test_norm_policy_all_invalid_falls_back_for_cost_first():
    assert _norm_policy(["nope", "also_nope"], "cost_first") == _STRATEGY_ORDER["cost_first"]


def test_norm_policy_partial_valid_still_filters_not_fallback():
    """Unaffected case: a list with at least one valid name is filtered, not
    replaced by the strategy default."""
    assert _norm_policy(["bogus", "ollama"], "balanced") == ["ollama"]


def test_norm_policy_none_falls_back_to_strategy_order():
    assert _norm_policy(None, "balanced") == _STRATEGY_ORDER["balanced"]


def test_norm_policy_empty_list_falls_back_to_strategy_order():
    assert _norm_policy([], "balanced") == _STRATEGY_ORDER["balanced"]
