from __future__ import annotations
from abc import ABC, abstractmethod


class LLMBackend(ABC):
    @abstractmethod
    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Single LLM call with no tool loop. Returns text response."""
