import pytest

from hiris.app.server import create_app


def _app(tmp_path, token="tok"):
    app = create_app()
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = token
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest.mark.asyncio
async def test_brain_routes_registered_and_authed(tmp_path, aiohttp_client, monkeypatch):
    """fetta E3 Task 5: era sull'ora-morta /api/brain/reasoning (usciva col
    Brain auto-proponente insieme a reasoning_log/ReasoningLog) per i primi
    due controlli -- ripuntato su /api/brain/advisories, che copre lo stesso
    middleware di autenticazione e resta vivo fino al Task 6."""
    # Force auth ON despite conftest defaults.
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "0")
    monkeypatch.setenv("HIRIS_ALLOW_NO_CSRF", "0")
    client = await aiohttp_client(_app(tmp_path))
    # 401 without token
    r = await client.get("/api/brain/advisories")
    assert r.status == 401
    # 200 with token (store absent -> empty)
    r = await client.get("/api/brain/advisories", headers={"X-HIRIS-Internal-Token": "tok"})
    assert r.status == 200
    # 403 CSRF on POST without X-Requested-With and no token header
    r = await client.post("/api/brain/advisories/1/ack")
    assert r.status in (401, 403)
