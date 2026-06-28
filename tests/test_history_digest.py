from hiris.app.brain.history_digest import (
    compute_insights, _sensitivity_for, _pct_delta,
)


def _numeric_buckets(start_day, vals):
    out = []
    for i, v in enumerate(vals):
        d = "2026-06-%02d" % (start_day + i)
        out.append({"t": d, "min": v - 1, "max": v + 1, "mean": v, "n": 24})
    return out


def test_pct_delta():
    assert _pct_delta(112.0, 100.0) == 12.0
    assert _pct_delta(100.0, 0.0) is None
    assert _pct_delta(90.0, 100.0) == -10.0


def test_sensitivity_for():
    assert _sensitivity_for("binary_sensor.porta") == "sensitive"
    assert _sensitivity_for("device_tracker.paolo") == "sensitive"
    assert _sensitivity_for("sensor.temp") == "normal"
    assert _sensitivity_for("climate.salotto") == "normal"


def test_compute_insights_numeric_delta():
    buckets = _numeric_buckets(7, [20, 20, 20, 20, 20, 20, 20, 24, 24, 24, 24, 24, 24, 24])
    ins = compute_insights("sensor.temp_salotto", buckets, today="2026-06-21")
    assert len(ins) == 1
    i = ins[0]
    assert i["entity_id"] == "sensor.temp_salotto"
    assert i["source_ref"] == "history-digest:sensor.temp_salotto:weekly"
    assert i["sensitivity"] == "normal"
    assert "20%" in i["text"] or "+20" in i["text"]
    assert "sensor.temp_salotto" in i["text"]


def test_compute_insights_onoff_summary():
    buckets = []
    for d in range(14, 21):
        buckets.append({"t": "2026-06-%02d" % d, "on_seconds": 3600, "transitions": 4})
    ins = compute_insights("binary_sensor.movimento", buckets, today="2026-06-21")
    assert len(ins) == 1
    i = ins[0]
    assert i["sensitivity"] == "sensitive"
    assert "ore" in i["text"].lower()


def test_compute_insights_insufficient_data_returns_none():
    buckets = [{"t": "2026-06-20", "mean": 20.0, "min": 19, "max": 21, "n": 5}]
    assert compute_insights("sensor.x", buckets, today="2026-06-21") == []


import pytest


class _FakeStore:
    def __init__(self, ents, buckets):
        self._ents = ents
        self._buckets = buckets
    def list_entities(self):
        return list(self._ents)
    def query(self, eid, days, today):
        b = self._buckets.get(eid)
        return {"id": eid, "source": "store", "buckets": b} if b else None


class _FakeKnowledge:
    def __init__(self):
        self.items = []
        self._id = 0
    def list_items(self, *, kind=None, limit=100, **kw):
        return [dict(it) for it in self.items if kind is None or it["kind"] == kind]
    def delete_item(self, item_id):
        self.items = [it for it in self.items if it["id"] != item_id]
    def add_item(self, *, kind, content, source_ref=None, sensitivity="normal",
                 embedding=None, **kw):
        self._id += 1
        self.items.append({"id": self._id, "kind": kind, "content": content,
                           "source_ref": source_ref, "sensitivity": sensitivity,
                           "has_emb": embedding is not None})
        return self._id


class _FakeEmbedder:
    async def embed(self, text):
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_run_history_digest_persists_and_supersedes():
    from hiris.app.brain.history_digest import run_history_digest
    buckets = {"sensor.temp": _numeric_buckets(7, [20] * 7 + [24] * 7)}
    store = _FakeStore(["sensor.temp"], buckets)
    kb = _FakeKnowledge()
    emb = _FakeEmbedder()
    n1 = await run_history_digest(store, kb, emb, today="2026-06-21")
    assert n1 == 1
    assert len(kb.items) == 1
    assert kb.items[0]["kind"] == "insight"
    assert kb.items[0]["source_ref"] == "history-digest:sensor.temp:weekly"
    assert kb.items[0]["has_emb"] is True
    n2 = await run_history_digest(store, kb, emb, today="2026-06-21")
    assert n2 == 1
    refs = [it for it in kb.items if it["source_ref"] == "history-digest:sensor.temp:weekly"]
    assert len(refs) == 1


@pytest.mark.asyncio
async def test_run_history_digest_handles_no_embedder():
    from hiris.app.brain.history_digest import run_history_digest
    buckets = {"sensor.temp": _numeric_buckets(7, [20] * 7 + [24] * 7)}
    store = _FakeStore(["sensor.temp"], buckets)
    kb = _FakeKnowledge()
    n = await run_history_digest(store, kb, None, today="2026-06-21")
    assert n == 1 and kb.items[0]["has_emb"] is False
