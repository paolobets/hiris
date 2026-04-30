from aiohttp import web

_VALID_STATUSES = frozenset({"pending", "applied", "rejected", "archived"})
_CSRF_HEADER = "X-Requested-With"
_CSRF_VALUE = "XMLHttpRequest"


def _check_csrf(request: web.Request) -> bool:
    return request.headers.get(_CSRF_HEADER) == _CSRF_VALUE


async def handle_list_proposals(request: web.Request) -> web.Response:
    proposal_store = request.app.get("proposal_store")
    if proposal_store is None:
        return web.json_response({"error": "ProposalStore not initialized"}, status=503)
    status = request.rel_url.query.get("status") or None
    if status is not None and status not in _VALID_STATUSES:
        return web.json_response({"error": f"Invalid status: {status!r}"}, status=400)
    proposals = await proposal_store.list(status=status)
    return web.json_response({"proposals": proposals})


async def handle_get_proposal(request: web.Request) -> web.Response:
    proposal_store = request.app.get("proposal_store")
    if proposal_store is None:
        return web.json_response({"error": "ProposalStore not initialized"}, status=503)
    proposal_id = request.match_info["proposal_id"]
    proposal = await proposal_store.get(proposal_id)
    if proposal is None:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(proposal)


async def handle_apply_proposal(request: web.Request) -> web.Response:
    if not _check_csrf(request):
        return web.json_response({"error": "Forbidden"}, status=403)
    proposal_store = request.app.get("proposal_store")
    if proposal_store is None:
        return web.json_response({"error": "ProposalStore not initialized"}, status=503)
    proposal_id = request.match_info["proposal_id"]
    ok = await proposal_store.apply(proposal_id)
    if not ok:
        return web.json_response(
            {"error": "Proposal not found or not in pending state"}, status=409
        )
    return web.json_response({"ok": True})


async def handle_reject_proposal(request: web.Request) -> web.Response:
    if not _check_csrf(request):
        return web.json_response({"error": "Forbidden"}, status=403)
    proposal_store = request.app.get("proposal_store")
    if proposal_store is None:
        return web.json_response({"error": "ProposalStore not initialized"}, status=503)
    proposal_id = request.match_info["proposal_id"]
    ok = await proposal_store.reject(proposal_id)
    if not ok:
        return web.json_response(
            {"error": "Proposal not found or not in pending state"}, status=409
        )
    return web.json_response({"ok": True})
