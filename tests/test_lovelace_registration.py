# tests/test_lovelace_registration.py
"""Unit tests for the _register_lovelace_card and _deploy_card_to_www startup helpers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLUG = "hiris"
OLD_CARD_URL = f"/api/hassio_ingress/{SLUG}/static/hiris-chat-card.js"
CARD_URL = f"/local/{SLUG}/hiris-chat-card.js"
TOKEN = "test-token"


# ---------------------------------------------------------------------------
# WebSocket mock helpers
# ---------------------------------------------------------------------------

def _make_ws_mock(messages: list[dict]):
    """WebSocket mock that returns messages in sequence from receive_json()."""
    it = iter(messages)

    async def _receive_json():
        return next(it)

    ws = AsyncMock()
    ws.receive_json = _receive_json
    ws.send_json = AsyncMock()
    ws.__aenter__ = AsyncMock(return_value=ws)
    ws.__aexit__ = AsyncMock(return_value=False)
    return ws


def _make_session_ws(ws_mock):
    """ClientSession mock whose ws_connect() returns ws_mock."""
    session = AsyncMock()
    session.ws_connect = MagicMock(return_value=ws_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


_AUTH_REQUIRED = {"type": "auth_required"}
_AUTH_OK = {"type": "auth_ok"}
_AUTH_INVALID = {"type": "auth_invalid"}


def _ws_list_ok(resources: list) -> dict:
    return {"id": 1, "type": "result", "success": True, "result": resources}


def _ws_list_fail() -> dict:
    return {"id": 1, "type": "result", "success": False,
            "error": {"code": "not_supported", "message": "Not in storage mode"}}


def _ws_create_ok(msg_id: int) -> dict:
    return {"id": msg_id, "type": "result", "success": True,
            "result": {"id": "x1", "type": "module", "url": CARD_URL}}


def _ws_delete_ok(msg_id: int) -> dict:
    return {"id": msg_id, "type": "result", "success": True, "result": None}


def _sent_types(ws) -> list[str]:
    return [c[0][0].get("type") for c in ws.send_json.call_args_list]


def _sent_msgs(ws) -> list[dict]:
    return [c[0][0] for c in ws.send_json.call_args_list]


# ---------------------------------------------------------------------------
# Tests — _register_lovelace_card (WebSocket-based)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registers_card_when_not_present():
    """create command sent when the card is absent from existing resources."""
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK,
        _ws_list_ok([{"id": "other", "url": "/other/card.js", "type": "module"}]),
        _ws_create_ok(2),
    ])
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=_make_session_ws(ws)):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    create = next(m for m in _sent_msgs(ws) if m.get("type") == "lovelace/resources/create")
    assert create["url"] == CARD_URL
    assert create["res_type"] == "module"


@pytest.mark.asyncio
async def test_skips_when_already_registered():
    """No create command when /local/ URL already exists in resources."""
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK,
        _ws_list_ok([{"id": "x1", "url": CARD_URL, "type": "module"}]),
    ])
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=_make_session_ws(ws)):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    assert "lovelace/resources/create" not in _sent_types(ws)


@pytest.mark.asyncio
async def test_yaml_mode_no_create():
    """When list returns failure (YAML/unsupported mode), no create attempted, no exception."""
    ws = _make_ws_mock([_AUTH_REQUIRED, _AUTH_OK, _ws_list_fail()])
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=_make_session_ws(ws)):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    assert "lovelace/resources/create" not in _sent_types(ws)


@pytest.mark.asyncio
async def test_auth_failure_does_not_raise():
    """If HA rejects the WS token, the function returns silently."""
    ws = _make_ws_mock([_AUTH_REQUIRED, _AUTH_INVALID])
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=_make_session_ws(ws)):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)


@pytest.mark.asyncio
async def test_network_error_does_not_raise():
    """Any exception during WS connection is swallowed — startup must not crash."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.ws_connect = MagicMock(side_effect=OSError("connection refused"))

    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)


@pytest.mark.asyncio
async def test_custom_slug():
    """The /local/ URL uses the provided slug."""
    ws = _make_ws_mock([_AUTH_REQUIRED, _AUTH_OK, _ws_list_ok([]), _ws_create_ok(2)])
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=_make_session_ws(ws)):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, slug="my-hiris")

    create = next(m for m in _sent_msgs(ws) if m.get("type") == "lovelace/resources/create")
    assert create["url"] == "/local/my-hiris/hiris-chat-card.js"


@pytest.mark.asyncio
async def test_migrates_old_ingress_url():
    """delete sent for old ingress URL, then create for new /local/ URL."""
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK,
        _ws_list_ok([{"id": "42", "url": OLD_CARD_URL, "type": "module"}]),
        _ws_delete_ok(2),
        _ws_create_ok(3),
    ])
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=_make_session_ws(ws)):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    msgs = _sent_msgs(ws)
    delete = next(m for m in msgs if m.get("type") == "lovelace/resources/delete")
    assert delete["resource_id"] == "42"
    create = next(m for m in msgs if m.get("type") == "lovelace/resources/create")
    assert create["url"] == CARD_URL


# ---------------------------------------------------------------------------
# Tests — _deploy_card_to_www
# ---------------------------------------------------------------------------

def _patch_ha_mounted(ha_config_dir: str | None = "/config"):
    """Return (exists_patch, isdir_patch) that simulate the given HA config dir being mounted.

    Pass None to simulate no volume mounted at all.
    """
    def _exists(path):
        if ha_config_dir is None:
            return False
        return path == os.path.join(ha_config_dir, "configuration.yaml")

    def _isdir(path):
        if ha_config_dir is None:
            return False
        return path == os.path.join(ha_config_dir, ".storage")

    import os
    return (
        patch("hiris.app.server.os.path.exists", side_effect=_exists),
        patch("hiris.app.server.os.path.isdir", side_effect=_isdir),
    )


def test_find_ha_config_dir_config_path():
    """_find_ha_config_dir returns /config when configuration.yaml is present there."""
    exists_patch, isdir_patch = _patch_ha_mounted("/config")
    with exists_patch, isdir_patch:
        from hiris.app.server import _find_ha_config_dir
        assert _find_ha_config_dir() == "/config"


def test_find_ha_config_dir_homeassistant_fallback():
    """_find_ha_config_dir falls back to /homeassistant if /config has no HA files."""
    exists_patch, isdir_patch = _patch_ha_mounted("/homeassistant")
    with exists_patch, isdir_patch:
        from hiris.app.server import _find_ha_config_dir
        assert _find_ha_config_dir() == "/homeassistant"


def test_find_ha_config_dir_not_mounted():
    """_find_ha_config_dir returns None when neither candidate path looks like HA config."""
    exists_patch, isdir_patch = _patch_ha_mounted(None)
    with exists_patch, isdir_patch:
        from hiris.app.server import _find_ha_config_dir
        assert _find_ha_config_dir() is None


def test_deploy_card_to_www_uses_config_path():
    """_deploy_card_to_www deploys to /config/www/{slug}/ when /config is the HA config dir."""
    exists_patch, isdir_patch = _patch_ha_mounted("/config")
    with exists_patch, isdir_patch, \
         patch("hiris.app.server.os.makedirs") as mock_makedirs, \
         patch("hiris.app.server.shutil.copy2") as mock_copy:
        from hiris.app.server import _deploy_card_to_www
        _deploy_card_to_www("hiris")

    import os as _os
    expected_dst_dir = _os.path.join("/config", "www", "hiris")
    mock_makedirs.assert_called_once_with(expected_dst_dir, exist_ok=True)
    expected_dst = _os.path.join(expected_dst_dir, "hiris-chat-card.js")
    assert mock_copy.call_args[0][1] == expected_dst


def test_deploy_card_to_www_not_mounted_does_not_copy():
    """When the HA config volume is not mounted, no file is written and no exception raised."""
    exists_patch, isdir_patch = _patch_ha_mounted(None)
    with exists_patch, isdir_patch, \
         patch("hiris.app.server.os.makedirs") as mock_makedirs:
        from hiris.app.server import _deploy_card_to_www
        _deploy_card_to_www("hiris")

    mock_makedirs.assert_not_called()


def test_deploy_card_to_www_failure_does_not_raise():
    """If the www directory is not writable, _deploy_card_to_www logs and returns."""
    exists_patch, isdir_patch = _patch_ha_mounted("/config")
    with exists_patch, isdir_patch, \
         patch("hiris.app.server.os.makedirs", side_effect=PermissionError("read-only")):
        from hiris.app.server import _deploy_card_to_www
        _deploy_card_to_www("hiris")
    # No exception raised


# ---------------------------------------------------------------------------
# Content-check tests for hiris-chat-card.js picker integration
# ---------------------------------------------------------------------------

from pathlib import Path

_CARD_JS = Path(__file__).parent.parent / "hiris" / "app" / "static" / "hiris-chat-card.js"


def _js() -> str:
    return _CARD_JS.read_text(encoding="utf-8")


def test_customcards_registration():
    """JS registers the card in window.customCards so HA shows it in the picker."""
    src = _js()
    assert "window.customCards" in src
    assert "'hiris-chat-card'" in src or '"hiris-chat-card"' in src


def test_editor_element_defined():
    """JS defines the hiris-chat-card-editor custom element for the config UI."""
    src = _js()
    assert "class HirisChatCardEditor" in src
    assert "hiris-chat-card-editor" in src
    assert "getConfigElement" in src


def test_stub_config_has_default_agent():
    """getStubConfig returns hiris-default so the picker can add the card without crashing."""
    src = _js()
    assert "hiris-default" in src


def test_setconfig_no_throw():
    """setConfig no longer throws when agent_id is missing."""
    src = _js()
    assert "throw new Error('agent_id is required')" not in src


def test_hiris_icon_inlined():
    """The HIRIS SVG icon is inlined in the JS (petal colour c084fc is present)."""
    src = _js()
    assert "c084fc" in src


def test_get_card_size_defined():
    """HirisCard implements getCardSize() so HA can allocate grid rows without showing shimmer."""
    src = _js()
    assert "getCardSize()" in src


def test_preview_is_false():
    """preview: false prevents HA from attempting a live render in the picker (which requires HIRIS)."""
    src = _js()
    assert "preview: false" in src
    assert "preview: true" not in src


def test_card_url_is_local_not_ingress():
    """The JS comment documents /local/ URL; the old static ingress resource URL is gone."""
    src = _js()
    assert "/local/hiris/hiris-chat-card.js" in src
    assert "/api/hassio_ingress/hiris/static/hiris-chat-card.js" not in src
