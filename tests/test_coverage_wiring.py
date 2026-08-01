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


def test_supervisor_client_lifecycle_wired_in_server_source():
    """Fix wave 1 (FIX 4): il ciclo di vita del SupervisorClient (costruzione
    solo con SUPERVISOR_TOKEN, avvio, slot nell'app, passaggio all'HealthMonitor,
    arresto nel cleanup) non era pinnato da nulla: cancellare la riga di stop
    non faceva fallire alcun test e la sessione aiohttp restava aperta.
    Controllo sul sorgente, stessa convenzione inspect.getsource degli altri
    wiring test di questo file."""
    import inspect
    from hiris.app import server

    startup = inspect.getsource(server._on_startup)
    # Su installazione standalone (nessun token) il client non si costruisce
    # affatto: eviterebbe tre GET a vuoto con timeout a ogni refresh.
    assert 'os.environ.get("SUPERVISOR_TOKEN", "").strip()' in startup
    assert "SupervisorClient(token=supervisor_token)" in startup
    assert "await supervisor_client.start()" in startup
    assert 'app["supervisor_client"] = supervisor_client' in startup
    assert "supervisor_client=supervisor_client" in startup

    cleanup = inspect.getsource(server._on_cleanup)
    assert 'await app["supervisor_client"].stop()' in cleanup


def test_health_monitor_lifecycle_wired_in_server_source():
    """Fix wave 1 (FIX 4): l'HealthMonitor deve essere costruito sul data_dir,
    avviato (registra il listener WS e il job a 30 minuti) e messo nello slot
    dell'app da cui lo leggono i tool e gli handler."""
    import inspect
    from hiris.app import server

    startup = inspect.getsource(server._on_startup)
    assert 'os.path.join(data_dir, "ha_health.json")' in startup
    assert "await health_monitor.start()" in startup
    assert 'app["health_monitor"] = health_monitor' in startup


def test_holistic_reason_wires_auto_tune_and_trace_coverage():
    """Slice 6 Task 4 wiring: _holistic_reason must call both
    trace_applied_coverage (write-back trace for auto-applied coverage
    suggestions) and auto_tune_detectors (learnable-detector auto-tuning).
    Source-level check, same inspect.getsource convention as the other
    wiring assertions in this file, so a regression that deletes either
    call is caught even though both are import-clean on their own (see
    test_coverage_review_symbols_importable above)."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert "auto_tune_detectors(" in src
    assert "trace_applied_coverage(" in src


def test_holistic_reason_refreshes_guardian_policy_after_auto_tune():
    """Whole-branch review I1: the live Guardian runs its DETECTORS loop off
    a policy override snapshot (guardian.py's `_policy_override`), which
    shadows the fresh disk read. auto_tune_detectors (and coverage
    suggestions applied just above it) write the policy FILE, but without
    refreshing the guardian's in-memory snapshot the running loop keeps
    stale thresholds until the next UI save or restart -- silently making
    the brain's tunings inert live. _holistic_reason must call
    guardian.set_policy(load_policy(data_dir)) right after
    auto_tune_detectors(...) so the live guardian picks up the fresh
    on-disk policy immediately. Source-level check, same inspect.getsource
    convention as the other wiring assertions in this file, so a regression
    that deletes the refresh is caught even though it has no import-time
    signature of its own."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert "await auto_tune_detectors(" in src
    assert "guardian.set_policy(load_policy(data_dir))" in src
    # server.py also calls guardian.set_policy(...) once at startup, before
    # _holistic_reason is even defined -- that's a DIFFERENT call and not
    # what this test is about. Find the refresh that happens AFTER the
    # auto_tune_detectors call specifically.
    tune_pos = src.index("await auto_tune_detectors(")
    refresh_pos = src.index("guardian.set_policy(load_policy(data_dir))", tune_pos)
    assert tune_pos < refresh_pos


def test_health_scan_job_receives_supervisor_client_from_app_source():
    """Fix wave 1 (FIX 1): il job periodico della scansione di salute (Task 6)
    passa a run_health_scan() il SupervisorClient tramite `app.get(...)` -- un
    accesso tollerante all'assenza perche' su installazioni senza Supervisor
    lo slot non esiste affatto. Nessun test di questo file lo pinnava:
    cancellare quell'argomento non farebbe fallire nulla (tutti i test di
    run_health_scan passano il client direttamente), e i tre controlli di
    sistema (addon_down, disk_space, updates_available) diventerebbero
    silenziosamente muti in produzione mentre la suite resta verde. Controllo
    sul sorgente, stessa convenzione inspect.getsource degli altri wiring
    test di questo file."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'supervisor_client=app.get("supervisor_client")' in src


def test_health_scan_job_reads_notify_option_and_config_from_server_source():
    """Fix wave 1 (FIX 5b): il job periodico deve passare a run_health_scan()
    sia `notify_config` (il canale su cui inviare) sia `notify_enabled` letto
    dall'opzione dell'add-on `brain_notify_high`. Nessun test lo pinnava:
    cancellando quelle due righe la suite resterebbe verde (tutti i test di
    run_health_scan passano la configurazione direttamente) e la notifica
    tornerebbe codice morto in produzione, senza che nulla se ne accorga.
    Controllo sul sorgente, stessa convenzione inspect.getsource degli altri
    wiring test di questo file; ristretto al blocco della chiamata perche'
    `notify_config=notify_config` compare anche altrove in _on_startup."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    inizio = src.index("await run_health_scan(")
    blocco = src[inizio:inizio + 1500]
    assert "notify_config=notify_config" in blocco
    assert 'notify_enabled=env_bool("BRAIN_NOTIFY_HIGH", True)' in blocco


def test_coverage_review_runs_before_bridge_enabled_branch():
    """The coverage-review block must sit BEFORE the BRIDGE_ENABLED early
    return in _holistic_reason, so it runs on every holistic pass regardless
    of the bridge flag (bridge coverage-review is out of scope/fast-follow)."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    review_pos = src.index("coverage-review")
    # SP-2 tech-debt: the BRIDGE_ENABLED gate now reads via env_util.env_bool.
    bridge_pos = src.index('env_bool("BRIDGE_ENABLED")')
    assert review_pos < bridge_pos
