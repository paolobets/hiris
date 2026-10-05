"""La tabella degli strumenti decide il soffitto, una volta (Tappa 5, Task 2).

Fino al 05/10/2026 il soffitto si chiedeva a mano in sette punti dentro i
gestori (D-23) e il filo in tre (D-42): uno strumento nuovo nasceva senza
permesso finche' qualcuno non se ne ricordava. Ora la riga dichiara cosa
serve (`Tool.needs_thread`, `Tool.permissions`, `Tool.mask`) e `dispatch` lo
chiede PRIMA di chiamare il gestore.

Queste prove guardano la tabella, non una lista scritta qui: le righe, i
gestori e i gesti si chiedono al modulo e a `api/soffitto.GESTI`.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import replace

import pytest

from hiris.app.api import soffitto
from hiris.app.home_space import tools
from hiris.app.home_space.tools import TOOLS, ToolDispatcher

_DENIES_EVERYTHING = {gesture: False for gesture in soffitto.GESTI} | {
    "rinviato": False, "perche": "questo soffitto non concede niente"}


class _Recorder:
    """Un gestore finto: registra le chiamate, e risponde come un gestore."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, dispatcher, arguments, **options):
        self.calls.append(arguments)
        return {"chiamato": True}


@pytest.mark.asyncio
async def test_una_riga_col_permesso_rifiuta_senza_chiamare_il_gestore(monkeypatch):
    """Il gestore di `execute` non viene chiamato quando il soffitto nega
    `comandare`: il rifiuto e' di `dispatch`, letto dalla riga.

    Mutazione ESEGUITA il 05/10/2026: tolto `permissions` dalla riga di
    `execute` -- rossa qui («il gestore di execute e' stato chiamato»), e in
    `test_admission.py` le prove del ruolo di sola lettura e dei servizi
    riservati."""
    recorder = _Recorder()
    row = next(tool for tool in TOOLS if tool.name == "execute")
    monkeypatch.setitem(tools._TOOL_PER_NAME, "execute", replace(row, handler=recorder))
    dispatcher = ToolDispatcher(None, None, actuator=object(), soffitto=_DENIES_EVERYTHING)

    answer = await dispatcher.dispatch(
        "execute", {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.x"]}})

    assert recorder.calls == [], "il gestore di execute e' stato chiamato"
    assert answer == {"errore": "questo soffitto non concede niente"}


@pytest.mark.asyncio
async def test_senza_soffitto_il_gestore_e_chiamato(monkeypatch):
    """Il metro opposto: un turno che nessuna persona ha aperto (`soffitto`
    `None`: lo schedulatore, il ponte) non si restringe."""
    recorder = _Recorder()
    row = next(tool for tool in TOOLS if tool.name == "execute")
    monkeypatch.setitem(tools._TOOL_PER_NAME, "execute", replace(row, handler=recorder))
    dispatcher = ToolDispatcher(None, None, actuator=object(), soffitto=None)

    answer = await dispatcher.dispatch(
        "execute", {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.x"]}})

    assert answer == {"chiamato": True}
    assert len(recorder.calls) == 1


def test_ogni_gesto_della_tabella_e_un_gesto_del_soffitto():
    """Un gesto scritto male (`comanda` invece di `comandare`) farebbe
    `ceiling.get(...)` falso, cioe' un rifiuto a tutti -- o, peggio, nessuno
    se un giorno la regola si rovesciasse. I gesti si chiedono a `GESTI`."""
    gestures = {permission.gesture for tool in TOOLS for permission in tool.permissions}
    gestures |= {tool.mask for tool in TOOLS if tool.mask is not None}
    assert gestures, "la tabella non dichiara nessun permesso"
    assert gestures <= set(soffitto.GESTI), sorted(gestures - set(soffitto.GESTI))


def _calls_the_ceiling(function) -> bool:
    source = textwrap.dedent(inspect.getsource(function))
    return any(isinstance(node, ast.Attribute) and node.attr == "_ceiling_denies"
               for node in ast.walk(ast.parse(source)))


def test_nessun_gestore_chiede_il_soffitto_da_se():
    """D-23: il soffitto si chiede in `dispatch`, dalla riga, e in nessun
    gestore. I gestori si chiedono alla tabella, insieme ai metodi di
    `ToolDispatcher` che non sono `dispatch` ne' il soffitto stesso: un
    metodo d'appoggio (`_full_detail_sync`) che lo richiedesse sarebbe la
    stessa copia un livello piu' in basso."""
    handlers = {tool.handler for tool in TOOLS}
    assert len(handlers) == len(TOOLS)
    methods = {member for name, member in inspect.getmembers(ToolDispatcher, inspect.isfunction)
               if name not in ("dispatch", "_ceiling_denies", "_refusal")}
    assert handlers <= methods
    offenders = sorted(function.__name__ for function in methods if _calls_the_ceiling(function))
    assert offenders == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [tool.name for tool in TOOLS if tool.needs_thread])
async def test_le_righe_col_filo_rifiutano_un_turno_senza_filo(name, monkeypatch):
    """D-42: il rifiuto «nessun filo» detto da `dispatch`, una volta, per ogni
    riga che lo dichiara -- prima del gestore e prima del soffitto."""
    recorder = _Recorder()
    row = tools._TOOL_PER_NAME[name]
    monkeypatch.setitem(tools._TOOL_PER_NAME, name, replace(row, handler=recorder))
    required = row.definition["input_schema"].get("required", [])
    arguments = {field: "x" for field in required}
    dispatcher = ToolDispatcher(None, None, agenda=object(), thread=None,
                                soffitto=_DENIES_EVERYTHING)

    answer = await dispatcher.dispatch(name, arguments)

    assert answer == {"errore": tools._NO_THREAD_REFUSAL}
    assert recorder.calls == []
