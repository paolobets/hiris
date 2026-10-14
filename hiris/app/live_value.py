"""Un valore di `app` che cambia dopo l'avvio (X-31, Chiusura dello sprint).

aiohttp congela l'app quando l'avvio finisce: da li' in poi scrivere in
`app[...]` e' deprecato in aiohttp 3 («Changing state of started or joined
application») e un errore in aiohttp 4. Fino al 14/10/2026 il prodotto lo
faceva in piu' di quindici punti: le rotte che salvano i modelli, le
impostazioni della chat e i giudizi sui tipi, e i giri che rileggono i
problemi, le integrazioni, il confronto dell'albero, la catena e il ponte.

Il valore che cambia vive qui dentro: l'avvio mette in `app` un
`LiveValue`, e chi lo aggiorna chiama `set`. La chiave non si riscrive mai,
quindi l'app resta quella congelata, e chi legge trova sempre lo stesso
oggetto. Un contenitore che si aggiorna in un posto (un dizionario, un
insieme) non ne ha bisogno: nasce all'avvio e si modifica sul posto.
"""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class LiveValue(Generic[T]):
    """Il valore corrente: si legge con `value`, si cambia con `set`."""

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    def set(self, value: T) -> None:
        self._value = value

    def __repr__(self) -> str:
        return f"LiveValue({self._value!r})"
