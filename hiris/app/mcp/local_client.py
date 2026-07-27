from __future__ import annotations
import logging
import aiohttp

logger = logging.getLogger(__name__)


class LocalExecuteClient:
    """Inoltra i tool MCP alla execute-API di HIRIS su loopback, riusando
    allowlist + semaforo + provenienza server-side. Nessun OAuth: l'auth e'
    l'internal token, la raggiungibilita' e' solo 127.0.0.1."""

    def __init__(self, base_url: str, internal_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = internal_token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def execute(self, tool: str, inputs: dict) -> dict:
        headers = {"X-HIRIS-Internal-Token": self._token} if self._token else {}
        body = {"tool": tool, "input": inputs, "origin": "hiris-chat"}
        try:
            async with self._session.post(
                f"{self._base_url}/api/execute", json=body, headers=headers
            ) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    logger.warning("execute-API %s -> %s: %s", tool, resp.status, detail[:200])
                    return {"error": f"execute-API status {resp.status}"}
                return await resp.json()
        except Exception as exc:
            logger.warning("execute-API %s non raggiungibile: %s", tool, type(exc).__name__)
            return {"error": "execute-API non raggiungibile"}
