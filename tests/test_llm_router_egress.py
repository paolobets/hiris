"""Slice 6b Task 1: deterministic egress gate on LLMRouter.

automatic_allows_sensitive() must return True only when the automatic
routing chain, restricted to AVAILABLE backends, is non-empty AND every
available backend in it is local (no cloud fallback possible).
"""
import pytest
from hiris.app.llm_router import LLMRouter


class _R:
    """Minimal fake backend runner (mirrors tests/test_llm_router_policies.py)."""

    def __init__(self, name):
        self.name = name


def test_only_ollama_available_allows_sensitive():
    r = LLMRouter(ollama=_R("ollama"), automatic_policy=["ollama"])
    assert r.automatic_allows_sensitive() is True


def test_ollama_and_claude_both_available_blocks_sensitive():
    r = LLMRouter(
        ollama=_R("ollama"), claude=_R("claude"),
        automatic_policy=["ollama", "claude"],
    )
    assert r.automatic_allows_sensitive() is False


def test_only_claude_available_blocks_sensitive():
    r = LLMRouter(claude=_R("claude"), automatic_policy=["claude"])
    assert r.automatic_allows_sensitive() is False


def test_no_backend_available_blocks_sensitive():
    r = LLMRouter()
    assert r.automatic_allows_sensitive() is False


def test_ollama_primary_with_claude_fallback_still_blocks():
    # ollama first in the policy, but claude is also registered and would
    # be tried on fallback if ollama fails -> still unsafe.
    r = LLMRouter(
        ollama=_R("ollama"), claude=_R("claude"),
        automatic_policy=["claude", "ollama"],
    )
    assert r.automatic_allows_sensitive() is False


def test_unregistered_cloud_backend_in_policy_is_not_considered_available():
    # claude is listed in the policy but never registered (None) -> it is
    # not "available", so it must not block sensitivity.
    r = LLMRouter(ollama=_R("ollama"), automatic_policy=["ollama", "claude"])
    assert r.automatic_allows_sensitive() is True


def test_openai_and_openrouter_are_treated_as_cloud():
    r = LLMRouter(openai=_R("openai"), automatic_policy=["openai"])
    assert r.automatic_allows_sensitive() is False
    r2 = LLMRouter(openrouter=_R("openrouter"), automatic_policy=["openrouter"])
    assert r2.automatic_allows_sensitive() is False


def test_registered_cloud_backend_absent_from_policy_still_allows():
    # claude IS registered but is NOT in the automatic policy, so it can
    # never receive an automatic fallback call -> it must not block.
    r = LLMRouter(
        ollama=_R("ollama"), claude=_R("claude"),
        automatic_policy=["ollama"],
    )
    assert r.automatic_allows_sensitive() is True


def test_never_crashes_with_empty_policy_and_no_backends():
    r = LLMRouter(automatic_policy=[])
    assert r.automatic_allows_sensitive() is False
