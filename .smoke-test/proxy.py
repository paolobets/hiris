"""
Mini proxy che inietta X-Ingress-Path header per testare HIRIS reale.
Bind 127.0.0.1:8765 → forward 192.168.1.95:8099 con header Ingress.
Serve /static/* dal disco locale (override file modificati senza rebuild addon).
"""
import asyncio
import os
import mimetypes
import aiohttp
from aiohttp import web

UPSTREAM = "http://192.168.1.95:8099"
INGRESS_HEADER = {"X-Ingress-Path": "/api/hassio_ingress/test_token_debug/"}
STATIC_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hiris", "app", "static"))


async def static_override(req: web.Request) -> web.Response | None:
    """Serve /static/* dal disco locale se il file esiste, altrimenti None per fallback proxy."""
    path = req.path
    if not path.startswith("/static/"):
        return None
    rel = path[len("/static/"):]
    # blocca path traversal
    if ".." in rel.split("/"):
        return None
    fs_path = os.path.join(STATIC_ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(fs_path):
        return None
    mt, _ = mimetypes.guess_type(fs_path)
    with open(fs_path, "rb") as f:
        body = f.read()
    return web.Response(status=200, body=body, headers={
        "Content-Type": mt or "application/octet-stream",
        "Cache-Control": "no-store",
        "X-Static-Override": "local",
    })


async def proxy(req: web.Request) -> web.Response:
    override = await static_override(req)
    if override is not None:
        return override
    path = req.path_qs
    url = UPSTREAM + path
    headers = {k: v for k, v in req.headers.items() if k.lower() not in (
        "host", "content-length", "x-ingress-path"
    )}
    headers.update(INGRESS_HEADER)
    body = await req.read() if req.body_exists else None
    timeout = aiohttp.ClientTimeout(total=605)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.request(req.method, url, headers=headers, data=body, allow_redirects=False) as resp:
                # Stream body
                content = await resp.read()
                # Filter hop-by-hop headers
                excluded = {"transfer-encoding", "content-encoding", "content-length", "connection"}
                resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
                return web.Response(status=resp.status, headers=resp_headers, body=content)
        except aiohttp.ClientError as e:
            return web.Response(status=502, text=f"Proxy error: {e}")


def build():
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", proxy)
    return app


if __name__ == "__main__":
    web.run_app(build(), host="127.0.0.1", port=8765, print=lambda *a, **kw: None)
