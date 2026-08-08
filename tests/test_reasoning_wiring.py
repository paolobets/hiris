import pytest


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


@pytest.mark.asyncio
async def test_submit_logs_exception_from_execute_decision(aiohttp_client, tmp_path, caplog):
    """Fix 2: a failing execute_decision must be logged, not swallowed silently."""
    from aiohttp import web
    from hiris.app.api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
    from hiris.app.reasoning.queue import ReasoningQueue

    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info",
              "evidence": {}, "ts": 1.0}, {"snapshot": {}}, deadline_ts=100.0, job_id="J", now=1.0)

    app = web.Application()
    app["reasoning_queue"] = q
    app["_clock"] = lambda: 10.0

    async def _boom(decision, wake):
        raise RuntimeError("boom")
    app["execute_decision"] = _boom
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    client = await aiohttp_client(app)
    c = await (await client.post("/api/reasoning/claim")).json()
    with caplog.at_level("ERROR", logger="hiris.app.api.handlers_reasoning"):
        r = await client.post("/api/reasoning/submit", json={
            "job_id": "J", "nonce": c["job"]["nonce"],
            "decision": {"verdict": "anomalia", "message": "x"}})
    body = await r.json()
    assert body["ok"] is True and body["outcome"] == "error"
    assert any("execute_decision failed" in rec.message for rec in caplog.records)
    q.close()
