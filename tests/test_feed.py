from hiris.app.brain import feed


def test_reasoning_and_advisory_and_proposal_mapping():
    r = feed.reasoning_items([{"id": 1, "ts": "2026-07-28T08:00:00Z", "mode": "holistic", "text": "Ho dedotto X"}])
    assert r[0]["type"] == "reasoning" and r[0]["actions"] == []
    a = feed.advisory_items([
        {"id": 3, "ts_updated": "2026-07-28T09:00:00Z", "severity": "warn", "title": "Batteria",
         "suggested_fix": "Cambia", "evidence": {}, "status": "open", "check_id": "low_battery", "fix_kind": "manual"},
        {"id": 4, "ts_updated": "2026-07-28T07:00:00Z", "title": "vecchia", "status": "resolved",
         "severity": "warn", "suggested_fix": "", "evidence": {}, "check_id": "x", "fix_kind": "manual"},
    ])
    assert len(a) == 1 and a[0]["type"] == "advisory"  # resolved excluded
    assert set(x["type"] for x in a[0]["actions"]) if isinstance(a[0]["actions"], list) else True
    p = feed.proposal_items([{"id": "p1", "created_at": "2026-07-28T06:00:00Z", "name": "Auto", "description": "d"}])
    assert p[0]["type"] == "proposal"


def test_merge_sorts_desc_and_limits():
    items = feed.merge_feed(
        feed.reasoning_items([{"id": 1, "ts": "2026-07-28T08:00:00Z", "mode": "m", "text": "a"}]),
        feed.advisory_items([{"id": 2, "ts_updated": "2026-07-28T10:00:00Z", "severity": "warn",
                              "title": "t", "suggested_fix": "f", "evidence": {}, "status": "open",
                              "check_id": "c", "fix_kind": "manual"}]),
        limit=10,
    )
    assert [i["ts"] for i in items] == ["2026-07-28T10:00:00Z", "2026-07-28T08:00:00Z"]


def test_type_filter():
    items = feed.merge_feed(
        feed.reasoning_items([{"id": 1, "ts": "2026-07-28T08:00:00Z", "mode": "m", "text": "a"}]),
        feed.advisory_items([{"id": 2, "ts_updated": "2026-07-28T10:00:00Z", "severity": "warn",
                              "title": "t", "suggested_fix": "f", "evidence": {}, "status": "open",
                              "check_id": "c", "fix_kind": "manual"}]),
        type_filter="reasoning",
    )
    assert len(items) == 1 and items[0]["type"] == "reasoning"
