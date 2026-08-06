from hiris.app.casa.comportamento import componi

_AUTOMAZIONI = [
    {"id": "1700", "alias": "Sveglia", "trigger": [{"platform": "time", "at": "07:00"}]},
    {"id": "1701", "alias": "Mai caricata", "trigger": []},
]
_SCRIPT = {
    "saluta": {"alias": "Saluta", "sequence": [{"service": "tts.speak"}]},
}
_STATI = [
    {"entity_id": "automation.sveglia", "state": "on",
     "attributes": {"id": "1700", "friendly_name": "Sveglia"}},
    {"entity_id": "automation.a_mano", "state": "on",
     "attributes": {"id": "9999", "friendly_name": "Scritta a mano"}},
    {"entity_id": "script.saluta", "state": "off",
     "attributes": {"friendly_name": "Saluta"}},
    {"entity_id": "light.cucina", "state": "on", "attributes": {}},
]


def _per_id(voci):
    return {v["id"]: v for v in voci}


def test_un_automazione_nel_file_e_nello_stato_ha_il_corpo():
    voci = _per_id(componi(_AUTOMAZIONI, _SCRIPT, _STATI))
    assert voci["automation.sveglia"]["origine"] == "file"
    assert voci["automation.sveglia"]["corpo"]["trigger"][0]["at"] == "07:00"


def test_un_automazione_scritta_a_mano_si_conosce_di_nome_e_si_dichiara():
    """Non sta in automations.yaml: puo' vivere nei pacchetti o in cartelle
    incluse. HIRIS deve sapere che esiste e sapere di non conoscerne il corpo."""
    voci = _per_id(componi(_AUTOMAZIONI, _SCRIPT, _STATI))
    assert voci["automation.a_mano"]["origine"] == "solo_stato"
    assert voci["automation.a_mano"]["corpo"] is None
    assert voci["automation.a_mano"]["nome"] == "Scritta a mano"


def test_una_voce_solo_nel_file_e_scritta_ma_non_caricata():
    voci = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    sola = [v for v in voci if v["origine"] == "solo_file"]
    assert [v["nome"] for v in sola] == ["Mai caricata"]


def test_lo_script_si_aggancia_per_object_id():
    """Per gli script la chiave del file E' l'object_id dell'entita':
    script.saluta <-> chiave `saluta`, nessuna ricerca."""
    voci = _per_id(componi(_AUTOMAZIONI, _SCRIPT, _STATI))
    assert voci["script.saluta"]["corpo"]["sequence"][0]["service"] == "tts.speak"


def test_le_entita_che_non_sono_comportamento_restano_fuori():
    voci = _per_id(componi(_AUTOMAZIONI, _SCRIPT, _STATI))
    assert "light.cucina" not in voci


def test_un_file_assente_non_e_un_file_vuoto():
    """`None` significa «non ho letto il file»: tutte le automazioni vive
    diventano solo_stato, non spariscono."""
    voci = _per_id(componi(None, None, _STATI))
    assert voci["automation.sveglia"]["origine"] == "solo_stato"
    assert voci["automation.sveglia"]["corpo"] is None
    assert len(voci) == 3
