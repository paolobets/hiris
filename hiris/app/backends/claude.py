from __future__ import annotations
from .base import LLMBackend


class ClaudeBackend(LLMBackend):
    """Thin wrapper around ClaudeRunner for simple (non-agentic) classification calls."""

    def __init__(self, runner: "ClaudeRunner") -> None:  # type: ignore[name-defined]
        self._runner = runner

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        return await self._runner.simple_chat(messages, system=system)
