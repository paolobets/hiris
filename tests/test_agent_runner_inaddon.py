import pytest
from unittest.mock import patch
from hiris.app.agent import runner, prompts


def test_build_chat_messages_available():
    system, user = prompts.build_chat_messages("Sei HIRIS.", [{"role": "user", "content": "ciao"}])
    assert "Sei HIRIS." in system and "Utente: ciao" in user


def test_mcp_config_loopback_no_auth():
    # 2A internal MCP is unauthenticated (loopback only) -> no auth header.
    cfg = runner.build_mcp_config("http://127.0.0.1:8199/mcp")
    srv = cfg["mcpServers"]["hiris"]
    assert srv["type"] == "http" and srv["url"] == "http://127.0.0.1:8199/mcp"
    assert "Authorization" not in srv.get("headers", {})
    assert "X-HIRIS-Internal-Token" not in srv.get("headers", {})


class _Resp:
    def __init__(self, data): self._d = data
    def json(self): return self._d
    def raise_for_status(self): pass


class _Client:
    def __init__(self, claim_body): self.claim_body = claim_body; self.submitted = []
    def post(self, url, headers=None, json=None):
        if url.endswith("/api/reasoning/claim"): return _Resp(self.claim_body)
        if url.endswith("/api/reasoning/submit"): self.submitted.append(json); return _Resp({"ok": True})
        raise AssertionError(url)


def test_run_once_chat_reasons_and_submits(monkeypatch):
    job = {"job_id": "J", "nonce": "N", "kind": "chat",
           "context": {"system_prompt": "Sei HIRIS.", "history": [{"role": "user", "content": "che luci?"}]}}
    c = _Client({"job": job})

    class _Proc: returncode = 0; stdout = '{"result": "2 luci accese"}'; stderr = ""
    monkeypatch.setattr(runner, "_CHAT_MCP_CONFIG_PATH", "/tmp/hiris-mcp.json")
    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        out = runner.run_once(c, "http://127.0.0.1:8099", {"X-HIRIS-Internal-Token": "TOK"}, "live")
    assert out == "done"
    assert c.submitted and c.submitted[0]["decision"] == {"reply": "2 luci accese"}
