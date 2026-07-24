"""Cognitive-loop round (Slice 6 Task 4 — INTEGRATION): wires together
Task 1 (`HistoryStore.baseline_for`), Task 2 (`learned_threshold`) and
Task 3 (`record_brain_action`) into the coverage-review holistic round
(`server.py`'s `_holistic_reason`).

Two composable pieces, both called from the same round:

  - `auto_tune_detectors`: for each `LEARNABLE` detector (v1: "power") that
    is `enabled` in policy, for each of its entities, compute a baseline
    from `history_store` and propose a new threshold via `learned_threshold`
    (pure, deterministic -- the tuning value NEVER comes from the LLM/
    reasoner, per HIRIS's deterministic-action discipline). If a change is
    warranted, apply it (sidecar-tracked, undoable via
    `watcher.policy.apply_brain_detector`) and write a recallable
    brain-action trace via `record_brain_action` so the chat can later
    explain what the brain did.

  - `trace_applied_coverage`: for each coverage suggestion that
    `suggestions.apply_suggestions` already auto-applied this round, write
    the matching brain-action trace (same write-back, for the LLM-suggested/
    auto-detector-added coverage path).

Both isolate failures per-item (bad baseline_for call, apply failure,
embedder hiccup, ...): one failing entity/suggestion is logged and skipped,
never aborting the rest of the round. The outer coverage-review try/except
in `_holistic_reason` remains a second safety net.
"""
from __future__ import annotations

import logging

from .brain_trace import record_brain_action
from .learned_thresholds import LEARNABLE, learned_threshold
from ..watcher.policy import apply_brain_detector

logger = logging.getLogger(__name__)

# Sane per-round cap on auto-tunings, mirroring BRAIN_SUGGEST_CAP's role for
# coverage suggestions: keeps one holistic pass bounded regardless of how
# many learnable detectors/entities exist. server.py may override via the
# BRAIN_TUNE_CAP env var; this is the default when unset.
BRAIN_TUNE_CAP = 5


def _tune_text(detector: str, entity: str, params: dict, baseline: dict) -> str:
    """Human-readable trace text for an auto-tuning. v1 only has "power" in
    LEARNABLE; the phrasing below is specific to that (watts, "consumo").
    A future learnable detector would need its own case here -- falls back
    to a generic message so this never raises."""
    mean = baseline.get("mean") if isinstance(baseline, dict) else None
    mean_txt = str(round(mean)) if isinstance(mean, (int, float)) else "?"
    if detector == "power" and "max_watt" in params:
        return (f"Ho tarato la soglia di consumo di {entity} a {params['max_watt']}W "
                f"(media recente ~{mean_txt}W).")
    return f"Ho tarato la soglia {detector} di {entity} a {params} (media recente ~{mean_txt})."


async def auto_tune_detectors(
    *, data_dir: str, policy: dict, history_store, knowledge_store, embedder,
    cap: int = BRAIN_TUNE_CAP, store=None,
) -> list[dict]:
    """Auto-tune enabled LEARNABLE detectors from history baselines.

    Never raises: any per-entity failure (baseline_for, learned_threshold,
    apply_brain_detector, record_brain_action) is caught, logged, and
    skipped -- the round continues with the next entity. Returns the list
    of {"detector", "entity", "params"} actually applied, up to `cap`.

    `store` (a brain.suggestions.SuggestionStore), if given, ALSO records
    each applied tuning as a kind="coverage"/status="applied" row -- the
    exact shape apply_suggestions uses for auto-applied coverage -- with
    delta.source_ref="brain-tune:<detector>:<entity>". This is what makes a
    directly-applied tuning (unlike a coverage suggestion, it is never routed
    through apply_suggestions/SuggestionStore.record on its own) show up in
    the existing "Suggerimenti del cervello" list and be undoable via the
    existing POST /api/suggestions/{id}/undo route (Slice 6 Task 5), with NO
    new API surface or UI needed -- sentinel-route.js already renders an
    "Annulla" button for any row with kind=="coverage" and status=="applied".
    Optional and best-effort: a failure recording this row never blocks the
    tuning itself (already applied by this point) or its brain-action trace.
    """
    applied: list[dict] = []
    detectors_cfg = (policy or {}).get("detectors") if isinstance(policy, dict) else None
    if not isinstance(detectors_cfg, dict):
        return applied

    for detector in LEARNABLE:
        if len(applied) >= cap:
            break
        det_cfg = detectors_cfg.get(detector)
        if not isinstance(det_cfg, dict) or not det_cfg.get("enabled"):
            continue
        entities = det_cfg.get("entities")
        if not isinstance(entities, list):
            continue

        for entity in entities:
            if len(applied) >= cap:
                break
            if not isinstance(entity, str) or not entity:
                continue
            try:
                baseline = history_store.baseline_for(entity)
                params = learned_threshold(detector, baseline, det_cfg)
                if not params:
                    continue
                apply_brain_detector(data_dir, detector, entity, params)
                # Count the tuning as applied THE MOMENT apply_brain_detector
                # succeeds -- the policy mutation already happened and is
                # deterministic, so BRAIN_TUNE_CAP must bind on it regardless
                # of whether the trace write below succeeds. A raising
                # embedder (real embedder, network call, service down) must
                # never leave the cap unbound -- see feedback in this file's
                # module docstring re: per-item failure isolation.
                applied.append({"detector": detector, "entity": entity, "params": params})

                if store is not None:
                    try:
                        store.record(
                            "coverage",
                            f"Taratura {detector}: {entity}",
                            _tune_text(detector, entity, params, baseline),
                            {"detector": detector, "entity": entity, **params},
                            "applied",
                            {"detector": detector, "entity": entity,
                             "source_ref": f"brain-tune:{detector}:{entity}"},
                        )
                    except Exception:
                        logger.exception(
                            "auto_tune_detectors: suggestion-store record failed for "
                            "detector=%s entity=%s (tuning already applied and counted)",
                            detector, entity,
                        )

                try:
                    await record_brain_action(
                        knowledge_store, embedder,
                        text=_tune_text(detector, entity, params, baseline),
                        source_ref=f"brain-tune:{detector}:{entity}",
                    )
                except Exception:
                    logger.exception(
                        "auto_tune_detectors: trace failed for detector=%s entity=%s "
                        "(tuning already applied and counted)",
                        detector, entity,
                    )
            except Exception:
                logger.exception(
                    "auto_tune_detectors: tuning failed for detector=%s entity=%s",
                    detector, entity,
                )
                continue
    return applied


async def trace_applied_coverage(knowledge_store, embedder, applied_coverage: list[dict]) -> list[str]:
    """Write a recallable brain-action trace for each auto-applied COVERAGE
    suggestion (as returned by `suggestions.apply_suggestions`), so the chat
    can later explain what the brain did. One failing trace is isolated and
    does not affect the others. Returns the ids of the traces written."""
    written: list[str] = []
    for row in applied_coverage or []:
        if not isinstance(row, dict) or row.get("kind") != "coverage":
            continue
        delta = row.get("delta") if isinstance(row.get("delta"), dict) else {}
        detector = delta.get("detector")
        entity = delta.get("entity")
        if not detector or not entity:
            continue
        try:
            title = row.get("title") or f"{detector} su {entity}"
            text = f"Ho attivato la sorveglianza {detector} su {entity} ({title})."
            item_id = await record_brain_action(
                knowledge_store, embedder, text=text,
                source_ref=f"brain-coverage:{detector}:{entity}",
            )
            if item_id is not None:
                written.append(item_id)
        except Exception:
            logger.exception(
                "trace_applied_coverage: trace failed for detector=%s entity=%s",
                detector, entity,
            )
            continue
    return written
