import asyncio
import os
import stat
import subprocess
import time
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
    assert "headers" not in srv


def test_configure_chat_mcp_writes_no_auth_config(tmp_path, monkeypatch):
    # configure_chat_mcp() writes the mcp-config actually used by `claude
    # --mcp-config`: it must be the loopback/no-auth shape (no headers key at
    # all), and (on POSIX) locked down to 0600 since it lives in a shared tmp dir.
    cfg_path = tmp_path / "hiris-mcp.json"
    monkeypatch.setenv("HIRIS_AGENT_MCP_CONFIG_PATH", str(cfg_path))
    monkeypatch.setenv("HIRIS_AGENT_MCP_URL", "http://127.0.0.1:8199/mcp")

    returned_path = runner.configure_chat_mcp()

    assert returned_path == str(cfg_path)
    assert runner._CHAT_MCP_CONFIG_PATH == str(cfg_path)
    assert cfg_path.exists()

    import json
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    srv = data["mcpServers"]["hiris"]
    assert srv["type"] == "http" and srv["url"] == "http://127.0.0.1:8199/mcp"
    assert "headers" not in srv

    if os.name != "nt":
        mode = stat.S_IMODE(os.stat(cfg_path).st_mode)
        assert mode == 0o600


def test_build_headers_only_internal_token_no_cf_access(monkeypatch):
    # Loopback-only reasoning API: only the internal token travels, never a
    # CF-Access service credential or a generic Authorization header.
    monkeypatch.setenv("INTERNAL_TOKEN", "TOK")
    headers = runner.build_headers()
    assert headers["X-HIRIS-Internal-Token"] == "TOK"
    assert "CF-Access-Client-Id" not in headers
    assert "CF-Access-Client-Secret" not in headers
    assert "Authorization" not in headers


def test_safe_subprocess_env_excludes_metered_api_keys(monkeypatch):
    # M-1 (Plan 2B final review, fast-follow): CLAUDE_API_KEY is HIRIS's own
    # METERED Anthropic key (see run.sh); the subscription runner must
    # authenticate `claude` via CLAUDE_CODE_OAUTH_TOKEN only. Forwarding the
    # metered key here would risk silent spend on the wrong credential. Both
    # denylisted names must be dropped even when present in os.environ,
    # while an unrelated CLAUDE_*/ANTHROPIC_* var (e.g. the OAuth token)
    # still passes through.
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-ant-metered-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-metered-secret-2")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")

    env = runner._safe_subprocess_env()

    assert "CLAUDE_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "oauth-token"


def test_reason_chat_returns_fallback_reply_on_nonzero_returncode(monkeypatch):
    job = {"kind": "chat", "context": {"system_prompt": "Sei HIRIS.",
                                        "history": [{"role": "user", "content": "ciao"}]}}
    monkeypatch.setattr(runner, "_CHAT_MCP_CONFIG_PATH", "/tmp/hiris-mcp.json")

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        result = runner._reason_chat(job, "live")

    assert isinstance(result, dict)
    assert isinstance(result.get("reply"), str) and result["reply"]


def test_reason_chat_returns_fallback_reply_on_timeout(monkeypatch):
    job = {"kind": "chat", "context": {"system_prompt": "Sei HIRIS.",
                                        "history": [{"role": "user", "content": "ciao"}]}}
    monkeypatch.setattr(runner, "_CHAT_MCP_CONFIG_PATH", "/tmp/hiris-mcp.json")

    def _raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=300)

    with patch.object(runner.subprocess, "run", _raise_timeout):
        result = runner._reason_chat(job, "live")

    assert isinstance(result, dict)
    assert isinstance(result.get("reply"), str) and result["reply"]


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


@pytest.mark.asyncio
async def test_run_loop_does_not_block_event_loop(monkeypatch):
    # run_once is slow+sync (real impl uses httpx.Client + subprocess.run); it
    # must be offloaded to a thread executor so a concurrent coroutine on the
    # same event loop keeps making progress while it runs. Regression test for
    # the event-loop-blocking defect found in Task 4 review.
    #
    # I-1 fast-follow (Plan 2B final review): the original version of this
    # test (`await ticker()` unconditionally, then assert `ticks >= 4`) is
    # tautological -- it passes even if run_loop blocks the loop, because the
    # ticker's sleeps just fire LATE once run_once finally releases the loop;
    # nothing bounds the wall-clock. Rewritten to bound it: the ticker's 5 x
    # 0.02s iterations are wrapped in `asyncio.wait_for(..., timeout=0.25)`.
    # With the run_in_executor offload, run_once's 0.3s sleep runs on a
    # separate thread, so the ticker finishes in ~0.1s and wait_for does NOT
    # raise. If run_loop were reverted to calling the blocking run_once
    # inline, the ticker would be stalled behind the 0.3s sleep and wait_for
    # WOULD raise TimeoutError -- making this test an actual regression guard.
    def slow_once(client, base_url, headers, mode):
        time.sleep(0.3)
        return "idle"
    monkeypatch.setattr(runner, "run_once", slow_once)

    # run_loop constructs a real httpx.Client(timeout=330) synchronously
    # before its first `await` -- in this environment that constructor alone
    # takes ~2.3s (Windows system cert-store loading), which would blow any
    # tight budget regardless of the run_once-offload fix under test. Stub it
    # out with a near-instant fake context manager so the test isolates
    # exactly the thing it's meant to check.
    class _FakeHttpxClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(runner.httpx, "Client", _FakeHttpxClient)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.02)
            ticks += 1

    loop_task = asyncio.create_task(
        runner.run_loop("http://127.0.0.1:8099", lambda: {}, "live", 0))
    try:
        await asyncio.wait_for(ticker(), timeout=0.25)
    except asyncio.TimeoutError:
        pytest.fail(
            "ticker did not complete within budget -- run_loop appears to be "
            "blocking the event loop instead of offloading run_once"
        )
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert ticks == 5  # all ticker iterations completed within the tight budget
