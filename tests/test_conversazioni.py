"""Più conversazioni nel filo (fetta «il seguito delle chat divise», Task 6).

Spec `docs/design/2026-09-26-il-seguito-delle-chat-divise.md` §4 e §0
(decisioni 7-9): una conversazione e' una sessione di `chat_sessions`; il filo
ne ha una attiva e molte chiuse, e le chiuse si elencano, si riprendono, si
cancellano. Tutto limitato al filo: l'id di una conversazione altrui e' un id
che non esiste.

Le prove guardano il fatto -- cio' che torna dall'elenco, cio' che sta
nell'archivio, cio' che il modello rilegge -- e le rotte stanno in due app:
quella a mano di `test_chat_divise.py` (il confine finto `X-Chi`, per avere
Paolo e Marta) e quella VERA (`create_app`), per il CSRF e per le rotte che
esistono davvero.
"""
import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from hiris.app.api.handlers_chat import PENDING_REPLY_ERROR
from hiris.app.api.handlers_chat_history import (
    handle_delete_conversation,
    handle_list_conversations,
    handle_new_conversation,
    handle_resume_conversation,
)
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import (
    CONVERSATION_TITLE_MAX_CHARS,
    OUTCOME_ONLY_TITLE,
    ChatStore,
    _get_store,
    append_assistant_line,
    append_messages,
    close_all_stores,
    delete_conversation,
    get_past_summaries,
    list_conversations,
    load_history,
    new_conversation,
    resume_conversation,
)
from hiris.app.chat_thread import ChatThread, SyncTurnsInFlight
from hiris.app.proxy._sanitize import _TRUNCATED
from hiris.app.reasoning.queue import ReasoningQueue
from tests.test_chat_divise import MARTA, PAOLO, _make_app, _semina_orfane
from tests.test_settings_api import csrf_stretto  # noqa: F401

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _user(text):
    return [{"role": "user", "content": text}]


def _turn(u, a):
    return [{"role": "user", "content": u}, {"role": "assistant", "content": a}]


def _contents(messages):
    return [m["content"] for m in messages]


def _sessions(data_dir, thread):
    conn = _get_store(data_dir)._conn
    return [dict(r) for r in conn.execute(
        "SELECT session_id, summary, last_msg_at FROM chat_sessions "
        "WHERE subject_key = ? AND entry_point = ? ORDER BY started_at, rowid",
        (thread.subject_key, thread.entry_point)).fetchall()]


def _age_session(data_dir, session_id, *, hours=0, days=0):
    """Invecchia una sessione e i suoi messaggi: il silenzio senza aspettarlo."""
    ts = (datetime.now(UTC) - timedelta(hours=hours, days=days)).strftime(_TS_FMT)
    conn = _get_store(data_dir)._conn
    conn.execute("UPDATE chat_sessions SET last_msg_at = ?, started_at = ? "
                 "WHERE session_id = ?", (ts, ts, session_id))
    conn.execute("UPDATE chat_messages SET timestamp = ? WHERE session_id = ?",
                 (ts, session_id))
    conn.commit()


def _two_conversations(data_dir, thread=PAOLO):
    """Una conversazione chiusa (col silenzio) e una attiva, nell'ordine."""
    append_messages(_turn("Com'è la temperatura in sala? Grazie", "21 gradi"),
                    data_dir, thread=thread)
    old = _sessions(data_dir, thread)[0]["session_id"]
    _age_session(data_dir, old, hours=3)
    append_messages(_turn("Accendi la luce", "Fatto"), data_dir, thread=thread)
    new = next(s["session_id"] for s in _sessions(data_dir, thread)
               if s["session_id"] != old)
    return old, new


# ---------------------------------------------------------------------------
# L'archivio
# ---------------------------------------------------------------------------

def test_l_elenco_porta_esattamente_quattro_campi_e_una_sola_attiva(tmp_path):
    d = str(tmp_path)
    old, new = _two_conversations(d)
    rows = list_conversations(d, thread=PAOLO)

    assert [set(r) for r in rows] == [{"id", "titolo", "ultimo_messaggio", "attiva"}] * 2
    # Ordinate per ultimo messaggio, la piu' recente in testa.
    assert [r["id"] for r in rows] == [new, old]
    assert [r["attiva"] for r in rows] == [True, False]
    assert rows[0]["ultimo_messaggio"] > rows[1]["ultimo_messaggio"]


def test_il_titolo_e_la_prima_frase_dell_utente(tmp_path):
    d = str(tmp_path)
    old, new = _two_conversations(d)
    titles = {r["id"]: r["titolo"] for r in list_conversations(d, thread=PAOLO)}
    assert titles == {old: "Com'è la temperatura in sala?", new: "Accendi la luce"}


def test_una_frase_scritta_a_mano_non_porta_il_segno_del_taglio(tmp_path):
    """Il taglio che si vede e' del CSS (spec §4): una prima frase lunga ma
    normale arriva intera, senza il segno nel testo del pulsante."""
    d = str(tmp_path)
    sentence = ("Vorrei capire perché la caldaia si accende alle sei anche nei giorni "
                "in cui nessuno è in casa e la temperatura esterna supera i quindici gradi")
    append_messages(_turn(sentence, "ok"), d, thread=PAOLO)
    title = list_conversations(d, thread=PAOLO)[0]["titolo"]
    assert title == sentence
    assert _TRUNCATED not in title


def test_un_muro_di_testo_incollato_si_ferma_al_tetto_col_segno(tmp_path):
    """Il tetto e' contro l'abuso: un testo incollato senza un punto."""
    d = str(tmp_path)
    wall = "parola " * 200
    append_messages(_turn(wall, "ok"), d, thread=PAOLO)
    title = list_conversations(d, thread=PAOLO)[0]["titolo"]
    assert len(title) == CONVERSATION_TITLE_MAX_CHARS
    assert title.endswith(_TRUNCATED)
    assert wall.startswith(title[:-len(_TRUNCATED)])


def test_una_prima_frase_di_soli_spazi_non_nasconde_il_titolo_vero(tmp_path):
    """Tabulazioni e a capo contano come vuoto, non solo gli spazi."""
    d = str(tmp_path)
    append_messages(_turn(" \t\r\n\t ", "?"), d, thread=PAOLO)
    append_messages(_turn("Com'è il meteo?", "Sereno"), d, thread=PAOLO)
    assert list_conversations(d, thread=PAOLO)[0]["titolo"] == "Com'è il meteo?"


def test_una_prima_frase_di_soli_caratteri_invisibili_vale_come_vuota(tmp_path):
    """Security Low-5 (review del Task 7): i caratteri di formato (categoria
    Unicode Cf: spazio a larghezza zero, BOM, controlli di direzione) non si
    vedono, e un titolo fatto solo di loro sarebbe un pulsante vuoto. Si
    tolgono prima del controllo del vuoto: il titolo ricade come per una
    frase vuota; dentro un titolo vero spariscono, e con loro il ribaltamento
    di direzione che U+202E farebbe sul testo accanto."""
    d = str(tmp_path)
    append_messages(_turn("\u200b\ufeff\u200b", "?"), d, thread=PAOLO)
    assert list_conversations(d, thread=PAOLO)[0]["titolo"] == OUTCOME_ONLY_TITLE
    new_conversation(d, thread=PAOLO)
    append_messages(_turn("Acc\u200bendi\u202e la luce", "ok"), d, thread=PAOLO)
    assert list_conversations(d, thread=PAOLO)[0]["titolo"] == "Accendi la luce"


def test_una_conversazione_aperta_da_un_esito_ha_il_titolo_di_ripiego(tmp_path):
    d = str(tmp_path)
    assert append_assistant_line("La promessa delle 17: la porta è chiusa.", d, thread=PAOLO)
    assert list_conversations(d, thread=PAOLO)[0]["titolo"] == OUTCOME_ONLY_TITLE
    # Appena la persona risponde, il titolo e' la sua frase.
    append_messages(_user("Grazie, e il garage?"), d, thread=PAOLO)
    assert list_conversations(d, thread=PAOLO)[0]["titolo"] == "Grazie, e il garage?"


def test_l_elenco_e_solo_del_filo(tmp_path):
    d = str(tmp_path)
    _two_conversations(d, PAOLO)
    append_messages(_user("sono Marta"), d, thread=MARTA)
    assert [r["titolo"] for r in list_conversations(d, thread=MARTA)] == ["sono Marta"]
    assert len(list_conversations(d, thread=PAOLO)) == 2


def test_le_orfane_non_compaiono_nell_elenco_di_nessuno(tmp_path):
    d = str(tmp_path)
    _get_store(d)
    _semina_orfane(d)
    assert list_conversations(d, thread=PAOLO) == []


def test_nuova_chiude_l_attiva_col_riassunto_e_la_prossima_append_ne_apre_un_altra(tmp_path):
    d = str(tmp_path)
    append_messages(_turn("Com'è la temperatura?", "21 gradi"), d, thread=PAOLO)
    first = _sessions(d, PAOLO)[0]["session_id"]

    new_conversation(d, thread=PAOLO)

    assert load_history(d, thread=PAOLO) == []
    summaries = get_past_summaries(d, thread=PAOLO)
    assert [s["session_id"] for s in summaries] == [first]
    assert "21 gradi" in summaries[0]["summary"]
    append_messages(_user("E adesso?"), d, thread=PAOLO)
    assert _contents(load_history(d, thread=PAOLO)) == ["E adesso?"]
    assert len(_sessions(d, PAOLO)) == 2


def test_nuova_ripetuta_non_crea_niente(tmp_path):
    """Security 6.10: una sessione nasce solo alla prossima append."""
    d = str(tmp_path)
    append_messages(_turn("ciao", "ciao"), d, thread=PAOLO)
    for _ in range(5):
        new_conversation(d, thread=PAOLO)
    assert len(_sessions(d, PAOLO)) == 1
    new_conversation(d, thread=MARTA)
    assert _sessions(d, MARTA) == []


def test_nuova_riassume_anche_l_esito_che_apriva_la_conversazione(tmp_path):
    """Il riassunto di una conversazione aperta da un esito lo tiene
    (`unanswered_assistant_lines`, la casa sola della domanda)."""
    d = str(tmp_path)
    assert append_assistant_line("Esito: la caldaia è spenta.", d, thread=PAOLO)
    append_messages(_turn("Riaccendila", "Fatto"), d, thread=PAOLO)
    new_conversation(d, thread=PAOLO)
    summary = get_past_summaries(d, thread=PAOLO)[0]["summary"]
    assert "A: Esito: la caldaia è spenta." in summary
    assert "U: Riaccendila" in summary


def test_riprendi_rende_attiva_la_vecchia_e_chiude_quella_aperta(tmp_path):
    d = str(tmp_path)
    old, new = _two_conversations(d)
    # La vecchia e' gia' chiusa: il silenzio l'ha chiusa alla prima scrittura
    # della nuova, col suo riassunto.
    assert {s["session_id"]: s for s in _sessions(d, PAOLO)}[old]["summary"]

    assert resume_conversation(d, thread=PAOLO, session_id=old) is True

    assert _contents(load_history(d, thread=PAOLO)) == [
        "Com'è la temperatura in sala? Grazie", "21 gradi"]
    by_id = {s["session_id"]: s for s in _sessions(d, PAOLO)}
    assert by_id[old]["summary"] is None, "il riassunto si azzera: si rifarà alla chiusura"
    assert by_id[new]["summary"] is not None, "quella che era aperta si chiude, riassunta"
    assert "Accendi la luce" in by_id[new]["summary"]
    assert [s["session_id"] for s in get_past_summaries(d, thread=PAOLO)] == [new]
    rows = list_conversations(d, thread=PAOLO)
    assert [(r["id"], r["attiva"]) for r in rows] == [(old, True), (new, False)]


def test_riprendi_rimette_la_conversazione_nella_regola_delle_due_ore(tmp_path):
    d = str(tmp_path)
    old, _new = _two_conversations(d)
    before = datetime.now(UTC).strftime(_TS_FMT)
    assert resume_conversation(d, thread=PAOLO, session_id=old)
    last = {s["session_id"]: s for s in _sessions(d, PAOLO)}[old]["last_msg_at"]
    assert last >= before
    # Il prossimo turno continua la ripresa, non ne apre un'altra.
    append_messages(_user("e adesso?"), d, thread=PAOLO)
    assert _contents(load_history(d, thread=PAOLO))[-1] == "e adesso?"
    assert len(_sessions(d, PAOLO)) == 2


def test_riprendi_rispetta_la_conservazione(tmp_path):
    """Security 6.9: cio' che la conservazione ha fatto dimenticare non torna
    al modello con la ripresa -- e non compare nell'elenco."""
    d = str(tmp_path)
    append_messages(_turn("vecchissimo", "ok"), d, thread=PAOLO)
    ancient = _sessions(d, PAOLO)[0]["session_id"]
    _age_session(d, ancient, days=40)
    append_messages(_turn("recente", "ok"), d, thread=PAOLO)

    assert [r["titolo"] for r in list_conversations(d, thread=PAOLO, days=30)] == ["recente"]
    assert resume_conversation(d, thread=PAOLO, session_id=ancient, days=30) is False
    assert _contents(load_history(d, thread=PAOLO, days=30)) == ["recente", "ok"]
    # `0` = nessun filtro, la stessa regola di `load_context`.
    assert len(list_conversations(d, thread=PAOLO, days=0)) == 2
    assert resume_conversation(d, thread=PAOLO, session_id=ancient, days=0) is True
    assert _contents(load_history(d, thread=PAOLO, days=0)) == ["vecchissimo", "ok"]


def test_riprendi_di_marta_non_tocca_la_conversazione_di_paolo(tmp_path):
    """Security 6.4: la ripresa chiude solo la sessione aperta del SUO filo."""
    d = str(tmp_path)
    append_messages(_user("Paolo parla"), d, thread=PAOLO)
    m_old, _m_new = _two_conversations(d, MARTA)
    assert resume_conversation(d, thread=MARTA, session_id=m_old)
    assert [s["summary"] for s in _sessions(d, PAOLO)] == [None]
    assert _contents(load_history(d, thread=PAOLO)) == ["Paolo parla"]


def test_un_id_altrui_o_inesistente_o_orfano_e_come_se_non_ci_fosse(tmp_path):
    """Security 6.3: ogni istruzione lega id, soggetto e ingresso."""
    d = str(tmp_path)
    paolo_old, paolo_new = _two_conversations(d, PAOLO)
    append_messages(_user("sono Marta"), d, thread=MARTA)
    _semina_orfane(d)
    before = _get_store(d)._conn.execute(
        "SELECT session_id, summary, last_msg_at, subject_key FROM chat_sessions "
        "ORDER BY session_id").fetchall()
    n_messages = _get_store(d)._conn.execute(
        "SELECT COUNT(*) FROM chat_messages").fetchone()[0]

    for sid in (paolo_old, paolo_new, "prima", "mai-esistita"):
        assert resume_conversation(d, thread=MARTA, session_id=sid) is False
        assert delete_conversation(d, thread=MARTA, session_id=sid) is False
    # Anche dall'altro ingresso della stessa persona: il filo e' persona+ingresso.
    other_entry = ChatThread(PAOLO.subject_key, "firma")
    assert resume_conversation(d, thread=other_entry, session_id=paolo_old) is False
    assert delete_conversation(d, thread=other_entry, session_id=paolo_old) is False

    after = _get_store(d)._conn.execute(
        "SELECT session_id, summary, last_msg_at, subject_key FROM chat_sessions "
        "ORDER BY session_id").fetchall()
    assert [tuple(r) for r in after] == [tuple(r) for r in before]
    assert _get_store(d)._conn.execute(
        "SELECT COUNT(*) FROM chat_messages").fetchone()[0] == n_messages


def test_cancella_toglie_messaggi_e_sessione_insieme(tmp_path):
    """Security 6.6: nessuna riga di `chat_messages` resta appesa."""
    d = str(tmp_path)
    old, new = _two_conversations(d)
    assert delete_conversation(d, thread=PAOLO, session_id=old) is True
    conn = _get_store(d)._conn
    assert conn.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
                        (old,)).fetchone()[0] == 0
    assert [s["session_id"] for s in _sessions(d, PAOLO)] == [new]
    assert conn.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE session_id NOT IN "
        "(SELECT session_id FROM chat_sessions)").fetchone()[0] == 0
    assert _contents(load_history(d, thread=PAOLO)) == ["Accendi la luce", "Fatto"]


def test_cancellare_l_attiva_fa_nascere_la_prossima_alla_prossima_append(tmp_path):
    d = str(tmp_path)
    _old, new = _two_conversations(d)
    assert delete_conversation(d, thread=PAOLO, session_id=new)
    assert load_history(d, thread=PAOLO) == []
    append_messages(_user("di nuovo"), d, thread=PAOLO)
    assert _contents(load_history(d, thread=PAOLO)) == ["di nuovo"]


def test_cancella_e_atomica_se_la_seconda_istruzione_fallisce(tmp_path):
    """Security 6.6: messaggi e sessione in UNA transazione. Se la cancellazione
    della sessione fallisce, i messaggi tornano indietro con lei."""
    d = str(tmp_path)
    old, _new = _two_conversations(d)
    conn = _get_store(d)._conn
    conn.execute("CREATE TRIGGER no_session_delete BEFORE DELETE ON chat_sessions "
                 "BEGIN SELECT RAISE(ABORT, 'bloccata'); END")
    conn.commit()
    with pytest.raises(Exception, match="bloccata"):
        delete_conversation(d, thread=PAOLO, session_id=old)
    assert conn.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
                        (old,)).fetchone()[0] == 2


# Proprieta' spostate da `clear` (uscito con `DELETE /api/chat/history`,
# security 6.8): «cancellare il mio non tocca quello degli altri» e «un filo
# lascia l'altro» valgono ora per la conversazione cancellata.
def test_cancellare_una_conversazione_di_un_filo_lascia_l_altro(tmp_path):
    s = ChatStore(str(tmp_path / "c.db"))
    s.append(_user("a"), PAOLO)
    s.append(_user("b"), MARTA)
    paolo_sid = s._fresh_session_id(PAOLO)
    assert s.delete_conversation(PAOLO, paolo_sid) is True
    assert s.load_context(PAOLO) == []
    assert _contents(s.load_context(MARTA)) == ["b"]
    s.close()


def test_cancellare_non_tocca_le_orfane(tmp_path):
    d = str(tmp_path)
    append_messages(_user("mio"), d, thread=PAOLO)
    _semina_orfane(d)
    sid = _sessions(d, PAOLO)[0]["session_id"]
    assert delete_conversation(d, thread=PAOLO, session_id=sid)
    from hiris.app.chat_store import has_orphans
    assert has_orphans(d)
    assert _get_store(d)._conn.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE session_id = 'prima'").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Le rotte, con Paolo e Marta (confine finto di test_chat_divise.py)
# ---------------------------------------------------------------------------

def _app_with_conversations(tmp_path, **kw):
    app, q, data_dir = _make_app(tmp_path, **kw)
    # Come in `create_app`: il segno dei turni sincroni nasce con l'app.
    app["sync_turns"] = SyncTurnsInFlight()
    app.router.add_get("/api/chat/conversations", handle_list_conversations)
    app.router.add_post("/api/chat/conversations", handle_new_conversation)
    app.router.add_post("/api/chat/conversations/{id}/resume", handle_resume_conversation)
    app.router.add_delete("/api/chat/conversations/{id}", handle_delete_conversation)
    return app, q, data_dir


_P = {"X-Chi": "paolo"}
_M = {"X-Chi": "marta"}


@pytest.mark.asyncio
async def test_rotte_elenco_nuova_riprendi_cancella(tmp_path):
    app, _q, d = _app_with_conversations(tmp_path)
    old, new = _two_conversations(d)
    async with TestClient(TestServer(app)) as client:
        body = await (await client.get("/api/chat/conversations", headers=_P)).json()
        assert [(c["id"], c["attiva"]) for c in body["conversations"]] == [
            (new, True), (old, False)]

        r = await client.post(f"/api/chat/conversations/{old}/resume", headers=_P)
        assert r.status == 200
        hist = await (await client.get("/api/chat/history", headers=_P)).json()
        assert [m["content"] for m in hist["messages"]] == [
            "Com'è la temperatura in sala? Grazie", "21 gradi"]

        r = await client.post("/api/chat/conversations", headers=_P)
        assert r.status == 200
        hist = await (await client.get("/api/chat/history", headers=_P)).json()
        assert hist["messages"] == []

        r = await client.delete(f"/api/chat/conversations/{old}", headers=_P)
        assert r.status == 200
        body = await (await client.get("/api/chat/conversations", headers=_P)).json()
        assert [c["id"] for c in body["conversations"]] == [new]


@pytest.mark.asyncio
async def test_l_id_di_paolo_per_marta_e_un_404_identico_all_inesistente(tmp_path):
    app, _q, d = _app_with_conversations(tmp_path)
    old, new = _two_conversations(d)
    async with TestClient(TestServer(app)) as client:
        for method, path in (("POST", "/api/chat/conversations/{}/resume"),
                             ("DELETE", "/api/chat/conversations/{}")):
            foreign = await client.request(method, path.format(old), headers=_M)
            unknown = await client.request(method, path.format("mai-esistita"), headers=_M)
            assert foreign.status == unknown.status == 404
            assert await foreign.json() == await unknown.json()
        marta = await (await client.get("/api/chat/conversations", headers=_M)).json()
        assert marta["conversations"] == []
    assert {s["session_id"] for s in _sessions(d, PAOLO)} == {old, new}
    assert _contents(load_history(d, thread=PAOLO)) == ["Accendi la luce", "Fatto"]


@pytest.mark.asyncio
async def test_cancellare_la_propria_conversazione_non_tocca_quella_degli_altri(tmp_path):
    """Spostata da `DELETE /api/chat/history` (security 6.8)."""
    app, _q, d = _app_with_conversations(tmp_path)
    append_messages(_user("sono Paolo"), d, thread=PAOLO)
    append_messages(_user("sono Marta"), d, thread=MARTA)
    marta_sid = _sessions(d, MARTA)[0]["session_id"]
    async with TestClient(TestServer(app)) as client:
        resp = await client.delete(f"/api/chat/conversations/{marta_sid}", headers=_M)
        assert resp.status == 200
    assert load_history(d, thread=MARTA) == []
    assert load_history(d, thread=PAOLO) == [{"role": "user", "content": "sono Paolo"}]


@pytest.mark.asyncio
async def test_con_una_risposta_in_arrivo_le_tre_scritture_rispondono_409(tmp_path,
                                                                           monkeypatch):
    """Security 6.5: stessa costante del 409 di `handle_chat`, e solo nel filo
    che aspetta -- Marta non e' bloccata."""
    # Col token il ponte esiste e il turno si accoda (stessa premessa di
    # test_chat_divise.py::il_piano_puo_rispondere).
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")
    app, _q, d = _app_with_conversations(tmp_path, ponte_attivo=True)
    old, _new = _two_conversations(d)
    async with TestClient(TestServer(app)) as client:
        assert (await client.post("/api/chat", json={"message": "ci sei?"},
                                  headers=_P)).status == 202
        before = _sessions(d, PAOLO)
        for method, path in (("POST", "/api/chat/conversations"),
                             ("POST", f"/api/chat/conversations/{old}/resume"),
                             ("DELETE", f"/api/chat/conversations/{old}")):
            r = await client.request(method, path, headers=_P)
            assert r.status == 409, path
            assert await r.json() == {"error": PENDING_REPLY_ERROR}
        assert _sessions(d, PAOLO) == before

        assert (await client.post("/api/chat/conversations", headers=_M)).status == 200


def _session_contents(data_dir, session_id):
    return [r["content"] for r in _get_store(data_dir)._conn.execute(
        "SELECT content FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,)).fetchall()]


async def _writes_during_turn(client, data_dir, old):
    """Le tre scritture di Paolo a meta' turno: 409, e l'archivio fermo."""
    before = _sessions(data_dir, PAOLO)
    for method, path in (("POST", "/api/chat/conversations"),
                         ("POST", f"/api/chat/conversations/{old}/resume"),
                         ("DELETE", f"/api/chat/conversations/{old}")):
        r = await client.request(method, path, headers=_P)
        assert r.status == 409, path
        assert await r.json() == {"error": PENDING_REPLY_ERROR}
    assert _sessions(data_dir, PAOLO) == before
    # Marta non aspetta la risposta di Paolo.
    assert (await client.post("/api/chat/conversations", headers=_M)).status == 200


@pytest.mark.asyncio
async def test_durante_un_turno_sincrono_le_tre_scritture_rispondono_409(tmp_path):
    """Review di sicurezza Low-1: il turno della catena non ha una riga in
    coda, e senza il suo segno la risposta atterrava nella conversazione
    ripresa a meta' turno."""
    app, _q, d = _app_with_conversations(tmp_path)
    old, new = _two_conversations(d)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_chat(**_kw):
        started.set()
        await release.wait()
        return "risposta lenta"

    app["llm_router"].chat = slow_chat
    async with TestClient(TestServer(app)) as client:
        turn = asyncio.ensure_future(client.post(
            "/api/chat", json={"message": "domanda lenta"}, headers=_P))
        await asyncio.wait_for(started.wait(), 5)
        await _writes_during_turn(client, d, old)
        release.set()
        assert (await turn).status == 200
        after = await client.post(f"/api/chat/conversations/{old}/resume", headers=_P)
        assert after.status == 200
    # La risposta e' nella conversazione in cui e' stata chiesta.
    assert _session_contents(d, new)[-2:] == ["domanda lenta", "risposta lenta"]
    assert "risposta lenta" not in _session_contents(d, old)


@pytest.mark.asyncio
async def test_durante_un_turno_in_streaming_le_tre_scritture_rispondono_409(tmp_path):
    app, _q, d = _app_with_conversations(tmp_path)
    old, new = _two_conversations(d)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_stream(**_kw):
        started.set()
        await release.wait()
        yield 'data: {"type": "token", "text": "risposta in streaming"}\n\n'

    app["llm_router"].chat_stream = slow_stream
    async with TestClient(TestServer(app)) as client:
        turn = asyncio.ensure_future(client.post(
            "/api/chat", json={"message": "domanda in streaming", "stream": True},
            headers=_P))
        await asyncio.wait_for(started.wait(), 5)
        await _writes_during_turn(client, d, old)
        release.set()
        resp = await turn
        assert resp.status == 200
        await resp.read()
        after = await client.post("/api/chat/conversations", headers=_P)
        assert after.status == 200
    assert _session_contents(d, new)[-2:] == ["domanda in streaming",
                                              "risposta in streaming"]


@pytest.mark.asyncio
async def test_un_turno_sincrono_che_fallisce_libera_il_filo(tmp_path):
    app, _q, d = _app_with_conversations(tmp_path)
    _two_conversations(d)

    async def broken_chat(**_kw):
        raise RuntimeError("guasto del modello")

    app["llm_router"].chat = broken_chat
    async with TestClient(TestServer(app)) as client:
        assert (await client.post("/api/chat", json={"message": "x"},
                                  headers=_P)).status == 500
        assert (await client.post("/api/chat/conversations", headers=_P)).status == 200


@pytest.mark.asyncio
async def test_l_elenco_adotta_la_cronologia_di_prima_per_il_proprietario(tmp_path):
    app, _q, d = _app_with_conversations(tmp_path)
    _get_store(d)
    _semina_orfane(d)
    async with TestClient(TestServer(app)) as client:
        marta = await (await client.get("/api/chat/conversations", headers=_M)).json()
        paolo = await (await client.get("/api/chat/conversations", headers=_P)).json()
    assert marta["conversations"] == []
    assert [(c["id"], c["titolo"]) for c in paolo["conversations"]] == [
        ("prima", "detto prima delle chat divise")]


@pytest.mark.asyncio
async def test_un_orfana_non_si_riprende_ne_si_cancella_prima_dell_adozione(tmp_path):
    app, _q, d = _app_with_conversations(tmp_path)
    _get_store(d)
    _semina_orfane(d)
    async with TestClient(TestServer(app)) as client:
        for method, path in (("POST", "/api/chat/conversations/prima/resume"),
                             ("DELETE", "/api/chat/conversations/prima")):
            assert (await client.request(method, path, headers=_P)).status == 404
    from hiris.app.chat_store import has_orphans
    assert has_orphans(d)


# ---------------------------------------------------------------------------
# L'app VERA: le rotte registrate, il CSRF (security 6.1)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def real_client(aiohttp_client, tmp_path, monkeypatch):
    from hiris.app.server import create_app

    app = create_app()
    app["data_dir"] = str(tmp_path)
    app["chat_settings"] = ChatSettings()
    app["reasoning_queue"] = ReasoningQueue(os.path.join(str(tmp_path), "reasoning.db"))
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c


# Il filo di chi chiede con l'app vera: il confine senza token da' `sviluppo`.
SVILUPPO = ChatThread("sviluppo:-", "sviluppo")


def _real_session(client):
    d = client.app["data_dir"]
    old, new = _two_conversations(d, SVILUPPO)
    return d, old, new


@pytest.mark.asyncio
async def test_la_vecchia_delete_della_cronologia_non_esiste_piu(real_client):
    resp = await real_client.delete("/api/chat/history",
                                     headers={"X-Requested-With": "fetch"})
    assert resp.status in (404, 405)


@pytest.mark.asyncio
async def test_post_nuova_senza_x_requested_with_e_403_e_non_chiude(real_client, csrf_stretto):
    d, _old, new = _real_session(real_client)
    r = await real_client.post("/api/chat/conversations")
    assert r.status == 403
    assert (await r.json())["error"] == "csrf_required"
    assert {s["session_id"]: s["summary"] for s in _sessions(d, SVILUPPO)}[new] is None

    r = await real_client.post("/api/chat/conversations",
                               headers={"X-Requested-With": "fetch"})
    assert r.status == 200
    assert {s["session_id"]: s["summary"] for s in _sessions(d, SVILUPPO)}[new] is not None


@pytest.mark.asyncio
async def test_post_riprendi_senza_x_requested_with_e_403_e_non_riprende(real_client,
                                                                        csrf_stretto):
    d, old, _new = _real_session(real_client)
    r = await real_client.post(f"/api/chat/conversations/{old}/resume")
    assert r.status == 403
    assert _contents(load_history(d, thread=SVILUPPO)) == ["Accendi la luce", "Fatto"]

    r = await real_client.post(f"/api/chat/conversations/{old}/resume",
                               headers={"X-Requested-With": "fetch"})
    assert r.status == 200
    assert _contents(load_history(d, thread=SVILUPPO))[0].startswith("Com'è")


@pytest.mark.asyncio
async def test_delete_conversazione_senza_x_requested_with_e_403_e_non_cancella(real_client,
                                                                               csrf_stretto):
    d, old, new = _real_session(real_client)
    r = await real_client.delete(f"/api/chat/conversations/{old}")
    assert r.status == 403
    assert {s["session_id"] for s in _sessions(d, SVILUPPO)} == {old, new}

    r = await real_client.delete(f"/api/chat/conversations/{old}",
                                 headers={"X-Requested-With": "fetch"})
    assert r.status == 200
    assert {s["session_id"] for s in _sessions(d, SVILUPPO)} == {new}


@pytest.mark.asyncio
async def test_l_elenco_dell_app_vera_risponde(real_client):
    # Il segno dei turni sincroni nasce con l'app, non all'avvio.
    assert isinstance(real_client.app["sync_turns"], SyncTurnsInFlight)
    _d, old, new = _real_session(real_client)
    body = await (await real_client.get("/api/chat/conversations")).json()
    assert [c["id"] for c in body["conversations"]] == [new, old]
