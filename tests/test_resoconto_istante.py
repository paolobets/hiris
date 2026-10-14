"""Il resoconto di un giorno si scrive con l'orologio di chi lo chiede (G-14).

F4 della Chiusura (`77035b87`) ha insegnato a `replace_report` -- e quindi a
`facts.aggregate_day` e `facts.rebuild_chronicle` -- a ricevere l'istante
della scrittura (`when_ts`). Restavano i chiamanti in `server.py`: il
recupero, la riparazione d'avvio e la notte prendevano l'ora da
`replace_report`, che senza istante vale «adesso» -- l'orologio del disco, non
quello di chi chiama. Qui si prova che ognuno passa il suo: con un orologio
iniettato a una data lontana dall'adesso vero, `scritto_ts` e' quella data.

Mutazioni ESEGUITE (14/10/2026), ognuna rossa sulla sua prova con
`scritto_ts` uguale all'adesso del processo invece che all'orologio dato:
tolto `when_ts=` da `write_day_report` verso `aggregate_day`; tolto
`when_ts=` da `backfill_one_report` verso `rebuild_chronicle`. Ripristini
verificati con `git status`.
"""
import asyncio
from datetime import UTC, datetime, timedelta

from hiris.app.home_space.type_vocabulary import REPO_JUDGMENTS
from hiris.app.mind import day_report
from hiris.app.mind.facts import aggregate_day
from hiris.app.mind.store import ObservationsStore
from tests.test_mind_wiring import _repair_house, _sapere

#: L'orologio iniettato: il 25/08/2026, lontano dall'adesso di chi esegue.
CLOCK = datetime(2026, 8, 25, 5, tzinfo=UTC)


def _written_ts(archive: ObservationsStore, day: str) -> float:
    row = archive._conn.execute(
        "SELECT scritto_ts FROM resoconto WHERE giorno = ?", (day,)).fetchone()
    return row[0]


def _app(archive, tmp_path) -> dict:
    return {"home_space_store": None, "observations": archive,
            "knowledge": _sapere(tmp_path), "type_judgments": REPO_JUDGMENTS,
            "backfill_quiet": {}}


def _record_days(archive) -> None:
    for delta in (3, 2, 1):
        when = (CLOCK - timedelta(days=delta)).replace(hour=10)
        archive.decide_scope("light.prova", inside=True, reason="prova", author="observer")
        archive.record(quando_ts=when.timestamp(), source="entita",
                       subject="light.prova", da="off", a="on")


def test_il_recupero_di_un_giorno_mancante_scrive_col_suo_orologio(tmp_path):
    archive = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        _record_days(archive)
        written = asyncio.run(day_report.backfill_one_report(
            _app(archive, tmp_path), ha_client=_repair_house(),
            now=lambda tz: CLOCK.astimezone(tz)))
        assert written == "2026-08-22"
        assert _written_ts(archive, written) == CLOCK.timestamp()
    finally:
        archive.close()


def test_il_recupero_di_una_cronaca_vecchia_scrive_col_suo_orologio(tmp_path):
    archive = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        _record_days(archive)
        for day in ("2026-08-22", "2026-08-23", "2026-08-24"):
            aggregate_day(store=archive, day=day, timezone=None,
                          judgments=REPO_JUDGMENTS, when_ts=1.0)
        stale = {**archive.report("2026-08-23"), "giudizio": {"impronta": "vecchia"}}
        archive.replace_report("2026-08-23", stale, when_ts=1.0)
        written = asyncio.run(day_report.backfill_one_report(
            _app(archive, tmp_path), ha_client=_repair_house(),
            now=lambda tz: CLOCK.astimezone(tz)))
        assert written == "2026-08-23"
        assert _written_ts(archive, written) == CLOCK.timestamp()
    finally:
        archive.close()


def test_la_riparazione_d_avvio_scrive_col_suo_orologio(tmp_path):
    archive = ObservationsStore(str(tmp_path / "osservazioni.db"))
    try:
        _record_days(archive)
        asyncio.run(day_report.reaggregate_last_two_days(
            _app(archive, tmp_path), ha_client=_repair_house(),
            now=lambda tz: CLOCK.astimezone(tz)))
        for day in ("2026-08-23", "2026-08-24"):
            assert _written_ts(archive, day) == CLOCK.timestamp(), day
    finally:
        archive.close()
