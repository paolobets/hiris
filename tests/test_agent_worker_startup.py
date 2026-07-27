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


# ---------------------------------------------------------------------------
# SP-2 Task 3: provider_subscription (first-class) must gate the worker the
# same way the legacy chat_via_subscription flag did -- still AND'd with the
# OAuth token, never activating the worker on its own.
# ---------------------------------------------------------------------------

def test_worker_starts_on_provider_subscription_with_token(monkeypatch):
    monkeypatch.delenv("CHAT_VIA_SUBSCRIPTION", raising=False)
    monkeypatch.setenv("PROVIDER_SUBSCRIPTION", "true")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker() is True


def test_worker_does_not_start_on_provider_subscription_without_token(monkeypatch):
    monkeypatch.delenv("CHAT_VIA_SUBSCRIPTION", raising=False)
    monkeypatch.setenv("PROVIDER_SUBSCRIPTION", "true")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False
