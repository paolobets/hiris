import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    async def get_history(self, entity_ids, days):
        return [{"entity_id": entity_ids[0], "last_changed": "2026-06-26T10:00:00+00:00",
                 "state": "21.0"}]

    async def get_statistics(self, statistic_ids, period, days):
        return {}


@pytest.mark.asyncio
async def test_dispatch_get_history_returns_series():
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history",
                           {"entity_ids": ["sensor.temp"], "days": 3})
    assert isinstance(out, list)
    assert out[0]["id"] == "sensor.temp"


@pytest.mark.asyncio
async def test_dispatch_get_history_ignores_action_whitelist():
    # Reads must NOT be filtered by allowed_entities (action whitelist).
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history", {"entity_ids": ["sensor.temp"], "days": 3},
                           allowed_entities=["light.*"])
    assert out[0]["id"] == "sensor.temp"   # not blocked
