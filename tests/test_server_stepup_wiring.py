import pytest


@pytest.mark.asyncio
async def test_make_task_stepup_returns_none_without_owner():
    from hiris.app.server import _make_task_stepup
    assert _make_task_stepup(app=object(), data_dir="/data", owner="") is None
    assert _make_task_stepup(app=object(), data_dir="/data", owner=None) is None


@pytest.mark.asyncio
async def test_make_task_stepup_delegates_to_confirmation_with_owner(monkeypatch):
    import hiris.app.server as server

    captured = {}

    async def fake_request(app, data_dir, *, tool, inputs, tier, user):
        captured.update(app=app, data_dir=data_dir, tool=tool,
                        inputs=inputs, tier=tier, user=user)
        return {"nonce": "n1"}

    monkeypatch.setattr(server, "request_confirmation_stepup", fake_request)

    sentinel_app = object()
    cb = server._make_task_stepup(app=sentinel_app, data_dir="/data", owner="paolo")
    assert cb is not None
    out = await cb(tool="call_ha_service",
                   inputs={"domain": "light", "service": "turn_on", "data": {}},
                   tier="yellow")
    assert out == {"nonce": "n1"}
    assert captured["user"] == "paolo"
    assert captured["app"] is sentinel_app
    assert captured["tier"] == "yellow"
