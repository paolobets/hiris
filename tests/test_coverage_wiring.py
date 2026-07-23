def test_create_app_registers_entities_and_suggestions_routes():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/entities" in paths
    assert "/api/suggestions" in paths
    assert "/api/suggestions/{id}/undo" in paths


def test_coverage_review_symbols_importable():
    """Task 6 wiring smoke test: the pieces _holistic_reason's coverage-review
    block wires together import cleanly and are usable, without reloading
    hiris.app.server (import-time side effects — see the route-registration
    test above for that coverage). The real startup wiring (server.py's
    _on_startup/_holistic_reason) is verified separately via
    `python -c "import hiris.app.server"`, same convention as fetta 1/3's
    wiring tests (test_sentinel_wiring.py, test_reasoning_wiring.py)."""
    from hiris.app.brain.coverage_review import (
        COVERAGE_REVIEW_SYSTEM, build_review_context, build_review_message,
        parse_suggestions)
    from hiris.app.brain.suggestions import SuggestionStore, apply_suggestions
    from hiris.app.api.handlers_entities import filter_entities

    assert COVERAGE_REVIEW_SYSTEM
    assert build_review_context is not None
    assert build_review_message is not None
    assert parse_suggestions is not None
    assert SuggestionStore is not None
    assert apply_suggestions is not None
    assert filter_entities is not None


def test_suggestion_store_instantiated_in_server_source():
    """Task 6: assert server.py actually wires up the SuggestionStore in
    _on_startup (instantiation + app slot + cleanup), source-level check as a
    light complement to the runtime route-registration test above."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server)
    assert 'SuggestionStore(os.path.join(data_dir, "suggestions.db"))' in src
    assert 'app["suggestion_store"] = suggestion_store' in src
    assert 'app["suggestion_store"].close()' in src


def test_coverage_review_runs_before_bridge_enabled_branch():
    """The coverage-review block must sit BEFORE the BRIDGE_ENABLED early
    return in _holistic_reason, so it runs on every holistic pass regardless
    of the bridge flag (bridge coverage-review is out of scope/fast-follow)."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    review_pos = src.index("coverage-review")
    bridge_pos = src.index('BRIDGE_ENABLED", "0") in ("1", "true", "yes", "on")')
    assert review_pos < bridge_pos
