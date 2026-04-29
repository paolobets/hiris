from __future__ import annotations
import logging
from urllib.parse import urlparse
import aiohttp
from .base import LLMBackend

logger = logging.getLogger(__name__)

_BLOCKED_HOSTS = frozenset({"169.254.169.254", "100.100.100.200", "metadata.google.internal"})
_DANGEROUS_PORTS = frozenset({22, 23, 25, 110, 143, 3306, 5432, 5672, 6379, 9200, 27017})


def _validate_ollama_url(url: str) -> None:
    """Raise ValueError if the URL is unsafe (non-http/https or points to a metadata endpoint)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"LOCAL_MODEL_URL must use http or https, got: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"LOCAL_MODEL_URL points to a blocked host: {host!r}")
    port = parsed.port
    if port is not None and port in _DANGEROUS_PORTS:
        logger.warning("LOCAL_MODEL_URL uses a dangerous port: %d", port)
        raise ValueError(f"LOCAL_MODEL_URL uses a dangerous port: {port}")


class OllamaBackend(LLMBackend):
    """OpenAI-compat chat completions via Ollama for low-complexity tasks."""

    def __init__(self, url: str, model: str) -> None:
        _validate_ollama_url(url)
        self._url = url.rstrip("/")
        self._model = model

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": self._model, "messages": msgs, "stream": False}
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self._url}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("message", {}).get("content", "")
        except Exception as exc:
            logger.warning("OllamaBackend simple_chat failed: %s", exc)
            raise
