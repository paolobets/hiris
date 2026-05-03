"""Regression tests for OpenAICompatRunner construction.

The 0.8.7 → 0.8.8 release passed `total=` to `httpx.Timeout`, which is not a
valid kwarg (httpx uses `timeout` as positional or `connect/read/write/pool`).
This crashed startup with `TypeError: Timeout.__init__() got an unexpected
keyword argument 'total'` whenever an OpenAI key or Ollama URL was configured.
"""
from unittest.mock import MagicMock

import httpx
import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner


@pytest.fixture
def dispatcher():
    return MagicMock()


def test_init_openai_cloud_does_not_raise(dispatcher, tmp_path):
    """Cloud variant (no fixed_model) must construct a valid httpx.Timeout."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "usage.json"),
    )
    assert isinstance(runner._client.timeout, httpx.Timeout)


def test_init_ollama_local_does_not_raise(dispatcher, tmp_path, monkeypatch):
    """Ollama variant (fixed_model set) must construct a valid httpx.Timeout."""
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "90")
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        dispatcher=dispatcher,
        fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "usage_ollama.json"),
    )
    assert isinstance(runner._client.timeout, httpx.Timeout)
