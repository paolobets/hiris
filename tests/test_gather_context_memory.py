"""Slice 6b Task 4: _gather_context (server.py) becomes memory-aware.

`_gather_context` is a closure defined inside `_on_startup` and isn't
independently reachable from tests (same situation as other _on_startup
closures -- see test_coverage_wiring.py / test_reasoning_wiring.py for the
established conventions this file follows). The memory-building logic was
therefore extracted to a module-level helper, `_reason_memory_context`,
which these tests exercise directly for the functional/discriminator
assertions the Task 4 brief calls for. A source-level check (same
`inspect.getsource` convention already used throughout this codebase for
_on_startup closures) confirms `_gather_context` itself is wired to call
the helper, stays async, and never raises.
"""
import inspect

import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.server import _reason_memory_context
from hiris.app.watcher.signals import WakeEvent


class _FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


class _RaisingEmbedder:
    async def embed(self, text):
        raise RuntimeError("embed boom")


class _RaisingSearchStore(KnowledgeStore):
    def search(self, **kwargs):
        raise RuntimeError("search boom")


class _LocalRouter:
    def automatic_allows_sensitive(self):
        return True


class _CloudRouter:
    def automatic_allows_sensitive(self):
        return False


class _RaisingRouter:
    def automatic_allows_sensitive(self):
        raise RuntimeError("router boom")


def _wake(signal_kind="battery_low", entity_id="sensor.x"):
    return WakeEvent(signal_kind=signal_kind, entity_id=entity_id,
                      severity_hint="warn", evidence={}, ts=1.0)


@pytest.mark.asyncio
async def test_local_router_includes_relevant_insight(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight",
        content="La caldaia va revisionata ogni anno a ottobre",
        owner="home", status="approved",
        embedding=[1.0, 0.0, 0.0], sensitivity="normal",
    )
    app = {"knowledge_store": store, "llm_router": _LocalRouter()}

    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Caldaia")

    assert any("caldaia" in s for s in mem.snippets)
    assert mem.by_meaning is True
    store.close()


@pytest.mark.asyncio
async def test_cloud_router_excludes_sensitive_includes_normal(tmp_path):
    """The egress gate discriminator: a cloud automatic chain
    (automatic_allows_sensitive() == False) must never see a
    sensitivity='sensitive' item, while a normal one still comes through."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight",
        content="Il codice del cancello segreto è 1234",
        owner="home", status="approved",
        embedding=[1.0, 0.0, 0.0], sensitivity="sensitive",
    )
    store.add_item(
        kind="insight",
        content="La caldaia va revisionata ogni anno a ottobre",
        owner="home", status="approved",
        embedding=[1.0, 0.0, 0.0], sensitivity="normal",
    )
    app = {"knowledge_store": store, "llm_router": _CloudRouter()}

    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Casa")

    assert not any("cancello" in s for s in mem.snippets)
    assert any("caldaia" in s for s in mem.snippets)
    assert mem.by_meaning is True
    store.close()


@pytest.mark.asyncio
async def test_local_router_with_sensitive_item_includes_it(tmp_path):
    """Mirror of the discriminator above with the gate open: a fully-local
    automatic chain is allowed to see sensitive memory too."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight",
        content="Il codice del cancello segreto è 1234",
        owner="home", status="approved",
        embedding=[1.0, 0.0, 0.0], sensitivity="sensitive",
    )
    app = {"knowledge_store": store, "llm_router": _LocalRouter()}

    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Casa")

    assert any("cancello" in s for s in mem.snippets)
    assert mem.by_meaning is True
    store.close()


@pytest.mark.asyncio
async def test_no_router_defaults_to_not_sensitive(tmp_path):
    """router is None (app.get('llm_router') returns None) -> allow_sensitive
    must default to False (fail closed), same contract as the brief."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight",
        content="Il codice del cancello segreto è 1234",
        owner="home", status="approved",
        embedding=[1.0, 0.0, 0.0], sensitivity="sensitive",
    )
    app = {"knowledge_store": store, "llm_router": None}

    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Casa")

    assert not any("cancello" in s for s in mem.snippets)
    store.close()


@pytest.mark.asyncio
async def test_no_knowledge_store_returns_empty_no_crash():
    app = {"knowledge_store": None, "llm_router": _LocalRouter()}
    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Casa")
    assert mem.snippets == []
    assert mem.by_meaning is False


@pytest.mark.asyncio
async def test_search_raises_returns_empty_no_crash(tmp_path):
    store = _RaisingSearchStore(str(tmp_path / "mem.db"))
    app = {"knowledge_store": store, "llm_router": _LocalRouter()}
    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Casa")
    assert mem.snippets == []
    assert mem.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_no_embedder_returns_empty_no_crash(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    app = {"knowledge_store": store, "llm_router": _LocalRouter()}
    mem = await _reason_memory_context(app, None, _wake(), "Casa")
    assert mem.snippets == []
    assert mem.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_embedder_raises_returns_empty_no_crash(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    app = {"knowledge_store": store, "llm_router": _LocalRouter()}
    mem = await _reason_memory_context(app, _RaisingEmbedder(), _wake(), "Casa")
    assert mem.snippets == []
    assert mem.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_router_raises_returns_empty_no_crash(tmp_path):
    """Defense-in-depth: relevant_memory() itself never raises, but a
    misbehaving router.automatic_allows_sensitive() could -- _reason_memory_
    context must degrade to MemoryRecall(snippets=[], by_meaning=False)
    rather than propagate (and never fall back to a bare list either, so
    _gather_context can keep reading `.snippets`/`.by_meaning` unconditionally)."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight", content="qualcosa", owner="home", status="approved",
        embedding=[1.0, 0.0, 0.0], sensitivity="normal",
    )
    app = {"knowledge_store": store, "llm_router": _RaisingRouter()}
    mem = await _reason_memory_context(app, _FakeEmbedder(), _wake(), "Casa")
    assert mem.snippets == []
    assert mem.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_app_none_returns_empty_no_crash():
    mem = await _reason_memory_context(None, _FakeEmbedder(), _wake(), "Casa")
    assert mem.snippets == []
    assert mem.by_meaning is False


# ---------------------------------------------------------------------------
# Wiring: _gather_context (the actual _on_startup closure) is async, calls
# the module-level helper above, and is itself never-raising end to end.
# Source-level check, same inspect.getsource convention as
# test_coverage_wiring.py / test_reasoning_wiring.py for closures that
# aren't independently reachable from tests.
# ---------------------------------------------------------------------------

def test_gather_context_is_async_and_wired_to_memory_helper():
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert "async def _gather_context(wake)" in src
    assert "await _reason_memory_context(app, embedder, wake, friendly_name)" in src
    assert '"memory": memory_snippets' in src
    # fetta 2b Task 2: `by_meaning` must ride alongside the snippets in the
    # SAME return -- a block can't claim/disclaim relevance without it.
    assert '"memory_by_meaning": memory_by_meaning' in src
    # Task 4 ("memoria unica 3a"): the declared block rides alongside memory
    # in the same return, same discipline.
    assert '"declared": declared_items' in src
    # Task 6: the twin assertion -- the portrait is wired into the same
    # return as memory, so both must survive together.
    assert '"portrait": _portrait_context(app)' in src


def test_gather_context_call_sites_await_reason():
    """Both reason(wake, gather_context=_gather_context, ...) call sites
    (_on_wake per-signal path, situations/holistic path) must await reason()
    -- reason() itself awaits gather_context when it's awaitable (Task 3),
    so no separate await of _gather_context is needed or expected at the
    call sites themselves."""
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    occurrences = [
        line for line in src.splitlines()
        if "gather_context=_gather_context" in line
    ]
    assert len(occurrences) == 2
    for line in occurrences:
        assert "await reason(" in line


def test_no_other_synchronous_gather_context_callers():
    """Grep-equivalent guard: the only *call syntax* occurrence of
    `_gather_context(` anywhere in server.py must be its own `async def`
    definition -- i.e. nothing in the module ever invokes it directly
    (`_gather_context(wake)`) outside of `reason`'s own body, where it's
    only ever passed BY REFERENCE (`gather_context=_gather_context`, no
    trailing paren) and awaited internally by `reason()` (Task 3)."""
    import re
    from hiris.app import server

    src = inspect.getsource(server)
    call_syntax = re.findall(r"_gather_context\(", src)
    assert len(call_syntax) == 1  # only the `async def _gather_context(wake)` line
    assert "async def _gather_context(wake)" in src

    by_reference = re.findall(r"gather_context=_gather_context\b", src)
    assert len(by_reference) == 2  # _on_wake (per-signal) + situations/ronda
