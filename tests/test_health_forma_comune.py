"""I tre oggetti diagnostici di `/api/health` hanno la stessa forma (C-30).

`ponte`, `istantanea` e `riparazione` dicono tutti «com'e' andata, e
perche'»: dalla Chiusura (decisione di Paolo, 13/10/2026, consigliata B)
aprono con le stesse due chiavi, `stato` (una parola del vocabolario chiuso
dichiarato accanto al produttore) e `perche` (una frase o `None`). Il resto
dell'oggetto resta suo. Le due forme per ruolo restano (R-2.23).

Ogni produttore si prova acceso e spento: la forma non deve dipendere
dall'esito.

Proposta di F5 (`chiusura/f5-patch/c30-forma-comune-health.md`); prova scritta
da F11, entra con la parte di F8 (la riparazione, oggi in `mind/day_report.py`).
Mutazione ESEGUITA (14/10/2026): rimessa la chiave `oggetti` in
`reaggregate_last_two_days` -- rossa («'stato'» manca).

Dal 14/10/2026 la riparazione controlla anche la parola esatta di ogni caso
(N162-2, revisore giro 162). Mutazione ESEGUITA: scambiati `REPAIR_DONE` e
`REPAIR_RAISED` in `reaggregate_last_two_days` -- prima di questa prova verde
(3 passate), con questa rossa sulla parola del caso sollevato. Ripristino
verificato con `git status`.
"""
import pytest

from hiris.app.agent import runner
from hiris.app.mind import day_report, judgments
from hiris.app.mind.day_report import LAST_REPAIR_KEY
from hiris.app.startup import live_values


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

    app = live_values()
    with monkeypatch.context() as patch:
        patch.setattr(day_report, "_reaggregate_days", _sollevata)
        with pytest.raises(RuntimeError):
            await day_report.reaggregate_last_two_days(app, None)
    _forma(app[LAST_REPAIR_KEY].value, day_report.REPAIR_STATES)
    # La parola esatta di ogni caso, non solo una del vocabolario (N162-2):
    # due casi scambiati restano nel vocabolario e la forma non li vede.
    assert app[LAST_REPAIR_KEY].value["stato"] == day_report.REPAIR_RAISED
    assert app[LAST_REPAIR_KEY].value["perche"] == "RuntimeError: ricetta rotta"

    monkeypatch.setattr(day_report, "_write_missing_reports", _nessun_resoconto)
    await day_report.reaggregate_last_two_days(app, None)
    _forma(app[LAST_REPAIR_KEY].value, day_report.REPAIR_STATES)
    assert app[LAST_REPAIR_KEY].value["stato"] == day_report.REPAIR_DONE
    assert app[LAST_REPAIR_KEY].value["perche"] is None
