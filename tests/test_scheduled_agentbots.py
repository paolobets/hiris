"""TDD for Slice 5b Task 5 -- SCHEDULED (cron/interval) user Agentbots
(renamed from "lens" in SP-4 Fase A Task 3).

`register_agentbot_schedules(app)` (registered in `hiris/app/server.py`)
reads the current enabled, `trigger.type == "schedule"` Agentbots
(`watcher.lenses.load_agentbots`) and (re)registers one job per Agentbot on
`engine._scheduler` (the SAME AsyncIOScheduler instance the built-in
ronda/reset jobs already use), `id=f"hiris_agentbot_{agentbot_id}"`,
`replace_existing=True`, `trigger="cron"` (from `trigger.cron`, mapped onto
APScheduler's minute/hour/day/month/day_of_week fields) or
`trigger="interval"` (minutes=`trigger.interval_min`). It also removes any
`hiris_agentbot_*` job whose Agentbot no longer exists, is disabled, or is
no longer schedule-triggered -- mirroring `agent_engine.py`'s
`_unschedule_agent` job-enumeration pattern.

The per-Agentbot job callback (`_run_scheduled_agentbot`) optionally gates
on `trigger.condition` (evaluated against the CURRENT cached state via
`_condition_holds`, reusing `make_generic_detector` from Task 2 -- same
operator/threshold comparison, same no-data guard) before calling
`app["run_agentbot"](agentbot, {"entity_id": ...})`.

These tests exercise `register_agentbot_schedules`/`_run_scheduled_agentbot`/
`_condition_holds` directly against fakes (a fake scheduler recording
add_job/remove_job calls, a fake entity_cache, a fake `run_agentbot` spy) --
never booting the real aiohttp app (`_on_startup` connects to HA, writes
ingress config, etc., same reasoning as `test_run_agentbot.py`).
"""
from types import SimpleNamespace

import pytest

from hiris.app.server import (
    _condition_holds,
    _run_scheduled_agentbot,
    register_agentbot_schedules,
)
from hiris.app.watcher.lenses import save_agentbots


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeScheduler:
    """Records add_job/remove_job calls; mimics just enough of APScheduler's
    surface (`get_jobs()` -> objects with `.id`, `add_job(...)`,
    `remove_job(job_id)`) for `register_agentbot_schedules` to drive."""

    def __init__(self):
        self.jobs: dict[str, SimpleNamespace] = {}

    def get_jobs(self):
        return list(self.jobs.values())

    def add_job(self, func, trigger=None, id=None, replace_existing=False, **kwargs):
        job = SimpleNamespace(id=id, func=func, trigger=trigger,
                               replace_existing=replace_existing, kwargs=kwargs)
        self.jobs[id] = job
        return job

    def remove_job(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)  # mimics apscheduler.JobLookupError-ish failure
        del self.jobs[job_id]


class FakeEngine:
    def __init__(self, scheduler):
        self._scheduler = scheduler


class FakeCache:
    def __init__(self, states: dict[str, dict]):
        self._states = states

    def get_state(self, entity_id):
        return self._states.get(entity_id)


def _app(scheduler, data_dir, *, cache=None, run_agentbot=None):
    return {
        "engine": FakeEngine(scheduler),
        "data_dir": str(data_dir),
        "entity_cache": cache,
        "run_agentbot": run_agentbot,
    }


INTERVAL_LENS = {
    "id": "111111111111", "name": "Ronda ogni 5 min", "enabled": True,
    "trigger": {"type": "schedule", "interval_min": 5},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "check"},
    "severity": "info",
}

CRON_LENS = {
    "id": "222222222222", "name": "Ogni notte", "enabled": True,
    "trigger": {"type": "schedule", "cron": "0 3 * * *"},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "notte"},
    "severity": "info",
}

EVENT_LENS = {
    "id": "333333333333", "name": "Non schedulata", "enabled": True,
    "trigger": {"type": "event", "entity_id": "sensor.x", "operator": ">", "threshold": 1},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "x"},
    "severity": "info",
}

DISABLED_SCHEDULE_LENS = {**INTERVAL_LENS, "id": "444444444444", "enabled": False}

CONDITION_LENS = {
    "id": "555555555555", "name": "Con condizione", "enabled": True,
    "trigger": {"type": "schedule", "interval_min": 10,
                "condition": {"entity_id": "person.paolo", "operator": "==", "threshold": "home"}},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "sei a casa"},
    "severity": "info",
}


# ---------------------------------------------------------------------------
# register_agentbot_schedules: registration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_creates_job_for_interval_lens(tmp_path):
    save_agentbots(str(tmp_path), [INTERVAL_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    job = scheduler.jobs.get("hiris_agentbot_111111111111")
    assert job is not None
    assert job.trigger == "interval"
    assert job.kwargs.get("minutes") == 5
    assert job.replace_existing is True
    # Review fix: without a grace window, APScheduler's ~1s default misfire
    # tolerance silently drops a fire that lands while the loop is briefly
    # busy -- same 3600s grace every other scheduler job in server.py sets.
    assert job.kwargs.get("misfire_grace_time") == 3600


def _trigger_fields(job) -> dict[str, str]:
    return {f.name: str(f) for f in job.trigger.fields}


@pytest.mark.asyncio
async def test_register_creates_job_for_cron_lens_mapped_to_apscheduler_fields(tmp_path):
    from apscheduler.triggers.cron import CronTrigger

    save_agentbots(str(tmp_path), [CRON_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    job = scheduler.jobs.get("hiris_agentbot_222222222222")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    # "0 3 * * *" -> minute hour day month day_of_week; day_of_week=="*"
    # needs no crontab->APScheduler translation.
    fields = _trigger_fields(job)
    assert fields["minute"] == "0"
    assert fields["hour"] == "3"
    assert fields["day"] == "*"
    assert fields["month"] == "*"
    assert fields["day_of_week"] == "*"
    # Review fix: same 3600s misfire grace as every other scheduler job in
    # server.py -- a daily cron Agentbot must not get silently skipped for
    # 24h just because the loop was briefly busy at fire time.
    assert job.kwargs.get("misfire_grace_time") == 3600


# ---------------------------------------------------------------------------
# FIX 1 (Task 5 review): standard-crontab day_of_week numbering (0 or 7 =
# Sunday, 1 = Monday, ..., 6 = Saturday) must be translated to APScheduler's
# OWN CronTrigger day_of_week numbering (0 = Monday, ..., 6 = Sunday) --
# otherwise a Sunday cron silently fires on Monday, and the POSIX-legal "7"
# spelling of Sunday is rejected outright by APScheduler (whose max is 6).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_cron_sunday_dow0_maps_to_apscheduler_sunday(tmp_path):
    sunday_lens = {
        "id": "777777777777", "name": "Solo domenica", "enabled": True,
        "trigger": {"type": "schedule", "cron": "0 3 * * 0"},
        "reasoning": {"enabled": False},
        "action": {"type": "notify", "message": "domenica"},
        "severity": "info",
    }
    save_agentbots(str(tmp_path), [sunday_lens])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    job = scheduler.jobs["hiris_agentbot_777777777777"]
    # APScheduler's Sunday is day_of_week=6 -- NOT a bare passthrough of the
    # crontab "0" (which would be APScheduler's Monday, the pre-fix bug).
    assert _trigger_fields(job)["day_of_week"] == "6"


@pytest.mark.asyncio
async def test_register_cron_dow7_legal_posix_sunday_is_accepted(tmp_path):
    sunday7_lens = {
        "id": "888888888888", "name": "Domenica (7)", "enabled": True,
        "trigger": {"type": "schedule", "cron": "0 3 * * 7"},
        "reasoning": {"enabled": False},
        "action": {"type": "notify", "message": "domenica"},
        "severity": "info",
    }
    save_agentbots(str(tmp_path), [sunday7_lens])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)  # must not raise / skip -- "7" is legal POSIX cron

    job = scheduler.jobs.get("hiris_agentbot_888888888888")
    assert job is not None
    assert _trigger_fields(job)["day_of_week"] == "6"


@pytest.mark.asyncio
async def test_register_cron_weekday_range_maps_each_day(tmp_path):
    """"1-5" (standard-crontab Mon-Fri) -> APScheduler "0,1,2,3,4"."""
    weekday_lens = {
        "id": "999999999999", "name": "Feriali", "enabled": True,
        "trigger": {"type": "schedule", "cron": "0 9 * * 1-5"},
        "reasoning": {"enabled": False},
        "action": {"type": "notify", "message": "feriale"},
        "severity": "info",
    }
    save_agentbots(str(tmp_path), [weekday_lens])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    job = scheduler.jobs["hiris_agentbot_999999999999"]
    assert _trigger_fields(job)["day_of_week"] == "0,1,2,3,4"


@pytest.mark.asyncio
async def test_register_ignores_event_trigger_lenses(tmp_path):
    save_agentbots(str(tmp_path), [EVENT_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    assert scheduler.jobs == {}


@pytest.mark.asyncio
async def test_register_ignores_disabled_schedule_lens(tmp_path):
    save_agentbots(str(tmp_path), [DISABLED_SCHEDULE_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    assert scheduler.jobs == {}


@pytest.mark.asyncio
async def test_register_is_idempotent_replace_existing(tmp_path):
    save_agentbots(str(tmp_path), [INTERVAL_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)
    await register_agentbot_schedules(app)

    assert len(scheduler.jobs) == 1
    assert scheduler.jobs["hiris_agentbot_111111111111"].replace_existing is True


# ---------------------------------------------------------------------------
# register_agentbot_schedules: deregistration of orphaned jobs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_removes_job_for_deleted_lens(tmp_path):
    save_agentbots(str(tmp_path), [INTERVAL_LENS, CRON_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)
    await register_agentbot_schedules(app)
    assert set(scheduler.jobs) == {"hiris_agentbot_111111111111", "hiris_agentbot_222222222222"}

    # Agentbot deleted -> only CRON_LENS remains in the store.
    save_agentbots(str(tmp_path), [CRON_LENS])
    await register_agentbot_schedules(app)

    assert set(scheduler.jobs) == {"hiris_agentbot_222222222222"}


@pytest.mark.asyncio
async def test_register_removes_job_when_lens_disabled(tmp_path):
    save_agentbots(str(tmp_path), [INTERVAL_LENS])
    scheduler = FakeScheduler()
    app = _app(scheduler, tmp_path)
    await register_agentbot_schedules(app)
    assert "hiris_agentbot_111111111111" in scheduler.jobs

    save_agentbots(str(tmp_path), [{**INTERVAL_LENS, "enabled": False}])
    await register_agentbot_schedules(app)

    assert "hiris_agentbot_111111111111" not in scheduler.jobs


@pytest.mark.asyncio
async def test_register_leaves_non_lens_jobs_untouched(tmp_path):
    scheduler = FakeScheduler()
    scheduler.add_job(lambda: None, trigger="cron", id="hiris_sentinel_reset",
                       replace_existing=True, hour=0, minute=1)
    app = _app(scheduler, tmp_path)

    await register_agentbot_schedules(app)

    assert "hiris_sentinel_reset" in scheduler.jobs


# ---------------------------------------------------------------------------
# Fail-safe cron parsing: a value-invalid cron (passes the store's shape
# regex but is rejected by APScheduler's own field validation) must not
# crash registration -- it is skipped, and OTHER valid Agentbots still register.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bad_cron_value_is_skipped_without_crashing_registration(tmp_path):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    bad_cron_lens = {
        "id": "666666666666", "name": "Cron rotto", "enabled": True,
        # Shape-valid (5 numeric/`*` fields) per watcher.lenses._CRON_RE, but
        # hour=99 is out of APScheduler's 0-23 range -> CronTrigger raises at
        # add_job time.
        "trigger": {"type": "schedule", "cron": "0 99 * * *"},
        "reasoning": {"enabled": False},
        "action": {"type": "notify", "message": "x"},
        "severity": "info",
    }
    save_agentbots(str(tmp_path), [INTERVAL_LENS, bad_cron_lens])

    real_scheduler = AsyncIOScheduler()  # not started -- add_job still validates
    app = _app(real_scheduler, tmp_path)

    await register_agentbot_schedules(app)  # must not raise

    ids = {job.id for job in real_scheduler.get_jobs()}
    assert "hiris_agentbot_111111111111" in ids
    assert "hiris_agentbot_666666666666" not in ids


# ---------------------------------------------------------------------------
# _condition_holds
# ---------------------------------------------------------------------------

def test_condition_holds_absent_condition_is_true():
    assert _condition_holds(None, FakeCache({})) is True


def test_condition_holds_matching_state():
    condition = {"entity_id": "person.paolo", "operator": "==", "threshold": "home"}
    cache = FakeCache({"person.paolo": {"state": "home"}})
    assert _condition_holds(condition, cache) is True


def test_condition_holds_non_matching_state():
    condition = {"entity_id": "person.paolo", "operator": "==", "threshold": "home"}
    cache = FakeCache({"person.paolo": {"state": "not_home"}})
    assert _condition_holds(condition, cache) is False


def test_condition_holds_numeric_operator():
    condition = {"entity_id": "sensor.temp", "operator": ">", "threshold": 30}
    cache = FakeCache({"sensor.temp": {"state": "35"}})
    assert _condition_holds(condition, cache) is True
    cache_low = FakeCache({"sensor.temp": {"state": "10"}})
    assert _condition_holds(condition, cache_low) is False


def test_condition_holds_entity_missing_from_cache_is_false():
    condition = {"entity_id": "person.paolo", "operator": "==", "threshold": "home"}
    assert _condition_holds(condition, FakeCache({})) is False


def test_condition_holds_no_data_guard():
    condition = {"entity_id": "sensor.temp", "operator": "!=", "threshold": "20"}
    cache = FakeCache({"sensor.temp": {"state": "unavailable"}})
    assert _condition_holds(condition, cache) is False


def test_condition_holds_no_cache_is_false():
    condition = {"entity_id": "person.paolo", "operator": "==", "threshold": "home"}
    assert _condition_holds(condition, None) is False


# ---------------------------------------------------------------------------
# _run_scheduled_agentbot (the job callback)
# ---------------------------------------------------------------------------

class _RunLensSpy:
    def __init__(self, raise_exc: bool = False):
        self.calls = []
        self._raise = raise_exc

    async def __call__(self, lens, evidence, **kwargs):
        self.calls.append((lens, evidence, kwargs))
        if self._raise:
            raise RuntimeError("boom")
        return "woke"


@pytest.mark.asyncio
async def test_run_scheduled_lens_no_condition_calls_run_lens():
    spy = _RunLensSpy()
    await _run_scheduled_agentbot(INTERVAL_LENS, cache=None, run_agentbot=spy)
    assert spy.calls == [(INTERVAL_LENS, {"entity_id": "-"}, {"cooldown_sec": 0})]


@pytest.mark.asyncio
async def test_run_scheduled_lens_condition_satisfied_calls_run_lens():
    spy = _RunLensSpy()
    cache = FakeCache({"person.paolo": {"state": "home"}})
    await _run_scheduled_agentbot(CONDITION_LENS, cache=cache, run_agentbot=spy)
    assert spy.calls == [(CONDITION_LENS, {"entity_id": "person.paolo"}, {"cooldown_sec": 0})]


# ---------------------------------------------------------------------------
# FIX 2 (Task 5 review): the scheduled-Agentbot callback must pass
# `cooldown_sec=0` to `run_agentbot` -- its own interval/cron cadence IS the
# rate limiter, not the sentinel's default ~30-min cooldown.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_scheduled_lens_bypasses_cooldown_via_zero_override():
    spy = _RunLensSpy()
    await _run_scheduled_agentbot(INTERVAL_LENS, cache=None, run_agentbot=spy)
    assert spy.calls[0][2] == {"cooldown_sec": 0}


@pytest.mark.asyncio
async def test_run_scheduled_lens_condition_not_satisfied_does_not_call_run_lens():
    spy = _RunLensSpy()
    cache = FakeCache({"person.paolo": {"state": "not_home"}})
    await _run_scheduled_agentbot(CONDITION_LENS, cache=cache, run_agentbot=spy)
    assert spy.calls == []


@pytest.mark.asyncio
async def test_run_scheduled_lens_swallows_run_lens_exception():
    spy = _RunLensSpy(raise_exc=True)
    # Must not raise -- a broken scheduled Agentbot can't kill the scheduler.
    await _run_scheduled_agentbot(INTERVAL_LENS, cache=None, run_agentbot=spy)
    assert spy.calls  # it was still invoked before raising


# ---------------------------------------------------------------------------
# End-to-end: registered job's callback wired through
# register_agentbot_schedules actually consults the condition and the real
# run_agentbot closure.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registered_job_callback_honors_condition_end_to_end(tmp_path):
    save_agentbots(str(tmp_path), [CONDITION_LENS])
    scheduler = FakeScheduler()
    spy = _RunLensSpy()
    cache = FakeCache({"person.paolo": {"state": "not_home"}})
    app = _app(scheduler, tmp_path, cache=cache, run_agentbot=spy)

    await register_agentbot_schedules(app)
    job = scheduler.jobs["hiris_agentbot_555555555555"]
    await job.func()

    assert spy.calls == []  # condition not satisfied

    cache._states["person.paolo"] = {"state": "home"}
    await job.func()

    assert len(spy.calls) == 1
    assert spy.calls[0][1] == {"entity_id": "person.paolo"}
