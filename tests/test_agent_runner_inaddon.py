import asyncio
import subprocess
import time
import pytest
from unittest.mock import patch
from hiris.app.agent import runner, prompts


def test_build_chat_messages_available():
    system, user = prompts.build_chat_messages("Sei HIRIS.", [{"role": "user", "content": "ciao"}])
    assert "Sei HIRIS." in system and "Utente: ciao" in user


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


def test_reason_chat_returns_fallback_reply_on_nonzero_returncode():
    job = {"kind": "chat", "context": {"system_prompt": "Sei HIRIS.",
                                        "history": [{"role": "user", "content": "ciao"}]}}

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        result = runner._reason_chat(job, "live")

    assert isinstance(result, dict)
    assert isinstance(result.get("reply"), str) and result["reply"]


def test_reason_chat_returns_fallback_reply_on_timeout():
    job = {"kind": "chat", "context": {"system_prompt": "Sei HIRIS.",
                                        "history": [{"role": "user", "content": "ciao"}]}}

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


def test_run_once_chat_reasons_and_submits():
    job = {"job_id": "J", "nonce": "N", "kind": "chat",
           "context": {"system_prompt": "Sei HIRIS.", "history": [{"role": "user", "content": "che luci?"}]}}
    c = _Client({"job": job})

    class _Proc: returncode = 0; stdout = '{"result": "2 luci accese"}'; stderr = ""
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


# ── fetta E3 Task 7: `parse_decision` viveva in `watcher.reasoner`
# ("Consolidamento 1.4: unica implementazione"); la Sentinella (unico altro
# chiamante) e' uscita per intero in questo task, quindi il parser si e'
# trasferito qui con l'ultimo chiamante rimasto (`_parse_decision` +
# `Decision`/`VERDICT_*`/`FALLBACK_MESSAGE_MAX` ora vivono in questo modulo).
# `parse_decision` adatta la `Decision` alla forma a dizionario che viaggia
# sulla reasoning API. I due test sotto (rifiuto di un json non-oggetto,
# soglia unica di troncamento) erano in tests/test_sentinel_reasoner.py,
# cancellato con la Sentinella: coprivano un comportamento del parser stesso,
# non del percorso Sentinella, quindi si spostano qui sul nuovo (unico)
# proprietario. ──────────────────────────────────────────────────────────

def test_parse_decision_is_fail_closed_and_returns_the_wire_dict():
    d = runner.parse_decision("nessun blocco json qui")
    assert isinstance(d, dict)
    assert set(d) == {"verdict", "severity", "message", "action"}
    assert d["verdict"] == "falso_positivo"
    assert d["severity"] == "info"
    assert d["action"] is None


def test_parse_decision_missing_verdict_field_stays_fail_closed():
    d = runner.parse_decision('```json\n{"severity":"critico","message":"x"}\n```')
    assert d["verdict"] == "falso_positivo"


def test_parse_decision_reads_the_last_json_block():
    txt = ('```json\n{"verdict":"falso_positivo","severity":"info","message":"a"}\n```\n'
           '```json\n{"verdict":"anomalia","severity":"warn","message":"b",'
           '"action":{"domain":"light","service":"turn_off","entity_id":"light.x"}}\n```')
    d = runner.parse_decision(txt)
    assert d["verdict"] == "anomalia" and d["severity"] == "warn"
    assert d["action"]["entity_id"] == "light.x"


def test_parse_decision_rejects_json_that_is_not_an_object():
    # Un blocco json che contiene una lista (o uno scalare) non ha campi da
    # leggere: deve ricadere sul fallback, non sollevare AttributeError.
    d = runner.parse_decision('```json\n[1, 2, 3]\n```')
    assert d["verdict"] == "falso_positivo" and d["action"] is None


def test_parse_decision_fallback_message_truncation_is_the_single_threshold():
    d = runner.parse_decision("x" * 2000)
    assert len(d["message"]) == runner.FALLBACK_MESSAGE_MAX == 500
