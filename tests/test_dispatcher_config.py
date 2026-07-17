import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS


def _dispatcher(ha):
    return ToolDispatcher(ha_client=ha, notify_config={})


@pytest.mark.asyncio
async def test_dispatch_create_ha_config_writes_directly():
    ha = AsyncMock()
    ha.create_script = AsyncMock(return_value={"ok": True, "id": "luci_sera"})
    d = _dispatcher(ha)
    res = await d.dispatch("create_ha_config", {
        "kind": "script", "name": "Luci sera", "slug": "luci_sera",
        "config": {"sequence": []},
    })
    assert res == {"ok": True, "id": "luci_sera"}
    ha.create_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_create_ha_config_bad_input():
    ha = AsyncMock()
    d = _dispatcher(ha)
    res = await d.dispatch("create_ha_config", {"kind": "nope", "name": "x",
                                                "slug": "x", "config": {"a": 1}})
    assert "error" in res


def test_create_ha_config_in_all_tool_defs():
    assert any(t["name"] == "create_ha_config" for t in ALL_TOOL_DEFS)


def test_create_ha_config_is_chat_only():
    assert "create_ha_config" not in EVALUATION_ONLY_TOOLS


@pytest.mark.asyncio
async def test_dispatch_add_dashboard_view():
    ha = AsyncMock()
    ha.add_dashboard_view = AsyncMock(return_value={"ok": True, "views": 2})
    d = _dispatcher(ha)
    res = await d.dispatch("add_dashboard_view", {"url_path": "casa-mia", "view": {"title": "Cucina"}})
    ha.add_dashboard_view.assert_awaited_once_with("casa-mia", {"title": "Cucina"})
    assert res["ok"] is True


def test_add_dashboard_view_in_all_tool_defs():
    assert any(t["name"] == "add_dashboard_view" for t in ALL_TOOL_DEFS)


def test_add_dashboard_view_is_chat_only():
    assert "add_dashboard_view" not in EVALUATION_ONLY_TOOLS
