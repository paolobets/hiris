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


def test_load_reads_legacy_chatbot_id_key(tmp_path, mock_ha, mock_cache):
    """Shim 1 (persistenza), non coperto da alcun test: un tasks.json scritto
    dalla generazione SP-4a (chiave 'chatbot_id') deve caricarsi comunque,
    facendo confluire il valore su agent_id -- senza riscrittura del file."""
    path = str(tmp_path / "tasks.json")
    legacy_task = {
        "id": "legacy-1",
        "label": "Legacy task",
        "chatbot_id": "legacy-agent",
        "created_at": "2026-01-01T00:00:00+00:00",
        "trigger": {"type": "delay", "minutes": 10},
        "actions": [],
        "status": "pending",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"schema_version": 1, "tasks": [legacy_task]}, f)

    te = TaskEngine(ha_client=mock_ha, entity_cache=mock_cache, notify_config={}, data_path=path)
    te._scheduler = MagicMock()
    te._load()

    assert "legacy-1" in te._tasks
    assert te._tasks["legacy-1"].agent_id == "legacy-agent"


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
async def test_execute_task_skipped_when_condition_false(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "25.0"})
    task = engine.add_task({
        "label": "Cond task",
        "trigger": {"type": "delay", "minutes": 1},
        "condition": {"entity_id": "sensor.temp", "operator": "<", "value": 19},
        "actions": [],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "skipped"


# ── Review finale fetta E2, I-1: l'attuazione esce dal Task Engine ─────────
# `call_ha_service` non e' piu' un'azione riconosciuta da `_run_action`: era
# l'unica via per cui HIRIS 2.0 poteva ancora agire su Home Assistant (via un
# tasks.json ereditato da un'installazione 1.x). Deve fallire in modo
# rumoroso -- come qualunque altro tipo di azione sconosciuto -- non essere
# saltata in silenzio.
@pytest.mark.asyncio
async def test_call_ha_service_action_is_no_longer_supported(engine, mock_ha):
    task = engine.add_task({
        "label": "Legacy da 1.x",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on",
                     "data": {"entity_id": "light.test"}, "on_fail": "stop"}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "failed"
    assert "call_ha_service" in engine._tasks[task.id].error
    mock_ha.call_service.assert_not_called()


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
            "actions": [],
        },
        agent_id="hiris-default",
    )
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "done"


def _patch_now(monkeypatch, hour, minute=0):
    """Freeze task_engine's clock at a fixed local time (deterministic
    midnight-wraparound tests, independent of the machine's wall-clock)."""
    import hiris.app.task_engine as te
    real = te.datetime
    fixed = real(2026, 7, 25, hour, minute)

    class _FakeDatetime(real):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(te, "datetime", _FakeDatetime)


@pytest.mark.asyncio
async def test_check_time_window_overnight_active_at_night(engine, mock_ha, monkeypatch):
    # Overnight window 23:00 -> 06:00 (spans midnight). At 02:00 we are INSIDE
    # it -> execute (regression: pre-fix this expired because to < from).
    _patch_now(monkeypatch, 2, 0)
    task = engine.add_task(
        {"label": "Notte", "trigger": {"type": "time_window", "from": "23:00",
         "to": "06:00", "check_interval_minutes": 5},
         "actions": []},
        agent_id="hiris-default")
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "done"


@pytest.mark.asyncio
async def test_check_time_window_overnight_dead_zone_waits_not_expired(engine, mock_ha, monkeypatch):
    # Same overnight window at 12:00 (the daytime dead-zone): NOT in window,
    # but a wrapping window recurs nightly -> stay pending, never "expired".
    _patch_now(monkeypatch, 12, 0)
    task = engine.add_task(
        {"label": "Notte", "trigger": {"type": "time_window", "from": "23:00",
         "to": "06:00", "check_interval_minutes": 5},
         "actions": []},
        agent_id="hiris-default")
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "pending"


@pytest.mark.asyncio
async def test_check_time_window_normal_expires_after_to(engine, mock_ha, monkeypatch):
    # Non-wrapping window 08:00 -> 10:00 at 12:00 -> fully past -> expired.
    _patch_now(monkeypatch, 12, 0)
    task = engine.add_task(
        {"label": "Mattina", "trigger": {"type": "time_window", "from": "08:00",
         "to": "10:00", "check_interval_minutes": 5},
         "actions": []},
        agent_id="hiris-default")
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "expired"


@pytest.mark.asyncio
async def test_check_time_window_degenerate_from_equals_to_expires(engine, mock_ha, monkeypatch):
    # A degenerate from==to window is a zero-length instant, NOT a wrapping
    # (always-active) window: once `now` is past it, the task must expire and
    # not live forever. Regression guard for `wraps = to_dt < from_dt`.
    _patch_now(monkeypatch, 12, 0)
    task = engine.add_task(
        {"label": "Istante", "trigger": {"type": "time_window", "from": "08:00",
         "to": "08:00", "check_interval_minutes": 5},
         "actions": []},
        agent_id="hiris-default")
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "expired"


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


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


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


# ── Perimetro del Task (Agenti v1.1 Fase 2 Task 3) ─────────────────────────
# Review finale fetta E2, I-1: l'enforcement di `allowed_entities`/
# `allowed_services` viveva SOLO dentro il ramo `call_ha_service` di
# `_run_action`, uscito con lui (era l'unica azione che li leggeva). I test
# che pinnavano quel rifiuto (dentro/fuori perimetro, liste vuote vs None,
# nessun perimetro) sono usciti con il loro soggetto: il ramo che applicava
# `allowed_entities`/`allowed_services` non esiste piu' in nessuna azione.
# Sopravvive solo l'eredita' identita'+perimetro nel chaining `create_task`
# sotto (attributi del Task, non un'esecuzione gated).


@pytest.mark.asyncio
async def test_child_task_inherits_parent_identity_and_perimeter(tmp_path):
    """Una catena di Task non e' una via d'uscita dal perimetro: il figlio
    nasce con l'`agent_id` e le allow-list del padre (attributi ereditati da
    `_run_action`'s ramo `create_task` -- non piu' applicati a un'esecuzione
    `call_ha_service`, uscita, ma restano metadati del Task figlio)."""
    eng = TaskEngine(
        ha_client=AsyncMock(), entity_cache=None, notify_config={},
        data_path=str(tmp_path / "tasks.json"),
    )
    eng._scheduler = MagicMock()
    action = {"type": "create_task", "task": {
        "label": "figlio", "trigger": {"type": "delay", "minutes": 5},
        "actions": []}}
    t = Task(id="p6", label="padre", agent_id="eeeeeeeeeeee", created_at=_now_iso(),
             trigger={"type": "immediate"}, actions=[action],
             allowed_entities=["light.cucina"], allowed_services=["light.*"])
    res = await eng._run_action(action, t)
    assert isinstance(res, str) and res.startswith("created child task")
    child = next(x for x in eng._tasks.values() if x.label == "figlio")
    assert child.agent_id == "eeeeeeeeeeee"
    assert child.allowed_entities == ["light.cucina"]
    assert child.allowed_services == ["light.*"]
    assert child.parent_task_id == "p6"
