from hiris.app.server import should_start_agent_worker


def test_worker_off_by_default(monkeypatch):
    monkeypatch.delenv("CHAT_VIA_SUBSCRIPTION", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False


def test_worker_needs_both_flag_and_token(monkeypatch):
    monkeypatch.setenv("CHAT_VIA_SUBSCRIPTION", "true")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker() is True
