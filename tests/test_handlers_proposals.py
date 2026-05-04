import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_proposals import (
    handle_list_proposals,
    handle_get_proposal,
    handle_apply_proposal,
    handle_reject_proposal,
)

_CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _make_app(proposal_store=None):
    app = MagicMock()
    app.get = MagicMock(
        side_effect=lambda k, *a: proposal_store if k == "proposal_store" else None
    )
    return app


def _make_store(**kwargs):
    store = MagicMock()
    for attr, val in kwargs.items():
        setattr(store, attr, val)
    return store


@pytest.mark.asyncio
async def test_list_proposals_returns_list():
    proposals = [{"id": "x", "status": "pending", "name": "Test"}]
    store = _make_store(list=AsyncMock(return_value=proposals))

    request = make_mocked_request("GET", "/api/proposals", app=_make_app(store))
    resp = await handle_list_proposals(request)

    assert resp.status == 200
    data = json.loads(resp.body)
    assert data == {"proposals": proposals}
    store.list.assert_awaited_once_with(status=None)


@pytest.mark.asyncio
async def test_list_proposals_invalid_status_returns_400():
    store = _make_store(list=AsyncMock(return_value=[]))

    request = make_mocked_request(
        "GET", "/api/proposals?status=bogus",
        app=_make_app(store),
    )
    resp = await handle_list_proposals(request)

    assert resp.status == 400
    data = json.loads(resp.body)
    assert "error" in data


@pytest.mark.asyncio
async def test_get_proposal_returns_detail():
    proposal = {"id": "abc", "status": "pending", "name": "Fix lights"}
    store = _make_store(get=AsyncMock(return_value=proposal))

    request = make_mocked_request(
        "GET", "/api/proposals/abc",
        match_info={"proposal_id": "abc"},
        app=_make_app(store),
    )
    resp = await handle_get_proposal(request)

    assert resp.status == 200
    data = json.loads(resp.body)
    assert data == proposal


@pytest.mark.asyncio
async def test_get_proposal_not_found_returns_404():
    store = _make_store(get=AsyncMock(return_value=None))

    request = make_mocked_request(
        "GET", "/api/proposals/missing",
        match_info={"proposal_id": "missing"},
        app=_make_app(store),
    )
    resp = await handle_get_proposal(request)

    assert resp.status == 404
    data = json.loads(resp.body)
    assert "error" in data


@pytest.mark.asyncio
async def test_apply_proposal_returns_ok():
    store = _make_store(apply=AsyncMock(return_value=True))

    request = make_mocked_request(
        "POST", "/api/proposals/abc/apply",
        match_info={"proposal_id": "abc"},
        headers=_CSRF_HEADERS,
        app=_make_app(store),
    )
    resp = await handle_apply_proposal(request)

    assert resp.status == 200
    data = json.loads(resp.body)
    assert data == {"ok": True}
    store.apply.assert_awaited_once_with("abc")


@pytest.mark.asyncio
async def test_reject_proposal_returns_ok():
    store = _make_store(reject=AsyncMock(return_value=True))

    request = make_mocked_request(
        "POST", "/api/proposals/abc/reject",
        match_info={"proposal_id": "abc"},
        headers=_CSRF_HEADERS,
        app=_make_app(store),
    )
    resp = await handle_reject_proposal(request)

    assert resp.status == 200
    data = json.loads(resp.body)
    assert data == {"ok": True}
    store.reject.assert_awaited_once_with("abc")


@pytest.mark.asyncio
async def test_list_proposals_no_store_returns_503():
    request = make_mocked_request("GET", "/api/proposals", app=_make_app(None))
    resp = await handle_list_proposals(request)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_get_proposal_no_store_returns_503():
    request = make_mocked_request(
        "GET", "/api/proposals/x",
        match_info={"proposal_id": "x"},
        app=_make_app(None),
    )
    resp = await handle_get_proposal(request)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_apply_proposal_no_store_returns_503():
    request = make_mocked_request(
        "POST", "/api/proposals/x/apply",
        match_info={"proposal_id": "x"},
        headers=_CSRF_HEADERS,
        app=_make_app(None),
    )
    resp = await handle_apply_proposal(request)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_reject_proposal_no_store_returns_503():
    request = make_mocked_request(
        "POST", "/api/proposals/x/reject",
        match_info={"proposal_id": "x"},
        headers=_CSRF_HEADERS,
        app=_make_app(None),
    )
    resp = await handle_reject_proposal(request)
    assert resp.status == 503
