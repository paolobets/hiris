import json
import os
import pytest
from aiohttp import web

from hiris.app.api.handlers_history_policy import (
    should_capture, load_policy, save_policy,
    handle_get_history_policy, handle_save_history_policy, DEFAULT_RETENTION_DAYS,
)


def test_should_capture_domain_and_allowlist_and_exclude():
    pol = {"domains": {"climate": True, "switch": False},
           "entities": ["valve.irrigazione"], "exclude": ["sensor.noise"],
           "retention_days": 90}
    assert should_capture("climate.salotto", pol) is True
    assert should_capture("switch.x", pol) is False
    assert should_capture("valve.irrigazione", pol) is True
    assert should_capture("light.x", pol) is False
    assert should_capture("sensor.noise", pol) is False
    pol2 = dict(pol, domains={"sensor": True})
    assert should_capture("sensor.noise", pol2) is False


def test_empty_policy_captures_nothing():
    assert should_capture("light.any", {}) is False
    assert should_capture("climate.any", {"domains": {}}) is False


def test_load_default_and_roundtrip(tmp_path):
    d = str(tmp_path)
    pol = load_policy(d)
    assert pol["domains"] == {} and pol["entities"] == [] and pol["exclude"] == []
    assert pol["retention_days"] == DEFAULT_RETENTION_DAYS
    save_policy(d, {"domains": {"climate": True}, "entities": ["valve.a"],
                    "exclude": [], "retention_days": 30})
    pol2 = load_policy(d)
    assert pol2["domains"] == {"climate": True}
    assert pol2["entities"] == ["valve.a"]
    assert pol2["retention_days"] == 30


def test_save_clamps_retention(tmp_path):
    d = str(tmp_path)
    save_policy(d, {"retention_days": 5000})
    assert load_policy(d)["retention_days"] == 365
    save_policy(d, {"retention_days": 0})
    assert load_policy(d)["retention_days"] == 1


@pytest.mark.asyncio
async def test_get_and_save_handlers(aiohttp_client, tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app.router.add_get("/api/history/policy", handle_get_history_policy)
    app.router.add_post("/api/history/policy", handle_save_history_policy)
    client = await aiohttp_client(app)
    r = await client.get("/api/history/policy")
    assert r.status == 200
    body = await r.json()
    assert "domains" in body and "categories" in body
    r2 = await client.post("/api/history/policy",
                           json={"domains": {"climate": True}, "retention_days": 45})
    assert r2.status == 200
    assert (await r2.json())["ok"] is True
    r3 = await client.get("/api/history/policy")
    assert (await r3.json())["domains"] == {"climate": True}
