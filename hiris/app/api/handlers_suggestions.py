from __future__ import annotations
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


async def handle_list_suggestions(request: web.Request) -> web.Response:
    store = request.app.get("suggestion_store")
    if store is None:
        return web.json_response({"suggestions": []})
    return web.json_response({"suggestions": store.list()})


async def handle_undo_suggestion(request: web.Request) -> web.Response:
    try:
        sid = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"ok": False}, status=400)

    store = request.app.get("suggestion_store")
    data_dir = request.app.get("data_dir")
    if store is None or data_dir is None:
        return web.json_response({"ok": False})

    from ..brain.suggestions import undo
    # Grab the row before undo() flips its status -- delta is untouched by
    # set_status, but reading it beforehand keeps this independent of that.
    row = store.get(sid)
    ok = undo(store, data_dir, sid)

    if ok:
        # Slice 6 (whole-branch review I1): undo just restored detector config
        # on disk (a tuned threshold, or a coverage entity). The live guardian
        # runs off a policy override snapshot, so without a refresh the running
        # DETECTORS loop keeps the pre-undo value until the next UI save or
        # restart -- silently breaking the undo promise. Refresh it from disk.
        guardian = request.app.get("guardian")
        if guardian is not None:
            from ..watcher.policy import load_policy
            try:
                guardian.set_policy(load_policy(data_dir))
            except Exception:
                logger.exception("handle_undo_suggestion: guardian policy refresh failed")

        # Slice 6 Task 5: an undone row can be either a genuine coverage
        # suggestion (source_ref="brain-coverage:...") or a directly-applied
        # tuning surfaced the same way (source_ref="brain-tune:...", see
        # cognitive_loop.auto_tune_detectors) -- both are kind="coverage"
        # rows so the SAME undo route handles them. Remove the matching
        # brain-action trace too, so chat/recall stops surfacing an action
        # that no longer applies. Best-effort: a missing/failing trace must
        # never turn a successful undo into an error response.
        knowledge_store = request.app.get("knowledge_store")
        delta = row.get("delta") if row and isinstance(row.get("delta"), dict) else {}
        source_ref = delta.get("source_ref")
        if not source_ref and delta.get("detector") and delta.get("entity"):
            source_ref = f"brain-coverage:{delta['detector']}:{delta['entity']}"
        if knowledge_store is not None and source_ref:
            from ..brain.brain_trace import remove_brain_action
            try:
                await remove_brain_action(knowledge_store, source_ref)
            except Exception:
                logger.exception(
                    "handle_undo_suggestion: remove_brain_action failed for source_ref=%s",
                    source_ref,
                )

    return web.json_response({"ok": bool(ok)})
