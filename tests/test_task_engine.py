import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from hiris.app.task_engine import Task, TaskEngine


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.call_service = AsyncMock(return_value=True)
    return ha


@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.get_state = MagicMock(return_value={"state": "15.0"})
    return cache


@pytest.fixture
def engine(tmp_path, mock_ha, mock_cache):
    te = TaskEngine(
        ha_client=mock_ha,
        entity_cache=mock_cache,
        notify_config={},
        data_path=str(tmp_path / "tasks.json"),
        execute_policy={"tiers": {"light": "green"}},
    )
    te._scheduler = MagicMock()  # prevent real scheduling
    return te


# ── Task 1: Core operations ────────────────────────────────────────────────


def test_add_task_returns_pending(engine):
    task = engine.add_task(
        {"label": "Test", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    assert task.status == "pending"
    assert task.agent_id == "hiris-default"
    assert task.id is not None


def test_cancel_pending_task(engine):
    task = engine.add_task(
        {"label": "Test", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    result = engine.cancel_task(task.id)
    assert result is True
    assert engine._tasks[task.id].status == "cancelled"


def test_cancel_nonexistent_task(engine):
    assert engine.cancel_task("does-not-exist") is False


def test_cancel_done_task_returns_false(engine):
    task = engine.add_task(
        {"label": "Test", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    engine._tasks[task.id].status = "done"
    assert engine.cancel_task(task.id) is False


def test_list_tasks_filter_by_status(engine):
    engine.add_task(
        {"label": "A", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-1",
    )
    t2 = engine.add_task(
        {"label": "B", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-2",
    )
    engine._tasks[t2.id].status = "done"
    pending = engine.list_tasks(status="pending")
    assert len(pending) == 1
    assert pending[0]["label"] == "A"


def test_list_tasks_filter_by_agent(engine):
    engine.add_task(
        {"label": "A", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-1",
    )
    engine.add_task(
        {"label": "B", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-2",
    )
    result = engine.list_tasks(agent_id="agent-1")
    assert len(result) == 1
    assert result[0]["label"] == "A"


def test_cleanup_removes_old_terminal_tasks(engine):
    task = engine.add_task(
        {"label": "Old", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=169)).isoformat()
    engine._tasks[task.id].status = "done"
    engine._tasks[task.id].created_at = old_ts
    engine._cleanup()
    assert task.id not in engine._tasks


def test_cleanup_keeps_recent_terminal_tasks(engine):
    task = engine.add_task(
        {"label": "Recent", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    engine._tasks[task.id].status = "done"
    engine._tasks[task.id].executed_at = datetime.now(timezone.utc).isoformat()
    engine._cleanup()
    assert task.id in engine._tasks


def test_cleanup_survives_concurrent_task_insertion(engine):
    """review M3/#3: _cleanup() is a sync APScheduler job run on a worker
    thread, iterating self._tasks while add_task() (event-loop thread) can
    insert a new key at the same time. Pre-fix this raised 'RuntimeError:
    dictionary changed size during iteration' because _cleanup iterated the
    live dict directly. This test reproduces the exact mechanism (a mutation
    landing mid-iteration, via a hook on datetime.fromisoformat which
    _cleanup calls once per terminal task) without needing real OS threads —
    the CPython-level hazard is identical regardless of what triggers the
    concurrent write.
    """
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
    for i in range(5):
        t = engine.add_task(
            {"label": f"Old{i}", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
            agent_id="hiris-default",
        )
        engine._tasks[t.id].status = "done"
        engine._tasks[t.id].executed_at = old_ts

    import hiris.app.task_engine as task_engine_module
    real_datetime = task_engine_module.datetime

    class _SpyDatetime:
        """Delegates to the real datetime class, but on the 2nd
        fromisoformat() call (i.e. mid-way through _cleanup's loop over the
        5 terminal tasks above) fires a concurrent add_task() — simulating
        the other thread inserting a new task while _cleanup is iterating."""

        calls = 0

        @staticmethod
        def now(tz=None):
            return real_datetime.now(tz)

        @staticmethod
        def fromisoformat(s):
            _SpyDatetime.calls += 1
            if _SpyDatetime.calls == 2:
                engine.add_task(
                    {"label": "concurrent", "trigger": {"type": "delay", "minutes": 1},
                     "actions": []},
                    agent_id="hiris-default",
                )
            return real_datetime.fromisoformat(s)

    task_engine_module.datetime = _SpyDatetime
    try:
        engine._cleanup()  # must not raise RuntimeError
    finally:
        task_engine_module.datetime = real_datetime

    # All 5 stale terminal tasks were reaped...
    remaining = list(engine._tasks.values())
    assert not any(t.label.startswith("Old") for t in remaining)
    # ...and the task inserted mid-iteration survived (it's pending, not terminal).
    assert any(t.label == "concurrent" for t in remaining)


def test_persistence_roundtrip(tmp_path, mock_ha, mock_cache):
    path = str(tmp_path / "tasks.json")
    te1 = TaskEngine(ha_client=mock_ha, entity_cache=mock_cache, notify_config={}, data_path=path)
    te1._scheduler = MagicMock()
    task = te1.add_task(
        {"label": "Persist me", "trigger": {"type": "delay", "minutes": 10}, "actions": []},
        agent_id="hiris-default",
    )

    te2 = TaskEngine(ha_client=mock_ha, entity_cache=mock_cache, notify_config={}, data_path=path)
    te2._scheduler = MagicMock()
    te2._load()
    assert task.id in te2._tasks
    assert te2._tasks[task.id].label == "Persist me"


# ── Task 2: Condition evaluation + execution ───────────────────────────────


def test_evaluate_condition_numeric_lt_passes(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "15.0"})
    assert engine._evaluate_condition(
        {"entity_id": "sensor.temp", "operator": "<", "value": 19}
    ) is True


def test_evaluate_condition_numeric_lt_fails(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "22.0"})
    assert engine._evaluate_condition(
        {"entity_id": "sensor.temp", "operator": "<", "value": 19}
    ) is False


def test_evaluate_condition_string_eq(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "on"})
    assert engine._evaluate_condition(
        {"entity_id": "binary_sensor.door", "operator": "=", "value": "on"}
    ) is True


def test_evaluate_condition_entity_missing(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value=None)
    assert engine._evaluate_condition(
        {"entity_id": "sensor.missing", "operator": "<", "value": 10}
    ) is False


@pytest.mark.asyncio
async def test_execute_task_done_on_success(engine, mock_ha):
    task = engine.add_task({
        "label": "Turn on",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on",
                     "data": {"entity_id": "light.test"}}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "done"
    mock_ha.call_service.assert_called_once_with("light", "turn_on", {"entity_id": "light.test"})


@pytest.mark.asyncio
async def test_execute_task_skipped_when_condition_false(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "25.0"})
    task = engine.add_task({
        "label": "Cond task",
        "trigger": {"type": "delay", "minutes": 1},
        "condition": {"entity_id": "sensor.temp", "operator": "<", "value": 19},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on", "data": {}}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "skipped"


@pytest.mark.asyncio
async def test_execute_task_failed_on_ha_error(engine, mock_ha):
    mock_ha.call_service = AsyncMock(side_effect=Exception("HA error"))
    task = engine.add_task({
        "label": "Fail task",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on", "data": {}, "on_fail": "stop"}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "failed"
    assert "HA error" in engine._tasks[task.id].error


@pytest.mark.asyncio
async def test_execute_task_chain_creates_child(engine):
    task = engine.add_task({
        "label": "Parent",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{
            "type": "create_task",
            "task": {
                "label": "Child",
                "trigger": {"type": "delay", "minutes": 60},
                "actions": [],
            }
        }],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "done"
    children = [t for t in engine._tasks.values() if t.parent_task_id == task.id]
    assert len(children) == 1
    assert children[0].label == "Child"


# ── Task 3: Additional coverage ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_time_window_within_window(engine, mock_ha):
    now = datetime.now()
    from_time = (now - timedelta(hours=1)).strftime("%H:%M")
    to_time = (now + timedelta(hours=1)).strftime("%H:%M")
    task = engine.add_task(
        {
            "label": "Window task",
            "trigger": {
                "type": "time_window",
                "from": from_time,
                "to": to_time,
                "check_interval_minutes": 5,
            },
            "actions": [
                {
                    "type": "call_ha_service",
                    "domain": "light",
                    "service": "turn_on",
                    "data": {"entity_id": "light.test"},
                }
            ],
        },
        agent_id="hiris-default",
    )
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "done"


def test_at_datetime_schedules_correct_run_date(engine):
    future = datetime.now() + timedelta(hours=2)
    future_iso = future.replace(microsecond=0).isoformat()
    task = engine.add_task(
        {"label": "Future", "trigger": {"type": "at_datetime", "datetime": future_iso}, "actions": []},
        agent_id="hiris-default",
    )
    run_date = engine._scheduler.add_job.call_args[1]["run_date"]
    assert abs((run_date - future).total_seconds()) < 2


def test_at_time_rollover(engine):
    task = engine.add_task(
        {"label": "Night", "trigger": {"type": "at_time", "time": "00:01"}, "actions": []},
        agent_id="hiris-default",
    )
    run_date = engine._scheduler.add_job.call_args[1]["run_date"]
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    assert run_date.date() == tomorrow


@pytest.mark.asyncio
async def test_unknown_action_marks_failed(engine):
    task = engine.add_task(
        {
            "label": "Bad action",
            "trigger": {"type": "delay", "minutes": 1},
            "actions": [{"type": "unknown_action", "foo": "bar", "on_fail": "stop"}],
        },
        agent_id="hiris-default",
    )
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "failed"
    assert "unknown_action" in engine._tasks[task.id].error


def test_cancel_removes_scheduler_job(engine):
    task = engine.add_task(
        {"label": "Cancel me", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    engine.cancel_task(task.id)
    removed = [c[0][0] for c in engine._scheduler.remove_job.call_args_list]
    assert f"task_{task.id}" in removed


class _FakeHA2:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {"ok": True}


def _engine(policy):
    return TaskEngine(
        ha_client=_FakeHA2(), entity_cache=None,
        notify_config={}, execute_policy=policy,
    )


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.asyncio
async def test_task_green_action_runs():
    eng = _engine({"tiers": {"light": "green"}})
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "data": {"entity_id": "light.kitchen"}}
    t = Task(id="t1", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert res == {"ok": True}
    assert eng._ha.calls == [("light", "turn_on", {"entity_id": "light.kitchen"})]


@pytest.mark.asyncio
async def test_task_off_action_skipped():
    eng = _engine({})  # fail-closed
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "data": {"entity_id": "light.kitchen"}}
    t = Task(id="t2", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert isinstance(res, str) and "skipped" in res
    assert eng._ha.calls == []


@pytest.mark.asyncio
async def test_task_dangerous_action_skipped():
    eng = _engine({"tiers": {"lock": "green"}})
    action = {"type": "call_ha_service", "domain": "lock", "service": "unlock",
              "data": {"entity_id": "lock.front"}}
    t = Task(id="t3", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert isinstance(res, str) and "skipped" in res
    assert eng._ha.calls == []


@pytest.mark.asyncio
async def test_task_area_target_without_entities_skipped():
    # A group target (area_id) with no explicit entity_id is not resolvable to
    # a per-entity tier -> fail-closed (skip), even if the domain is green.
    eng = _engine({"tiers": {"light": "green"}})
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "data": {"area_id": "cucina"}}
    t = Task(id="t4", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert isinstance(res, str) and res.startswith("skipped")
    assert eng._ha.calls == []


@pytest.mark.asyncio
async def test_task_group_target_log_message_matches_dispatcher_wording(caplog):
    # Fix 4: the guard fires on ANY group target (area/device/label), even
    # with explicit entities accompanying it — the stale message said "without
    # explicit entities" and omitted "label". Wording should now match the
    # dispatcher's own log line (dispatcher.py: "area/device/label target
    # present").
    eng = _engine({"tiers": {"light": "green"}})
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "data": {"label_id": "salotto", "entity_id": "light.sofa"}}
    t = Task(id="t4b", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    with caplog.at_level("WARNING", logger="hiris.app.task_engine"):
        res = await eng._run_action(action, t)
    assert isinstance(res, str) and res.startswith("skipped")
    logged = [r.message for r in caplog.records if "gated" in r.message]
    assert logged
    assert "area/device/label target present" in logged[0]
    assert "without explicit entities" not in logged[0]


# ── review A/#5: target-vs-data split (gated entities must == executed entities) ──


@pytest.mark.asyncio
async def test_task_target_only_scoped_call_not_broadcast_to_domain():
    # A deferred call_ha_service scoped via `target` (no `data.entity_id`) must
    # execute scoped to that entity, not as a domain-wide broadcast -- the task
    # engine previously read only `data`, so `target` was silently dropped and
    # HA received no entity_id filter at all.
    eng = _engine({"tiers": {"light": "green"}})
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "target": {"entity_id": "light.kitchen"}}
    t = Task(id="t5", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert res == {"ok": True}
    assert eng._ha.calls == [("light", "turn_on", {"entity_id": "light.kitchen"})]


@pytest.mark.asyncio
async def test_task_group_target_in_target_field_fail_closed():
    # The group-target fail-closed guard must fire when the area/device/label
    # lives under `target`, not only under `data` -- the task engine previously
    # never even read `target`, so this bypassed the guard entirely.
    eng = _engine({"tiers": {"light": "green"}})
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "target": {"area_id": "cucina"}}
    t = Task(id="t6", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert isinstance(res, str) and res.startswith("skipped")
    assert eng._ha.calls == []


@pytest.mark.asyncio
async def test_task_domain_wide_call_without_entity_still_works():
    # Neither data nor target carries an entity_id (or a group target) -> this
    # is a legitimate domain-wide call gated on the domain tier. Must keep
    # working exactly as before.
    eng = _engine({"tiers": {"light": "green"}})
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_off",
              "data": {}}
    t = Task(id="t7", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert res == {"ok": True}
    assert eng._ha.calls == [("light", "turn_off", {})]


@pytest.mark.asyncio
async def test_task_non_string_entity_id_does_not_crash():
    # entity_id: [123] (non-string list contents) must be filtered out (not
    # crash domain-of / gate lookup) and fall back to the domain-level tier;
    # with an unconfigured (fail-closed) domain that means deny_off/skipped.
    eng = _engine({})  # domain unconfigured -> off, fail-closed
    action = {"type": "call_ha_service", "domain": "light", "service": "turn_on",
              "data": {"entity_id": [123]}}
    t = Task(id="t5", label="x", agent_id="a", created_at=_now_iso(),
              trigger={"type": "immediate"}, actions=[action])
    res = await eng._run_action(action, t)
    assert isinstance(res, str) and "skipped" in res
    assert eng._ha.calls == []


@pytest.mark.asyncio
async def test_execute_task_records_gated_skip_honestly(engine):
    # engine fixture policy is {"tiers": {"light": "green"}} -> a lock action is
    # denylisted; the audit trail must show the real skip, not ":OK".
    task = engine.add_task({
        "label": "Gated",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{"type": "call_ha_service", "domain": "lock", "service": "unlock",
                     "data": {"entity_id": "lock.front"}}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "done"
    assert "skipped" in engine._tasks[task.id].result
    assert ":OK" not in engine._tasks[task.id].result


def test_cleanup_keeps_tasks_within_7_days(engine):
    """Tasks terminali più vecchi di 7gg vengono rimossi; quelli entro 7gg no."""
    from hiris.app.task_engine import _CLEANUP_AFTER_HOURS

    assert _CLEANUP_AFTER_HOURS == 168, "Expected 7 days (168h)"

    old_task = engine.add_task(
        {"label": "old", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="test",
    )
    old_task.status = "done"
    old_task.created_at = (
        datetime.now(timezone.utc) - timedelta(hours=169)
    ).isoformat()
    engine._tasks[old_task.id] = old_task

    recent_task = engine.add_task(
        {"label": "recent", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="test",
    )
    recent_task.status = "done"
    recent_task.created_at = (
        datetime.now(timezone.utc) - timedelta(hours=10)
    ).isoformat()
    engine._tasks[recent_task.id] = recent_task

    engine._cleanup()

    assert old_task.id not in engine._tasks
    assert recent_task.id in engine._tasks


# ── review C/#14: malformed condition must never stick a task at 'running' ─


def test_add_task_rejects_condition_missing_operator(engine):
    with pytest.raises(ValueError, match="operator"):
        engine.add_task(
            {
                "label": "Bad cond",
                "trigger": {"type": "delay", "minutes": 1},
                "actions": [],
                "condition": {"entity_id": "sensor.temp", "value": 10},
            },
            agent_id="hiris-default",
        )


def test_add_task_rejects_condition_missing_value(engine):
    with pytest.raises(ValueError, match="value"):
        engine.add_task(
            {
                "label": "Bad cond",
                "trigger": {"type": "delay", "minutes": 1},
                "actions": [],
                "condition": {"entity_id": "sensor.temp", "operator": "<"},
            },
            agent_id="hiris-default",
        )


def test_add_task_rejects_condition_missing_entity_id(engine):
    with pytest.raises(ValueError, match="entity_id"):
        engine.add_task(
            {
                "label": "Bad cond",
                "trigger": {"type": "delay", "minutes": 1},
                "actions": [],
                "condition": {"operator": "<", "value": 10},
            },
            agent_id="hiris-default",
        )


def test_add_task_rejects_condition_unknown_operator(engine):
    with pytest.raises(ValueError, match="operator"):
        engine.add_task(
            {
                "label": "Bad cond",
                "trigger": {"type": "delay", "minutes": 1},
                "actions": [],
                "condition": {"entity_id": "sensor.temp", "operator": "??", "value": 10},
            },
            agent_id="hiris-default",
        )


def test_add_task_rejects_condition_not_a_dict(engine):
    with pytest.raises(ValueError, match="object"):
        engine.add_task(
            {
                "label": "Bad cond",
                "trigger": {"type": "delay", "minutes": 1},
                "actions": [],
                "condition": "not-a-dict",
            },
            agent_id="hiris-default",
        )


def test_add_task_accepts_valid_condition(engine):
    task = engine.add_task(
        {
            "label": "Good cond",
            "trigger": {"type": "delay", "minutes": 1},
            "actions": [],
            "condition": {"entity_id": "sensor.temp", "operator": "<", "value": 19},
        },
        agent_id="hiris-default",
    )
    assert task.status == "pending"
    assert task.condition == {"entity_id": "sensor.temp", "operator": "<", "value": 19}


def test_add_task_no_condition_still_works(engine):
    task = engine.add_task(
        {"label": "No cond", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    assert task.status == "pending"
    assert task.condition is None


@pytest.mark.asyncio
async def test_execute_task_condition_crash_ends_terminal_not_stuck_running(engine, mock_cache):
    """If a malformed condition somehow reaches execution (e.g. legacy data
    on disk from before add_task validated the shape), _evaluate_condition
    raising must NOT leave the task stuck at 'running' forever -- it must
    end in a terminal status so it can be cleaned up. Bypasses add_task's
    validation by writing the bad condition directly onto the task, since
    add_task itself now rejects it at creation (defense in depth: this
    exercises the execution-time fail-safe independently)."""
    task = engine.add_task(
        {"label": "Crash cond", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    # Simulate a condition that raises inside _evaluate_condition (missing
    # 'operator' -> KeyError on condition["operator"]).
    engine._tasks[task.id].condition = {"entity_id": "sensor.temp", "value": 10}

    await engine._execute_task(task.id)

    from hiris.app.task_engine import _TERMINAL
    result_task = engine._tasks[task.id]
    assert result_task.status != "running"
    assert result_task.status in _TERMINAL
    assert result_task.status == "failed"
    assert result_task.error is not None

    # Terminal now -> _cleanup() will eventually reap it (was previously
    # impossible for a stuck 'running' task).
    result_task.executed_at = (
        datetime.now(timezone.utc) - timedelta(hours=169)
    ).isoformat()
    engine._cleanup()
    assert task.id not in engine._tasks


@pytest.mark.asyncio
async def test_execute_task_condition_crash_not_cancellable_but_not_stuck(engine):
    """A task already in a terminal status (post-fix) is not 'stuck running':
    cancel_task legitimately reports False (it's not pending -- it already
    finished), which is the correct terminal-state semantics, unlike the old
    bug where the task was permanently 'running' and ALSO uncancellable."""
    task = engine.add_task(
        {"label": "Crash cond 2", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    # Missing 'value' -> KeyError inside _evaluate_condition.
    engine._tasks[task.id].condition = {"entity_id": "sensor.temp", "operator": "<"}

    await engine._execute_task(task.id)

    result_task = engine._tasks[task.id]
    assert result_task.status == "failed"
    # Already terminal, so cancel correctly no-ops (not stuck at 'running').
    assert engine.cancel_task(task.id) is False


@pytest.mark.asyncio
async def test_execute_task_runs_when_valid_condition_met(engine, mock_cache, mock_ha):
    """Regression: a well-formed, satisfied condition still lets the task run
    its actions normally (the fail-safe must not interfere with the legit
    path)."""
    mock_cache.get_state = MagicMock(return_value={"state": "15.0"})
    task = engine.add_task(
        {
            "label": "Runs fine",
            "trigger": {"type": "delay", "minutes": 1},
            "condition": {"entity_id": "sensor.temp", "operator": "<", "value": 19},
            "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on",
                         "data": {"entity_id": "light.test"}}],
        },
        agent_id="hiris-default",
    )
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "done"
    mock_ha.call_service.assert_called_once_with("light", "turn_on", {"entity_id": "light.test"})
