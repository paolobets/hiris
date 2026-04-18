from __future__ import annotations

from typing import Any


class HAClient:
    """Home Assistant REST + WebSocket client. Stub — implementation in Phase 1."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token

    async def get_states(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def call_service(
        self,
        domain: str,
        service: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        raise NotImplementedError

    async def get_history(
        self,
        entity_ids: list[str],
        days: int = 1,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
