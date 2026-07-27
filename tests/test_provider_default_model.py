from hiris.app.claude_runner import resolve_model


def test_resolve_model_uses_provider_default_when_auto():
    # default esplicito vince su AUTO_MODEL_MAP quando model="auto"
    assert resolve_model("auto", "agent", "claude-opus-4-7") == "claude-opus-4-7"


def test_resolve_model_falls_back_to_auto_map_when_no_default():
    # nessun default -> comportamento odierno (AUTO_MODEL_MAP)
    assert resolve_model("auto", "agent", "") == "claude-haiku-4-5-20251001"


def test_resolve_model_explicit_wins_over_default():
    assert resolve_model("claude-sonnet-4-6", "agent", "claude-opus-4-7") == "claude-sonnet-4-6"
