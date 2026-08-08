"""Pins the memoria-unica rule in BASE_SYSTEM_PROMPT (sdd task 1).

Root cause of a measured production bug: BASE_SYSTEM_PROMPT named the memory
tool once, but never told the model WHEN to use it. Four months in
production: 3 `memory` rows against 199 `insight` rows, all three with the
same timestamp (the user had to demand it explicitly).

These tests cannot measure model behaviour, but they pin that the
instruction exists, names the right tool, closes the "preso nota" path, and
reaches BOTH runners -- claude_runner.py and backends/openai_compat_runner.py
assemble the system prompt separately, so a rule reaching only one of them
is a rule half the users never get.

Review finale fetta E3, Important #1: this file used to pin the literal
string "save_memory" -- a tool that stopped existing at E3 Task 8 (the chat
catalog is today casa/strumenti.py's four tools: cerca, guarda, ricorda,
richiama). The suite was DEFENDING the stale prompt instead of catching it.
Fixed by reading the real save-tool name from casa/strumenti.py
(RICORDA_TOOL_DEF["name"]) instead of hardcoding a guess -- if the tool is
ever renamed again, this pin moves with it instead of silently going stale.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.casa.strumenti import RICORDA_TOOL_DEF
from hiris.app.claude_runner import BASE_SYSTEM_PROMPT, ClaudeRunner

NOME_RICORDA = RICORDA_TOOL_DEF["name"]


def _sys_text(system) -> str:
    """Flatten Claude's system blocks list (or a plain string) to text."""
    if isinstance(system, str):
        return system
    return "\n".join(b.get("text", "") for b in system if b.get("type") == "text")


def test_base_prompt_instructs_saving_user_statements():
    """Must name the real save tool (`ricorda`, casa/strumenti.py) and use an
    imperative save verb -- asserting on a whole sentence would break on the
    first stylistic touch-up."""
    assert NOME_RICORDA in BASE_SYSTEM_PROMPT
    assert BASE_SYSTEM_PROMPT.count(NOME_RICORDA) >= 2, (
        f"{NOME_RICORDA} must appear at least twice: in the positive instruction and "
        "in the negative clause forbidding claims without saving. If only one "
        "occurrence remains, the first (positive) bullet was likely removed."
    )


def test_base_prompt_forbids_claiming_note_without_saving():
    """Closes the "preso nota" path named in the task brief: the model must
    not claim to have taken note of something it never actually saved."""
    assert "preso nota" in BASE_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_claude_runner_system_prompt_carries_memory_rule():
    """claude_runner.py's own chat() must place the rule in the `system`
    kwarg sent to the Anthropic API -- not just in the module constant."""
    with patch("anthropic.AsyncAnthropic"):
        runner = ClaudeRunner(api_key="test-key")

    fake_message = MagicMock()
    fake_message.stop_reason = "end_turn"
    fake_message.content = [MagicMock(type="text", text="ok")]

    instance = MagicMock()
    instance.messages.create = AsyncMock(return_value=fake_message)
    runner._client = instance

    await runner.chat("ciao")

    sent_system = instance.messages.create.call_args.kwargs["system"]
    assert NOME_RICORDA in _sys_text(sent_system)


@pytest.mark.asyncio
async def test_openai_compat_runner_system_prompt_carries_memory_rule(tmp_path):
    """backends/openai_compat_runner.py assembles its own system message
    (a single OpenAI "system" role) -- the rule must reach it too."""
    dispatcher = MagicMock()
    dispatcher.has_memory = True
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "usage.json"),
    )

    class _FakeMessage:
        content = "ok"
        tool_calls = None

    class _FakeChoice:
        finish_reason = "stop"
        message = _FakeMessage()

    class _FakeResponse:
        usage = None
        choices = [_FakeChoice()]

    runner._client = MagicMock()
    runner._client.chat.completions.create = AsyncMock(return_value=_FakeResponse())

    await runner.chat(user_message="ciao", model="gpt-4o", max_tokens=64)

    sent_messages = runner._client.chat.completions.create.call_args.kwargs["messages"]
    assert NOME_RICORDA in sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_openai_compat_runner_chat_stream_carries_memory_rule(tmp_path):
    """backends/openai_compat_runner.py's chat_stream() must also place the
    memory rule in the system message sent to the OpenAI API, since the
    streaming path assembles the system prompt independently of chat()."""
    dispatcher = MagicMock()
    dispatcher.has_memory = True
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "usage.json"),
    )

    class _FakeDelta:
        content = None

    class _FakeChunk:
        """Minimal mock of an OpenAI stream chunk with the structure
        chat_stream() iterates over."""
        finish_reason = None
        delta = _FakeDelta()
        tool_calls = None

    class _FakeStreamChoice:
        finish_reason = "stop"
        delta = _FakeDelta()
        index = 0

    class _FakeStreamResponse:
        """Represents a single chunk from the stream."""
        choices = [_FakeStreamChoice()]

    async def _fake_stream():
        """Async generator simulating the stream response."""
        yield _FakeStreamResponse()

    runner._client = MagicMock()
    runner._client.chat.completions.create = AsyncMock(return_value=_fake_stream())

    # Consume the generator to trigger the API call
    _ = [chunk async for chunk in runner.chat_stream(
        user_message="ciao", model="gpt-4o", max_tokens=64
    )]

    sent_messages = runner._client.chat.completions.create.call_args.kwargs["messages"]
    assert NOME_RICORDA in sent_messages[0]["content"]
