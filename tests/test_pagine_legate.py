"""Le pagine disegnano e non ricalcolano (Tappa 4, Task 5, passo 1; R15).

Ogni prova qui sotto lega una cosa che una pagina sa alla sua fonte nel
server. Le due parti si LEGGONO entrambe: il Python si chiede al modulo (la
costante, o il comportamento dell'archivio), il JavaScript si legge nel file.
Niente e' ricopiato in questa prova -- una lista scritta qui sarebbe la terza
copia dello stesso fatto (CLAUDE.md, I-0).

Nate verdi: le copie oggi coincidono. La loro evidenza e' la mutazione
eseguita il 05/10/2026, scritta accanto a ciascuna.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from hiris.app.action.construction.revisions import STATES_SOSPESO
from hiris.app.api import servizi
from hiris.app.home_space.briefing import _MEASUREMENT_NAMES
from hiris.app.home_space.reader import TABLES
from hiris.app.mind.store import READING_RETENTION_S, ObservationsStore
from tests._avvio import started_app  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "hiris" / "app" / "static"


def _js(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def _js_object(source: str, name: str) -> dict[str, str]:
    """`var NAME = { chiave: 'valore', ... }` letto dal sorgente, nell'ordine."""
    match = re.search(r"var " + name + r" = \{([^}]*)\}", source)
    assert match, f"{name} non trovata: il file e' cambiato sotto questa prova?"
    return dict(re.findall(r"(\w+): '([^']*)'", match.group(1)))


def _js_array(source: str, name: str) -> list[str]:
    match = re.search(r"var " + name + r" = \[([^\]]*)\]", source)
    assert match, f"{name} non trovata: il file e' cambiato sotto questa prova?"
    return re.findall(r"'([^']*)'", match.group(1))


def _cron_time(app, job_id: str) -> str:
    """L'ora di un lavoro a orario, chiesta allo schedulatore dell'app avviata
    (`tests/_avvio.py`): «HH:MM»."""
    fields = {f.name: str(f) for f in app["scheduler"].get_job(job_id).trigger.fields}
    return f"{int(fields['hour']):02d}:{int(fields['minute']):02d}"


def _interval_minutes(app, job_id: str) -> int:
    return int(app["scheduler"].get_job(job_id).trigger.interval.total_seconds() // 60)


# -- C-09: i nomi delle misure ------------------------------------------------
# Mutazione eseguita: "vento" -> "venti" in `briefing._MEASUREMENT_NAMES` ->
# rossa con la differenza sulla chiave `wind_speed`.

def test_measurement_names_match_briefing():
    source = _js("config/tree-route.js")
    assert _js_object(source, "NOMI_MISURA") == _MEASUREMENT_NAMES
    # E lo stesso ordine: e' l'ordine in cui la casa si legge, sul nucleo e
    # sulla pagina.
    assert _js_array(source, "CHIAVI_MISURA_NOTE") == list(_MEASUREMENT_NAMES)


# -- C-12: il raggruppamento «in sospeso» delle Proposte ----------------------
# La pagina mostra due code (`handlers_constructions._both_queues`): le
# costruzioni, sospese in `STATES_SOSPESO`, e le proposte da fare a mano, la
# cui attesa si chiede all'archivio vero.
# Mutazione eseguita: tolto "in_corso" da `revisions.STATES_SOSPESO` -> rossa.

def test_constructions_open_states_match_both_queues(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        store.add_proposal(text="t", perche="p", fingerprint="f", prova={},
                           chi_applica="tu", now_ts=1790000000.0)
        manual_pending = {row["stato"] for row in store.proposals(pending_only=True)}
    finally:
        store.close()
    assert manual_pending, "l'archivio non ha restituito la proposta appena scritta"
    js = set(_js_array(_js("config/constructions-route.js"), "OPEN_STATES"))
    assert js == set(STATES_SOSPESO) | manual_pending


# -- C-10: gli stati dei servizi ----------------------------------------------
# Gli stati si chiedono all'archivio facendolo lavorare: presentarsi, essere
# approvati, essere revocati.
# Mutazione eseguita: `stato='revocato'` -> `stato='revocata'` in
# `ServiziStore.revoca` -> rossa.

def test_service_states_match_store(tmp_path):
    store = servizi.ServiziStore(str(tmp_path / "servizi.db"))
    # Un ruolo e una specie qualunque fra quelli ammessi, chiesti per stringa:
    # questa prova non lega ruoli e specie al JavaScript, e nominarli nel
    # codice la farebbe passare per il loro legame agli occhi di
    # `scripts/doppioni.py` (`_costanti_gia_legate`).
    role, kind = vars(servizi)["RUOLI"][0], vars(servizi)["SPECIE"][0]
    try:
        pending = store.presenta(nome="n", chiave="k", indirizzo="i", now_ts=1.0)["stato"]
        store.approva("k", ruolo=role, specie=kind, now_ts=2.0)
        authorized = store.autorizzato("k")["stato"]
        store.revoca("k", now_ts=3.0)
        revoked = store.elenco()[0]["stato"]
    finally:
        store.close()
    source = _js("config/services-route.js")
    js = {state for group in re.findall(r"righe\(\[([^\]]*)\]\)", source)
          for state in re.findall(r"'([^']*)'", group)}
    assert js == {pending, authorized, revoked}


# -- C-11: gli orari dello scheduler scritti in prosa -------------------------
# Mutazioni eseguite: `minute=20` -> `minute=25` sull'aggregazione notturna,
# `minutes=5` -> `minutes=10` sul recupero, `22 * 86400` -> `23 * 86400` in
# `READING_RETENTION_S`: tre rosse, ognuna sulla sua riga.

@pytest.mark.asyncio(loop_scope="module")
async def test_report_page_names_nightly_time(started_app):
    when = _cron_time(started_app, "hiris_mind_aggregation")
    assert f"alle {when}." in _js("config/watcher-giorno.js")


@pytest.mark.asyncio(loop_scope="module")
async def test_knowledge_page_names_backfill_rhythm(started_app):
    source = _js("config/watcher-sapere.js")
    minutes = _interval_minutes(started_app, "hiris_mind_backfill")
    assert f"un giorno ogni {minutes} minuti" in source
    days = re.search(r"var CHRONICLE_RETENTION_DAYS = (\d+);", source)
    assert days and int(days.group(1)) * 86400 == READING_RETENTION_S


# -- C-10: i nomi dei registri ------------------------------------------------
# `NOMI_REGISTRI` (common.js) e' TESTO DI PAGINA -- le parole con cui la home e
# l'albero nominano i registri -- e resta nel JavaScript: nel server non c'e'
# una tabella di quelle parole da cui riceverle. Le CHIAVI invece sono un fatto
# del server, le tabelle dell'anagrafe: un registro nuovo senza la sua parola
# comparirebbe col nome grezzo, e questa prova lo dice prima.
# Mutazione eseguita: aggiunta "zone" a `reader.TABLES` -> rossa.

def test_register_names_cover_reader_tables():
    assert set(_js_object(_js("common.js"), "NOMI_REGISTRI")) == set(TABLES)
