from __future__ import annotations
import logging
import aiohttp
from .base import LLMBackend

logger = logging.getLogger(__name__)


class OllamaBackend(LLMBackend):
    """OpenAI-compat chat completions via Ollama for low-complexity tasks."""

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/")
        self._model = model

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": self._model, "messages": msgs, "stream": False}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self._url}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("message", {}).get("content", "")
        except Exception as exc:
            logger.warning("OllamaBackend simple_chat failed: %s", exc)
            raise
