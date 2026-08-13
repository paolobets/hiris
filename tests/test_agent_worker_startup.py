from hiris.app.server import should_start_agent_worker


def test_worker_off_by_default(monkeypatch):
    monkeypatch.delenv("BRIDGE_ENABLED", raising=False)
    monkeypatch.delenv("PROVIDER_SUBSCRIPTION", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False


def test_worker_needs_both_flag_and_token(monkeypatch):
    """L'interruttore del ponte accende il worker solo INSIEME al token.

    Fino alla 2.3.1 la variabile letta qui era CHAT_VIA_SUBSCRIPTION; dalla
    fusione dei due interruttori e' BRIDGE_ENABLED (l'opzione `ponte.attivo`).
    Cambia quale variabile accende il worker, non l'invariante: da sola non
    basta mai.
    """
    monkeypatch.delenv("PROVIDER_SUBSCRIPTION", raising=False)
    monkeypatch.setenv("BRIDGE_ENABLED", "true")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker() is True


# ---------------------------------------------------------------------------
# SP-2 Task 3: provider_subscription (first-class) must gate the worker the
# same way the bridge switch (`ponte.attivo`) does -- still AND'd with the
# OAuth token, never activating the worker on its own.
# ---------------------------------------------------------------------------

def test_worker_starts_on_provider_subscription_with_token(monkeypatch):
    monkeypatch.delenv("BRIDGE_ENABLED", raising=False)
    monkeypatch.setenv("PROVIDER_SUBSCRIPTION", "true")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert should_start_agent_worker() is True


def test_worker_does_not_start_on_provider_subscription_without_token(monkeypatch):
    monkeypatch.delenv("BRIDGE_ENABLED", raising=False)
    monkeypatch.setenv("PROVIDER_SUBSCRIPTION", "true")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert should_start_agent_worker() is False
