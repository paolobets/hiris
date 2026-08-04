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


class _NotLoadedCache(_FakeCache):
    """Simula la cache subito dopo l'avvio quando HA core non e' ancora
    pronto: `entity_cache.load()` e' fallito (inghiottito) e `loaded` resta
    False, ma il listener sugli eventi puo' aver gia' popolato qualche stato."""
    loaded = False


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


@pytest.mark.asyncio
async def test_observation_skips_when_cache_not_loaded(tmp_path):
    """Riavvio host: il Supervisor puo' avviare HIRIS prima che HA core sia
    pronto. `entity_cache.loaded` resta False finche' il primo `load()` non
    va a buon fine. Osservare comunque svuoterebbe/inquinerebbe la linea di
    base -- il giro va saltato, non eseguito su dati parziali."""
    store = PortraitStore(str(tmp_path / "p.db"))
    n = await server._osserva_la_casa({
        "portrait_store": store,
        "entity_cache": _NotLoadedCache([
            {"id": "light.a", "state": "on", "name": "A",
             "domain": "light", "device_class": None, "unit": ""}
        ]),
    })
    assert n == 0
    assert store.baseline() == {}
    store.close()


@pytest.mark.asyncio
async def test_observation_preserves_baseline_when_cache_not_loaded(tmp_path):
    """La linea di base gia' scritta da un giro precedente (buono) deve
    sopravvivere intatta a un giro successivo con cache non pronta: un
    giro saltato e' "un delta piu' vecchio", mai una linea di base perduta
    o inquinata da falsi "riapparsi" quando la cache si riprende."""
    store = PortraitStore(str(tmp_path / "p.db"))
    good_cache = _FakeCache([
        {"id": "light.a", "state": "on", "name": "A",
         "domain": "light", "device_class": None, "unit": ""}
    ])
    assert await server._osserva_la_casa(
        {"portrait_store": store, "entity_cache": good_cache}) == 0
    baseline_before = store.baseline()
    assert baseline_before  # il giro buono ha scritto qualcosa

    not_loaded = _NotLoadedCache([])  # cache tornata vuota durante il riavvio
    n = await server._osserva_la_casa(
        {"portrait_store": store, "entity_cache": not_loaded})
    assert n == 0
    assert store.baseline() == baseline_before
    store.close()


def test_observation_job_is_registered():
    src = inspect.getsource(server._on_startup)
    assert "hiris_portrait_observe" in src
    assert "_osserva_la_casa(app)" in src
    assert 'app["portrait_store"]' in src


def test_portrait_store_construction_is_wrapped_in_try_except():
    """Un portrait.db corrotto (perdita di corrente, disco guasto) fa
    sollevare sqlite3.DatabaseError da init_schema anche se connect() apre il
    file: senza un try/except attorno alla costruzione, l'eccezione uscirebbe
    da _on_startup e fermerebbe l'intero add-on (niente reasoner, niente
    scheduler, niente chat) per una cache ricostruibile. La costruzione vive
    dentro la closure di _on_startup e non e' raggiungibile direttamente dai
    test -- stessa convenzione delle altre verifiche di cablaggio in questo
    file, che ispezionano il sorgente."""
    src = inspect.getsource(server._on_startup)
    idx = src.index("PortraitStore(os.path.join(data_dir")
    before_construction = src[max(0, idx - 200):idx]
    assert "try:" in before_construction, (
        "la costruzione di PortraitStore deve essere dentro un try: un "
        "file corrotto non deve poter fermare l'intero avvio"
    )
    after_construction = src[idx:idx + 500]
    assert "except Exception" in after_construction, (
        "la costruzione di PortraitStore deve essere seguita da un "
        "except Exception che degrada a portrait_store non impostato"
    )


from hiris.app.watcher.reasoner import build_user_message
from hiris.app.watcher.signals import WakeEvent


class _FakeCacheWithAreas(_FakeCache):
    def get_area_map(self):
        return {"Cucina": ["light.a"]}


def test_portrait_context_returns_rendered_block(tmp_path):
    store = PortraitStore(str(tmp_path / "p.db"))
    states = [{"id": "light.a", "state": "on", "name": "Luce",
               "domain": "light", "device_class": None, "unit": ""}]
    store.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    txt = server._portrait_context({"portrait_store": store,
                                    "entity_cache": _FakeCacheWithAreas(states)})
    assert "Com'e' la casa" in txt and "Luce" in txt
    store.close()


def test_portrait_context_is_failure_safe(tmp_path):
    assert server._portrait_context({}) == ""
    assert server._portrait_context(None) == ""
    # Nessuno store: la guardia iniziale esce presto, la cache che solleva
    # non viene mai toccata -- questo caso da solo NON esercita il
    # try/except che protegge entrambi i consumatori del prompt.
    assert server._portrait_context({"entity_cache": _RaisingCache()}) == ""
    # Store reale + cache che solleva: qui la guardia iniziale passa e la
    # chiamata a cache.all_states() dentro il blocco protetto solleva
    # davvero -- e' il catch-all di _portrait_context, non la guardia, che
    # deve riportare "".
    store = PortraitStore(str(tmp_path / "p.db"))
    assert server._portrait_context({"portrait_store": store,
                                     "entity_cache": _RaisingCache()}) == ""
    store.close()


def test_user_message_renders_the_portrait_block():
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    msg = build_user_message(we, {"friendly_name": "Batt",
                                  "portrait": "Com'e' la casa:\n- Cucina — acceso: Luce"})
    assert "Com'e' la casa:" in msg
    assert "portrait" not in msg  # estratta dal context, non finita nel json
    assert msg.index("Com'e' la casa:") < msg.index("Valuta e rispondi")


def test_user_message_is_unchanged_when_portrait_absent_or_empty():
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    base = build_user_message(we, {"friendly_name": "Batt"})
    assert build_user_message(we, {"friendly_name": "Batt", "portrait": ""}) == base
    assert build_user_message(we, {"friendly_name": "Batt", "portrait": None}) == base


def test_long_portrait_survives_sanitization():
    """sanitize_ha_value tronca ogni valore a 120 caratteri. Se il ritratto
    passasse da _san insieme al resto del context arriverebbe al prompt mozzato
    alla prima riga, in silenzio. Va estratto PRIMA della sanificazione."""
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    lungo = "Com'e' la casa:\n" + "\n".join(f"- Area{i} — acceso: Luce{i}"
                                            for i in range(60))
    assert len(lungo) > 1000
    msg = build_user_message(we, {"friendly_name": "Batt", "portrait": lungo})
    assert "Area59" in msg
    assert len(msg) > 1000


def test_gather_context_is_wired_to_the_portrait():
    src = inspect.getsource(server._on_startup)
    assert "_portrait_context(app)" in src
    assert '"portrait"' in src


def test_holistic_is_wired_to_the_portrait():
    src = inspect.getsource(server._on_startup)
    assert "portrait=_portrait_context(app)" in src
