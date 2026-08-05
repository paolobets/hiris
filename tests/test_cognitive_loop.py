"""Slice 6 Task 5B (INTEGRATION rework): the coverage-review round's
auto-tune step now tunes at the DETECTOR level, not per-entity.

Pivot: the real schema has ONE `max_watt` per detector, shared by every
entity on it. The earlier per-entity tuning (Task 4/5) was incoherent (last
entity tuned silently overwrote the shared threshold; undo could only remove
an entity, never restore a value). Now: ONE threshold is learned from the
busiest (highest-mean) qualifying entity's baseline, and undo RESTORES the
previous value via watcher.policy.apply_brain_tuning/remove_brain_tuning --
it never adds/removes entities.

Follows the same conventions as test_suggestions.py (real SuggestionStore +
watcher.policy) and test_brain_trace.py (real KnowledgeStore + fake
embedder) -- only the LLM reasoning itself would ever be mocked, and this
module doesn't touch that at all (learned_threshold is pure/deterministic).
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_suggestions import handle_undo_suggestion
from hiris.app.brain.brain_trace import remove_brain_action
from hiris.app.brain.cognitive_loop import (
    BRAIN_TUNE_CAP,
    auto_tune_detectors,
    trace_applied_coverage,
)
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.suggestions import SuggestionStore, apply_suggestions, undo
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.watcher.policy import load_policy, save_policy


class _FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


class _FakeHistoryStore:
    """Minimal fake matching HistoryStore.baseline_for's signature/shape."""

    def __init__(self, baselines: dict):
        self._baselines = baselines

    def baseline_for(self, entity_id, days=14, today=None):
        return self._baselines.get(
            entity_id, {"mean": None, "on_hours": None, "n_days": 0})


@pytest.fixture
def kstore(tmp_path):
    s = KnowledgeStore(str(tmp_path / "k.db"))
    yield s
    s.close()


def _enable_power(dd, entities, max_watt=3000):
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": entities,
                                              "max_watt": max_watt}}})


@pytest.mark.asyncio
async def test_busiest_entity_baseline_justifies_detector_tuning_applies_and_traces(tmp_path, kstore):
    """Two entities on the same detector: the QUIET one (mean~50, well under
    history threshold) must NOT drive the tuning -- the BUSY one (mean~800)
    is the representative baseline, per Task 5B's busiest-entity selection."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.quiet_power", "sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.quiet_power": {"mean": 50.0, "on_hours": None, "n_days": 14},
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    emb = _FakeEmbedder()

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=emb, cap=BRAIN_TUNE_CAP,
    )

    # Detector-level result: no "entity" key -- one shared param was tuned.
    assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]

    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 1600
    # Tuning a detector-level param must NOT add/remove entities.
    assert "sensor.plug_power" in pol["detectors"]["power"]["entities"]
    assert "sensor.quiet_power" in pol["detectors"]["power"]["entities"]

    rows = kstore.list_items(kind="brain-action")
    assert len(rows) == 1
    assert rows[0]["source_ref"] == "brain-tune:power"
    assert rows[0]["status"] == "approved"
    assert "sensor.plug_power" in rows[0]["content"]
    assert "1600" in rows[0]["content"]
    assert "800" in rows[0]["content"]

    res = kstore.search(query_vec=[1.0, 0.0, 0.0], k=5, kinds="brain-action")
    assert any(r["id"] == rows[0]["id"] for r in res)


@pytest.mark.asyncio
async def test_insufficient_history_on_all_entities_means_no_tuning(tmp_path, kstore):
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 5},
    })
    emb = _FakeEmbedder()

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=emb,
    )

    assert applied == []
    assert load_policy(dd)["detectors"]["power"]["max_watt"] == 3000
    assert kstore.list_items(kind="brain-action") == []


@pytest.mark.asyncio
async def test_disabled_detector_is_skipped(tmp_path, kstore):
    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {"enabled": False,
                                              "entities": ["sensor.plug_power"],
                                              "max_watt": 3000}}})
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=_FakeEmbedder(),
    )
    assert applied == []
    assert kstore.list_items(kind="brain-action") == []


@pytest.mark.asyncio
async def test_cap_respected_for_single_learnable_detector(tmp_path, kstore):
    """Task 5B: BRAIN_TUNE_CAP now bounds the number of DETECTORS tuned per
    round, not entities. v1 has exactly one LEARNABLE detector ("power"), so
    cap=0 must skip it entirely and any cap>=1 must tune it exactly once."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })

    capped = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=_FakeEmbedder(), cap=0,
    )
    assert capped == []
    assert load_policy(dd)["detectors"]["power"]["max_watt"] == 3000

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=_FakeEmbedder(), cap=BRAIN_TUNE_CAP,
    )
    assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]


@pytest.mark.asyncio
async def test_one_entity_baseline_failure_does_not_abort_detector_tuning(tmp_path, kstore):
    """baseline_for raising for ONE entity of the detector must not prevent
    the busiest-entity scan from still finding a valid baseline on another
    entity and tuning the detector from it."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.bad", "sensor.good"])

    class _RaisingHistoryStore:
        def baseline_for(self, entity_id, days=14, today=None):
            if entity_id == "sensor.bad":
                raise RuntimeError("boom")
            return {"mean": 800.0, "on_hours": None, "n_days": 14}

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=_RaisingHistoryStore(),
        knowledge_store=kstore, embedder=_FakeEmbedder(),
    )

    assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]


@pytest.mark.asyncio
async def test_no_embedder_still_applies_tuning_and_writes_undoable_trace(tmp_path, kstore):
    """record_brain_action no longer refuses to write with no embedder
    (memoria fetta 2a, Task 4): the tuning itself (deterministic,
    config-level) still goes through, AND the trace is now written too --
    with a NULL embedding, so it won't surface via vector search, but it is
    still found and removed by remove_brain_action, which is what makes the
    tuning undoable from the interface."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=None,
    )

    assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]
    assert load_policy(dd)["detectors"]["power"]["max_watt"] == 1600

    rows = kstore.list_items(kind="brain-action")
    assert len(rows) == 1
    assert rows[0]["source_ref"] == "brain-tune:power"

    removed = await remove_brain_action(kstore, "brain-tune:power")
    assert removed == 1
    assert kstore.list_items(kind="brain-action") == []


@pytest.mark.asyncio
async def test_raising_embedder_does_not_abort_tuning_and_still_writes_undoable_trace(
    tmp_path, kstore,
):
    """Regression for the cap-fails-open bug, updated for the final review
    fix: a REAL embedder makes a network call, and a service outage means
    record_brain_action's call to embed() can raise. record_brain_action now
    catches that raise itself (same as embedder=None or a falsy vector) and
    still writes the trace with a NULL embedding, because catching there
    writes the trace rather than swallowing anything -- the caller's own
    try/except around record_brain_action still protects the rest of this
    function's work regardless. apply_brain_tuning's policy mutation is
    deterministic and already happened, so it must be counted immediately;
    and the trace must come out undoable via remove_brain_action, exactly
    like the no-embedder case in
    test_no_embedder_still_applies_tuning_and_writes_undoable_trace -- a
    raising embedder must not cost the Brain its undo trace."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })

    class _RaisingEmbedder:
        async def embed(self, text):
            raise ConnectionError("embedder service down")

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=_RaisingEmbedder(), cap=BRAIN_TUNE_CAP,
    )

    # (a) the tuning still counts as applied.
    assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]
    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 1600

    # (b) the trace WAS written despite the raise, with no embedding.
    rows = kstore.list_items(kind="brain-action")
    assert len(rows) == 1
    assert rows[0]["source_ref"] == "brain-tune:power"
    assert kstore.get_item(rows[0]["id"])["has_embedding"] is False

    # (c) and it is removable, i.e. undoable from the interface.
    removed = await remove_brain_action(kstore, "brain-tune:power")
    assert removed == 1
    assert kstore.list_items(kind="brain-action") == []


@pytest.mark.asyncio
async def test_applied_coverage_suggestion_writes_trace(tmp_path, kstore):
    dd = str(tmp_path)
    store = SuggestionStore(str(tmp_path / "s.db"))
    try:
        suggs = [{"kind": "coverage", "title": "Freezer", "rationale": "catena del freddo",
                  "config": {"detector": "fridge_temp", "entity": "sensor.freezer", "max_temp_c": 8}}]
        applied = apply_suggestions(
            suggs, data_dir=dd, store=store, inventory_ids={"sensor.freezer"},
            current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5,
        )
        assert len(applied) == 1

        written = await trace_applied_coverage(kstore, _FakeEmbedder(), applied)

        assert len(written) == 1
        rows = kstore.list_items(kind="brain-action")
        assert len(rows) == 1
        assert rows[0]["source_ref"] == "brain-coverage:fridge_temp:sensor.freezer"
        assert "sensor.freezer" in rows[0]["content"]
        assert "fridge_temp" in rows[0]["content"]
    finally:
        store.close()


@pytest.mark.asyncio
async def test_management_suggestion_writes_no_trace(tmp_path, kstore):
    """Only kind="coverage" rows are traced -- management suggestions are
    forwarded to create_proposal and never appear in apply_suggestions'
    return value, so trace_applied_coverage naturally sees nothing for them."""
    dd = str(tmp_path)
    store = SuggestionStore(str(tmp_path / "s.db"))
    try:
        suggs = [{"kind": "management", "title": "Auto-off bagno", "rationale": "r", "config": {"x": 1}}]
        applied = apply_suggestions(
            suggs, data_dir=dd, store=store, inventory_ids=set(),
            current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5,
        )
        assert applied == []

        written = await trace_applied_coverage(kstore, _FakeEmbedder(), applied)
        assert written == []
        assert kstore.list_items(kind="brain-action") == []
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Slice 6 Task 5B: undo of a directly-applied DETECTOR-LEVEL tuning restores
# the previous value (and leaves entities untouched), plus removes its trace.
#
# auto_tune_detectors applies a tuning by calling apply_brain_tuning DIRECTLY
# -- it never goes through apply_suggestions/SuggestionStore.record on its
# own, so (unlike a coverage suggestion) there is no suggestion row and hence
# no {id} for the existing POST /api/suggestions/{id}/undo route to key off.
# The fix: when a SuggestionStore is passed to auto_tune_detectors, it ALSO
# records the applied tuning as a kind="coverage"/status="applied" row
# (delta={"detector": detector, "source_ref": "brain-tune:<detector>"}, NO
# "entity" -- a detector-level tuning isn't tied to one entity) -- the exact
# shape apply_suggestions already uses, so the EXISTING undo route/UI
# (sentinel-route.js renders "Annulla" for any kind="coverage"+
# status="applied" row) handles it with no new API surface. suggestions.
# undo() branches on delta["source_ref"].startswith("brain-tune:") to call
# remove_brain_tuning (restores the value) instead of remove_brain_detector
# (which would remove an entity -- wrong for a shared detector-level param).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tuning_recorded_as_undoable_suggestion_row(tmp_path, kstore):
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    sstore = SuggestionStore(str(tmp_path / "s.db"))
    try:
        applied = await auto_tune_detectors(
            data_dir=dd, policy=load_policy(dd), history_store=history,
            knowledge_store=kstore, embedder=_FakeEmbedder(), store=sstore,
        )
        assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]

        rows = sstore.list()
        assert len(rows) == 1
        assert rows[0]["kind"] == "coverage"
        assert rows[0]["status"] == "applied"
        # No "entity" key -- detector-level delta shape (Task 5B).
        assert rows[0]["delta"] == {
            "detector": "power",
            "source_ref": "brain-tune:power",
        }
    finally:
        sstore.close()


@pytest.mark.asyncio
async def test_no_store_passed_skips_suggestion_row_backward_compat(tmp_path, kstore):
    """store defaults to None -- existing callers (and the tests above) that
    don't pass it keep working exactly as before Task 5."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=_FakeEmbedder(),
    )
    assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]
    assert len(kstore.list_items(kind="brain-action")) == 1


@pytest.mark.asyncio
async def test_recall_finds_tune_trace_then_real_undo_restores_value_and_keeps_entities(
    tmp_path, kstore, aiohttp_client,
):
    """Full Task 5B flow, end to end:
      1. Apply a detector-level tuning (auto_tune_detectors path, two
         entities so we can also assert neither is touched by undo) with a
         SuggestionStore wired in.
      2. BEFORE undo: the REAL chat recall path (ToolDispatcher.dispatch(
         "recall_memory", ...), not a raw store call) finds the
         brain-action trace on a consumption-related query.
      3. Undo via the REAL API route (handle_undo_suggestion / POST
         /api/suggestions/{id}/undo) -- not a direct call to internal helpers.
      4. AFTER undo: max_watt is RESTORED to its pre-tuning value (via
         watcher.policy.remove_brain_tuning), BOTH entities remain on the
         detector (undo of a tuning must never remove an entity), and
         recall no longer finds the trace.
    """
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.quiet_power", "sensor.plug_power"], max_watt=3000)
    history = _FakeHistoryStore({
        "sensor.quiet_power": {"mean": 50.0, "on_hours": None, "n_days": 14},
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    emb = _FakeEmbedder()
    sstore = SuggestionStore(str(tmp_path / "s.db"))
    try:
        applied = await auto_tune_detectors(
            data_dir=dd, policy=load_policy(dd), history_store=history,
            knowledge_store=kstore, embedder=emb, store=sstore,
        )
        assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]
        assert load_policy(dd)["detectors"]["power"]["max_watt"] == 1600

        rows = sstore.list()
        assert len(rows) == 1
        sid = rows[0]["id"]

        # (2) Real chat recall path, BEFORE undo: recall_memory must surface
        # the brain-action trace for a consumption query -- kind is NOT
        # restricted to exclude "brain-action" (knowledge_kinds=None default).
        dispatcher = ToolDispatcher(None, {}, knowledge_store=kstore, embedder=emb)
        before = await dispatcher.dispatch(
            "recall_memory", {"query": "consumo energetico della presa"},
            user_id="home",
        )
        assert any(r["kind"] == "brain-action" for r in before["results"]), before

        # (3) Real undo route.
        app = web.Application()
        app["suggestion_store"] = sstore
        app["data_dir"] = dd
        app["knowledge_store"] = kstore
        app.router.add_post("/api/suggestions/{id}/undo", handle_undo_suggestion)
        client = await aiohttp_client(app)
        resp = await client.post(f"/api/suggestions/{sid}/undo")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True

        # (4a) Value RESTORED to the pre-tuning value (3000) via
        # remove_brain_tuning -- NOT entity removal. Both entities remain.
        pol = load_policy(dd)
        assert pol["detectors"]["power"]["max_watt"] == 3000
        assert "sensor.plug_power" in pol["detectors"]["power"]["entities"]
        assert "sensor.quiet_power" in pol["detectors"]["power"]["entities"]
        assert sstore.get(sid)["status"] == "dismissed"

        # (4b) Trace gone: recall no longer finds it via the real chat path.
        after = await dispatcher.dispatch(
            "recall_memory", {"query": "consumo energetico della presa"},
            user_id="home",
        )
        assert not any(r["kind"] == "brain-action" for r in after["results"]), after
        assert kstore.list_items(kind="brain-action") == []
    finally:
        sstore.close()


# ---------------------------------------------------------------------------
# M1 fast-follow: repeated drift rounds on the same detector must keep only
# ONE live, undoable applied brain-tune row. apply_brain_tuning snapshots the
# pre-tuning value ONLY ONCE (the very first tune), so if a SECOND round's
# tuning also recorded a fresh "applied" suggestion row without dealing with
# the first one, both rows would sit as kind="coverage"/status="applied" --
# but only the newest is backed by a live snapshot; undoing the STALE one
# would call remove_brain_tuning a second time (no-op, snapshot already
# consumed/overwritten) and either fail or restore the wrong value, while the
# UI still shows an "Annulla" button for it. _supersede_prior_tune_rows fixes
# this by marking any prior applied brain-tune:<detector> row "superseded"
# right before the new one is recorded.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_tune_round_supersedes_prior_applied_row_and_undo_restores_original(
    tmp_path, kstore,
):
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"], max_watt=3000)
    sstore = SuggestionStore(str(tmp_path / "s.db"))
    try:
        # Round 1: mean ~800 -> raw 1600, well past hysteresis vs the
        # original 3000 (diff ~47% > 15%) -- genuinely applies.
        history_round1 = _FakeHistoryStore({
            "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
        })
        applied1 = await auto_tune_detectors(
            data_dir=dd, policy=load_policy(dd), history_store=history_round1,
            knowledge_store=kstore, embedder=_FakeEmbedder(), store=sstore,
        )
        assert applied1 == [{"detector": "power", "params": {"max_watt": 1600}}]
        assert load_policy(dd)["detectors"]["power"]["max_watt"] == 1600

        rows_after_1 = sstore.list()
        assert len(rows_after_1) == 1
        assert rows_after_1[0]["status"] == "applied"
        assert rows_after_1[0]["delta"] == {
            "detector": "power",
            "source_ref": "brain-tune:power",
        }
        first_id = rows_after_1[0]["id"]

        # Round 2 (drift): mean ~1200 -> raw 2400, past hysteresis vs the NEW
        # current value 1600 (diff 50% > 15%) -- this round genuinely
        # applies AGAIN, moving max_watt from 1600 to 2400.
        history_round2 = _FakeHistoryStore({
            "sensor.plug_power": {"mean": 1200.0, "on_hours": None, "n_days": 14},
        })
        applied2 = await auto_tune_detectors(
            data_dir=dd, policy=load_policy(dd), history_store=history_round2,
            knowledge_store=kstore, embedder=_FakeEmbedder(), store=sstore,
        )
        assert applied2 == [{"detector": "power", "params": {"max_watt": 2400}}]
        assert load_policy(dd)["detectors"]["power"]["max_watt"] == 2400

        # Exactly ONE applied brain-tune:power row remains -- the newest.
        rows_after_2 = sstore.list()
        applied_power_rows = [
            r for r in rows_after_2
            if r["kind"] == "coverage" and r["status"] == "applied"
            and isinstance(r["delta"], dict)
            and r["delta"].get("source_ref") == "brain-tune:power"
        ]
        assert len(applied_power_rows) == 1
        second_id = applied_power_rows[0]["id"]
        assert second_id != first_id

        # The earlier row must no longer read "applied" -- it is superseded,
        # never left dangling with an "Annulla" that would fail.
        first_row = sstore.get(first_id)
        assert first_row["status"] == "superseded"

        # Undo the SURVIVING row via the real undo path: restores the
        # ORIGINAL pre-tuning value (3000) -- apply_brain_tuning snapshots
        # only ONCE (round 1's call captured 3000); round 2 did not
        # re-snapshot the intermediate 1600, so this is the only correct
        # restore target regardless of how many rounds occurred.
        ok = undo(sstore, dd, second_id)
        assert ok is True
        assert load_policy(dd)["detectors"]["power"]["max_watt"] == 3000
        assert sstore.get(second_id)["status"] == "dismissed"
    finally:
        sstore.close()
