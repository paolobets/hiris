"""I tre oggetti diagnostici di `/api/health` hanno la stessa forma (C-30).

`ponte`, `istantanea` e `riparazione` dicono tutti «com'e' andata, e
perche'»: dalla Chiusura (decisione di Paolo, 13/10/2026, consigliata B)
aprono con le stesse due chiavi, `stato` (una parola del vocabolario chiuso
dichiarato accanto al produttore) e `perche` (una frase o `None`). Il resto
dell'oggetto resta suo. Le due forme per ruolo restano (R-2.23).

Ogni produttore si prova acceso e spento: la forma non deve dipendere
dall'esito.

Proposta di F5 (`chiusura/f5-patch/c30-forma-comune-health.md`); prova scritta
da F11, entra con la parte di F8 (la riparazione, in `server.py`).
Mutazione ESEGUITA (14/10/2026): rimessa la chiave `oggetti` in
`server.reaggregate_last_two_days` -- rossa («'stato'» manca).
"""
import pytest

from hiris.app import server
from hiris.app.agent import runner
from hiris.app.mind import day_report, judgments


def _forma(oggetto: dict, vocabolario: tuple[str, ...]) -> None:
    assert oggetto["stato"] in vocabolario, oggetto
    assert oggetto["perche"] is None or isinstance(oggetto["perche"], str), oggetto


def test_il_ponte_prima_e_dopo_il_primo_init(monkeypatch):
    monkeypatch.setattr(runner, "_ULTIMO_INIT", {})
    _forma(runner.last_bridge_init(), runner.INIT_STATES)
    monkeypatch.setattr(runner, "_ULTIMO_INIT", {"claude_code_version": "2.1.0"})
    _forma(runner.last_bridge_init(), runner.INIT_STATES)


def test_l_istantanea_dal_sapere_e_dal_solo_seme():
    _, from_seed = judgments.build_judgments(None, unavailable_reason="disco pieno")
    _forma(from_seed, judgments.SNAPSHOT_STATES)

    class _Sapere:
        def judgment_rows_and_skipped(self):
            return [], []

    _, from_knowledge = judgments.build_judgments(_Sapere())
    _forma(from_knowledge, judgments.SNAPSHOT_STATES)


@pytest.mark.asyncio
async def test_la_riparazione_fatta_e_sollevata(monkeypatch):
    async def _nessun_resoconto(app, ha_client, days, timezone, *, when_ts):
        return []

    async def _sollevata(app, ha_client, *, now):
        raise RuntimeError("ricetta rotta")

    app: dict = {}
    with monkeypatch.context() as patch:
        patch.setattr(server, "_reaggregate_days", _sollevata)
        with pytest.raises(RuntimeError):
            await server.reaggregate_last_two_days(app, None)
    _forma(app["ultima_riparazione"], day_report.REPAIR_STATES)

    monkeypatch.setattr(server, "_write_missing_reports", _nessun_resoconto)
    await server.reaggregate_last_two_days(app, None)
    _forma(app["ultima_riparazione"], day_report.REPAIR_STATES)
