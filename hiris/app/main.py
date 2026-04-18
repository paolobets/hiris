import asyncio
import logging
import os

from aiohttp import web

from .routes import setup_routes


def create_app() -> web.Application:
    app = web.Application()
    setup_routes(app)
    return app


def main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "info").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8099)


if __name__ == "__main__":
    main()
