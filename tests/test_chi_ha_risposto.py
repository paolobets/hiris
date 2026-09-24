"""Il registro dei turni diceva «ignoto» di ogni turno della catena.

Misurato il 24/09/2026 su 37 turni veri: la colonna `provider` valeva
`ignoto` su tutti. `misura_turno` la ricava cosi' --

    chi = provider or getattr(runner, "provider_name", "") or "ignoto"

-- e nessuno dei sette punti che misurano passa `provider`, perche' nessuno
di loro lo sa: chiamano `LLMRouter`, che e' un proxy. Il router invece lo
sa benissimo (`backend_name`, nel ciclo di ripiego) e lo usava solo per il
registro degli esiti, buttandolo via per tutto il resto.

Non e' un dettaglio del registro: «chi spende cosa» e' una delle tre
domande per cui le misure esistono, e senza questa colonna non ha risposta
sulla strada piu' usata.

**Per chiamata, non per oggetto**, come `last_tool_calls` e la misura del
carico: il router e' costruito una volta e vive quanto l'add-on. Un
attributo su di lui farebbe dire al turno dell'analista chi ha risposto
alla chat del proprietario, se i due si accavallano.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app.claude_runner import RunnerBackendError
from hiris.app.llm_router import LLMRouter


@pytest.mark.asyncio
async def test_chi_risponde_in_catena_si_dichiara():
    """Il primo rifiuta, risponde il secondo: il nome e' quello del SECONDO.

    Leggere il primo della catena direbbe «ha risposto claude» proprio nel
    caso interessante -- quello in cui claude non ha risposto.
    """
    primo = MagicMock()
    primo.chat = AsyncMock(side_effect=RunnerBackendError("Errore Claude."))
    secondo = MagicMock()
    secondo.chat = AsyncMock(return_value="risposta")
    router = LLMRouter(claude=primo, openrouter=secondo, strategy="balanced")

    assert await router.chat(user_message="ciao", model="auto") == "risposta"
    assert router.provider_name == "openrouter"


@pytest.mark.asyncio
async def test_prima_di_rispondere_non_si_sa():
    """Un nome che c'e' gia' prima della chiamata sarebbe il nome del turno
    PRECEDENTE, ed e' peggio di «ignoto»: si legge come un fatto."""
    router = LLMRouter(claude=MagicMock(), strategy="balanced")
    assert router.provider_name == ""


@pytest.mark.asyncio
async def test_nessuno_risponde_nessun_nome():
    """Tutti rifiutano: non si dichiara un vincitore che non c'e'."""
    primo = MagicMock()
    primo.chat = AsyncMock(side_effect=RunnerBackendError("giu'"))
    router = LLMRouter(claude=primo, strategy="balanced")
    await router.chat(user_message="ciao", model="auto")
    assert router.provider_name == ""


@pytest.mark.asyncio
async def test_anche_il_modello_chiesto_per_nome_dichiara_chi_ha_risposto():
    """Il ramo senza ripiego (`model` esplicito) non passa dal ciclo: se la
    dichiarazione vivesse solo nel ciclo, meta' dei turni resterebbe muta."""
    runner = MagicMock()
    runner.chat = AsyncMock(return_value="ok")
    router = LLMRouter(claude=runner, strategy="balanced")
    await router.chat(user_message="ciao", model="claude-opus-4-8")
    assert router.provider_name == "claude"
