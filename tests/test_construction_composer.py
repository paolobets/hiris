"""Le forme: si compongono dai PARAMETRI, mai inoltrando lo YAML del modello."""
from hiris.app.action.construction.composer import (
    available_slug,
    compose_automation,
    compose_scene,
    compose_script,
    new_id,
    parts_to_validate,
    state_problems,
)


def test_l_automazione_porta_lo_schema_moderno_al_plurale():
    """Su HA 2026.8 le chiavi sono `triggers`/`conditions`/`actions`. Il singolare
    e' la forma vecchia che il modello ha letto di piu' -- e che qui non passa."""
    corpo = compose_automation(
        id_="1771346155970", alias="Tapparelle all'alba",
        descrizione="Apre le tapparelle quando sorge il sole",
        innesco=[{"trigger": "sun", "event": "sunrise"}],
        conditions=[],
        actions=[{"action": "cover.open_cover", "target": {"entity_id": "cover.salotto"}}])
    assert corpo["id"] == "1771346155970"
    assert corpo["triggers"][0]["trigger"] == "sun"
    assert corpo["actions"][0]["action"] == "cover.open_cover"
    assert "trigger" not in corpo and "action" not in corpo
    assert corpo["mode"] == "single"


def test_la_descrizione_porta_l_intenzione():
    """Fondamenta 1: chi apre l'automazione nell'editor fra sei mesi deve capirla
    senza HIRIS."""
    corpo = compose_automation(
        id_="1", alias="X", descrizione="Apre le tapparelle quando sorge il sole",
        innesco=[{"trigger": "sun"}], conditions=[], actions=[{"action": "a.b"}])
    assert "tapparelle" in corpo["description"]


def test_lo_script_e_una_sequenza_e_puo_avere_campi():
    corpo = compose_script(
        alias="Buonanotte", descrizione="Spegne tutto tranne il corridoio",
        passi=[{"action": "light.turn_off", "target": {"entity_id": "light.salotto"}}],
        fields={"stanza": {"selector": {"text": None}}})
    assert corpo["sequence"][0]["action"] == "light.turn_off"
    assert corpo["fields"]["stanza"]["selector"] == {"text": None}
    assert "id" not in corpo


def test_lo_script_senza_campi_non_porta_la_chiave_vuota():
    corpo = compose_script(alias="X", descrizione="d", passi=[{"delay": 1}])
    assert "fields" not in corpo


def test_la_scena_ha_nome_ed_entita():
    corpo = compose_scene(id_="1771", alias="Serata film",
                          states=[{"entity_id": "light.salotto", "state": "on",
                                  "brightness": 40}])
    assert corpo["name"] == "Serata film"
    assert corpo["entities"]["light.salotto"]["state"] == "on"
    assert corpo["entities"]["light.salotto"]["brightness"] == 40


def test_un_id_nuovo_non_collide_mai_con_quelli_gia_in_casa():
    existing = {"1000", "1001", "1002"}
    ident = new_id(existing, seme=1000)
    assert ident not in existing


def test_uno_slug_occupato_diventa_un_altro_slug():
    assert available_slug("Buonanotte", {"buonanotte"}) == "buonanotte_2"
    assert available_slug("Buona notte!", set()) == "buona_notte"


def test_uno_slug_che_si_svuota_non_diventa_stringa_vuota():
    """Un alias fatto solo di punteggiatura non puo' produrre una chiave vuota:
    finirebbe in un URL come `/api/config/script/config/` -- un'altra rotta."""
    assert available_slug("!!!", set()) != ""


def test_da_validare_manda_i_tre_pezzi_dell_automazione():
    corpo = compose_automation(id_="1", alias="X", descrizione="d",
                                innesco=[{"trigger": "state"}], conditions=[{"condition": "sun"}],
                                actions=[{"action": "a.b"}])
    parti = parts_to_validate("automation", corpo)
    assert set(parti) == {"triggers", "conditions", "actions"}


def test_da_validare_di_uno_script_manda_solo_le_azioni():
    corpo = compose_script(alias="X", descrizione="d", passi=[{"action": "a.b"}])
    assert parts_to_validate("script", corpo) == {"actions": [{"action": "a.b"}]}


def test_da_validare_di_una_scena_non_manda_niente():
    """Una scena non ha ne' inneschi ne' azioni: `validate_config` non la copre,
    e chiedergli di validare liste vuote tornerebbe «valido» su nulla."""
    corpo = compose_scene(id_="1", alias="X", states=[{"entity_id": "light.x", "state": "on"}])
    assert parts_to_validate("scene", corpo) == {}


def test_lo_slug_traslittera_gli_accenti_e():
    """Un alias con accenti non perde lettere: «perché» → «perche», non «perch»."""
    assert "perche" in available_slug("Buonanotte perché", set())


def test_lo_slug_traslittera_gli_accenti_a():
    """Un alias con accenti non perde lettere: «città» → «citta», non «citt»."""
    assert "citta" in available_slug("Luci città", set())


def test_problemi_stati_lista_vuota_ok():
    """Una lista vuota di stati non ha problemi."""
    assert state_problems([]) == []


def test_problemi_stati_due_voci_valide_ok():
    """Correzione scritta nel ledger dal Task 4 e mai applicata (ondata
    finale, punto 5): una lista VUOTA non entra nemmeno nel ciclo di
    `state_problems`, quindi un difetto futuro che segnalasse come
    problematica ogni voce valida non verrebbe preso da nessun test del file
    -- le scene sono l'unico dominio senza validazione a valle (`parti_da_
    validare` restituisce {} per loro), il posto peggiore per avere un test
    che non puo' fallire."""
    assert state_problems([{"entity_id": "light.cucina", "state": "on"},
                           {"entity_id": "light.salotto", "state": "off"}]) == []


def test_problemi_stati_voce_non_dizionario():
    """Una voce che non è un dizionario è un problema."""
    problemi = state_problems(["not_a_dict", None, 123])
    assert len(problemi) > 0


def test_problemi_stati_voce_senza_entity_id():
    """Una voce senza `entity_id` è un problema."""
    problemi = state_problems([{"state": "on"}])
    assert len(problemi) > 0


def test_problemi_stati_entity_id_duplicato():
    """Due voci con lo stesso `entity_id` è un problema, e il nome deve comparire."""
    problemi = state_problems([
        {"entity_id": "light.salotto", "state": "on"},
        {"entity_id": "light.salotto", "state": "off"}
    ])
    assert len(problemi) > 0
    assert "light.salotto" in " ".join(problemi)
