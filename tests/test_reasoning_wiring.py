def test_reasoning_routes_registered():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/reasoning/claim" in paths
    assert "/api/reasoning/submit" in paths


def test_reasoning_queue_importable():
    from hiris.app.reasoning.queue import ReasoningQueue
    assert ReasoningQueue is not None
