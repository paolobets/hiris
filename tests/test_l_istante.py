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


def test_an_instant_goes_out_to_the_second():
    """A15 (approvata il 05/10/2026): niente microsecondi. Lo specchio di Home
    Assistant li porta, e uscivano (`...T08:15:00.123456+02:00`): l'esempio di
    D3 e' al secondo, a chi legge non servono, e sono sette caratteri per
    istante. Si tronca, non si arrotonda: un istante non passa al secondo
    dopo.

    Mutazione eseguita: tolto `timespec="seconds"` -> rossa sulle tre forme."""
    expected = "2026-10-04T08:15:00+02:00"
    assert historian.instant_out(QUARTER_PAST_EIGHT_ROME + 0.999999, ROME) == expected
    assert historian.instant_out("2026-10-04T06:15:00.123456+00:00", ROME) == expected
    assert historian.instant_out("2026-10-04T06:15:00.987654Z", ROME) == expected


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


# -- cio' che va al modello: `search` ------------------------------------------
#
# C-32, D3: fino al 05/10/2026 `search` mandava `ultimo_cambio` come l'UTC
# grezzo dello specchio e `ultima_esecuzione` come l'UTC grezzo di Home
# Assistant, o la parola «mai» -- mentre la storia, sulla stessa entita',
# mandava l'ora della casa. Due forme dello stesso istante da due porte.

def _search(states: dict, since: dict, arguments: dict, *, behavior=(),
            attributes=None, timezone="Europe/Rome"):
    from hiris.app.home_space import house_query as hq
    from hiris.app.home_space.house import House
    from hiris.app.home_space.topology import Mirror

    entities = [{"id": eid, "nome": "", "area_id": None, "dispositivo_id": None,
                 "piattaforma": "x", "categoria": None, "classe": None,
                 "unita": None, "disabilitata": 0, "nascosta": 0}
                for eid in states]
    home = {"piani": [], "aree": [], "dispositivi": [], "entita": entities,
            "etichette": [], "categorie": [], "integrazioni": []}
    mirror = Mirror(dict(states), since=dict(since), attributes=attributes or {})
    filters = hq.parse_filters(arguments)
    assert not isinstance(filters, dict), filters
    return hq.query_house(House(home, mirror), list(behavior), filters,
                          detail=lambda kind, ref: {"esiste": False},
                          now=QUARTER_PAST_EIGHT_ROME, timezone=timezone)


def test_search_gives_the_last_change_in_the_house_zone():
    r = _search({"sensor.a": "1", "sensor.b": "2"},
                {"sensor.a": "2026-10-04T06:15:00+00:00",
                 "sensor.b": "2026-10-04T06:15:00.250000+00:00"},
                {"tipo": "sensor"})
    by_id = {v["id"]: v for v in r["voci"]}
    assert by_id["sensor.a"]["ultimo_cambio"] == "2026-10-04T08:15:00+02:00"
    # Al secondo anche dalla porta (A15): i microsecondi dello specchio non escono.
    assert by_id["sensor.b"]["ultimo_cambio"] == "2026-10-04T08:15:00+02:00"


def test_search_without_a_known_last_change_omits_the_key():
    # Chiave assente = «non lo so» (D3). `null` direbbe «non e' mai cambiata».
    r = _search({"sensor.a": "1", "sensor.b": "2"},
                {"sensor.a": "2026-10-04T06:15:00+00:00"}, {"tipo": "sensor"})
    by_id = {v["id"]: v for v in r["voci"]}
    assert "ultimo_cambio" not in by_id["sensor.b"]


def test_search_orders_by_the_instant_not_by_the_text():
    """Il 25/10/2026 alle 03:00 Roma torna da +02:00 a +01:00: le 02:30+02:00
    vengono PRIMA delle 02:10+01:00, ma come testo vengono dopo. Ordinare le
    stringhe dell'ora della casa sbaglierebbe una notte l'anno.

    Mutazione ESEGUITA (05/10/2026): `_sort_key` riportato al confronto fra
    testi -- rossa, `sensor.dopo` prima di `sensor.prima`."""
    r = _search({"sensor.prima": "1", "sensor.dopo": "2"},
                {"sensor.prima": "2026-10-25T00:30:00+00:00",
                 "sensor.dopo": "2026-10-25T01:10:00+00:00"},
                {"tipo": "sensor", "ordina": "ultimo_cambio"})
    assert [v["id"] for v in r["voci"]] == ["sensor.prima", "sensor.dopo"]
    assert [v["ultimo_cambio"] for v in r["voci"]] == [
        "2026-10-25T02:30:00+02:00", "2026-10-25T02:10:00+01:00"]


def test_search_says_never_with_null_and_unknown_with_no_key():
    """`last_triggered` c'e' SEMPRE fra gli attributi di un'automazione e di
    uno script, `None` se non e' mai partita: letto nel sorgente di Home
    Assistant il 05/10/2026, tag 2026.9.4,
    `homeassistant/components/automation/__init__.py:515-526` e
    `homeassistant/components/script/__init__.py:592-604`. Quindi `None` e'
    «mai», e la chiave che manca e' «non lo so» (un'automazione che lo
    specchio non ha letto)."""
    behavior = [{"id": f"automation.{n}", "tipo": "automazione", "nome": n}
                for n in ("mai", "ieri", "ignota")]
    r = _search({"automation.mai": "on", "automation.ieri": "on",
                 "automation.ignota": "on"}, {},
                {"genere": "automazione"}, behavior=behavior,
                attributes={"automation.mai": {"values": {"last_triggered": None}},
                            "automation.ieri": {"values": {
                                "last_triggered": "2026-10-03T18:00:00+00:00"}}})
    by_id = {v["id"]: v for v in r["voci"]}
    assert by_id["automation.mai"]["ultima_esecuzione"] is None
    assert by_id["automation.ieri"]["ultima_esecuzione"] == "2026-10-03T20:00:00+02:00"
    assert "ultima_esecuzione" not in by_id["automation.ignota"]


# -- cio' che va al modello: la storia -----------------------------------------
#
# La storia mandava gia' l'ora della casa (`_local`, ora `instant_out`), ma
# per un'automazione mai partita scriveva la parola «mai», e la scriveva
# anche quando lo specchio l'automazione non l'aveva letta affatto.

def _runs(subjects, depth_count):
    from hiris.app.home_space import house_history as hh
    from tests.test_house_history import _NESSUNA, _q

    chosen = hh.Chosen(depth_count, dict(_NESSUNA), hh.depth_for(depth_count), subjects)
    return hh.run_rows(_q(genere="esecuzioni"), chosen, traces={},
                       keys={s.ident: None for s in subjects}, unread={})


def test_history_says_never_with_null():
    from hiris.app.home_space import house_history as hh

    alone = _runs([hh.Subject("automation.mai", "mai", None)], 1)
    assert alone["soggetto"]["ultima_esecuzione"] is None


def test_history_says_unknown_with_no_key():
    from hiris.app.home_space import house_history as hh

    alone = _runs([hh.Subject("automation.ignota", "ignota", None, last_unknown=True)], 1)
    assert "ultima_esecuzione" not in alone["soggetto"]


# -- cio' che va al modello: l'istantanea di una promessa ----------------------
#
# `tools._snapshot` archivia l'istante della misura in epoch (`misurato_ts`):
# e' il RECORD, e resta (il piano: «cambia la resa, non il record»). La resa
# e' `keeper/promise.serializza`, l'unica forma della promessa per lo
# strumento e per la pagina: li' l'istante esce nell'ora della casa, col fuso
# che la promessa stessa porta (`fuso`, fondamenta 1). Nessuna pagina legge
# `misurato_ts` (cercato in `static/` il 05/10/2026): `quando_ts`,
# `nata_ts`, `risvegliata_ts` ed `esito_letto_ts` invece la pagina Impegni li
# legge come numeri, e restano epoch finche' la pagina non cambia con loro
# (Task 4, passo 6).

def _promise_row(snapshot, fuso="Europe/Rome") -> dict:
    import json

    from hiris.app.keeper.promise import _CHIAVI

    row = {key: None for key in _CHIAVI}
    row.update({"id": 1, "specie": "chiedi", "frase": "x", "quando_ts": 1.0,
                "fuso": fuso, "stato": "in_attesa", "nata_ts": 1.0,
                "chiamata_json": None, "istantanea_json": json.dumps(snapshot),
                "subject_key": None, "entry_point": None})
    return row


def test_the_snapshot_instant_reaches_the_model_in_the_house_zone():
    from hiris.app.keeper.promise import serializza

    out = serializza(_promise_row([
        {"entita": "sensor.t", "valore": "21", "unita": "°C",
         "misurato_ts": QUARTER_PAST_EIGHT_ROME}]))
    assert out["istantanea"][0]["misurato_ts"] == "2026-10-04T08:15:00+02:00"
    # Il record non cambia: i numeri che la pagina legge restano numeri.
    assert out["quando_ts"] == 1.0 and out["nata_ts"] == 1.0


def test_a_snapshot_without_a_known_zone_stays_utc():
    from hiris.app.keeper.promise import serializza

    out = serializza(_promise_row([{"entita": "sensor.t", "valore": "21",
                                    "unita": None,
                                    "misurato_ts": QUARTER_PAST_EIGHT_ROME}],
                                  fuso=None))
    assert out["istantanea"][0]["misurato_ts"] == "2026-10-04T06:15:00+00:00"
