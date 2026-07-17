import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.config_tools import (
    normalize_config_inputs, apply_ha_config, build_config_proposal, VALID_KINDS,
)


def _script_inputs(**o):
    base = {"kind": "script", "name": "Luci sera", "slug": "luci_sera",
            "config": {"sequence": []}}
    base.update(o)
    return base


def _dash_inputs(**o):
    base = {"kind": "dashboard", "name": "Casa Mia", "slug": "casa-mia",
            "config": {"views": [{"cards": []}]}, "icon": "mdi:home",
            "show_in_sidebar": True}
    base.update(o)
    return base


def test_normalize_script_ok():
    n = normalize_config_inputs(_script_inputs())
    assert n["kind"] == "script" and n["slug"] == "luci_sera"
    assert n["ha_config"] == {"sequence": []}


def test_normalize_dashboard_ok():
    n = normalize_config_inputs(_dash_inputs())
    assert n["kind"] == "dashboard" and n["slug"] == "casa-mia"
    assert n["icon"] == "mdi:home" and n["show_in_sidebar"] is True


def test_normalize_bad_kind():
    with pytest.raises(ValueError):
        normalize_config_inputs(_script_inputs(kind="automation"))


def test_normalize_bad_script_slug():
    with pytest.raises(ValueError):
        normalize_config_inputs(_script_inputs(slug="Luci Sera"))


def test_normalize_dashboard_slug_needs_hyphen():
    with pytest.raises(ValueError):
        normalize_config_inputs(_dash_inputs(slug="casa"))


def test_normalize_empty_config():
    with pytest.raises(ValueError):
        normalize_config_inputs(_script_inputs(config={}))


def test_normalize_dashboard_missing_views():
    with pytest.raises(ValueError):
        normalize_config_inputs(_dash_inputs(config={"cards": []}))


@pytest.mark.asyncio
async def test_apply_ha_config_routes_to_script():
    ha = AsyncMock()
    ha.create_script = AsyncMock(return_value={"ok": True, "id": "luci_sera"})
    n = normalize_config_inputs(_script_inputs())
    res = await apply_ha_config(ha, n)
    ha.create_script.assert_awaited_once_with("luci_sera", {"sequence": []})
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_apply_ha_config_routes_to_dashboard():
    ha = AsyncMock()
    ha.create_dashboard = AsyncMock(return_value={"ok": True, "url_path": "casa-mia"})
    n = normalize_config_inputs(_dash_inputs())
    res = await apply_ha_config(ha, n)
    ha.create_dashboard.assert_awaited_once_with(
        "casa-mia", "Casa Mia", {"views": [{"cards": []}]},
        icon="mdi:home", show_in_sidebar=True,
    )
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_apply_ha_config_missing_kind_returns_error():
    ha = AsyncMock()
    res = await apply_ha_config(ha, {})
    assert isinstance(res, dict) and res.get("error")
    ha.create_script.assert_not_awaited()
    ha.create_scene.assert_not_awaited()
    ha.create_dashboard.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_ha_config_missing_slug_and_ha_config_returns_error():
    ha = AsyncMock()
    res = await apply_ha_config(ha, {"kind": "script"})
    assert isinstance(res, dict) and res.get("error")
    ha.create_script.assert_not_awaited()
    ha.create_scene.assert_not_awaited()
    ha.create_dashboard.assert_not_awaited()


def test_build_config_proposal():
    n = normalize_config_inputs(_dash_inputs())
    p = build_config_proposal(n)
    assert p["type"] == "ha_dashboard"
    assert p["name"] == "Casa Mia"
    assert p["config"] == n
    assert p["routing_reason"] and p["description"]


def test_valid_kinds():
    assert VALID_KINDS == frozenset({"dashboard", "script", "scene"})
