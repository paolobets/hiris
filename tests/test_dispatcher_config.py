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
async def test_dispatch_create_ha_config_dashboard_kind_rejected():
    """L'LLM non puo' piu' creare una plancia direttamente: deve proporla.

    Il kind 'dashboard' non e' piu' nell'input_schema, ma il modello puo'
    comunque emetterlo: il dispatcher deve rifiutarlo, non scrivere su HA."""
    ha = AsyncMock()
    d = _dispatcher(ha)
    res = await d.dispatch("create_ha_config", {
        "kind": "dashboard", "name": "Casa Mia", "slug": "casa-mia",
        "config": {"views": []},
    })
    assert "error" in res and "propose_dashboard" in res["error"]
    ha.create_dashboard.assert_not_awaited()


# --- i tre tool plance a proposta ---

@pytest.mark.asyncio
async def test_dispatch_list_dashboards():
    ha = AsyncMock()
    ha.list_dashboards = AsyncMock(return_value=[{"url_path": "casa-mia", "title": "Casa"}])
    d = _dispatcher(ha)
    res = await d.dispatch("list_dashboards", {})
    ha.list_dashboards.assert_awaited_once_with()
    assert res[0]["url_path"] == "casa-mia"


@pytest.mark.asyncio
async def test_dispatch_get_dashboard_config():
    ha = AsyncMock()
    ha.get_lovelace_config = AsyncMock(return_value={"views": [{"title": "Home"}]})
    d = _dispatcher(ha)
    res = await d.dispatch("get_dashboard_config", {"url_path": "casa-mia"})
    ha.get_lovelace_config.assert_awaited_once_with("casa-mia")
    assert res["views"][0]["title"] == "Home"


@pytest.mark.asyncio
async def test_dispatch_propose_dashboard_saves_pending():
    ha = AsyncMock()
    store = AsyncMock()
    store.save = AsyncMock(return_value="p1")
    d = ToolDispatcher(ha_client=ha, notify_config={}, proposal_store=store)
    res = await d.dispatch("propose_dashboard", {
        "mode": "replace", "url_path": "casa-mia",
        "config": {"views": [{"title": "Home"}]}, "reason": "riorganizzo",
    })
    assert res["proposal_id"] == "p1" and res["status"] == "pending"
    rec = store.save.await_args.args[0]
    assert rec["type"] == "ha_dashboard"
    assert rec["config"] == {
        "kind": "dashboard", "mode": "replace", "slug": "casa-mia",
        "name": None, "ha_config": {"views": [{"title": "Home"}]},
    }
    # non tocca mai HA direttamente
    ha.save_dashboard_config.assert_not_awaited()
    ha.create_dashboard.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_propose_dashboard_bad_input_not_saved():
    ha = AsyncMock()
    store = AsyncMock()
    d = ToolDispatcher(ha_client=ha, notify_config={}, proposal_store=store)
    res = await d.dispatch("propose_dashboard", {
        "mode": "create", "url_path": "casa-mia",
        "config": {"views": []}, "reason": "motivo",  # manca title
    })
    assert "error" in res
    store.save.assert_not_awaited()


def test_dashboard_tools_in_all_tool_defs():
    names = {t["name"] for t in ALL_TOOL_DEFS}
    assert {"list_dashboards", "get_dashboard_config", "propose_dashboard"} <= names
    assert "add_dashboard_view" not in names


def test_dashboard_tools_are_chat_only():
    # Brain e Agentbot non devono poter toccare le plance: protezione contro
    # il prompt injection dallo stato di HA.
    for n in ("list_dashboards", "get_dashboard_config", "propose_dashboard"):
        assert n not in EVALUATION_ONLY_TOOLS
