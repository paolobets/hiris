def test_create_app_registers_entities_routes():
    """fetta E3 Task 5: era test_create_app_registers_entities_and_suggestions_
    routes -- le due asserzioni /api/suggestions* sono uscite col Brain
    auto-proponente (handlers_suggestions.py, cancellato). /api/entities non
    c'entra nulla col Brain: resta, potato al proprio soggetto."""
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/entities" in paths


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


# fetta E3 Task 4: test_holistic_reason_wires_auto_tune_and_trace_coverage e
# test_holistic_reason_refreshes_guardian_policy_after_auto_tune sono usciti
# -- entrambi source-level check sul CORPO di `_holistic_reason`
# (auto_tune_detectors/trace_applied_coverage e il refresh guardian.set_
# policy() dopo l'auto-tune), che e' stato cancellato per intero con la
# ronda. Nessun successore: quella call-site non esiste piu' in nessuna
# forma. `auto_tune_detectors`/`trace_applied_coverage` erano rimasti
# importabili come orfani dichiarati per il Task 5 -- il Task 5 li ha
# cancellati per intero insieme a `brain.cognitive_loop`.
#
# fetta E3 Task 5: test_coverage_review_runs_before_bridge_enabled_branch
# (l'ordinamento del blocco coverage-review prima del ramo BRIDGE_ENABLED,
# dentro _holistic_reason) NON era stato davvero cancellato dal Task 4
# nonostante il suo report lo dichiarasse: il report aveva diagnosticato
# correttamente che passava per un motivo sbagliato (la stringa
# "coverage-review" sopravviveva per coincidenza in un commento successivo
# non correlato) ma la funzione era rimasta nel file. Trovato ed eliminato
# qui: `brain.coverage_review` e' cancellato per intero in questo task,
# quindi non c'e' proprio piu' nessun blocco coverage-review da ordinare.


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
