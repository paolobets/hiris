from aiohttp import web

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
THEME_KEY = web.AppKey("theme")


async def handle_config(request: web.Request) -> web.Response:
    return web.json_response({"theme": request.app.get(THEME_KEY, "auto")})
