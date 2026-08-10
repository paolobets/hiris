import asyncio
import logging
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


# ── fetta E4 Task 8 ("un bot solo"): il ramo olistico di `reason()` e' uscito
# (con `prompts.build_holistic_prompt`/`_SYSTEM` e tutto l'apparato che ne
# leggeva la risposta: `Decision`, `VERDICT_*`, `_JSON_RE`,
# `FALLBACK_MESSAGE_MAX`, `_parse_decision`, `parse_decision` -- i cinque test
# che li pinnavano sono caduti per costruzione, `AttributeError: module ... has
# no attribute 'parse_decision'`). Al suo posto un SILENZIO DICHIARATO, e i due
# test qui sotto sono la sua rete: senza di loro, cancellare il `log.warning`
# lascerebbe la suite verde e il ponte tornerebbe a scartare job in silenzio --
# il difetto numero uno di questo prodotto. ──────────────────────────────────

def test_job_non_chat_e_dichiarato_nel_log_e_decide_vuoto(caplog):
    job = {"job_id": "J-legacy", "kind": "holistic",
           "context": {"snapshot": {"luci": 2}}}
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        decision = runner.reason(job, "live")

    # decisione VUOTA: nessun verdetto, nessuna severita', nessuna azione.
    assert decision == {}
    rec = [r for r in caplog.records if r.name == "hiris.agent"]
    assert len(rec) == 1, "il job scartato deve essere dichiarato una volta sola"
    assert rec[0].levelno == logging.WARNING
    messaggio = rec[0].getMessage()
    assert "J-legacy" in messaggio and "holistic" in messaggio
    assert "non-chat" in messaggio


def test_run_once_job_non_chat_invia_la_decisione_vuota_senza_chiamare_claude():
    # Il guard non e' un `return` muto a meta' strada: il job viene comunque
    # chiuso sulla reasoning API (submit con decisione vuota, che
    # `handle_reasoning_submit` si limita a registrare), e nessun `claude -p`
    # viene speso per ragionarlo.
    job = {"job_id": "J", "nonce": "N", "kind": "holistic", "context": {"snapshot": {}}}
    c = _Client({"job": job})

    def _boom(*a, **k):
        raise AssertionError("nessun subprocess claude per un job non-chat")

    with patch.object(runner.subprocess, "run", _boom):
        out = runner.run_once(c, "http://127.0.0.1:8099", {"X-HIRIS-Internal-Token": "TOK"}, "live")

    assert out == "done"
    assert c.submitted and c.submitted[0]["decision"] == {}


# ── fetta E4 Task 8, Step 1: `_CHAT_TOOL_GUIDANCE` diceva al modello di avere
# strumenti per leggere la casa "e, quando serve, per agire", e che "le azioni
# possono richiedere una conferma" -- tre affermazioni false in tre righe
# (rilievo I-1/I-2 della review finale della fetta E3, dal lato abbonamento).
# Questo runner ragiona in puro testo: nessun catalogo di strumenti gli viene
# passato (`_chat_claude_args` non passa ne' `--mcp-config` ne'
# `--allowedTools`), HIRIS conosce e non agisce, le conferme sono uscite con
# l'impianto OTP. Il test difende il CONTENUTO del prompt, l'unica riga del
# prodotto che il modello legge come verita': senza, la falsita' potrebbe
# rientrare a suite verde. ───────────────────────────────────────────────────

def test_il_prompt_di_sistema_del_ponte_non_promette_strumenti_ne_azioni():
    system, _user = prompts.build_chat_messages(
        "Per scoprire cosa c'e' in casa usa `cerca` e `guarda`.", [])

    # dice il vero su cio' che NON ha
    assert "NON hai alcuno strumento" in system
    assert "non agisce" in system
    assert "nessuna conferma" in system
    # e dice al modello di DICHIARARE cio' che non puo' leggere, non di fingerlo
    assert "DILLO" in system

    # le tre falsita' storiche non devono poter rientrare
    assert "per agire" not in system
    assert "Hai accesso a strumenti" not in system
    assert "in attesa di conferma" not in system


def test_il_prompt_del_ponte_smentisce_gli_strumenti_nominati_dalla_persona():
    # Il `system_prompt` che arriva al ponte e' quello delle impostazioni della
    # chat (`impostazioni_chat.DEFAULT_SYSTEM_PROMPT`), scritto per il percorso
    # SINCRONO -- dove i quattro strumenti di casa/strumenti.py esistono
    # davvero. Qui non esistono: la guida deve smentirlo esplicitamente, o il
    # modello leggerebbe "usa `cerca`" senza alcun modo di scoprire che non c'e'.
    from hiris.app.impostazioni_chat import DEFAULT_SYSTEM_PROMPT

    system, _user = prompts.build_chat_messages(DEFAULT_SYSTEM_PROMPT, [])

    assert "cerca" in DEFAULT_SYSTEM_PROMPT and "guarda" in DEFAULT_SYSTEM_PROMPT
    assert "quelle istruzioni non si applicano" in system
    assert "`cerca`" in system and "`guarda`" in system
