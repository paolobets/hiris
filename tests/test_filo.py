from hiris.app.filo import Filo, chiave_soggetto, da_contesto, filo_da, in_contesto, ingresso_da


def test_la_chiave_e_specie_e_id_mai_il_nome():
    s = {"specie": "persona", "id": "abc123", "nome": "Paolo", "utente": "paolo"}
    assert chiave_soggetto(s) == "persona:abc123"


def test_persona_anonima_ha_una_chiave_dichiarata():
    assert chiave_soggetto({"specie": "persona", "id": None}) == "persona:-"


def test_nessun_soggetto_e_nessuno():
    assert chiave_soggetto(None) == "nessuno:-"


def test_ingresso_dalla_via():
    assert ingresso_da("ingress") == "pannello"
    assert ingresso_da("canale") == "firma"
    assert ingresso_da("no_token") == "sviluppo"
    assert ingresso_da("turno") == "interno"
    assert ingresso_da(None) == "interno"


def test_due_persone_due_fili_stessa_persona_due_ingressi_due_fili():
    paolo = {"specie": "persona", "id": "p"}
    marta = {"specie": "persona", "id": "m"}
    assert filo_da(paolo, "ingress") != filo_da(marta, "ingress")
    assert filo_da(paolo, "ingress") != filo_da(paolo, "no_token")
    assert filo_da(paolo, "ingress") == Filo("persona:p", "pannello")


def test_il_filo_attraversa_il_contesto_del_job():
    f = Filo("persona:p", "pannello")
    assert da_contesto(in_contesto(f)) == f
    assert da_contesto({}) is None
    assert da_contesto(None) is None
