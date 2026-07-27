from __future__ import annotations
import logging
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


def build_mcp(client: Any) -> FastMCP:
    mcp = FastMCP("HIRIS", instructions=_INSTRUCTIONS)

    def _make(hiris_tool: str):
        async def _handler(inputs: dict | None = None) -> Any:
            return await client.execute(hiris_tool, inputs or {})
        return _handler

    for t in TOOLS:
        h = _make(t.hiris_tool)
        h.__name__ = t.name
        h.__doc__ = t.description
        mcp.tool(name=t.name, description=t.description)(h)
    return mcp


def make_asgi_app(mcp: FastMCP):
    return mcp.http_app()
