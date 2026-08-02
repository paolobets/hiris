from hiris.app.watcher.off_task import build_off_task


def test_build_off_task_for_irrigation():
    a = {"domain": "switch", "service": "turn_on", "entity_id": "switch.irr", "data": {}, "off_after_min": 5}
    t = build_off_task(a)
    assert t["trigger"] == {"type": "delay", "minutes": 5}
    assert t["actions"][0] == {"type": "call_ha_service", "domain": "switch",
                               "service": "turn_off", "data": {"entity_id": "switch.irr"}}
    assert t["one_shot"] is True


def test_build_off_task_none_when_no_off():
    assert build_off_task({"domain": "switch", "service": "turn_on", "entity_id": "switch.irr"}) is None
    assert build_off_task({"off_after_min": 0, "entity_id": "switch.irr", "service": "turn_on"}) is None


# ── I minuti arrivano dall'azione decisa dall'LLM ────────────────────────────
#
# `off_after_min` non e' un campo scritto da noi: e' parte dell'azione che il
# modello produce, e un modello scrive volentieri il numero come testo. Il
# confronto `mins <= 0` su una stringa alzava TypeError, e sul percorso che
# confeziona la proposta della Sentinella la chiamata e' fuori dal blocco
# protetto: l'eccezione risaliva fino al gestore dell'evento, che registrava un
# errore -- ne' proposta ne' notifica. Alla radice: un valore non usabile come
# minuti produce lo stesso esito di un valore non valido (None), mai
# un'eccezione.

def test_off_after_min_come_testo_numerico_vale_come_numero():
    # Il caso comune: il modello scrive "30" invece di 30. L'intento e'
    # inequivocabile e lo spegnimento ritardato non va perso.
    t = build_off_task({"domain": "switch", "service": "turn_on",
                        "entity_id": "switch.irr", "off_after_min": "30"})
    assert t["trigger"] == {"type": "delay", "minutes": 30}
    # Anche con spazi intorno, e in forma decimale (troncata come per un float).
    t2 = build_off_task({"domain": "switch", "service": "turn_on",
                         "entity_id": "switch.irr", "off_after_min": " 10 "})
    assert t2["trigger"]["minutes"] == 10
    t3 = build_off_task({"domain": "switch", "service": "turn_on",
                         "entity_id": "switch.irr", "off_after_min": 5.9})
    assert t3["trigger"]["minutes"] == 5


def test_off_after_min_non_numerico_vale_come_non_valido():
    base = {"domain": "switch", "service": "turn_on", "entity_id": "switch.irr"}
    for valore in ("presto", "30 minuti", "", "-", [30], {"min": 30}, object()):
        assert build_off_task({**base, "off_after_min": valore}) is None, valore


def test_off_after_min_non_positivo_resta_non_valido_in_ogni_forma():
    base = {"domain": "switch", "service": "turn_on", "entity_id": "switch.irr"}
    for valore in ("0", "-5", -5, 0.4, "0.4"):
        assert build_off_task({**base, "off_after_min": valore}) is None, valore


def test_off_after_min_booleano_non_e_un_numero_di_minuti():
    # True e' un int per Python, ma "spegni fra 1 minuto" non e' cio' che il
    # modello intendeva scrivendo un booleano.
    base = {"domain": "switch", "service": "turn_on", "entity_id": "switch.irr"}
    assert build_off_task({**base, "off_after_min": True}) is None
    assert build_off_task({**base, "off_after_min": False}) is None


def test_la_proposta_della_sentinella_sopravvive_ai_minuti_testuali():
    """Il chiamante nuovo: la chiamata a build_off_task e' fuori dal try, quindi
    un TypeError qui costava proposta E notifica."""
    from hiris.app.watcher.sentinel_proposal import build_sentinel_script_proposal

    record = build_sentinel_script_proposal(
        {"domain": "switch", "service": "turn_on",
         "entity_id": "switch.irr", "off_after_min": "30"},
        signal_kind="irrigazione", entity_id="switch.irr",
        message="Valvola aperta", routing_reason="test",
    )
    assert record is not None
    sequenza = record["config"]["ha_config"]["sequence"]
    assert {"delay": {"minutes": 30}} in sequenza
    assert sequenza[-1]["service"] == "switch.turn_off"
