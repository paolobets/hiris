"""Le pagine ricevono l'ora della casa (C-17, Tappa 4, Task 4, passo 6).

Ogni rotta che manda un istante a una pagina lo manda in ISO con l'offset della
casa (`historian.instant_out`, D3) e porta accanto `orologio`
(`historian.house_clock`): la pagina mostra le cifre e sa che giorno e' oggi
senza chiederlo al browser. Qui si prova la meta' del server; la meta' della
pagina e' in `tests/js/ora-della-casa-pagine.test.mjs`.
"""
from __future__ import annotations

import re

import pytest
from aiohttp import web

from hiris.app.api import servizi
from hiris.app.api.handlers_home_space import handle_get_home_space
from hiris.app.api.handlers_servizi import listing
from hiris.app.home_space.reader import HOME_SPACE_KEY
from hiris.app.home_space.rounds import TREE_COMPARISON_KEY
from hiris.app.live_value import LiveValue
from hiris.app.startup import live_values
from tests._anagrafe_finta import AnagrafeFinta

ROMA = "Europe/Rome"
#: Un ISO con l'offset di Roma (ora solare o legale), al secondo.
ROME_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+0[12]:00$")


def _casa():
    return AnagrafeFinta({"piani": [], "aree": [], "dispositivi": [], "entita": []},
                         cornice={"fuso": ROMA})


@pytest.mark.asyncio
async def test_home_space_sends_its_instants_in_the_house_hour(aiohttp_client):
    store = _casa()
    store.hold_behavior([])
    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = store
    app[TREE_COMPARISON_KEY] = LiveValue({"aree_totali": 1, "guardate": [],
                                          "letto_il": "2026-10-13T22:30:00+00:00"})
    app.router.add_get("/api/home-space", handle_get_home_space)
    corpo = await (await (await aiohttp_client(app)).get("/api/home-space")).json()

    assert corpo["orologio"]["fuso"] == ROMA
    assert ROME_ISO.match(corpo["orologio"]["adesso"])
    assert ROME_ISO.match(corpo["anagrafe_letta_il"]), corpo["anagrafe_letta_il"]
    assert ROME_ISO.match(corpo["comportamento"]["letto_il"])
    # Le 22:30 UTC del 13 sono le 00:30 del 14 a Roma: il giorno cambia.
    assert corpo["confronto"]["letto_il"] == "2026-10-14T00:30:00+02:00"
    assert app[TREE_COMPARISON_KEY].value["letto_il"] == "2026-10-13T22:30:00+00:00", \
        "la copia in memoria non si tocca"


@pytest.mark.asyncio
async def test_home_space_without_a_store_still_has_a_clock(aiohttp_client):
    app = web.Application()
    app.update(live_values())
    app[HOME_SPACE_KEY] = None
    app.router.add_get("/api/home-space", handle_get_home_space)
    corpo = await (await (await aiohttp_client(app)).get("/api/home-space")).json()
    assert corpo["orologio"]["fuso"] == "UTC"


def test_services_send_their_instants_in_the_house_hour(tmp_path):
    store = servizi.ServiziStore(str(tmp_path / "servizi.db"))
    try:
        # 13/10/2026 22:30 UTC: le 00:30 del 14 a Roma.
        store.presenta(nome="pannello", chiave="k", indirizzo="i", now_ts=1791930600.0)
        rows = listing(store, 1791930700.0, {HOME_SPACE_KEY: _casa()})
    finally:
        store.close()
    assert rows["da_decidere"][0]["visto_ts"] == "2026-10-14T00:30:00+02:00"
    assert rows["da_decidere"][0]["deciso_ts"] is None


# -- L'osservatore: il giorno da chiedere lo dice il server (passo 5) ---------

def test_yesterday_and_today_are_the_house_ones():
    from hiris.app.home_space import historian

    # 13/10/2026 23:00 UTC: all'01:00 del 14 a Roma; a New York sono le 19:00
    # del 13. «Ieri», per la casa, e' il 13.
    now = 1791932400.0
    assert historian.resolve_day("ieri", ROMA, now=now) == "2026-10-13"
    assert historian.resolve_day("oggi", ROMA, now=now) == "2026-10-14"
    assert historian.resolve_day("2026-09-01", ROMA, now=now) == "2026-09-01"


class _Request:
    def __init__(self, app, query):
        self.app, self.query = app, query


@pytest.mark.asyncio
async def test_the_report_asked_by_name_answers_which_day_it_is(tmp_path):
    import json

    from hiris.app.api.handlers_mind import handle_analysis, handle_report
    from hiris.app.home_space import historian
    from hiris.app.mind.store import OBSERVATIONS_KEY, ObservationsStore

    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        app = {**live_values(), OBSERVATIONS_KEY: store, HOME_SPACE_KEY: _casa()}
        yesterday = historian.resolve_day("ieri", ROMA)
        missing = await handle_report(_Request(app, {"day": "ieri"}))
        assert missing.status == 404
        assert json.loads(missing.body)["giorno"] == yesterday
        # Anche il 404 porta l'orologio: il «Letto alle» della scheda e' l'ora
        # della casa pure quando il resoconto non c'e' ancora.
        assert json.loads(missing.body)["orologio"]["fuso"] == ROMA
        store.replace_report(yesterday, {"giorno": yesterday, "misure": [], "forme": [],
                                         "cronaca": []})
        found = json.loads((await handle_report(_Request(app, {"day": "ieri"}))).body)
        assert found["giorno"] == yesterday
        assert found["orologio"]["fuso"] == ROMA
        analysis = await handle_analysis(_Request(app, {"day": "oggi"}))
        assert json.loads(analysis.body)["giorno"] == historian.resolve_day("oggi", ROMA)
        assert json.loads(analysis.body)["orologio"]["fuso"] == ROMA
    finally:
        store.close()


def test_a_whole_reading_goes_out_in_the_house_hour():
    from hiris.app.home_space import historian

    zone = historian.home_space_zone(ROMA)
    reading = {"tentativi": [{"quando_ts": 1791930600.0, "esito": "x"}],
               "watching": [{"quando": 1791930600.0, "giorno": "2026-10-13"}],
               "riconsiderazione": {"finestra_s": 3600.0, "quando_ts": None},
               "flag_ts": True}
    assert historian.instants_out(reading, zone) == {
        "tentativi": [{"quando_ts": "2026-10-14T00:30:00+02:00", "esito": "x"}],
        "watching": [{"quando": "2026-10-14T00:30:00+02:00", "giorno": "2026-10-13"}],
        "riconsiderazione": {"finestra_s": 3600.0, "quando_ts": None},
        "flag_ts": True}
    once = historian.instants_out(reading, zone)
    assert historian.instants_out(once, zone) == once, "due volte non cambia niente"


# -- La chat: le bolle e la barra delle conversazioni -------------------------

@pytest.mark.asyncio
async def test_the_chat_sends_its_instants_in_the_house_hour(tmp_path):
    """La cronologia e l'elenco delle conversazioni: l'archivio restituisce
    l'epoca (G-14), la rotta l'ora della casa con l'orologio accanto.
    Mutazione ESEGUITA (14/10/2026): tolta la conversione in
    `handle_list_conversations` -- rossa, `ultimo_messaggio` torna l'epoca."""
    import json
    from unittest.mock import MagicMock

    from aiohttp.test_utils import make_mocked_request

    from hiris.app.api.handlers_chat_history import (
        handle_get_chat_history,
        handle_list_conversations,
    )
    from hiris.app.chat_settings import CHAT_SETTINGS_KEY, ChatSettings
    from hiris.app.chat_store import _get_store, append_messages, close_all_stores
    from hiris.app.chat_thread import thread_for
    from hiris.app.storage import DATA_DIR_KEY

    close_all_stores()
    try:
        append_messages([{"role": "user", "content": "ciao"}], str(tmp_path),
                        thread=thread_for(None, None))
        valori = {DATA_DIR_KEY: str(tmp_path), CHAT_SETTINGS_KEY: LiveValue(ChatSettings()),
                  HOME_SPACE_KEY: _casa()}
        app = MagicMock()
        app.__getitem__ = MagicMock(side_effect=lambda k: valori.get(k))
        app.get = MagicMock(side_effect=lambda k, d=None: valori.get(k, d))

        storia = json.loads((await handle_get_chat_history(
            make_mocked_request("GET", "/api/chat/history", app=app))).body)
        assert ROME_ISO.match(storia["messages"][0]["timestamp"])
        assert storia["orologio"]["fuso"] == ROMA

        # Un istante fermo che a Roma cambia giorno: le 22:30 UTC del 13 sono
        # le 00:30 del 14. (Dopo la cronologia: la sessione non e' piu'
        # fresca, e la cronologia non la leggerebbe.)
        store = _get_store(str(tmp_path))
        store._conn.execute("UPDATE chat_sessions SET last_msg_at = ?",
                            ("2026-10-13T22:30:00Z",))
        store._conn.commit()
        elenco = json.loads((await handle_list_conversations(
            make_mocked_request("GET", "/api/chat/conversations", app=app))).body)
        assert elenco["conversations"][0]["ultimo_messaggio"] == "2026-10-14T00:30:00+02:00"
        assert elenco["orologio"]["fuso"] == ROMA
    finally:
        close_all_stores()
