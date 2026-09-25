from hiris.app.chat_thread import ChatThread, subject_key_for, thread_from_context, thread_for, thread_to_context, entry_point_for


def test_la_chiave_e_specie_e_id_mai_il_nome():
    s = {"specie": "persona", "id": "abc123", "nome": "Paolo", "utente": "paolo"}
    assert subject_key_for(s) == "persona:abc123"


def test_persona_anonima_ha_una_chiave_dichiarata():
    assert subject_key_for({"specie": "persona", "id": None}) == "persona:-"


def test_nessun_soggetto_e_nessuno():
    assert subject_key_for(None) == "nessuno:-"


def test_ingresso_dalla_via():
    assert entry_point_for("ingress") == "pannello"
    assert entry_point_for("canale") == "firma"
    assert entry_point_for("no_token") == "sviluppo"
    assert entry_point_for("turno") == "interno"
    assert entry_point_for(None) == "interno"


def test_due_persone_due_fili_stessa_persona_due_ingressi_due_fili():
    paolo = {"specie": "persona", "id": "p"}
    marta = {"specie": "persona", "id": "m"}
    assert thread_for(paolo, "ingress") != thread_for(marta, "ingress")
    assert thread_for(paolo, "ingress") != thread_for(paolo, "no_token")
    assert thread_for(paolo, "ingress") == ChatThread("persona:p", "pannello")


def test_il_filo_attraversa_il_contesto_del_job():
    f = ChatThread("persona:p", "pannello")
    assert thread_from_context(thread_to_context(f)) == f
    assert thread_from_context({}) is None
    assert thread_from_context(None) is None
