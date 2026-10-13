"""Il tetto d'uscita non ha un predefinito nei runner (D-13; Chiusura, 13/10/2026).

Ogni mestiere dichiara il suo tetto e `steering.chain_turn` lo pretende; i
due runner tenevano pero' un predefinito ciascuno, scritto a parte
(`claude_runner.MAX_TOKENS = 4096` e `max_tokens: int = 4096`). Un
chiamante che lo dimenticasse avrebbe ricevuto quello, in silenzio.

La temperatura non e' un tetto: nessun turno la passa, e vale quella del
provider. Non c'e' un valore nostro da dichiarare.
"""
import inspect

import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import ClaudeRunner


@pytest.mark.parametrize("runner", [ClaudeRunner, OpenAICompatRunner],
                         ids=lambda r: r.__name__)
def test_il_tetto_d_uscita_si_dichiara_sempre(runner):
    """Mutazione ESEGUITA il 13/10/2026: rimesso `= 4096` in
    `OpenAICompatRunner.chat` -- rossa su quel runner."""
    param = inspect.signature(runner.chat).parameters["max_tokens"]
    assert param.default is inspect.Parameter.empty
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
