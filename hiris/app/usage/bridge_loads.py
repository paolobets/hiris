"""Cio' che `/api/mcp` consegna alla CLI del ponte, per turno.

Spec «le misure complete» §4(2). La CLI fa il proprio ciclo di strumenti
dentro di se': le definizioni e i risultati pero' passano da questa casa, e
la rotta sa per quale turno (`X-HIRIS-Turno`). Qui si annotano i CARATTERI --
mai gli argomenti, mai i contenuti.

**Due thread, quindi un lock.** Scrive il loop di aiohttp; legge il thread
dell'executor del ponte (`server._registra_turno_ponte`). Il contatore dei
giri di `handlers_mcp` fa a meno del lock perche' lo tocca un thread solo:
questo no.

**Un tetto, LRU**, con la stessa ragione di `_MAX_TRACKED_EXCHANGES`: un
turno del ponte dura al piu' due invocazioni da 300 s, e un turno ancora in
uso non si espelle.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

BRIDGE_LOADS_KEY = "bridge_loads"
MAX_TRACKED = 64


class BridgeLoads:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._per_exchange: OrderedDict[str, dict] = OrderedDict()

    def _entry(self, exchange_id: str) -> dict:
        entry = self._per_exchange.get(exchange_id)
        if entry is None:
            entry = {"tools_chars": 0, "tools_sent": 0, "results": []}
            self._per_exchange[exchange_id] = entry
            while len(self._per_exchange) > MAX_TRACKED:
                self._per_exchange.popitem(last=False)
        else:
            self._per_exchange.move_to_end(exchange_id)
        return entry

    def tools_listed(self, exchange_id: str, chars: int, count: int) -> None:
        if not exchange_id:
            return
        with self._lock:
            entry = self._entry(exchange_id)
            entry["tools_chars"] = int(chars)
            entry["tools_sent"] = int(count)

    def result_served(self, exchange_id: str, chars: int) -> None:
        if not exchange_id:
            return
        with self._lock:
            self._entry(exchange_id)["results"].append(int(chars))

    def take(self, exchange_id: str) -> dict | None:
        if not exchange_id:
            return None
        with self._lock:
            return self._per_exchange.pop(exchange_id, None)


def create_bridge_loads(app) -> None:
    """Si crea mentre l'app si compone, come i contatori dei giri (M-2):
    scrivere in `app[...]` a richiesta gia' servita e' deprecato in aiohttp."""
    app[BRIDGE_LOADS_KEY] = BridgeLoads()
