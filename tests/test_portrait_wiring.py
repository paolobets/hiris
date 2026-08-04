"""Osservazione periodica e cablaggio del ritratto.

I test di cablaggio leggono il sorgente di _on_startup perche' gli helper
interni sono closure non raggiungibili: stessa convenzione di
tests/test_gather_context_memory.py.
"""
import inspect

import pytest

from hiris.app import server
from hiris.app.brain.portrait_store import PortraitStore


class _FakeCache:
    def __init__(self, states):
        self._states = states

    def all_states(self):
        return self._states


class _RaisingCache:
    def all_states(self):
        raise RuntimeError("cache boom")


@pytest.mark.asyncio
async def test_observation_records_changes(tmp_path):
    store = PortraitStore(str(tmp_path / "p.db"))
    app = {"portrait_store": store,
           "entity_cache": _FakeCache([
               {"id": "light.a", "state": "on", "name": "A",
                "domain": "light", "device_class": None, "unit": ""}
           ])}
    assert await server._osserva_la_casa(app) == 0
    app["entity_cache"] = _FakeCache([
        {"id": "light.a", "state": "off", "name": "A",
         "domain": "light", "device_class": None, "unit": ""}
    ])
    assert await server._osserva_la_casa(app) == 1
    assert store.last_changes()[0]["was"] == "on"
    store.close()


@pytest.mark.asyncio
async def test_observation_is_failure_safe(tmp_path):
    store = PortraitStore(str(tmp_path / "p.db"))
    assert await server._osserva_la_casa({"portrait_store": store,
                                          "entity_cache": _RaisingCache()}) == 0
    assert await server._osserva_la_casa({}) == 0
    assert await server._osserva_la_casa(None) == 0
    store.close()


def test_observation_job_is_registered():
    src = inspect.getsource(server._on_startup)
    assert "hiris_portrait_observe" in src
    assert "_osserva_la_casa(app)" in src
    assert 'app["portrait_store"]' in src
