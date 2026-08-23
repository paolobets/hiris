"""Le forme: si compongono dai PARAMETRI, mai inoltrando lo YAML del modello."""
import pytest

from hiris.app.azione.costruzione.forme import (
    componi_automazione, componi_scena, componi_script, nuovo_id,
    parti_da_validare, slug_libero)


def test_l_automazione_porta_lo_schema_moderno_al_plurale():
    """Su HA 2026.8 le chiavi sono `triggers`/`conditions`/`actions`. Il singolare
    e' la forma vecchia che il modello ha letto di piu' -- e che qui non passa."""
    corpo = componi_automazione(
        id_="1771346155970", alias="Tapparelle all'alba",
        descrizione="Apre le tapparelle quando sorge il sole",
        innesco=[{"trigger": "sun", "event": "sunrise"}],
        condizioni=[],
        azioni=[{"action": "cover.open_cover", "target": {"entity_id": "cover.salotto"}}])
    assert corpo["id"] == "1771346155970"
    assert corpo["triggers"][0]["trigger"] == "sun"
    assert corpo["actions"][0]["action"] == "cover.open_cover"
    assert "trigger" not in corpo and "action" not in corpo
    assert corpo["mode"] == "single"


def test_la_descrizione_porta_l_intenzione():
    """Fondamenta 1: chi apre l'automazione nell'editor fra sei mesi deve capirla
    senza HIRIS."""
    corpo = componi_automazione(
        id_="1", alias="X", descrizione="Apre le tapparelle quando sorge il sole",
        innesco=[{"trigger": "sun"}], condizioni=[], azioni=[{"action": "a.b"}])
    assert "tapparelle" in corpo["description"]


def test_lo_script_e_una_sequenza_e_puo_avere_campi():
    corpo = componi_script(
        alias="Buonanotte", descrizione="Spegne tutto tranne il corridoio",
        passi=[{"action": "light.turn_off", "target": {"entity_id": "light.salotto"}}],
        campi={"stanza": {"selector": {"text": None}}})
    assert corpo["sequence"][0]["action"] == "light.turn_off"
    assert corpo["fields"]["stanza"]["selector"] == {"text": None}
    assert "id" not in corpo


def test_lo_script_senza_campi_non_porta_la_chiave_vuota():
    corpo = componi_script(alias="X", descrizione="d", passi=[{"delay": 1}])
    assert "fields" not in corpo


def test_la_scena_ha_nome_ed_entita():
    corpo = componi_scena(id_="1771", alias="Serata film",
                          stati=[{"entity_id": "light.salotto", "state": "on",
                                  "brightness": 40}])
    assert corpo["name"] == "Serata film"
    assert corpo["entities"]["light.salotto"]["state"] == "on"
    assert corpo["entities"]["light.salotto"]["brightness"] == 40


def test_un_id_nuovo_non_collide_mai_con_quelli_gia_in_casa():
    esistenti = {"1000", "1001", "1002"}
    ident = nuovo_id(esistenti, seme=1000)
    assert ident not in esistenti


def test_uno_slug_occupato_diventa_un_altro_slug():
    assert slug_libero("Buonanotte", {"buonanotte"}) == "buonanotte_2"
    assert slug_libero("Buona notte!", set()) == "buona_notte"


def test_uno_slug_che_si_svuota_non_diventa_stringa_vuota():
    """Un alias fatto solo di punteggiatura non puo' produrre una chiave vuota:
    finirebbe in un URL come `/api/config/script/config/` -- un'altra rotta."""
    assert slug_libero("!!!", set()) != ""


def test_da_validare_manda_i_tre_pezzi_dell_automazione():
    corpo = componi_automazione(id_="1", alias="X", descrizione="d",
                                innesco=[{"trigger": "state"}], condizioni=[{"condition": "sun"}],
                                azioni=[{"action": "a.b"}])
    parti = parti_da_validare("automation", corpo)
    assert set(parti) == {"triggers", "conditions", "actions"}


def test_da_validare_di_uno_script_manda_solo_le_azioni():
    corpo = componi_script(alias="X", descrizione="d", passi=[{"action": "a.b"}])
    assert parti_da_validare("script", corpo) == {"actions": [{"action": "a.b"}]}


def test_da_validare_di_una_scena_non_manda_niente():
    """Una scena non ha ne' inneschi ne' azioni: `validate_config` non la copre,
    e chiedergli di validare liste vuote tornerebbe «valido» su nulla."""
    corpo = componi_scena(id_="1", alias="X", stati=[{"entity_id": "light.x", "state": "on"}])
    assert parti_da_validare("scene", corpo) == {}
