# tests/test_mayan_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from hiris.app.brain.mayan_client import MayanClient


@pytest.mark.asyncio
async def test_list_tag_documents_parses_results():
    c = MayanClient(base_url="http://x/api/v4", token="t")
    resp = MagicMock(); resp.status_code = 200
    resp.json = MagicMock(return_value={"results": [
        {"id": 42, "label": "Estratto conto"}, {"id": 43, "label": "Bolletta"}]})
    resp.raise_for_status = MagicMock()
    c._client.get = AsyncMock(return_value=resp)
    docs = await c.list_tag_documents(7)
    assert [d["id"] for d in docs] == [42, 43]
    await c.aclose()


@pytest.mark.asyncio
async def test_circuit_opens_after_connection_failures():
    import httpx
    from hiris.app.brain.mayan_client import _MAYAN_CIRCUIT_THRESHOLD
    c = MayanClient(base_url="http://dead/api/v4", token="t")
    c._client.get = AsyncMock(side_effect=httpx.ConnectError("no dns"))
    for _ in range(_MAYAN_CIRCUIT_THRESHOLD + 3):
        assert await c.list_tag_documents(7) == []   # degrada a lista vuota
    assert c._client.get.await_count == _MAYAN_CIRCUIT_THRESHOLD  # poi salta la rete
    await c.aclose()
