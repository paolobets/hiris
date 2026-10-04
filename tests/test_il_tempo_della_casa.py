"""Tappa 3, Task 10 («TEMPO», B-15 e B-16): il fuso della casa e «oggi» hanno
una casa sola, `home_space/historian.py`.

- **B-15.** Il nome del fuso si leggeva in due posti (l'aiutante di `server.py`,
  importato per nome privato da due gestori, e `ToolDispatcher._timezone`), il
  giorno «oggi» era scritto in linea in sette punti, e due moduli
  (`briefing.py`, `usage/vocabulary.py`) costruivano un `ZoneInfo` da se',
  ognuno col suo ripiego. Le prove qui sotto CHIEDONO all'albero del codice
  chi legge il fuso e chi costruisce un fuso: nessun elenco a mano.
- **B-16.** L'etichetta di data delle sessioni passate, nel contesto del
  modello, era `started_at[:10]` -- il giorno UTC. Fra mezzanotte di Roma e
  mezzanotte UTC una conversazione di stanotte risultava di ieri.

Mutazione ESEGUITA (passo 3 del piano): `handlers_chat` riportato a
`s["started_at"][:10]` -- rossa
`test_l_etichetta_di_una_sessione_e_il_giorno_della_casa` («[2026-08-21]» al
posto di «[2026-08-22]»).
Mutazione ESEGUITA: rimessa in `briefing.py` la riga
`timezone = ZoneInfo(name)` con il suo import -- rossa
`test_nessuno_costruisce_un_fuso_fuori_da_historian`.
Mutazione ESEGUITA: rimessa in `home_space/tools.py` la lettura
`self._home_space.reference_frame().get("fuso")` -- rossa
`test_il_fuso_della_casa_ha_un_solo_lettore`.
"""
import ast
import pathlib
from datetime import UTC, date, datetime

import pytest

from hiris.app.api.handlers_chat import compose_chat_context
from hiris.app.chat_store import _TS_FMT, _get_store, close_all_stores
from hiris.app.chat_thread import ChatThread
from hiris.app.home_space import historian

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"
HISTORIAN = APP / "home_space" / "historian.py"

#: 00:30 del 22/08/2026 a Roma (ora legale, +02:00) = 22:30 UTC del 21/08.
HALF_PAST_MIDNIGHT_ROME = datetime(2026, 8, 21, 22, 30, tzinfo=UTC).timestamp()


def _trees():
    for path in sorted(APP.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _is_reference_frame_call(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reference_frame")


def _is_fuso_key(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == "fuso"


def _timezone_reads(tree) -> int:
    """Quante volte un modulo chiede il fuso a `reference_frame()`: la chiamata
    `<qualcosa>.reference_frame()` seguita da `.get("fuso")` o da `["fuso"]`."""
    conto = 0
    for node in ast.walk(tree):
        per_get = (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == "get" and _is_reference_frame_call(node.func.value)
                   and bool(node.args) and _is_fuso_key(node.args[0]))
        per_indice = (isinstance(node, ast.Subscript) and _is_reference_frame_call(node.value)
                      and _is_fuso_key(node.slice))
        conto += per_get or per_indice
    return conto


def _zone_constructions(tree) -> int:
    """Quante volte un modulo importa `zoneinfo` o chiama `ZoneInfo(...)`."""
    conto = 0
    for node in ast.walk(tree):
        importa = ((isinstance(node, ast.ImportFrom) and node.module == "zoneinfo")
                   or (isinstance(node, ast.Import)
                       and any(a.name == "zoneinfo" for a in node.names)))
        chiama = (isinstance(node, ast.Call)
                  and ((isinstance(node.func, ast.Name) and node.func.id == "ZoneInfo")
                       or (isinstance(node.func, ast.Attribute)
                           and node.func.attr == "ZoneInfo")))
        conto += importa or chiama
    return conto


def test_il_fuso_della_casa_ha_un_solo_lettore():
    letture = {path.relative_to(ROOT).as_posix(): n
               for path, tree in _trees() if (n := _timezone_reads(tree))}
    # La derivazione non e' rotta: vede la lettura che c'e' davvero.
    assert letture.get(HISTORIAN.relative_to(ROOT).as_posix()) == 1, letture
    fuori = {f: n for f, n in letture.items() if f != HISTORIAN.relative_to(ROOT).as_posix()}
    assert fuori == {}, f"il fuso della casa si legge fuori da historian: {fuori}"


def test_l_aiutante_di_server_e_uscito():
    from hiris.app import server

    assert not hasattr(server, "_timezone_from_home_space_store")


def test_nessuno_costruisce_un_fuso_fuori_da_historian():
    costruzioni = {path.relative_to(ROOT).as_posix(): n
                   for path, tree in _trees() if (n := _zone_constructions(tree))}
    # La derivazione non e' rotta: l'import e la chiamata di historian ci sono.
    assert costruzioni.get(HISTORIAN.relative_to(ROOT).as_posix()) == 2, costruzioni
    fuori = {f: n for f, n in costruzioni.items()
             if f != HISTORIAN.relative_to(ROOT).as_posix()}
    assert fuori == {}, f"ZoneInfo costruito fuori da historian: {fuori}"


# -- le funzioni ---------------------------------------------------------------

class _HomeSpaceStub:
    def __init__(self, fuso):
        self._fuso = fuso

    def reference_frame(self):
        return {"fuso": self._fuso} if self._fuso else {}


def test_house_timezone_legge_l_anagrafe_e_tace_senza():
    assert historian.house_timezone(_HomeSpaceStub("Europe/Rome")) == "Europe/Rome"
    assert historian.house_timezone(_HomeSpaceStub(None)) is None
    assert historian.house_timezone(None) is None


def test_today_e_il_giorno_della_casa():
    assert historian.today("Europe/Rome", now=HALF_PAST_MIDNIGHT_ROME) == date(2026, 8, 22)
    # Senza fuso, o con un fuso che non esiste, si conta in UTC: non si inventa.
    assert historian.today(None, now=HALF_PAST_MIDNIGHT_ROME) == date(2026, 8, 21)
    assert historian.today("Non/Esiste", now=HALF_PAST_MIDNIGHT_ROME) == date(2026, 8, 21)


def test_local_date_segue_il_fuso_della_casa():
    assert historian.local_date(HALF_PAST_MIDNIGHT_ROME, "Europe/Rome") == date(2026, 8, 22)
    assert historian.local_date(HALF_PAST_MIDNIGHT_ROME, "") == date(2026, 8, 21)


# -- B-16: l'etichetta delle sessioni passate -----------------------------------

PAOLO = ChatThread("persona:paolo", "pannello")


@pytest.fixture(autouse=True)
def _close_chat_stores():
    yield
    close_all_stores()


def test_l_etichetta_di_una_sessione_e_il_giorno_della_casa(tmp_path):
    """Una sessione aperta alle 00:30 ora di Roma porta la data di Roma.

    E' la domanda `oggi` della sonda di parita' (attesa: 0 disaccordi)."""
    data_dir = str(tmp_path)
    aperta = datetime.fromtimestamp(HALF_PAST_MIDNIGHT_ROME, UTC).strftime(_TS_FMT)
    store = _get_store(data_dir)
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, summary, "
        "subject_key, entry_point) VALUES(?,?,?,?,?,?)",
        ("notte-1", aperta, aperta, "parlato della caldaia",
         PAOLO.subject_key, PAOLO.entry_point),
    )
    store._conn.commit()

    contesto = compose_chat_context({"home_space_store": _HomeSpaceStub("Europe/Rome")},
                                    data_dir, thread=PAOLO, soggetto=None)

    assert "[2026-08-22] parlato della caldaia" in contesto, contesto


def test_l_etichetta_senza_fuso_resta_il_giorno_utc(tmp_path):
    """Senza fuso si ripiega su UTC, come ovunque: la data non si inventa."""
    data_dir = str(tmp_path)
    aperta = datetime.fromtimestamp(HALF_PAST_MIDNIGHT_ROME, UTC).strftime(_TS_FMT)
    store = _get_store(data_dir)
    store._conn.execute(
        "INSERT INTO chat_sessions(session_id, started_at, last_msg_at, summary, "
        "subject_key, entry_point) VALUES(?,?,?,?,?,?)",
        ("notte-1", aperta, aperta, "parlato della caldaia",
         PAOLO.subject_key, PAOLO.entry_point),
    )
    store._conn.commit()

    contesto = compose_chat_context({}, data_dir, thread=PAOLO, soggetto=None)

    assert "[2026-08-21] parlato della caldaia" in contesto, contesto


# -- l'ora del nucleo: il fuso da historian, il ripiego dichiarato ---------------

def test_l_ora_del_nucleo_dice_il_fuso_vero_e_dichiara_il_ripiego():
    """`briefing._now_line` non costruisce piu' il suo fuso: lo chiede a
    `historian`. Quando il nome non vale, l'ora e' in UTC E lo dice -- il
    nome sbagliato accanto a un'ora UTC sarebbe un'ora falsa.

    Mutazione ESEGUITA: `label = name` senza il confronto con UTC -- rossa
    (la riga diceva «fuso Non/Esiste» accanto alle 22:30)."""
    from hiris.app.home_space.briefing import _now_line

    assert _now_line({"fuso": "Europe/Rome"}, HALF_PAST_MIDNIGHT_ROME) == (
        "Adesso sono le 00:30 del 22/08/2026 (fuso Europe/Rome).")
    assert _now_line({"fuso": "Non/Esiste"}, HALF_PAST_MIDNIGHT_ROME) == (
        "Adesso sono le 22:30 del 21/08/2026 (fuso UTC).")
    assert _now_line({}, HALF_PAST_MIDNIGHT_ROME) == (
        "Adesso sono le 22:30 del 21/08/2026 (fuso UTC).")
