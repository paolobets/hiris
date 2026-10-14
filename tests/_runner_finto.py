"""Il runner delle prove: UNO, nella forma dei runner veri (T-02, 14/10/2026).

Fino a oggi ogni file se ne scriveva uno (misurato il 14/10/2026: 42 classi
con un `chat()` in 30 file, e 64 `AsyncMock` assegnati a `.chat` in 22):
chi teneva i kwargs in `ricevuto`, chi in `chiamato_con`, chi la sola domanda
in `questions`, e quasi nessuno portava cio' che il prodotto LEGGE da
un runner dopo la chiamata (`last_tool_calls`, `last_truncated`,
`last_tool_leaked`, `last_unanswered`): su quelle finte i segnali tacevano
coperti dal ripiego di `getattr`, e nessuna prova poteva accorgersene.

`RunnerFinto` porta quegli attributi e li azzera all'ingresso di `chat()`,
come i runner veri. Non li elenca a memoria contro il sorgente:
`tests/test_runner_after_call.py` chiede al prodotto quali si leggono e
verifica che questo finto li porti e li azzeri, come fa per `ClaudeRunner` e
`OpenAICompatRunner` (I-0).

- `risposta`: cio' che `chat()` restituisce; un'eccezione si solleva.
- `turno`: una funzione asincrona `turno(runner, **kwargs)` per i finti che
  devono FARE qualcosa durante il turno (chiamare uno strumento attraverso il
  `dispatcher`, scrivere un segnale): cio' che restituisce, se non e' `None`,
  prende il posto di `risposta`.
- `dopo`: gli attributi che la chiamata lascia scritti (es.
  `{"last_truncated": True}`), come li lascerebbe un runner vero.
- `chiamate`: i kwargs di ogni `chat()`, in ordine.

Come `ClaudeRunner`, non porta `provider_name`: chi misura riceve il router,
che lo scrive da se' (ammissione in `tests/test_runner_after_call.py`).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class RunnerFinto:
    def __init__(self, risposta: Any = "ok", *,
                 turno: Callable[..., Awaitable[Any]] | None = None,
                 dopo: dict | None = None) -> None:
        self.risposta = risposta
        self.turno = turno
        self.dopo = dict(dopo or {})
        self.chiamate: list[dict] = []
        self.last_tool_calls: list[dict] = []
        self.last_truncated = False
        self.last_tool_leaked = False
        self.last_unanswered = False

    async def chat(self, **kwargs) -> Any:
        self.last_tool_calls = []
        self.last_truncated = False
        self.last_tool_leaked = False
        self.last_unanswered = False
        self.chiamate.append(kwargs)
        esito = None
        if self.turno is not None:
            esito = await self.turno(self, **kwargs)
        for nome, valore in self.dopo.items():
            setattr(self, nome, valore)
        if esito is not None:
            return esito
        if isinstance(self.risposta, BaseException):
            raise self.risposta
        return self.risposta

    @property
    def ultima(self) -> dict | None:
        """I kwargs dell'ultima chiamata, o `None` se `chat()` non e' partita."""
        return self.chiamate[-1] if self.chiamate else None
