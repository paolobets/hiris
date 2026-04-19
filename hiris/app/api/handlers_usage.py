from aiohttp import web

# Pricing per million tokens (USD) — claude-sonnet-4-6
_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5":  {"input": 0.25, "output": 1.25},
}
_EUR_RATE = 0.92  # approximate USD→EUR


async def handle_usage(request: web.Request) -> web.Response:
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)

    from ..claude_runner import MODEL
    prices = _PRICING.get(MODEL, {"input": 3.0, "output": 15.0})

    inp = getattr(runner, "total_input_tokens", 0)
    out = getattr(runner, "total_output_tokens", 0)
    reqs = getattr(runner, "total_requests", 0)

    cost_usd = (inp * prices["input"] + out * prices["output"]) / 1_000_000
    cost_eur = cost_usd * _EUR_RATE

    return web.json_response({
        "model": MODEL,
        "total_requests": reqs,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_eur, 6),
        "pricing_per_mtok": {"input_usd": prices["input"], "output_usd": prices["output"]},
        "last_reset": getattr(runner, "usage_last_reset", None),
    })


async def handle_reset_usage(request: web.Request) -> web.Response:
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    runner.reset_usage()
    return web.json_response({"reset": True, "last_reset": runner.usage_last_reset})
