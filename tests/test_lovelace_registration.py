# tests/test_lovelace_registration.py
"""Unit tests for the _register_lovelace_card and _deploy_card_to_www startup helpers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SLUG = "hiris"
OLD_CARD_URL = f"/api/hassio_ingress/{SLUG}/static/hiris-chat-card.js"
CARD_URL = f"/local/{SLUG}/hiris-chat-card.js"
RESOURCES_URL = "http://supervisor/core/api/lovelace/resources"
TOKEN = "test-token"


def _make_session_mock(
    get_status: int,
    get_body,
    post_status: int = 201,
    post_body: str = "{}",
    delete_status: int = 204,
):
    """Build an async context-manager mock that simulates ClientSession behaviour."""
    get_resp = AsyncMock()
    get_resp.status = get_status
    get_resp.json = AsyncMock(return_value=get_body)
    get_resp.text = AsyncMock(return_value=str(get_body))
    get_resp.__aenter__ = AsyncMock(return_value=get_resp)
    get_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.status = post_status
    post_resp.text = AsyncMock(return_value=post_body)
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    delete_resp = AsyncMock()
    delete_resp.status = delete_status
    delete_resp.__aenter__ = AsyncMock(return_value=delete_resp)
    delete_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=get_resp)
    session.post = MagicMock(return_value=post_resp)
    session.delete = MagicMock(return_value=delete_resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# Tests — _register_lovelace_card
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registers_card_when_not_present():
    """POST is called with /local/ URL when the card is absent from existing resources."""
    session = _make_session_mock(
        get_status=200,
        get_body=[{"url": "/some/other/card.js", "res_type": "module"}],
        post_status=201,
    )
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    session.post.assert_called_once()
    call_kwargs = session.post.call_args
    assert call_kwargs[1]["json"]["url"] == CARD_URL
    assert call_kwargs[1]["json"]["res_type"] == "module"


@pytest.mark.asyncio
async def test_skips_when_already_registered():
    """No POST is made if the /local/ URL already exists in resources."""
    session = _make_session_mock(
        get_status=200,
        get_body=[{"url": CARD_URL, "res_type": "module"}],
    )
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_yaml_mode_get_405_no_post():
    """When GET /lovelace/resources returns 405 (YAML mode), no POST is attempted."""
    session = _make_session_mock(get_status=405, get_body=None)
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_yaml_mode_post_405_no_exception():
    """When POST returns 405 (YAML mode response), the function completes silently."""
    session = _make_session_mock(
        get_status=200,
        get_body=[],
        post_status=405,
        post_body="Method Not Allowed",
    )
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)
    # No exception raised — test passes if we reach here


@pytest.mark.asyncio
async def test_network_error_does_not_raise():
    """Any exception during HTTP calls is swallowed — startup must not crash."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(side_effect=OSError("connection refused"))

    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)


@pytest.mark.asyncio
async def test_custom_slug():
    """The /local/ URL uses the provided slug."""
    session = _make_session_mock(get_status=200, get_body=[], post_status=201)
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, slug="my-hiris")

    call_kwargs = session.post.call_args
    assert call_kwargs[1]["json"]["url"] == "/local/my-hiris/hiris-chat-card.js"


@pytest.mark.asyncio
async def test_migrates_old_ingress_url():
    """DELETE is called for the old ingress URL, then POST registers the new /local/ URL."""
    session = _make_session_mock(
        get_status=200,
        get_body=[{"id": "42", "url": OLD_CARD_URL, "res_type": "module"}],
        post_status=201,
        delete_status=204,
    )
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)

    session.delete.assert_called_once()
    delete_url = session.delete.call_args[0][0]
    assert delete_url.endswith("/42")
    session.post.assert_called_once()
    assert session.post.call_args[1]["json"]["url"] == CARD_URL


# ---------------------------------------------------------------------------
# Tests — _deploy_card_to_www
# ---------------------------------------------------------------------------

def test_deploy_card_to_www():
    """_deploy_card_to_www copies hiris-chat-card.js to /homeassistant/www/{slug}/."""
    with patch("hiris.app.server.os.makedirs") as mock_makedirs, \
         patch("hiris.app.server.shutil.copy2") as mock_copy:
        from hiris.app.server import _deploy_card_to_www
        _deploy_card_to_www("hiris")

    mock_makedirs.assert_called_once_with("/homeassistant/www/hiris", exist_ok=True)
    import os as _os
    expected_dst = _os.path.join("/homeassistant/www/hiris", "hiris-chat-card.js")
    assert mock_copy.call_args[0][1] == expected_dst


def test_deploy_card_to_www_failure_does_not_raise():
    """If the www directory is not writable, _deploy_card_to_www logs and returns."""
    with patch("hiris.app.server.os.makedirs", side_effect=PermissionError("read-only")):
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
