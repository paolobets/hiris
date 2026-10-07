"""La risposta con uno strumento «scappato» ha un esito suo (B22; D-58,
seconda meta').

Alcuni instradamenti di OpenRouter (Mistral, Hermes) non traducono la
chiamata a uno strumento nel suo formato nativo: arriva come TESTO
(`chat_store.LEAKED_TOOL_NAME_RE`). `OpenAICompatRunner` lo riconosce e
risponde all'utente `TOOL_LEAK_USER_MSG` -- ma il registro dei turni lo
scriveva «riuscito», come una risposta vera. Da qui (approvata da Paolo il
05/10/2026, domanda 22 del secondo giro): il runner lo DICE
(`last_tool_leaked`, per chiamata, come `last_truncated`), e
`steering.misura_turno` lo registra con l'esito `steering.TOOL_LEAKED`.
Il testo che l'utente legge non cambia.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app import steering
from hiris.app.backends.openai_compat_runner import TOOL_LEAK_USER_MSG, OpenAICompatRunner
from hiris.app.claude_runner import ClaudeRunner
from hiris.app.llm_router import LLMRouter
from hiris.app.usage.store import UsageStore

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"
_TOOLS = [{"name": "search", "description": "cerca",
           "input_schema": {"type": "object", "properties": {}}}]


def _risposta(content: str):
    messaggio = MagicMock(content=content, tool_calls=None)
    risposta = MagicMock(choices=[MagicMock(finish_reason="stop", message=messaggio)])
    risposta.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    return risposta


def _runner(content: str) -> OpenAICompatRunner:
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-prova")
    runner._client.chat.completions.create = AsyncMock(return_value=_risposta(content))
    return runner


@pytest.mark.asyncio
async def test_OpenAICompatRunner_dice_lo_strumento_scappato():
    """Mutazione eseguita: il ramo dello strumento scappato che non scrive
    `last_tool_leaked` -- rossa."""
    runner = _runner("search▁{\"testo\": \"luce\"}")
    testo = await runner.chat(user_message="ciao", model="gpt-4o", tools=_TOOLS)
    assert testo == TOOL_LEAK_USER_MSG
    assert runner.last_tool_leaked is True


@pytest.mark.asyncio
async def test_una_risposta_vera_non_e_uno_strumento_scappato():
    runner = _runner("La luce della cucina e' accesa.")
    await runner.chat(user_message="ciao", model="gpt-4o", tools=_TOOLS)
    assert runner.last_tool_leaked is False


@pytest.mark.asyncio
async def test_il_segnale_si_azzera_a_ogni_chiamata():
    runner = OpenAICompatRunner(base_url="https://api.openai.com/v1", api_key="sk-prova")
    runner._client.chat.completions.create = AsyncMock(side_effect=[
        _risposta("search▁{}"), _risposta("tutto bene")])
    await runner.chat(user_message="uno", model="gpt-4o", tools=_TOOLS)
    assert runner.last_tool_leaked is True
    await runner.chat(user_message="due", model="gpt-4o", tools=_TOOLS)
    assert runner.last_tool_leaked is False


@pytest.mark.asyncio
async def test_il_router_dice_lo_strumento_scappato_di_chi_ha_risposto():
    router = LLMRouter(openai=_runner("search▁{}"), model_chain=["openai"])
    await router.chat(user_message="ciao", model="auto", tools=_TOOLS)
    assert router.last_tool_leaked is True


@pytest.mark.asyncio
async def test_il_router_senza_nessuno_che_risponde_non_eredita_il_segnale():
    primo = MagicMock()
    primo.chat = AsyncMock(side_effect=RuntimeError("giu'"))
    router = LLMRouter(claude=primo, model_chain=["claude"])
    ClaudeRunner(api_key="sk-prova").last_tool_leaked = True
    await router.chat(user_message="ciao", model="auto")
    assert router.last_tool_leaked is False


def _runner_classes() -> dict[str, Path]:
    """Le classi del prodotto che definiscono `chat`, chieste al sorgente."""
    trovate = {}
    for percorso in APP.rglob("*.py"):
        for nodo in ast.walk(ast.parse(percorso.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ClassDef) and any(
                    isinstance(f, ast.AsyncFunctionDef) and f.name == "chat"
                    for f in nodo.body):
                trovate[nodo.name] = percorso
    return trovate


def test_ogni_runner_espone_il_segnale():
    """Mutazione eseguita: tolto `last_tool_leaked` da `LLMRouter` -- rossa,
    nominandolo."""
    import importlib

    classi = _runner_classes()
    assert {"ClaudeRunner", "OpenAICompatRunner", "LLMRouter"} <= set(classi), sorted(classi)
    for nome, percorso in classi.items():
        modulo = ".".join(percorso.relative_to(APP.parents[1]).with_suffix("").parts)
        classe = getattr(importlib.import_module(modulo), nome)
        assert hasattr(classe, "last_tool_leaked"), f"{nome} non espone `last_tool_leaked`"


class _Scappato:
    def __init__(self):
        self.last_tool_leaked = True
        self.last_truncated = False
        self.last_tool_calls = []

    async def chat(self, **kwargs):
        return TOOL_LEAK_USER_MSG


@pytest.fixture()
def consumi(tmp_path):
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    yield archivio
    archivio.close()


@pytest.mark.asyncio
async def test_il_registro_dei_turni_scrive_lo_strumento_scappato(consumi):
    """Mutazione eseguita: `misura_turno` che non legge il segnale -- rossa
    («riuscito»)."""
    runner = _Scappato()
    async with steering.misura_turno(consumi, runner, specie=steering.ANALYST_SPECIES,
                                     canale="catena"):
        await runner.chat()
    assert consumi.turns()[0]["outcome"] == steering.TOOL_LEAKED


def test_l_esito_e_suo():
    assert steering.TOOL_LEAKED not in ("riuscito", steering.TRUNCATED, "fallito", "esaurito")
