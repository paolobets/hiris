import logging
import pytest
from hiris.app.server import build_internal_mcp_server


def test_build_internal_mcp_server_binds_loopback(monkeypatch):
    monkeypatch.setenv("INTERNAL_MCP_PORT", "8199")
    monkeypatch.setenv("INTERNAL_TOKEN", "TOK")
    client, config = build_internal_mcp_server(hiris_base_url="http://127.0.0.1:8099")
    # uvicorn.Config bound to loopback only, on the configured port
    assert config.host == "127.0.0.1"
    assert config.port == 8199
    assert client._token == "TOK"


@pytest.mark.asyncio
async def test_run_internal_mcp_contains_systemexit(caplog):
    from hiris.app.server import _run_internal_mcp

    class _BoomServer:
        async def serve(self):
            raise SystemExit(3)  # uvicorn does this on bind failure

    caplog.set_level(logging.ERROR)
    # must NOT raise -- a bind failure on the internal MCP port must be
    # contained to this optional feature, never propagate into the shared
    # asyncio loop and kill the whole addon.
    await _run_internal_mcp(_BoomServer())
    assert "Internal MCP server non avviato" in caplog.text
