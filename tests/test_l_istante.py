"""Tappa 4, Task 4 («l'istante», A-26, C-32; decisione D3 del 05/10/2026):
un istante della casa si LEGGE in un posto solo e si SCRIVE in una forma sola,
tutte e due in `home_space/historian.py`.

- **A-26, la lettura.** Fino al 05/10/2026 tre moduli leggevano un ISO-8601
  per conto proprio con `datetime.fromisoformat` -- `house_query._age_s`,
  `appointments._in_home_zone`, l'importazione dei consumi in
  `usage/store.py` -- accanto a `historian.instant_epoch`, che il suo
  docstring chiamava «l'UNICA lettura di un istante nel prodotto». La prova
  qui sotto CHIEDE all'albero sintattico chi chiama `datetime.fromisoformat`:
  nessun elenco a mano.
- **D3, la forma.** ISO 8601 con l'offset della casa; `null` = «mai»; la
  chiave assente = «non lo so». La produce `historian.instant_out`.

Il rosso visto (05/10/2026, prima della sostituzione):
`test_only_historian_parses_an_instant` con `appointments.py`,
`house_query.py` e `usage/store.py` fra i trasgressori, uno ciascuno.

`date.fromisoformat` non e' nel cancello: legge un GIORNO del calendario
(`2026-10-05`), non un istante.
"""
import ast
import pathlib
from datetime import UTC, datetime

from hiris.app.home_space import historian

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
HISTORIAN = (APP / "home_space" / "historian.py").relative_to(ROOT).as_posix()

ROME = historian.home_space_zone("Europe/Rome")
#: Le 08:15 di Roma del 04/10/2026, ora legale (+02:00) = 06:15 UTC.
QUARTER_PAST_EIGHT_ROME = datetime(2026, 10, 4, 6, 15, tzinfo=UTC).timestamp()


def _instant_parses(tree) -> int:
    """Quante volte un modulo chiama `datetime.fromisoformat(...)`, sia col
    nome nudo (`from datetime import datetime`) sia qualificato
    (`datetime.datetime.fromisoformat`, `_dt.datetime.fromisoformat`)."""
    count = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "fromisoformat"):
            continue
        owner = node.func.value
        count += ((isinstance(owner, ast.Name) and owner.id == "datetime")
                  or (isinstance(owner, ast.Attribute) and owner.attr == "datetime"))
    return count


def _parses_by_module() -> dict[str, int]:
    out = {}
    for path in sorted(APP.rglob("*.py")):
        n = _instant_parses(ast.parse(path.read_text(encoding="utf-8")))
        if n:
            out[path.relative_to(ROOT).as_posix()] = n
    return out


def test_only_historian_parses_an_instant():
    parses = _parses_by_module()
    # La derivazione non e' rotta: vede le letture che historian fa davvero
    # (l'istante, e il giorno di `day_boundaries`).
    assert parses.get(HISTORIAN, 0) >= 1, parses
    outside = {f: n for f, n in parses.items() if f != HISTORIAN}
    assert outside == {}, f"un istante si legge fuori da historian: {outside}"


def test_the_gate_sees_a_qualified_call():
    # La seconda prova della derivazione: la forma qualificata entra da sola.
    tree = ast.parse("import datetime as _dt\n_dt.datetime.fromisoformat(x)\n"
                     "from datetime import date\ndate.fromisoformat(y)\n")
    assert _instant_parses(tree) == 1


# -- la forma: `instant_out` ---------------------------------------------------

def test_epoch_utc_and_offset_come_out_the_same():
    expected = "2026-10-04T08:15:00+02:00"
    assert historian.instant_out(QUARTER_PAST_EIGHT_ROME, ROME) == expected
    assert historian.instant_out(int(QUARTER_PAST_EIGHT_ROME), ROME) == expected
    assert historian.instant_out("2026-10-04T06:15:00+00:00", ROME) == expected
    assert historian.instant_out("2026-10-04T06:15:00Z", ROME) == expected
    assert historian.instant_out("2026-10-04T01:15:00-05:00", ROME) == expected
    assert historian.instant_out(expected, ROME) == expected


def test_none_is_null():
    # `null` = «so che non c'e'» (un'automazione mai eseguita): D3.
    assert historian.instant_out(None, ROME) is None


def test_what_cannot_be_read_comes_out_as_is():
    # Senza fuso «alle 8» non e' un istante: non si inventa, si lascia com'e'.
    assert historian.instant_out("2026-10-04T08:15:00", ROME) == "2026-10-04T08:15:00"
    assert historian.instant_out("ieri", ROME) == "ieri"
    assert historian.instant_out(True, ROME) == "True"


def test_the_offset_follows_daylight_saving():
    # Il 25/10/2026 Roma torna all'ora solare: stesso fuso, offset diverso.
    winter = datetime(2026, 12, 1, 7, 0, tzinfo=UTC).timestamp()
    assert historian.instant_out(winter, ROME) == "2026-12-01T08:00:00+01:00"


def test_without_a_known_zone_it_stays_utc():
    utc = historian.home_space_zone(None)
    assert historian.instant_out(QUARTER_PAST_EIGHT_ROME, utc) == "2026-10-04T06:15:00+00:00"


def test_the_zone_is_the_house_one_not_the_process_one(monkeypatch):
    """Il processo a New York, la casa a Roma: esce l'ora di Roma.

    Mutazione ESEGUITA (05/10/2026): in `instant_out` il fuso del processo al
    posto di `zone` (`datetime.fromtimestamp(raw).astimezone()` e
    `moment.astimezone()`) -- rossa, «2026-10-04T02:15:00-04:00».
    """
    import time

    if not hasattr(time, "tzset"):  # Windows: il fuso del processo non si cambia
        return
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        rome = "2026-10-04T08:15:00+02:00"
        assert historian.instant_out(QUARTER_PAST_EIGHT_ROME, ROME) == rome
        assert historian.instant_out("2026-10-04T06:15:00+00:00", ROME) == rome
    finally:
        monkeypatch.undo()
        time.tzset()
