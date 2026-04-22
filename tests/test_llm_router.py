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
