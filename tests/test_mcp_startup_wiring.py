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
