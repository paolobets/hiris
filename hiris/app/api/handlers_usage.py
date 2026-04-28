from aiohttp import web
from ..config import EUR_RATE as _EUR_RATE


async def handle_usage(request: web.Request) -> web.Response:
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)

    inp = getattr(runner, "total_input_tokens", 0)
    out = getattr(runner, "total_output_tokens", 0)
    reqs = getattr(runner, "total_requests", 0)
    cost_usd = getattr(runner, "total_cost_usd", 0.0)
    rate_limit_errors = getattr(runner, "total_rate_limit_errors", 0)
    cost_eur = cost_usd * _EUR_RATE

    return web.json_response({
        "total_requests": reqs,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_eur, 6),
        "rate_limit_errors": rate_limit_errors,
        "last_reset": getattr(runner, "usage_last_reset", None),
    })


async def handle_reset_usage(request: web.Request) -> web.Response:
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    runner.reset_usage()
    return web.json_response({"reset": True, "last_reset": runner.usage_last_reset})
