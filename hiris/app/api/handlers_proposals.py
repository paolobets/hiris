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
        from ..tools.config_tools import apply_ha_config
        result = await apply_ha_config(ha, proposal.get("config") or {})
        if not isinstance(result, dict) or result.get("error"):
            msg = result.get("error") if isinstance(result, dict) else "errore sconosciuto"
            return web.json_response(
                {"error": f"Config non creata in HA: {msg}"}, status=502
            )
        applied = await proposal_store.apply(proposal_id)
        return web.json_response({"ok": bool(applied), "result": result})
    # Brain-proposed Agentbot: materialize it through the SAME whitelist
    # re-construction the HTTP /api/agentbots create path uses
    # (`watcher.agentbots.validate_agentbot`) -- this config was authored by
    # an LLM, so it is never trusted/persisted as-is. Only mark the
    # proposal applied if a real, validated Agentbot was actually created;
    # a rejected/unsalvageable config stays pending/retryable, mirroring the
    # ha_automation and _CONFIG_TYPES branches above.
    if proposal.get("type") == "hiris_agent":
        data_dir = request.app.get("data_dir")
        if not data_dir:
            return web.json_response({"error": "data_dir non disponibile"}, status=503)
        from ..watcher import agentbots as agentbots_store
        from .handlers_agentbots import _apply_mutation
        raw_config = proposal.get("config")
        raw_config = raw_config if isinstance(raw_config, dict) else {}
        # Applying a proposal always CREATES a brand-new Agentbot -- never
        # trust an LLM-authored "id" (mirrors handle_create_agentbot's
        # id-stripping discipline in handlers_agentbots.py), so
        # validate_agentbot always mints a fresh one instead of silently
        # overwriting an unrelated existing Agentbot that happens to share
        # that id.
        raw_config = {k: v for k, v in raw_config.items() if k != "id"}
        cleaned = agentbots_store.validate_agentbot(raw_config)
        if cleaned is None:
            return web.json_response(
                {"error": "Config Agentbot non valida o non sicura"}, status=400
            )
        all_agentbots = agentbots_store.upsert_agentbot(data_dir, cleaned)
        # Same post-save step the /api/agentbots create handler runs: re-register
        # scheduler jobs, then refresh the in-memory Agentbot cache the Guardian
        # reads -- otherwise a newly created scheduled/event Agentbot would sit
        # on disk but not actually run until the next restart.
        await _apply_mutation(request.app, all_agentbots)
        applied = await proposal_store.apply(proposal_id)
        return web.json_response({"ok": bool(applied), "agentbot": cleaned})
    # Other proposal types: status-only apply. Con la validazione del tipo alla
    # creazione (proposal_tools._VALID_PROPOSAL_TYPES) nessuna proposta nota
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
