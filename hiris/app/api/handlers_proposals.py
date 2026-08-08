import logging

from aiohttp import web

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset({"pending", "applied", "rejected", "archived"})
_CONFIG_TYPES = frozenset({"ha_dashboard", "ha_script", "ha_scene"})

# CSRF protection is now provided globally by csrf_middleware (require
# X-Requested-With on POST/PUT/DELETE under /api/). Removed inline _check_csrf.


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
    proposal_store = request.app.get("proposal_store")
    if proposal_store is None:
        return web.json_response({"error": "ProposalStore not initialized"}, status=503)
    proposal_id = request.match_info["proposal_id"]
    proposal = await proposal_store.get(proposal_id)
    if proposal is None or proposal.get("status") != "pending":
        return web.json_response(
            {"error": "Proposal not found or not in pending state"}, status=409
        )
    # For HA automations, materialize the config in Home Assistant first; only
    # mark applied if HA accepted it (so a rejected config stays pending/retryable).
    if proposal.get("type") == "ha_automation":
        ha = request.app.get("ha_client")
        if ha is None:
            return web.json_response({"error": "HA client non disponibile"}, status=503)
        result = await ha.create_automation(proposal.get("config") or {})
        if not isinstance(result, dict) or result.get("error"):
            msg = result.get("error") if isinstance(result, dict) else "errore sconosciuto"
            return web.json_response(
                {"error": f"Automazione non creata in HA: {msg}"}, status=502
            )
        applied = await proposal_store.apply(proposal_id)
        return web.json_response({"ok": bool(applied), "automation_id": result.get("id")})
    if proposal.get("type") in _CONFIG_TYPES:
        ha = request.app.get("ha_client")
        if ha is None:
            return web.json_response({"error": "HA client non disponibile"}, status=503)
        from ..proxy.proposta_config import apply_ha_config
        result = await apply_ha_config(
            ha, proposal.get("config") or {}, data_dir=request.app.get("data_dir")
        )
        if not isinstance(result, dict) or result.get("error"):
            msg = result.get("error") if isinstance(result, dict) else "errore sconosciuto"
            return web.json_response(
                {"error": f"Config non creata in HA: {msg}"}, status=502
            )
        applied = await proposal_store.apply(proposal_id)
        return web.json_response({"ok": bool(applied), "result": result})
    # fetta E3 Task 3: il ramo "hiris_agent" (materializzava un Agentbot via
    # `watcher.agentbots.validate_agentbot` + `handlers_agentbots._apply_mutation`)
    # e' uscito insieme all'intero strato Agentbot -- entrambi i moduli che
    # importava sono cancellati. Il tipo "hiris_agent" e' uscito anche da
    # `proposal_tools._VALID_PROPOSAL_TYPES`/`_PROPOSAL_TYPE_ALIASES`, quindi
    # nessuna proposta NUOVA puo' piu' nascere con questo tipo. Una proposta
    # "hiris_agent" gia' su disco da prima di questo task (upgrade da
    # un'installazione precedente) cade ora nel ramo generico sotto: marcata
    # applied senza alcun effetto, con un warning esplicito -- il silenzio e'
    # dichiarato, non muto.
    # Other proposal types: status-only apply. Con la validazione del tipo alla
    # creazione (proposal_tools._VALID_PROPOSAL_TYPES per le automazioni,
    # dashboard_tools.propose_dashboard per le plance) nessuna proposta nota
    # dovrebbe arrivare qui; se succede e' un tipo non gestito -> NON ingoiare in
    # silenzio (era la causa del bug #2: type='automation' finiva qui senza mai
    # toccare HA, "sembrava applicata" ma non cambiava nulla).
    logger.warning("apply: proposta %s con tipo non gestito %r -> marcata applied "
                   "senza effetti su HA", proposal_id, proposal.get("type"))
    ok = await proposal_store.apply(proposal_id)
    if not ok:
        return web.json_response(
            {"error": "Proposal not found or not in pending state"}, status=409
        )
    return web.json_response({"ok": True})


async def handle_reject_proposal(request: web.Request) -> web.Response:
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
