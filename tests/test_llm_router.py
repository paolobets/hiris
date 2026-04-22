import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.backends.base import LLMBackend
from hiris.app.backends.ollama import OllamaBackend


def test_llm_backend_is_abstract():
    import inspect
    assert inspect.isabstract(LLMBackend)


@pytest.mark.asyncio
async def test_ollama_backend_simple_chat():
    backend = OllamaBackend(url="http://localhost:11434", model="llama3.2")
    mock_resp_data = {"message": {"content": '{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}'}}
    with patch("aiohttp.ClientSession") as MockSession:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.json = AsyncMock(return_value=mock_resp_data)
        ctx.raise_for_status = MagicMock()
        session_inst = MagicMock()
        session_inst.__aenter__ = AsyncMock(return_value=session_inst)
        session_inst.__aexit__ = AsyncMock(return_value=False)
        session_inst.post = MagicMock(return_value=ctx)
        MockSession.return_value = session_inst

        result = await backend.simple_chat([{"role": "user", "content": "classify"}])
        assert isinstance(result, str)
        assert "energy_meter" in result


from unittest.mock import patch
import json
from hiris.app.llm_router import LLMRouter


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    runner.chat = AsyncMock(return_value="response text")
    runner.run_with_actions = AsyncMock(return_value=("text", "OK", "action"))
    runner.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
    runner.last_tool_calls = []
    runner.total_input_tokens = 10
    runner.total_output_tokens = 5
    runner.total_requests = 1
    runner.total_cost_usd = 0.001
    runner.total_rate_limit_errors = 0
    runner.usage_last_reset = "2026-04-22T00:00:00Z"
    runner.get_agent_usage = MagicMock(return_value={"input_tokens": 10})
    runner.reset_agent_usage = MagicMock()
    runner.reset_usage = MagicMock()
    return runner


@pytest.mark.asyncio
async def test_router_chat_delegates_to_runner(mock_runner):
    router = LLMRouter(runner=mock_runner)
    result = await router.chat(user_message="hello", system_prompt="sys")
    mock_runner.chat.assert_awaited_once()
    assert result == "response text"


@pytest.mark.asyncio
async def test_router_classify_entities_no_local_uses_runner(mock_runner):
    router = LLMRouter(runner=mock_runner)
    entities = [{"id": "sensor.test", "state": "100", "name": "Test", "unit": "W"}]
    result = await router.classify_entities(entities)
    mock_runner.simple_chat.assert_awaited_once()
    assert "sensor.test" in result
    assert result["sensor.test"]["role"] == "energy_meter"


@pytest.mark.asyncio
async def test_router_classify_entities_uses_ollama_if_configured(mock_runner):
    router = LLMRouter(runner=mock_runner, local_model_url="http://localhost:11434", local_model_name="llama3.2")
    entities = [{"id": "sensor.test", "state": "100", "name": "Test", "unit": "W"}]
    with patch("hiris.app.llm_router.OllamaBackend") as MockOllama:
        mock_ollama = MagicMock()
        mock_ollama.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
        MockOllama.return_value = mock_ollama
        result = await router.classify_entities(entities)
    mock_ollama.simple_chat.assert_awaited_once()
    mock_runner.simple_chat.assert_not_awaited()


def test_router_proxies_usage_properties(mock_runner):
    router = LLMRouter(runner=mock_runner)
    assert router.total_input_tokens == 10
    assert router.last_tool_calls == []
