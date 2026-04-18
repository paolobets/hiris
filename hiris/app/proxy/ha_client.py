import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
import aiohttp

logger = logging.getLogger(__name__)


class HAClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._state_listeners: list[Callable[[dict], None]] = []

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(headers=self._headers)

    async def stop(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
        if self._session:
            await self._session.close()

    async def get_states(self, entity_ids: list[str]) -> list[dict]:
        url = f"{self._base_url}/api/states"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            all_states: list[dict] = await resp.json()
        if entity_ids:
            return [s for s in all_states if s["entity_id"] in entity_ids]
        return all_states

    async def get_history(self, entity_ids: list[str], days: int) -> list[dict]:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        filter_param = ",".join(entity_ids)
        url = f"{self._base_url}/api/history/period/{start}?filter_entity_id={filter_param}&minimal_response=true"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            nested: list[list[dict]] = await resp.json()
        return [item for sublist in nested for item in sublist]

    async def call_service(self, domain: str, service: str, data: dict) -> bool:
        url = f"{self._base_url}/api/services/{domain}/{service}"
        async with self._session.post(url, json=data) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error("call_service %s.%s failed %s: %s", domain, service, resp.status, body)
                return False
            return True

    async def get_automations(self) -> list[dict]:
        url = f"{self._base_url}/api/states"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            all_states: list[dict] = await resp.json()
        return [s for s in all_states if s["entity_id"].startswith("automation.")]

    def add_state_listener(self, callback: Callable[[dict], None]) -> None:
        self._state_listeners.append(callback)

    async def start_websocket(self) -> None:
        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/websocket"
        self._ws_task = asyncio.create_task(self._ws_loop(ws_url))

    async def _ws_loop(self, ws_url: str) -> None:
        try:
            async with self._session.ws_connect(ws_url) as ws:
                auth_req = await ws.receive_json()
                if auth_req.get("type") == "auth_required":
                    token = self._headers["Authorization"].removeprefix("Bearer ")
                    await ws.send_json({"type": "auth", "access_token": token})
                    auth_resp = await ws.receive_json()
                    if auth_resp.get("type") != "auth_ok":
                        logger.error("HA WebSocket auth failed")
                        return

                await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        if data.get("type") == "event" and data.get("event", {}).get("event_type") == "state_changed":
                            for cb in self._state_listeners:
                                cb(data["event"]["data"])
        except Exception as exc:
            logger.warning("HA WebSocket disconnected: %s", exc)
