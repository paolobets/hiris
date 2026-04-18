from aiohttp import web

_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HIRIS</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #0f0f1a;
      color: #e2e8f0;
    }
    .card {
      text-align: center;
      padding: 2.5rem 3rem;
      border: 1px solid #2d2d4a;
      border-radius: 16px;
      background: #1a1a2e;
    }
    h1 { font-size: 2.5rem; margin: 0 0 0.25rem; letter-spacing: 0.05em; }
    .subtitle { color: #94a3b8; margin: 0 0 1.5rem; font-size: 0.95rem; }
    .badge {
      display: inline-block;
      background: #2d2d4a;
      color: #7c86b8;
      font-size: 0.8rem;
      padding: 0.25rem 0.75rem;
      border-radius: 999px;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>HIRIS</h1>
    <p class="subtitle">Home Intelligent Reasoning &amp; Integration System</p>
    <span class="badge">Phase 0 — scaffold</span>
  </div>
</body>
</html>
"""


async def handle_index(request: web.Request) -> web.Response:
    return web.Response(text=_INDEX_HTML, content_type="text/html")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": "0.1.0"})


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/health", handle_health)
