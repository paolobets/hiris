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

from hiris.app.api import servizi
from hiris.app.api.handlers_home_space import (
    handle_get_home_space,
    outside_marks,
    register_names,
)
from hiris.app.home_space.briefing import _MEASUREMENT_NAMES
from hiris.app.home_space.house import _EXCLUDED_KEY
from hiris.app.home_space.reader import HOME_SPACE_KEY, TABLES, HomeSpace
from hiris.app.home_space.topology import OUTSIDE_CLASSES, visibility_classes
from hiris.app.mind.facts import NOT_ENTITY_PREFIXES
from hiris.app.mind.report import BACKFILL_EVERY_MINUTES, NIGHTLY_HOUR, NIGHTLY_MINUTE
from hiris.app.mind.store import READING_RETENTION_S
from hiris.app.startup import SCHEDULER_KEY, live_values
from hiris.app.states import SUSPENDED
from tests._avvio import started_app  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "hiris" / "app" / "static"


def _js(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def _js_array(source: str, name: str) -> list[str]:
    match = re.search(r"var " + name + r" = \[([^\]]*)\]", source)
    assert match, f"{name} non trovata: il file e' cambiato sotto questa prova?"
    return re.findall(r"'([^']*)'", match.group(1))


def _cron_time(app, job_id: str) -> str:
    """L'ora di un lavoro a orario, chiesta allo schedulatore dell'app avviata
    (`tests/_avvio.py`): «HH:MM»."""
    fields = {f.name: str(f) for f in app[SCHEDULER_KEY].get_job(job_id).trigger.fields}
    return f"{int(fields['hour']):02d}:{int(fields['minute']):02d}"


def _interval_minutes(app, job_id: str) -> int:
    return int(app[SCHEDULER_KEY].get_job(job_id).trigger.interval.total_seconds() // 60)


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
    app.update(live_values())
    app[HOME_SPACE_KEY] = store
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    body = await (await client.get("/api/home-space")).json()
    # Valori E ordine: e' l'ordine in cui la casa si legge, sul nucleo e
    # sulla pagina.
    assert list(body["nomi_misure"].items()) == list(_MEASUREMENT_NAMES.items())

    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = None
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
# costruzioni, sospese in `states.SUSPENDED`, e le proposte da fare a mano,
# sospese in `states.PENDING`. Dal passo 2 il server manda `sospesa` per riga
# (`test_constructions_api.py`), e la pagina non tiene un elenco di stati.
# Mutazione eseguita (passo 1, con la copia): tolto "in_corso" da
# `revisions.STATES_SOSPESO` -> rossa. Passo 2: rimesso nel JS l'elenco
# `['in_attesa', 'in_corso', 'attesa']` -> rossa.

def test_constructions_page_keeps_no_pending_states():
    source = _js("config/constructions-route.js")
    pending = set(SUSPENDED)
    arrays = [set(re.findall(r"'([^']*)'", body))
              for body in re.findall(r"\[([^\[\]]*)\]", source)]
    copies = [sorted(found & pending) for found in arrays if found & pending]
    assert not copies, f"constructions-route.js elenca stati sospesi: {copies}"


# -- C-10: le pagine delle code non scrivono parole di stato -----------------
# Le pagine Impegni e Proposte confrontano `stato` con le parole che la rotta
# manda (`stati`, e `stati_rifacimento` per un «Rifalla»), e sanno cosa fare
# di una riga dai campi che la riga porta (`disdicibile`, `decidibile`,
# `ripristinabile`). Le parole si chiedono al vocabolario (`states.py`, le tre
# code) e alla rotta (`handlers_constructions.REDO_STATES`), non si ricopiano.
# Mutazioni ESEGUITE (14/10/2026): rimesso in constructions-route.js
# `c.stato === 'incerta'` -> rossa, col nome del file e la parola;
# `rifacimento.stato === 'in_corso'` -> rossa.

def _queue_state_words() -> set[str]:
    from hiris.app import states
    from hiris.app.api.handlers_constructions import REDO_STATES
    return {*states.PROMISE_STATES, *states.CONSTRUCTION_STATES,
            *states.PROPOSAL_STATES, *REDO_STATES.values()}


def test_queue_pages_write_no_state_word():
    words = _queue_state_words()
    # Una derivazione che si svuota fa un cancello che non guarda niente.
    assert len(words) >= 15, f"le parole di stato non si leggono piu': {sorted(words)}"
    for page in ("config/constructions-route.js", "config/agenda-route.js"):
        written = sorted(set(_string_literals(_js(page))) & words)
        assert not written, f"{page} scrive parole di stato: {written}"


# -- C-10: gli stati dei servizi ----------------------------------------------
# Gli stati vivono in `servizi.STATE_*`; la rotta divide i servizi nelle tre
# sezioni della pagina (`handlers_servizi.listing`), e la pagina non ne tiene
# una copia. Supera il giro 2 del 05/10 (n.7), per D2 della Chiusura.
# Mutazioni ESEGUITE (13/10/2026): rimessa in services-route.js la scelta per
# stato (`righe(['in_attesa'])`) -> rossa la seconda; `STATE_REVOKED` a
# «revocata» con l'SQL che scrive ancora il letterale -> rossa la prima.

def test_service_sections_follow_the_store_states(tmp_path):
    from hiris.app.api.handlers_servizi import listing
    store = servizi.ServiziStore(str(tmp_path / "servizi.db"))
    role, kind = vars(servizi)["RUOLI"][0], vars(servizi)["SERVICE_SPECIES"][0]
    try:
        for key in ("a", "b", "c"):
            store.presenta(nome=key, chiave=key, indirizzo="i", now_ts=1.0)
        store.approva("b", ruolo=role, specie=kind, now_ts=2.0)
        store.approva("c", ruolo=role, specie=kind, now_ts=2.0)
        store.revoca("c", now_ts=3.0)
        sections = listing(store, 4.0, {})
    finally:
        store.close()
    assert {name: [r["nome"] for r in rows] for name, rows in sections.items()} == \
        {"da_decidere": ["a"], "accoppiati": ["b"], "revocati": ["c"]}


def test_services_page_keeps_no_states():
    source = _js("config/services-route.js")
    states = {servizi.STATE_PENDING, servizi.STATE_AUTHORIZED, servizi.STATE_REVOKED}
    assert len(states) == 3
    copied = sorted(state for state in states
                    if f"'{state}'" in source or f'"{state}"' in source)
    assert not copied, f"services-route.js tiene gli stati dei servizi: {copied}"


# -- C-10: le parole delle costruzioni ----------------------------------------
# Il nome del dominio e del gesto le manda la rotta (`construction_words`), con
# le chiavi dei loro padroni: i domini costruibili di `HAClient` e i gesti
# dell'officina. La pagina tiene solo il colore del gesto.
# Mutazioni ESEGUITE (13/10/2026): aggiunto «input_boolean» ai domini
# costruibili -> rossa la prima; rimessa in constructions-route.js la mappa
# `DOMAIN_NAME` -> rossa la seconda.

def test_construction_words_cover_their_owners():
    from hiris.app.action.construction.workshop import OPERATIONS
    from hiris.app.api.handlers_constructions import _DOMAIN_WORDS, _GESTURE_WORDS
    from hiris.app.proxy.ha_client import HAClient
    assert set(_DOMAIN_WORDS) == set(HAClient.CONFIGURABLE_DOMAINS)
    assert set(_GESTURE_WORDS) == set(OPERATIONS)


def test_constructions_page_keeps_no_construction_words():
    from hiris.app.api.handlers_constructions import _DOMAIN_WORDS, _GESTURE_WORDS
    source = _js("config/constructions-route.js")
    words = list(_DOMAIN_WORDS.values()) + [word for word, _ in _GESTURE_WORDS.values()]
    assert len(words) >= 6
    copied = [w for w in words if f"'{w}'" in source]
    assert not copied, f"constructions-route.js ricopia le parole delle costruzioni: {copied}"


# -- C-10: come si legge un costo ---------------------------------------------
# Quali stati sono numeri, quale e' il pavimento e le parole degli altri li dice
# la rotta dei consumi (`handlers_usage._cost_reading`, su ogni riga e ogni
# secchiello); la pagina tiene solo la tipografia. Supera la nota della Tappa 4
# (C-08: «le parole dei costi restano testo di pagina»), per D2 della Chiusura.
# Mutazioni ESEGUITE (13/10/2026): aggiunto «stimato» a `STATES` -> rossa la
# prima; rimessa in usage-route.js la mappa delle parole -> rossa la terza.

def test_cost_reading_partitions_the_usage_states():
    from hiris.app.api.handlers_usage import _COST_FLOOR, _COST_NUMBERS, _COST_WORDS
    from hiris.app.usage.vocabulary import STATES
    assert sorted([*_COST_NUMBERS, *_COST_WORDS]) == sorted(STATES)
    assert _COST_FLOOR in _COST_WORDS


def test_every_usage_row_carries_its_cost_reading():
    from hiris.app.api.handlers_usage import _counters_out
    row = {"richieste": 1, "token_in": 1, "token_out": 1, "cache_lettura": 0,
           "cache_scrittura": 0, "costo_usd": 0.5, "costo_stato": "non_noto",
           "errori_rate_limit": 0}
    out = _counters_out(row)
    assert (out["cost_is_number"], out["cost_is_floor"], out["cost_word"]) == \
        (False, True, "Prezzo sconosciuto")
    out = _counters_out({**row, "costo_stato": "reale"})
    assert (out["cost_is_number"], out["cost_is_floor"], out["cost_word"]) == (True, False, None)
    assert _counters_out({**row, "costo_stato": "futuro"})["cost_word"] == "futuro"


def test_usage_page_keeps_no_cost_words():
    from hiris.app.api.handlers_usage import _COST_WORDS
    source = _js("config/usage-route.js")
    copied = [w for w in _COST_WORDS.values() if w in source]
    assert not copied, f"usage-route.js ricopia le parole del costo: {copied}"


# -- C-11: gli orari dello scheduler ------------------------------------------
# Passo 1: «alle 00:20», «un giorno ogni 5 minuti» e i 22 giorni erano prosa
# delle pagine, legati allo schedulatore dell'app avviata (mutazioni eseguite:
# `minute=20`->`25`, backfill `minutes=5`->`10`, ritenzione 22->23: tre rosse).
# Passo 2: vivono in `mind/report.py` (`NIGHTLY_*`, `BACKFILL_EVERY_MINUTES`),
# lo schedulatore li riceve da li', e le pagine li ricevono dalle rotte
# (`test_mind_api.py`). Qui: lo schedulatore usa le costanti, e le pagine non
# ne tengono una copia.
# Mutazioni eseguite (passo 2): `hour=0, minute=20` rimessi a mano e
# `NIGHTLY_MINUTE` a 25 -> rossa la prima; «alle 00:20» rimessa come stringa
# nella pagina -> rossa la seconda.

@pytest.mark.asyncio(loop_scope="module")
async def test_scheduler_runs_report_jobs_from_constants(started_app):
    assert _cron_time(started_app, "hiris_mind_aggregation") == \
        f"{NIGHTLY_HOUR:02d}:{NIGHTLY_MINUTE:02d}"
    assert _interval_minutes(started_app, "hiris_mind_backfill") == BACKFILL_EVERY_MINUTES


def _string_literals(source: str) -> list[str]:
    """Le stringhe fra apici singoli del sorgente JS: dove una pagina scrive
    il testo che mostra (i commenti non contano)."""
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.findall(r"'((?:[^'\\\n]|\\.)*)'", code)


def test_report_pages_keep_no_scheduler_copy():
    when = f"{NIGHTLY_HOUR:02d}:{NIGHTLY_MINUTE:02d}"
    giorno = [t for t in _string_literals(_js("config/watcher-giorno.js")) if when in t]
    assert not giorno, f"watcher-giorno.js scrive l'ora del resoconto: {giorno}"
    sapere = _js("config/watcher-sapere.js")
    rhythm = f"ogni {BACKFILL_EVERY_MINUTES} minut"
    copied = [t for t in _string_literals(sapere) if rhythm in t]
    assert not copied, f"watcher-sapere.js scrive il ritmo del recupero: {copied}"
    days = READING_RETENTION_S // 86400
    assert not re.search(rf"=\s*{days}\s*;", sapere), \
        "watcher-sapere.js tiene i giorni di ritenzione"


# -- C-10: i nomi dei registri ------------------------------------------------
# Le parole con cui la home e l'albero nominano i registri le manda il server
# (`nomi_registri` di `GET /api/home-space`), con le chiavi chieste a
# `reader.TABLES`; la pagina non ne tiene una copia. Supera la decisione del
# giro 2 del 05/10 (n.6: «restano nel JS, legate da una prova»): D2 della
# Chiusura vuole un vocabolario chiuso in una casa sola.
# Mutazioni ESEGUITE (13/10/2026): rimessa in common.js la mappa
# `NOMI_REGISTRI` -> rossa la seconda; tolto `nomi_registri` dal ramo senza
# archivio -> rossa la prima.

@pytest.mark.asyncio
async def test_home_space_route_sends_register_names(aiohttp_client, tmp_path):
    store = HomeSpace(str(tmp_path))
    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = store
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    body = await (await client.get("/api/home-space")).json()
    assert list(body["nomi_registri"]) == list(TABLES)
    assert body["nomi_registri"] == register_names()
    # «Categorie» e' la parola di Home Assistant, non una nostra (3.22.3).
    assert register_names()["categorie"] == "Categorie"

    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    body = await (await client.get("/api/home-space")).json()
    assert body["nomi_registri"] == register_names()


def test_no_page_keeps_the_register_names():
    words = set(register_names().values())
    assert len(words) == len(TABLES), "la derivazione non porta piu' i nomi dei registri"
    copies = [path.name for path in STATIC.rglob("*.js")
              if all(f"'{w}'" in path.read_text(encoding="utf-8") for w in words)]
    assert not copies, f"pagine che ricopiano i nomi dei registri: {copies}"


# -- C-10: i segni del `fuori` -------------------------------------------------
# Il segno con cui l'albero marca un'entita' disabilitata, nascosta o di
# servizio lo manda il server (`segni_fuori` di `GET /api/home-space`), con le
# chiavi chieste a `topology.OUTSIDE_CLASSES`; la pagina non ne tiene una copia
# (fino al 14/10/2026 era `OUTSIDE_MARK` in tree-route.js). F11 della Chiusura.
# Mutazioni ESEGUITE (14/10/2026): rimessa in tree-route.js la mappa con le tre
# parole -> rossa la terza; tolto `segni_fuori` dal ramo senza archivio ->
# rossa la prima; la classe `servizio` scritta in linea in `visibility_classes`
# come «di_servizio» -> rossa la seconda.

@pytest.mark.asyncio
async def test_home_space_route_sends_outside_marks(aiohttp_client, tmp_path):
    store = HomeSpace(str(tmp_path))
    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = store
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    body = await (await client.get("/api/home-space")).json()
    assert body["segni_fuori"] == outside_marks()

    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    client = await aiohttp_client(app)
    body = await (await client.get("/api/home-space")).json()
    assert body["segni_fuori"] == outside_marks()


def test_outside_marks_cover_every_class_the_rule_produces():
    """Le chiavi sono le classi che `visibility_classes` produce davvero, e
    ognuna ha la sua parola (nessuna esce col solo nome di ripiego)."""
    tutte = {"disabilitata": 1, "nascosta": 1, "categoria": "diagnostic"}
    produced = [name for name, _cause in visibility_classes(tutte)]
    assert produced == list(OUTSIDE_CLASSES)
    assert list(outside_marks()) == produced


def test_no_page_keeps_the_outside_marks():
    words = set(outside_marks().values())
    assert len(words) == len(OUTSIDE_CLASSES), "la derivazione non porta piu' i segni"
    copies = [path.name for path in STATIC.rglob("*.js")
              if any(f"'{w}'" in path.read_text(encoding="utf-8") for w in words)]
    assert not copies, f"pagine che ricopiano i segni del fuori: {copies}"


# -- C-10: i prefissi dei soggetti di sistema ---------------------------------
# `NOT_ENTITY_PREFIXES` (`mind/facts.py`) e' la grammatica con cui la cronaca
# scrive un soggetto che non e' un'entita'; `parseSubjectPrefix`
# (`watcher-shared.js`) e' la pagina che la legge. Un prefisso nuovo senza la
# sua lettura comparirebbe a schermo come un identificatore grezzo -- ed e'
# successo quasi: `connessione:` (il riallineamento, 06/10/2026) e' nato in
# Python. Fino a quel giorno la coppia era un doppione noto senza legame.
# Mutazione ESEGUITA: tolto il ramo `connessione:` da `parseSubjectPrefix`
# -> rossa.

def test_subject_prefixes_are_read_by_the_page():
    source = _js("config/watcher-shared.js")
    body = re.search(r"function parseSubjectPrefix\(s\) \{(.*?)\n  \}", source, re.DOTALL)
    assert body, "parseSubjectPrefix non trovata: il file e' cambiato sotto questa prova?"
    read = re.findall(r"s\.indexOf\('([a-z]+:)'\) === 0", body.group(1))
    assert len(read) >= 4, f"la lettura dei prefissi non trova piu' niente: {read}"
    assert sorted(read) == sorted(NOT_ENTITY_PREFIXES)


def test_i_segni_del_fuori_dell_albero_sono_le_classi_del_server():
    """L'albero scrive un segno per ogni classe del `fuori` (Tappa 9, F5:
    «Parole di oggi», scelta del proprietario il 12/10/2026). Le classi sono
    quelle di `topology.visibility_classes`, che `House` conta in
    `_EXCLUDED_KEY`: una classe nuova senza segno uscirebbe col nome grezzo,
    e un segno senza classe sarebbe una parola morta. Dal 14/10/2026 (C-10,
    F11) i segni li manda il server (`segni_fuori`): la prova guarda li'.

    Mutazione ESEGUITA (Tappa 9): `servizio` tolto dai segni -- rossa."""
    assert set(outside_marks()) == set(_EXCLUDED_KEY), (sorted(outside_marks()),
                                                        sorted(_EXCLUDED_KEY))
