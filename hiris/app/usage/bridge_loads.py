"""Cio' che `/api/mcp` consegna alla CLI del ponte, per turno.

Spec «le misure complete» §4(2). La CLI fa il proprio ciclo di strumenti
dentro di se': le definizioni e i risultati pero' passano da questa casa, e
la rotta sa per quale turno (`X-HIRIS-Turno`). Qui si annotano i CARATTERI --
mai gli argomenti, mai i contenuti.

**Due thread, quindi un lock.** Scrive il loop di aiohttp; legge il thread
dell'executor del ponte (`server._registra_turno_ponte`). Il contatore dei
giri di `handlers_mcp` fa a meno del lock perche' lo tocca un thread solo:
questo no.

**Un tetto, LRU**, e lo stesso dei contatori dei giri di `api/handlers_mcp.py`,
che lo importano da qui (B-53): un
turno del ponte dura al piu' fino alla sua scadenza (S-09), e un turno ancora in
uso non si espelle.
"""
from __future__ import annotations

import threading
import time
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


def _registra_turno_ponte(archivio, carichi=None):
    """Collega il registro dei turni al ponte.

    Non traduce niente: il ponte emette gia' le chiavi di `log_turn`. Un
    vocabolario intermedio qui sarebbe un terzo posto in cui una colonna
    nuova si dimentica di comparire.

    `subject` arriva nella riga: per un turno di chat e' il soggetto che
    `handlers_chat` mette nel contesto del job all'accodamento (fetta «le chat
    divise»), letto da `runner._measure_turn`; per le altre specie e' `None`,
    perche' nessuna persona le ha aperte. Qui non si inventa niente.

    **La giunzione** (spec «le misure complete» §4): la riga porta
    l'`exchange_id`, la composizione e i giri dello stream; `carichi` (il
    `BridgeLoads` dell'app) sa le definizioni e i risultati che /api/mcp ha
    servito a quel turno. `payload_rows_ponte` li unisce. Gira nel thread
    dell'executor del ponte: `BridgeLoads` ha il suo lock.

    Una riga senza composizione (la forma di prima del 28/09/2026) scrive il
    solo turno: `payload_rows_ponte` non inventa giri senza cio' che e' stato
    consegnato. Un guasto qui non fa cadere il turno: lo prende il
    `try` di `runner._measure_turn`, che chiama questo gancio.
    """
    from .giro import payload_rows_ponte

    def registra(riga: dict) -> str:
        riga = dict(riga)
        soggetto = riga.pop("subject", None)
        exchange_id = riga.pop("exchange_id", "")
        composizione = riga.pop("composition", None)
        giri = riga.pop("exchanges", None) or []
        adesso = time.time()
        ident = archivio.log_turn(**riga, subject=soggetto, now=adesso)
        preso = carichi.take(exchange_id) if carichi is not None else None
        for pesi in payload_rows_ponte(composizione, giri, preso):
            archivio.log_payload(ident, now=adesso, **pesi)
        return ident

    return registra
