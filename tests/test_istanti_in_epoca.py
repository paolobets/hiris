"""Gli archivi restituiscono ogni istante in epoca (G-14, Tappa 8, D8).

Sul disco gli istanti hanno ancora forme diverse -- l'epoca quasi ovunque,
l'ISO con `+00:00` di `ricordi.detto_il`, l'ISO con `Z` della cronologia della
chat -- e la forma del disco cambia con la fetta della rinomina (spec §9).
Chi LEGGE un archivio, pero', riceve una forma sola: l'epoca, convertita in
lettura con l'unica lettura di un istante del prodotto
(`historian.instant_epoch`). Al modello un istante arriva come ISO con
l'offset della casa (D3, `instant_out`)."""
from zoneinfo import ZoneInfo

from hiris.app.home_space.queries import sanitized_memories
from hiris.app.memory.store import MemoryStore

ROMA = ZoneInfo("Europe/Rome")


def test_un_ricordo_esce_con_l_istante_in_epoca(tmp_path):
    """Mutazione ESEGUITA (08/10/2026): tolta la conversione in `_compose` --
    rossa, `detto_il` torna la stringa ISO del disco."""
    memoria = MemoryStore(str(tmp_path / "memoria.db"))
    ident = memoria.remember("mi piace il caffe'")
    memoria._conn.execute("UPDATE ricordi SET detto_il = ? WHERE id = ?",
                          ("2026-08-02T09:00:00+00:00", ident))
    memoria._conn.commit()
    assert memoria.get(ident)["detto_il"] == 1785661200.0
    assert memoria.fetch()[0]["detto_il"] == 1785661200.0


def test_al_modello_l_istante_esce_nell_ora_della_casa():
    [ricordo] = sanitized_memories([{"id": 1, "testo": "x", "detto_il": 1785661200.0}],
                                   zone=ROMA)
    assert ricordo["detto_il"] == "2026-08-02T11:00:00+02:00"


# -- La cronologia della chat: sul disco l'ISO con `Z`, in lettura l'epoca. --

def _chat(tmp_path):
    from hiris.app.chat_store import _get_store, append_messages
    from hiris.app.chat_thread import ChatThread
    thread = ChatThread("persona:paolo", "pannello")
    append_messages([{"role": "user", "content": "ciao"}], str(tmp_path), thread=thread)
    store = _get_store(str(tmp_path))
    store._conn.execute("UPDATE chat_sessions SET started_at = ?", ("2026-08-02T09:00:00Z",))
    store._conn.execute("UPDATE chat_messages SET timestamp = ?", ("2026-08-02T09:00:00Z",))
    store._conn.commit()
    return store, thread


def test_la_chat_restituisce_gli_istanti_in_epoca(tmp_path):
    """Mutazione ESEGUITA (08/10/2026): tolta la conversione da
    `list_conversations` -- rossa, `ultimo_messaggio` torna la stringa ISO del
    disco."""
    from hiris.app.chat_store import close_all_stores
    store, thread = _chat(tmp_path)
    try:
        # La sessione e' ancora fresca (l'ultimo messaggio e' di adesso): il
        # contesto la legge.
        [messaggio] = store.load_context(thread, days=0, include_timestamp=True)
        assert messaggio["timestamp"] == 1785661200.0
        store._conn.execute("UPDATE chat_sessions SET last_msg_at = ?",
                            ("2026-08-02T09:00:00Z",))
        store._conn.commit()
        [riga] = store.list_conversations(thread, days=0)
        assert riga["ultimo_messaggio"] == 1785661200.0
        store._conn.execute("UPDATE chat_sessions SET summary = 'riassunto'")
        store._conn.commit()
        [passata] = store.get_past_summaries(thread)
        assert (passata["started_at"], passata["last_msg_at"]) == (1785661200.0, 1785661200.0)
    finally:
        close_all_stores()
