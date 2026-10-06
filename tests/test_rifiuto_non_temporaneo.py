"""S-37: un rifiuto che non passa da solo non si dice «temporaneo».

Misurato nel registro dell'add-on il 05/10/2026 (verifiche dal vivo della
3.75.0): Claude rispondeva 400 «credit balance is too low», OpenRouter 403
«Key limit exceeded (total limit)», e la chat diceva per tutti e due «Errore
temporaneo del servizio AI. Riprova tra poco.». Il codice e la famiglia
arrivavano gia' al router (`RunnerBackendError.family`/`code`) e alla pagina
Modelli; la frase della chat li buttava.

Qui la strada intera: il router con una catena che rifiuta tutta, e il filtro
della cronologia, che una frase di guasto non deve lasciar entrare.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app.chat_store import _is_toxic_assistant
from hiris.app.claude_runner import RunnerBackendError
from hiris.app.llm_router import LLMRouter
from hiris.app.model_resolution import TEMPORARY_FAILURE, failure_reply


def _refusing(family, code):
    runner = MagicMock()
    runner.chat = AsyncMock(side_effect=RunnerBackendError(
        failure_reply(family, code), family=family, code=code))
    return runner


@pytest.mark.asyncio
async def test_la_catena_che_rifiuta_per_credito_non_dice_temporaneo():
    """La catena del proprietario il 05/10: Claude a credito zero, OpenRouter
    con la quota della chiave finita. Risponde l'ultimo rifiuto, col suo
    fatto."""
    router = LLMRouter(claude=_refusing("credenziale", 400),
                       openrouter=_refusing("credenziale", 403),
                       model_chain=["claude", "openrouter"])
    answer = await router.chat(model="auto")
    assert "temporaneo" not in answer
    assert "la chiave non è accettata (403)" in answer
    assert router.last_unanswered is True


@pytest.mark.parametrize(("family", "code"), [
    ("credenziale", 400), ("credenziale", 402), ("credenziale", 401),
    ("credenziale", 403), ("modello", 404), ("irraggiungibile", None)])
def test_ogni_frase_di_rifiuto_resta_fuori_dalla_cronologia(family, code):
    """Una frase di guasto in cronologia torna al modello a ogni turno
    (`chat_store._TOXIC_ASSISTANT_EXACT`): le frasi nuove valgono come la
    vecchia."""
    phrase = failure_reply(family, code)
    assert "temporaneo" not in phrase
    assert _is_toxic_assistant(phrase)


@pytest.mark.parametrize(("family", "code"), [("altro", 500), ("altro", 429), ("altro", None)])
def test_un_guasto_non_classificato_resta_la_frase_di_prima(family, code):
    """Il ramo `altro`: un 500 o un 429 non dicono a chi legge cosa fare, e la
    frase non inventa una causa (`provider_occurrences.family_from_code`)."""
    assert failure_reply(family, code) == TEMPORARY_FAILURE
    assert _is_toxic_assistant(TEMPORARY_FAILURE)


def test_la_causa_e_la_stessa_della_pagina_modelli():
    """Fondamenta 3: lo stesso rifiuto ha la stessa causa dalla chat e dalla
    pagina Modelli (`occurrence_phrase`), da una tabella sola."""
    from hiris.app.model_resolution import occurrence_phrase
    for code in (400, 401, 402, 403):
        page = occurrence_phrase({"tipo": "rifiutato", "famiglia": "credenziale",
                                  "codice": code, "quando": 0.0, "da_quante": 1},
                                 position=1, now=0.0)
        cause = page.split(" — ")[1].split(" (")[0]
        assert f": {cause} ({code})." in failure_reply("credenziale", code)
