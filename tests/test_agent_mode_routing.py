import pytest

from hiris.app.llm_router import LLMRouter


class _R:
    def __init__(self, name):
        self.name = name
        self.seen = []

    async def chat(self, **kw):
        self.seen.append(kw)
        return self.name


@pytest.mark.asyncio
async def test_scheduled_chat_agent_uses_automatic_policy():
    # agentA chat scheduled run should route via automatic_policy (ollama first),
    # NOT chat_policy (claude first)
    claude, ollama = _R("claude"), _R("ollama")
    router = LLMRouter(claude=claude, ollama=ollama,
                        automatic_policy=["ollama", "claude"], chat_policy=["claude"])
    # simulate the scheduled-chat call site: chat(model="auto", mode="automatic")
    out = await router.chat(model="auto", mode="automatic")
    assert out == "ollama"


# test_scheduled_chat_agent_run_passes_mode_automatic_to_runner e
# test_agent_type_run_uses_chat_with_mode_automatic sono usciti con l'intero
# Test Run (fetta E4 Task 2, 2.0): chiamavano `engine.run_chatbot(agent)`,
# morto per costruzione (TypeError su ogni chiamata reale ai runner, difeso
# solo da un AsyncMock -- vedi task-2-report.md). Verificato che cadessero
# per costruzione (`AttributeError: 'ChatbotEngine' object has no attribute
# 'run_chatbot'`) prima della cancellazione. Il test sopra non chiama
# l'engine -- esercita `LLMRouter.chat` direttamente -- e resta vivo.
