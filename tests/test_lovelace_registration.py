# tests/test_lovelace_registration.py
"""Unit tests for the _register_lovelace_card startup helper."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SLUG = "hiris"
CARD_URL = f"/api/hassio_ingress/{SLUG}/static/hiris-chat-card.js"
RESOURCES_URL = "http://supervisor/core/api/lovelace/resources"
TOKEN = "test-token"


def _make_session_mock(get_status: int, get_body, post_status: int = 201, post_body: str = "{}"):
    """Build an async context-manager mock that simulates ClientSession behaviour."""
    # GET response
    get_resp = AsyncMock()
    get_resp.status = get_status
    get_resp.json = AsyncMock(return_value=get_body)
    get_resp.text = AsyncMock(return_value=str(get_body))
    get_resp.__aenter__ = AsyncMock(return_value=get_resp)
    get_resp.__aexit__ = AsyncMock(return_value=False)

    # POST response
    post_resp = AsyncMock()
    post_resp.status = post_status
    post_resp.text = AsyncMock(return_value=post_body)
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=get_resp)
    session.post = MagicMock(return_value=post_resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registers_card_when_not_present():
    """POST is called when the card URL is absent from existing resources."""
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
    """No POST is made if the card URL already exists in resources."""
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
        # Must not raise
        await _register_lovelace_card("http://supervisor/core", TOKEN, SLUG)


@pytest.mark.asyncio
async def test_custom_slug():
    """The card URL uses the provided slug, not a hardcoded default."""
    session = _make_session_mock(get_status=200, get_body=[], post_status=201)
    with patch("hiris.app.server.aiohttp.ClientSession", return_value=session):
        from hiris.app.server import _register_lovelace_card
        await _register_lovelace_card("http://supervisor/core", TOKEN, slug="my-hiris")

    call_kwargs = session.post.call_args
    assert "/api/hassio_ingress/my-hiris/static/hiris-chat-card.js" == call_kwargs[1]["json"]["url"]
