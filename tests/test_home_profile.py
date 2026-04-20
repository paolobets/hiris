from unittest.mock import MagicMock
from hiris.app.proxy.home_profile import generate_home_profile


def _make_cache(entities):
    cache = MagicMock()
    cache.get_all_useful.return_value = entities
    return cache


def test_generate_home_profile_starts_with_casa():
    cache = _make_cache([])
    result = generate_home_profile(cache)
    assert result.startswith("CASA [aggiornato")


def test_generate_home_profile_counts_on_entities():
    cache = _make_cache([
        {"id": "light.living",  "state": "on",   "name": "Living",  "unit": ""},
        {"id": "light.kitchen", "state": "on",   "name": "Kitchen", "unit": ""},
        {"id": "switch.pump",   "state": "on",   "name": "Pump",    "unit": ""},
        {"id": "sensor.temp",   "state": "22.5", "name": "Temp",    "unit": "°C"},
    ])
    result = generate_home_profile(cache)
    assert "Accesi(3):" in result
    assert "light(2)" in result
    assert "switch(1)" in result


def test_generate_home_profile_empty_cache():
    cache = _make_cache([])
    result = generate_home_profile(cache)
    assert "Accesi(0):" in result


def test_generate_home_profile_reports_climate():
    cache = _make_cache([
        {"id": "climate.soggiorno", "state": "heat", "name": "Soggiorno", "unit": ""},
    ])
    result = generate_home_profile(cache)
    assert "Soggiorno: heat" in result


def test_generate_home_profile_no_climate():
    cache = _make_cache([
        {"id": "light.test", "state": "on", "name": "Test", "unit": ""},
    ])
    result = generate_home_profile(cache)
    assert "Clima:" in result


import time
from unittest.mock import patch
from hiris.app.proxy.home_profile import get_cached_home_profile, _reset_profile_cache


def test_cached_home_profile_returns_string():
    _reset_profile_cache()
    cache = _make_cache([])
    result = get_cached_home_profile(cache)
    assert result.startswith("CASA [aggiornato")


def test_cached_home_profile_hit_within_ttl():
    _reset_profile_cache()
    cache = _make_cache([
        {"id": "light.a", "state": "on", "name": "A", "unit": ""},
    ])
    t0 = 1000.0
    with patch("hiris.app.proxy.home_profile._now", return_value=t0):
        first = get_cached_home_profile(cache, ttl=60.0)
    with patch("hiris.app.proxy.home_profile._now", return_value=t0 + 30.0):
        second = get_cached_home_profile(cache, ttl=60.0)
    assert first == second
    # get_all_useful deve essere chiamato 1 sola volta (cache hit)
    assert cache.get_all_useful.call_count == 1


def test_cached_home_profile_miss_after_ttl():
    _reset_profile_cache()
    cache = _make_cache([])
    t0 = 1000.0
    with patch("hiris.app.proxy.home_profile._now", return_value=t0):
        get_cached_home_profile(cache, ttl=60.0)
    with patch("hiris.app.proxy.home_profile._now", return_value=t0 + 61.0):
        get_cached_home_profile(cache, ttl=60.0)
    assert cache.get_all_useful.call_count == 2


def test_reset_profile_cache_forces_regeneration():
    _reset_profile_cache()
    cache = _make_cache([])
    t0 = 1000.0
    with patch("hiris.app.proxy.home_profile._now", return_value=t0):
        get_cached_home_profile(cache, ttl=600.0)
    _reset_profile_cache()
    with patch("hiris.app.proxy.home_profile._now", return_value=t0 + 1.0):
        get_cached_home_profile(cache, ttl=600.0)
    assert cache.get_all_useful.call_count == 2
