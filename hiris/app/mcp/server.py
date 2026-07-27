from __future__ import annotations
import logging
import time
from typing import Any
from fastmcp import FastMCP
from .tiers import TOOLS

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Controlli la smart home tramite HIRIS. Letture sempre permesse; le azioni "
    "(call_service) passano dal semaforo e possono tornare 'in attesa di conferma' "
    "(verde=eseguita, giallo=conferma su iPhone, rosso=conferma in HIRIS): non e' un "
    "errore. Non eseguire azioni senza consenso esplicito dell'utente."
)


def build_mcp(client: Any, guard: Any = None) -> FastMCP:
    mcp = FastMCP("HIRIS", instructions=_INSTRUCTIONS)

    def _make(hiris_tool: str):
        async def _handler(inputs: dict | None = None) -> Any:
            if guard is not None and guard.is_killed():
                return {"error": "kill-switch attivo", "blocked": True}
            start = time.monotonic()
            outcome = "ok"
            try:
                return await client.execute(hiris_tool, inputs or {})
            except Exception:
                outcome = "error"
                raise
            finally:
                if guard is not None:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    guard.record(hiris_tool, outcome, latency_ms)
        return _handler

    for t in TOOLS:
        h = _make(t.hiris_tool)
        h.__name__ = t.name
        h.__doc__ = t.description
        mcp.tool(name=t.name, description=t.description)(h)
    return mcp


def make_asgi_app(mcp: FastMCP):
    return mcp.http_app()
