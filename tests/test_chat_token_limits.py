from hiris.app.claude_runner import _max_tokens_message, _TRUNCATION_NOTICE, CHAT_MAX_TOKENS


# --- Part 1: max_tokens cap (persistence-time, at create/update) ---
# Retired (fetta E4 Task 3, "un bot solo"): test_cap_allows_up_to_16000,
# test_create_agent_keeps_high_max_tokens, test_create_agent_clamped_to_16000,
# test_update_agent_raises_cap and test_chat_max_tokens_constant_matches_cap
# pinned `ChatbotEngine._cap_max_tokens`/`_CHAT_MAX_TOKENS_CAP`, applied only
# inside `create_chatbot`/`update_chatbot` when persisting `max_tokens` --
# all four are gone with the CRUD routes (the three creation paths that
# survived the E3 all converged on POST /api/chatbots with `enabled: true`
# by default, the opposite of what the scope prescribes). Verified failing
# for construction (`AttributeError: type object 'ChatbotEngine' has no
# attribute '_cap_max_tokens'` / `'... has no attribute 'create_chatbot'`)
# before deletion. `CHAT_MAX_TOKENS` (claude_runner.py) is a separate,
# still-live mechanism -- the runtime floor applied to every chat request
# regardless of the stored per-persona value (see
# tests/test_api.py::test_chat_passes_model_to_runner) -- and is untouched.

# --- Part 2: max_tokens truncation message ---

def test_max_tokens_message_with_prefix_appends_notice():
    msg = _max_tokens_message(["Ora creo la dashboard!"])
    assert msg.startswith("Ora creo la dashboard!")
    assert _TRUNCATION_NOTICE in msg


def test_max_tokens_message_without_prefix_is_the_notice():
    assert _max_tokens_message([]) == _TRUNCATION_NOTICE
    assert _max_tokens_message(["   "]) == _TRUNCATION_NOTICE
