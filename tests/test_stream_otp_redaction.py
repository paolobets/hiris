"""Streaming-path OTP redaction (Slice 2 residual leak).

Companion fix to commit d86efea, which redacted confirm_pending's OTP `code`
from the non-streaming chat HTTP debug payload (handlers_chat.py). That fix
did not cover the SSE "done" event's `tool_calls` list emitted by the two
chat runners' `chat_stream()` — ClaudeRunner and OpenAICompatRunner both
append `{"tool": ..., "input": ...}` to `self.last_tool_calls` and then yield
it verbatim in the SSE done event, so a chat-typed `confirm_pending({"code":
"123456"})` leaked the raw 6-digit OTP to the client over SSE.

FIX: a shared helper `_redact_stream_tool_calls` (hiris/app/claude_runner.py)
mirrors handlers_chat.py's `_debug_input` redaction for the same shape, and
is applied at both runners' "done" event emit sites.
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hiris.app.claude_runner import ClaudeRunner, _redact_stream_tool_calls
from hiris.app.backends.openai_compat_runner import OpenAICompatRunner


# ---------------------------------------------------------------------------
# Unit tests for the shared redaction helper
# ---------------------------------------------------------------------------

def test_redact_stream_tool_calls_masks_confirm_pending_code():
    tool_calls = [{"tool": "confirm_pending", "input": {"code": "123456"}}]
    out = _redact_stream_tool_calls(tool_calls)
    assert out == [{"tool": "confirm_pending", "input": {"code": "***"}}]


def test_redact_stream_tool_calls_leaves_other_tools_untouched():
    tool_calls = [{"tool": "call_ha_service",
                   "input": {"domain": "switch", "service": "turn_on",
                             "data": {"entity_id": "switch.boiler"}}}]
    out = _redact_stream_tool_calls(tool_calls)
    assert out == tool_calls


def test_redact_stream_tool_calls_ignores_confirm_pending_without_code():
    # e.g. malformed/partial input — nothing to redact, pass through as-is.
    tool_calls = [{"tool": "confirm_pending", "input": {}}]
    out = _redact_stream_tool_calls(tool_calls)
    assert out == [{"tool": "confirm_pending", "input": {}}]


def test_redact_stream_tool_calls_handles_empty_and_non_dict_entries():
    assert _redact_stream_tool_calls([]) == []
    # Defensive: a stray non-dict entry must not crash the redaction pass.
    out = _redact_stream_tool_calls(["not-a-dict"])
    assert out == ["not-a-dict"]


def test_redact_stream_tool_calls_does_not_mutate_input_dict():
    original_input = {"code": "123456"}
    tool_calls = [{"tool": "confirm_pending", "input": original_input}]
    _redact_stream_tool_calls(tool_calls)
    assert original_input == {"code": "123456"}, "must not mutate the caller's dict in place"


# ---------------------------------------------------------------------------
# Integration: ClaudeRunner.chat_stream's SSE "done" event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_runner_chat_stream_redacts_otp_in_done_event():
    # La redazione si applica a `last_tool_calls` DOPO il dispatch, a
    # prescindere dal suo esito (claude_runner.py: l'append avviene sempre,
    # anche quando il dispatch fallisce/non e' disponibile) -- nessun
    # dispatcher reale serve a provare questo: fetta E2 Task 7, il vecchio
    # ToolDispatcher usato qui e' uscito senza toccare questo soggetto.
    with patch("anthropic.AsyncAnthropic"):
        runner = ClaudeRunner(api_key="test-key")

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.id = "tu_1"
    tool_use_block.name = "confirm_pending"
    tool_use_block.input = {"code": "123456"}

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Confermato."

    msg1 = MagicMock()
    msg1.stop_reason = "tool_use"
    msg1.content = [tool_use_block]

    msg2 = MagicMock()
    msg2.stop_reason = "end_turn"
    msg2.content = [text_block]

    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(side_effect=[msg1, msg2])
        runner._client = instance

        lines = [line async for line in runner.chat_stream(
            user_message="conferma con codice 123456",
            system_prompt="",
        )]

    full_output = "\n".join(lines)
    assert "123456" not in full_output, "raw OTP must never reach the SSE stream"

    done_lines = [l for l in lines if '"type": "done"' in l]
    assert done_lines, "expected a 'done' SSE event"
    payload = json.loads(done_lines[0][len("data: "):])
    tc = payload["tool_calls"]
    assert tc and tc[0]["tool"] == "confirm_pending"
    assert tc[0]["input"]["code"] == "***"


# ---------------------------------------------------------------------------
# Integration: OpenAICompatRunner.chat_stream's SSE "done" event
# ---------------------------------------------------------------------------

class _FakeStream:
    """Minimal async-iterable stand-in for the OpenAI SDK's streaming response."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            yield c


def _chunk(content=None, tool_calls=None, finish_reason=None):
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _tool_call_delta(index, call_id, name, arguments):
    fn = MagicMock()
    fn.name = name
    fn.arguments = arguments
    tcd = MagicMock()
    tcd.index = index
    tcd.id = call_id
    tcd.function = fn
    return tcd


@pytest.mark.asyncio
async def test_openai_compat_runner_chat_stream_redacts_otp_in_done_event(tmp_path):
    # Stesso ragionamento del test gemello sopra: la redazione non dipende
    # da un dispatch riuscito.
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        usage_path=str(tmp_path / "usage.json"),
    )

    tool_call_chunk = _chunk(
        tool_calls=[_tool_call_delta(0, "call_1", "confirm_pending", '{"code": "123456"}')],
    )
    tool_call_end_chunk = _chunk(finish_reason="tool_calls")
    final_text_chunk = _chunk(content="Confermato.")
    final_end_chunk = _chunk(finish_reason="stop")

    stream1 = _FakeStream([tool_call_chunk, tool_call_end_chunk])
    stream2 = _FakeStream([final_text_chunk, final_end_chunk])

    with patch.object(runner._client.chat.completions, "create",
                      AsyncMock(side_effect=[stream1, stream2])):
        lines = [line async for line in runner.chat_stream(
            user_message="conferma con codice 123456",
            system_prompt="",
        )]

    full_output = "\n".join(lines)
    assert "123456" not in full_output, "raw OTP must never reach the SSE stream"

    done_lines = [l for l in lines if '"type": "done"' in l]
    assert done_lines, "expected a 'done' SSE event"
    payload = json.loads(done_lines[0][len("data: "):])
    tc = payload["tool_calls"]
    assert tc and tc[0]["tool"] == "confirm_pending"
    assert tc[0]["input"]["code"] == "***"
