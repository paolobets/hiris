# tests/test_openai_compat_usage.py  (nuovo file)
from hiris.app.backends.openai_compat_runner import OpenAICompatRunner, _estimate_tokens


def test_estimate_tokens_is_conservative_and_bounded():
    assert _estimate_tokens(0) == 0
    assert _estimate_tokens(-5) == 0
    assert _estimate_tokens(1) == 1
    assert _estimate_tokens(4) == 1
    assert _estimate_tokens(5) == 2
    assert _estimate_tokens(400) == 100


class _NoUsageResp:
    usage = None
    class _Choice:
        class _Msg:
            content = "acceso la luce del salotto"  # 27 char -> out ~7
            tool_calls = None
        message = _Msg()
    choices = [_Choice()]


def _runner():
    r = OpenAICompatRunner.__new__(OpenAICompatRunner)
    r._per_chatbot_usage = {}
    r.total_input_tokens = 0
    r.total_output_tokens = 0
    r.total_cost_usd = 0.0
    r._save_usage = lambda: None
    r._ensure_today_reset = lambda pau: None
    return r


def test_track_usage_estimates_when_usage_absent():
    r = _runner()
    # 200 char di prompt -> ~50 token input; ~7 token output dal contenuto
    r._track_usage(_NoUsageResp(), "some/model", "ag1", est_input_chars=200)
    pau = r._per_chatbot_usage["ag1"]
    assert pau["tokens_today"] >= 50          # il tetto ora MORDE
    assert pau["input_tokens"] + pau["output_tokens"] >= 50  # cio' che agent_run_usage legge -> il budget morde
    assert pau.get("last_estimated") is True


def test_track_usage_records_nothing_extra_when_no_text_and_no_chars():
    r = _runner()

    class _Empty:
        usage = None
        choices = []

    r._track_usage(_Empty(), "some/model", "ag1", est_input_chars=0)
    # nessun agente creato per una misura a zero: niente rumore
    assert "ag1" not in r._per_chatbot_usage
