"""Slice 4 final-review backlog, closed out in Slice 4b Task 5.

Originariamente copriva due backlog:
1. ``LLMRouter.run_with_actions``'s all-backends-fail fallback (e il ramo
   explicit-model/no-runner-configured) return-shape 2-tupla.
2. ``_norm_policy``: a non-empty policy list that filters down to nothing
   (all names unknown) used to return ``[]`` instead of falling back to the
   strategy's default order, silently leaving the router with an empty
   backend chain.

fetta E3 Task 8: i tre test del backlog (1), su `run_with_actions`, sono
usciti insieme al metodo -- il suo unico chiamante (server.py's
`_llm_reason`, la Sentinella) e' uscito al Task 7 di questa fetta. Cancellati
e non spostati: il soggetto (la 2-tupla di ritorno di un metodo che non
esiste piu') non esiste da nessuna parte. Il backlog (2), `_norm_policy`,
resta intatto -- soggetto vivo, non toccato da questo task.

Real APIs verified before writing this test:
- ``hiris/app/llm_router.py``'s ``_norm_policy(policy, strategy)`` and
  ``_STRATEGY_ORDER`` module-level dict.
"""

from hiris.app.llm_router import _STRATEGY_ORDER, _norm_policy

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
