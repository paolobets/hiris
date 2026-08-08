def test_reasoning_routes_registered():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/reasoning/claim" in paths
    assert "/api/reasoning/submit" in paths


def test_reasoning_queue_importable():
    from hiris.app.reasoning.queue import ReasoningQueue
    assert ReasoningQueue is not None


# fetta E3 Task 5 (raccoglie la riserva della review E3 blocco 1, I-1):
# `_resolve_verdict` viveva qui come specchio LOCALE della risoluzione del
# verdetto che un tempo viveva in `_execute_decision` (server.py) --
# cancellata per intero dal Task 4 (101189a). Da allora
# `test_verdict_resolution_fails_closed` testava solo lo specchio, non
# poteva piu' cadere per nessuna modifica al prodotto: cancellato.
# La META' VIVA di `test_missing_verdict_decision_does_not_execute_action`
# (il fail-closed vero, dentro `watcher.executor.execute` su un verdetto
# "falso_positivo") era stata SPOSTATA in tests/test_sentinel_executor.py
# come `test_falso_positivo_verdict_skips_execution` -- quell'esecutore era
# vivo (Guardian/Sentinella, sarebbe uscito solo al Task 7), quindi il test
# si era spostato invece di morire, come impone la regola della fetta.
# fetta E3 Task 7: quel Task 7 e' questo. `watcher/executor.py` (e con lui
# tutto `watcher/`) e' uscito per intero: `test_sentinel_executor.py`
# (insieme al test spostato che portava) e' cancellato, non c'e' piu' un
# esecutore vivo a cui il fail-closed possa spostarsi di nuovo.
#
# fetta E3 Task 9 (rilievo 1 della review indipendente sul blocco 5-8):
# `test_submit_logs_exception_from_execute_decision`, che viveva qui,
# cancellato a sua volta: verificava che un `execute_decision` che solleva
# fosse loggato invece di sparire silenzioso (Fix 2). Il ramo che chiamava
# quel callable -- `ex = request.app.get("execute_decision"); if ex is not
# None: ...` -- e' uscito per intero da handlers_reasoning.py: sopravviveva
# dal Task 7 senza che nessun report lo nominasse, benche' la review del
# blocco 1 lo assegnasse "al piu' tardi col Task 7" e il Task 5 lo
# differisse qui per iscritto. Era l'ultimo punto del prodotto in cui un
# callable cablato in `app` avrebbe attuato una Decisione -- dormiente,
# cablato solo da questo test e dal suo gemello in test_reasoning_api.py,
# mai da produzione (verificato con grep esaustivo su `hiris/app`). Fatto
# cadere per costruzione prima della cancellazione: con l'hook rimosso
# l'outcome torna sempre "recorded" e il messaggio di log diventa quello
# del ramo "nessun execute_decision wired" (test_reasoning_api.py::
# test_submit_without_execute_decision_wired_records_and_logs, ancora vivo
# e ora l'UNICO comportamento possibile), non piu' "execute_decision
# failed" -- l'assert su `outcome == "error"` cadeva.
