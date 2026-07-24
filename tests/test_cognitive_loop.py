"""Slice 6 Task 4 (integration): the coverage-review round gains an
auto-tune step (learnable detectors from history baselines, deterministic
-- never LLM-routed) and write-back brain-action traces, both for tunings
and for auto-applied coverage suggestions.

Follows the same conventions as test_suggestions.py (real SuggestionStore +
watcher.policy) and test_brain_trace.py (real KnowledgeStore + fake
embedder) -- only the LLM reasoning itself would ever be mocked, and this
module doesn't touch that at all (learned_threshold is pure/deterministic).
"""
import pytest

from hiris.app.brain.cognitive_loop import (
    BRAIN_TUNE_CAP,
    auto_tune_detectors,
    trace_applied_coverage,
)
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.suggestions import SuggestionStore, apply_suggestions
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
async def test_power_baseline_justifies_tuning_applies_and_traces(tmp_path, kstore):
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    emb = _FakeEmbedder()

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=emb, cap=BRAIN_TUNE_CAP,
    )

    assert applied == [{"detector": "power", "entity": "sensor.plug_power",
                        "params": {"max_watt": 1600}}]

    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 1600
    assert "sensor.plug_power" in pol["detectors"]["power"]["entities"]

    rows = kstore.list_items(kind="brain-action")
    assert len(rows) == 1
    assert rows[0]["source_ref"] == "brain-tune:power:sensor.plug_power"
    assert rows[0]["status"] == "approved"
    assert "sensor.plug_power" in rows[0]["content"]
    assert "1600" in rows[0]["content"]
    assert "800" in rows[0]["content"]

    res = kstore.search(query_vec=[1.0, 0.0, 0.0], k=5, kinds="brain-action")
    assert any(r["id"] == rows[0]["id"] for r in res)


@pytest.mark.asyncio
async def test_insufficient_history_no_tuning(tmp_path, kstore):
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
async def test_cap_respected_across_multiple_entities(tmp_path, kstore):
    dd = str(tmp_path)
    entities = [f"sensor.plug_{i}" for i in range(7)]
    _enable_power(dd, entities)
    baselines = {e: {"mean": 800.0, "on_hours": None, "n_days": 14} for e in entities}
    history = _FakeHistoryStore(baselines)

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=_FakeEmbedder(), cap=3,
    )

    assert len(applied) == 3
    assert len(kstore.list_items(kind="brain-action")) == 3


@pytest.mark.asyncio
async def test_one_failing_entity_does_not_abort_the_round(tmp_path, kstore):
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

    assert applied == [{"detector": "power", "entity": "sensor.good",
                        "params": {"max_watt": 1600}}]


@pytest.mark.asyncio
async def test_no_embedder_still_applies_tuning_but_writes_no_trace(tmp_path, kstore):
    """record_brain_action refuses to write with no embedder (Task 3); the
    tuning itself (deterministic, config-level) must still go through."""
    dd = str(tmp_path)
    _enable_power(dd, ["sensor.plug_power"])
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })

    applied = await auto_tune_detectors(
        data_dir=dd, policy=load_policy(dd), history_store=history,
        knowledge_store=kstore, embedder=None,
    )

    assert applied == [{"detector": "power", "entity": "sensor.plug_power",
                        "params": {"max_watt": 1600}}]
    assert load_policy(dd)["detectors"]["power"]["max_watt"] == 1600
    assert kstore.list_items(kind="brain-action") == []


@pytest.mark.asyncio
async def test_cap_binds_when_embedder_raises_on_trace_write(tmp_path, kstore, caplog):
    """Regression for the cap-fails-open bug: a REAL embedder makes a
    network call, and a service outage means record_brain_action can raise
    (this is not the same as embedder=None, which record_brain_action
    itself refuses gracefully -- see test_no_embedder_still_applies_tuning_
    but_writes_no_trace above). apply_brain_detector's policy mutation is
    deterministic and already happened, so it must be counted immediately;
    a raising trace write must not leave BRAIN_TUNE_CAP unbound -- with N >
    cap qualifying entities and a persistently-raising embedder, tuning
    must stop AT the cap, not silently tune all N in one round."""
    dd = str(tmp_path)
    entities = [f"sensor.plug_{i}" for i in range(7)]
    _enable_power(dd, entities)
    baselines = {e: {"mean": 800.0, "on_hours": None, "n_days": 14} for e in entities}
    history = _FakeHistoryStore(baselines)

    class _RaisingEmbedder:
        async def embed(self, text):
            raise ConnectionError("embedder service down")

    with caplog.at_level("ERROR"):
        applied = await auto_tune_detectors(
            data_dir=dd, policy=load_policy(dd), history_store=history,
            knowledge_store=kstore, embedder=_RaisingEmbedder(), cap=3,
        )

    # (a) capped at BRAIN_TUNE_CAP (here cap=3), NOT all 7 qualifying entities.
    assert len(applied) == 3
    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 1600

    # (b) no exception propagated out of auto_tune_detectors (already true
    # since we're past the `await` above without a raise, asserted for clarity).
    assert isinstance(applied, list)

    # (c) the failed trace write was logged, but no brain-action trace exists
    # (record_brain_action itself never got to write anything before raising).
    assert kstore.list_items(kind="brain-action") == []
    assert any("trace failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_applied_coverage_suggestion_writes_trace(tmp_path, kstore):
    dd = str(tmp_path)
    store = SuggestionStore(str(tmp_path / "s.db"))
    try:
        suggs = [{"kind": "coverage", "title": "Freezer", "rationale": "catena del freddo",
                  "config": {"detector": "fridge_temp", "entity": "sensor.freezer", "max_temp_c": 8}}]
        applied = apply_suggestions(
            suggs, data_dir=dd, store=store, inventory_ids={"sensor.freezer"},
            current_config=load_policy(dd), create_proposal=lambda c: None, cap=5,
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
            current_config=load_policy(dd), create_proposal=lambda c: None, cap=5,
        )
        assert applied == []

        written = await trace_applied_coverage(kstore, _FakeEmbedder(), applied)
        assert written == []
        assert kstore.list_items(kind="brain-action") == []
    finally:
        store.close()
