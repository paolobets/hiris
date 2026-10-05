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
from aiohttp import web

from hiris.app.action.construction.revisions import STATES_SOSPESO
from hiris.app.api import servizi
from hiris.app.api.handlers_home_space import handle_get_home_space
from hiris.app.home_space.briefing import _MEASUREMENT_NAMES
from hiris.app.home_space.reader import TABLES, HomeSpace
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
# La pagina dell'albero li riceve in `GET /api/home-space` (`nomi_misure`) e non
# ne tiene una copia.
# Mutazione eseguita (nato rosso il passo 1 con la copia, 05/10/2026): rimessa
# in tree-route.js la mappa `NOMI_MISURA` -> rossa la seconda prova; tolto
# `nomi_misure` dal ramo con l'archivio -> rossa la prima.

@pytest.mark.asyncio
async def test_home_space_route_sends_measurement_names(aiohttp_client, tmp_path):
    store = HomeSpace(str(tmp_path))
    app = web.Application()
    app["home_space_store"] = store
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    try:
        body = await (await client.get("/api/home-space")).json()
    finally:
        store.close()
    # Valori E ordine: e' l'ordine in cui la casa si legge, sul nucleo e
    # sulla pagina.
    assert list(body["nomi_misure"].items()) == list(_MEASUREMENT_NAMES.items())

    app = web.Application()
    app["home_space_store"] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    body = await (await client.get("/api/home-space")).json()
    assert list(body["nomi_misure"].items()) == list(_MEASUREMENT_NAMES.items())


def test_tree_page_keeps_no_measurement_names():
    source = _js("config/tree-route.js")
    # Le chiavi che in italiano si scrivono uguali («area», «volume») sono
    # anche parole della pagina: non dicono niente, e restano fuori.
    copied = [key for key, name in _MEASUREMENT_NAMES.items() if key != name
              and (f"'{key}'" in source or re.search(rf"\b{key}\s*:", source))]
    assert not copied, f"tree-route.js ricopia i nomi delle misure: {copied}"


# -- C-12: il raggruppamento «in sospeso» delle Proposte ----------------------
# La pagina mostra due code (`handlers_constructions._both_queues`): le
# costruzioni, sospese in `STATES_SOSPESO`, e le proposte da fare a mano,
# sospese in `PROPOSAL_PENDING`. Dal passo 2 il server manda `sospesa` per riga
# (`test_constructions_api.py`), e la pagina non tiene un elenco di stati.
# Mutazione eseguita (passo 1, con la copia): tolto "in_corso" da
# `revisions.STATES_SOSPESO` -> rossa. Passo 2: rimesso nel JS l'elenco
# `['in_attesa', 'in_corso', 'attesa']` -> rossa.

def test_constructions_page_keeps_no_pending_states():
    source = _js("config/constructions-route.js")
    pending = set(STATES_SOSPESO) | {ObservationsStore.PROPOSAL_PENDING}
    arrays = [set(re.findall(r"'([^']*)'", body))
              for body in re.findall(r"\[([^\[\]]*)\]", source)]
    copies = [sorted(found & pending) for found in arrays if found & pending]
    assert not copies, f"constructions-route.js elenca stati sospesi: {copies}"


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
