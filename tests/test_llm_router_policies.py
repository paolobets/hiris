import pytest
from hiris.app.llm_router import LLMRouter


class _R:
    def __init__(self, name):
        self.name = name
        self.calls = []

    async def chat(self, **kw):
        self.calls.append(kw)
        return self.name

    async def run_with_actions(self, **kw):
        self.calls.append(kw)
        return (self.name, None, None)

    async def chat_stream(self, **kw):
        self.calls.append(kw)
        yield self.name


def _router():
    return LLMRouter(
        claude=_R("claude"), ollama=_R("ollama"),
        automatic_policy=["ollama", "claude"],
        chat_policy=["claude", "ollama"],
    )


@pytest.mark.asyncio
async def test_chat_mode_uses_chat_policy_first():
    r = _router()
    out = await r.chat(model="auto")  # default mode chat -> chat_policy[0]=claude
    assert out == "claude"


@pytest.mark.asyncio
async def test_automatic_mode_uses_automatic_policy_first():
    r = _router()
    out, _, _ = await r.run_with_actions(model="auto")  # default automatic -> ollama
    assert out == "ollama"


@pytest.mark.asyncio
async def test_scheduled_chat_can_force_automatic_mode():
    r = _router()
    out = await r.chat(model="auto", mode="automatic")  # ollama first
    assert out == "ollama"


@pytest.mark.asyncio
async def test_mode_not_forwarded_to_runner():
    r = _router()
    await r.chat(model="auto")
    assert all("mode" not in kw for kw in r._claude.calls)


@pytest.mark.asyncio
async def test_explicit_model_overrides_policy():
    r = _router()
    out = await r.chat(model="claude-sonnet-4-6")  # explicit -> claude regardless of mode
    assert out == "claude"


@pytest.mark.asyncio
async def test_backward_compat_policies_default_from_strategy():
    r = LLMRouter(claude=_R("claude"), ollama=_R("ollama"), strategy="cost_first")
    # cost_first order: ollama before claude; both modes derive from it
    out, _, _ = await r.run_with_actions(model="auto")
    assert out == "ollama"
    assert await r.chat(model="auto") == "ollama"


@pytest.mark.asyncio
async def test_chat_stream_auto_uses_chat_policy_first_backend():
    r = _router()
    chunks = [c async for c in r.chat_stream(model="auto")]
    assert chunks == ["claude"]


@pytest.mark.asyncio
async def test_chat_stream_mode_not_forwarded_to_runner():
    r = _router()
    async for _ in r.chat_stream(model="auto", mode="automatic"):
        pass
    assert all("mode" not in kw for kw in r._ollama.calls)


def test_policy_drops_unknown_backend_names_preserving_order():
    r = LLMRouter(
        claude=_R("claude"), ollama=_R("ollama"),
        automatic_policy=["bogus", "ollama", "claude", "also_bogus"],
    )
    assert r._automatic_policy == ["ollama", "claude"]
