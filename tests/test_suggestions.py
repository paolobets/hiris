import math

import pytest
from hiris.app.brain.suggestions import (SuggestionStore, validate_coverage, apply_suggestions,
                                         undo, reconcile_proposal_outcome)
from hiris.app.watcher.policy import load_policy

@pytest.fixture
def store(tmp_path):
    s = SuggestionStore(str(tmp_path / "s.db")); yield s; s.close()

def test_validate_coverage(tmp_path):
    inv = {"sensor.freezer"}
    ok = {"kind":"coverage","config":{"detector":"fridge_temp","entity":"sensor.freezer"}}
    assert validate_coverage(ok, inv, {"detectors":{}}) is True
    assert validate_coverage({"kind":"coverage","config":{"detector":"fridge_temp","entity":"sensor.ghost"}}, inv, {"detectors":{}}) is False
    assert validate_coverage({"kind":"coverage","config":{"detector":"bogus","entity":"sensor.freezer"}}, inv, {"detectors":{}}) is False

def test_apply_and_undo_coverage(tmp_path, store):
    dd = str(tmp_path)
    suggs = [{"kind":"coverage","title":"Freezer","rationale":"r","config":{"detector":"fridge_temp","entity":"sensor.freezer","max_temp_c":8}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.freezer"},
                                current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert len(applied) == 1
    pol = load_policy(dd)
    assert "sensor.freezer" in pol["detectors"]["fridge_temp"]["entities"]
    assert pol["detectors"]["fridge_temp"]["enabled"] is True
    sid = store.list()[0]["id"]
    assert undo(store, dd, sid) is True
    pol2 = load_policy(dd)
    assert "sensor.freezer" not in pol2["detectors"]["fridge_temp"].get("entities", [])

def test_hostile_config_cannot_wipe_entities_or_disable(tmp_path, store):
    """A brain suggestion is untrusted LLM output. A crafted config that tries
    to smuggle "entities": [] / "enabled": False through params must NOT wipe
    a pre-existing USER entity nor disable the detector -- it may only add the
    brain's own entity alongside what the user already configured."""
    dd = str(tmp_path)
    # Pre-existing USER-configured entity + enabled detector.
    from hiris.app.watcher.policy import save_policy
    save_policy(dd, {"detectors": {"fridge_temp": {"enabled": True, "entities": ["sensor.user_freezer"]}}})

    suggs = [{"kind": "coverage", "title": "Freezer2", "rationale": "r",
              "config": {"detector": "fridge_temp", "entity": "sensor.brain_freezer",
                         "entities": [], "enabled": False}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.brain_freezer"},
                                current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert len(applied) == 1
    pol = load_policy(dd)
    det = pol["detectors"]["fridge_temp"]
    assert det["enabled"] is True
    assert "sensor.user_freezer" in det["entities"]
    assert "sensor.brain_freezer" in det["entities"]

def test_non_numeric_threshold_rejects_whole_suggestion(tmp_path, store):
    """Review C/#6: max_watt: "abc" (non-numeric, clearly invalid) must NOT
    be applied to the shared detector config at all -- reject the whole
    suggestion rather than let a string reach the detector."""
    dd = str(tmp_path)
    suggs = [{"kind": "coverage", "title": "Plug", "rationale": "r",
              "config": {"detector": "power", "entity": "sensor.plug", "max_watt": "abc"}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.plug"},
                                current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert applied == []
    pol = load_policy(dd)
    assert pol["detectors"]["power"]["enabled"] is False
    assert "sensor.plug" not in pol["detectors"]["power"]["entities"]
    assert pol["detectors"]["power"]["max_watt"] == 3000


def test_nan_threshold_rejects_whole_suggestion(tmp_path, store):
    """NaN must be treated as clearly-invalid (not a "very high" number) --
    same reject path as a non-numeric string."""
    dd = str(tmp_path)
    suggs = [{"kind": "coverage", "title": "Plug", "rationale": "r",
              "config": {"detector": "power", "entity": "sensor.plug", "max_watt": math.nan}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.plug"},
                                current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert applied == []
    assert load_policy(dd)["detectors"]["power"]["enabled"] is False


def test_out_of_range_threshold_is_clamped_and_applied(tmp_path, store):
    """Review C/#6: an in-type but wildly out-of-range value (e.g.
    max_watt: 999999999) is clamped to the sane bound and the suggestion IS
    still applied -- the detector must not be neutered by an absurd value,
    but a legitimate coverage suggestion should still go through."""
    dd = str(tmp_path)
    suggs = [{"kind": "coverage", "title": "Plug", "rationale": "r",
              "config": {"detector": "power", "entity": "sensor.plug", "max_watt": 999999999}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.plug"},
                                current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert len(applied) == 1
    pol = load_policy(dd)
    assert pol["detectors"]["power"]["enabled"] is True
    assert "sensor.plug" in pol["detectors"]["power"]["entities"]
    assert pol["detectors"]["power"]["max_watt"] == 20000  # clamped to the absolute upper bound


def test_valid_threshold_still_applies_unchanged(tmp_path, store):
    """Legit configs (valid types/ranges) still save and apply unchanged."""
    dd = str(tmp_path)
    suggs = [{"kind": "coverage", "title": "Plug", "rationale": "r",
              "config": {"detector": "power", "entity": "sensor.plug", "max_watt": 2500}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.plug"},
                                current_config=load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert len(applied) == 1
    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 2500


_MANAGEMENT_AUTOMATION = {"alias": "Auto-off bagno",
                          "trigger": [{"platform": "state", "entity_id": "light.bagno"}],
                          "action": [{"service": "light.turn_off",
                                      "target": {"entity_id": "light.bagno"}}]}


def test_cap_and_management(tmp_path, store):
    """Un suggerimento 'management' che porta davvero una config di automazione
    viene inoltrato a create_proposal (la proposta ha_automation e' applicabile)."""
    proposed = []
    suggs = [{"kind": "management", "title": "Auto-off bagno", "rationale": "r",
              "config": _MANAGEMENT_AUTOMATION}]
    apply_suggestions(suggs, data_dir=str(tmp_path), store=store, inventory_ids=set(),
                      current_config=load_policy(str(tmp_path)),
                      create_proposal=lambda c, _sid: proposed.append(c), cap=5)
    assert proposed == [_MANAGEMENT_AUTOMATION] and store.list()[0]["status"] == "proposed"


def test_management_without_automation_config_is_recorded_but_not_proposed(tmp_path, store):
    """Consolidamento 1.2: un config che non e' un'automazione non puo' diventare
    una proposta ha_automation (l'apply la scriverebbe in HA senza trigger ne'
    azioni). Resta registrato fra i suggerimenti, che sono la sua superficie."""
    proposed = []
    suggs = [{"kind": "management", "title": "Idea", "rationale": "r", "config": {"x": 1}}]
    apply_suggestions(suggs, data_dir=str(tmp_path), store=store, inventory_ids=set(),
                      current_config=load_policy(str(tmp_path)),
                      create_proposal=lambda c, _sid: proposed.append(c), cap=5)
    assert proposed == []
    assert store.list()[0]["config"] == {"x": 1}


def test_management_proposal_callback_receives_the_row_id(tmp_path, store):
    """I-1 (TDD, rosso prima di questa fix): create_proposal e' fire-and-
    forget lato chiamante reale (server.py._mk_proposal lancia un task e non
    puo' attenderlo da apply_suggestions, che e' sincrona) -- l'unico modo
    perche' il chiamante possa poi correggere lo stato della riga quando il
    task finisce e' conoscerne l'id FIN DA SUBITO. Prima di questa fix
    create_proposal riceveva solo il config."""
    received = {}
    suggs = [{"kind": "management", "title": "T", "rationale": "R", "config": _MANAGEMENT_AUTOMATION}]
    apply_suggestions(suggs, data_dir=str(tmp_path), store=store, inventory_ids=set(),
                      current_config=load_policy(str(tmp_path)),
                      create_proposal=lambda c, sid: received.update(config=c, suggestion_id=sid),
                      cap=5)
    row = store.list()[0]
    assert row["status"] == "proposed"
    assert received["suggestion_id"] == row["id"]
    assert received["config"] == _MANAGEMENT_AUTOMATION


def test_reconcile_proposal_outcome_downgrades_status_on_failed_result(store):
    """I-1 (TDD, rosso prima di questa fix -- riprodotto: riga 'proposed',
    zero proposte salvate). create_automation_proposal segnala il fallimento
    come VALORE DI RITORNO ({'error': ...}), non un'eccezione: se il task
    fire-and-forget che la esegue completa con quell'esito, la riga
    'management' -- scritta ottimisticamente 'proposed' da apply_suggestions
    prima di conoscere il vero esito -- deve tornare a dire il vero."""
    sid = store.record("management", "T", "R", _MANAGEMENT_AUTOMATION, "proposed", None)
    reconcile_proposal_outcome(store, sid, {"error": "ProposalStore not available"})
    assert store.get(sid)["status"] == "recorded"


def test_reconcile_proposal_outcome_downgrades_status_on_exception_result(store):
    """Stesso caso ma con il task fire-and-forget che ha sollevato (il
    chiamante lo traduce in {'error': str(exc)} prima di richiamare questa
    funzione, vedi server.py._mk_proposal)."""
    sid = store.record("management", "T", "R", _MANAGEMENT_AUTOMATION, "proposed", None)
    reconcile_proposal_outcome(store, sid, {"error": "boom"})
    assert store.get(sid)["status"] == "recorded"


def test_reconcile_proposal_outcome_leaves_status_when_proposal_id_present(store):
    """Esito vero positivo: la proposta esiste davvero (proposal_id valorizzato)
    -- 'proposed' era corretto e la riga non va toccata."""
    sid = store.record("management", "T", "R", _MANAGEMENT_AUTOMATION, "proposed", None)
    reconcile_proposal_outcome(store, sid, {"proposal_id": "abc123", "status": "pending"})
    assert store.get(sid)["status"] == "proposed"


def test_undo_routes_brain_tune_source_ref_to_value_restore(tmp_path, store):
    """Slice 6 Task 5B: a suggestion row whose delta.source_ref starts with
    "brain-tune:" is a detector-level tuning (cognitive_loop.
    auto_tune_detectors), not an entity-coverage row -- its delta has no
    "entity" key at all. undo() must route it to remove_brain_tuning
    (restores the detector's pre-tuning value), not remove_brain_detector."""
    from hiris.app.watcher.policy import apply_brain_tuning, save_policy

    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {"enabled": True,
                                              "entities": ["sensor.plug"],
                                              "max_watt": 3000}}})
    apply_brain_tuning(dd, "power", {"max_watt": 1600})
    assert load_policy(dd)["detectors"]["power"]["max_watt"] == 1600

    delta = {"detector": "power", "source_ref": "brain-tune:power"}
    sid = store.record(kind="coverage", title="Taratura power", rationale="r",
                        config={"detector": "power", "max_watt": 1600},
                        status="applied", delta=delta)

    assert undo(store, dd, sid) is True
    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 3000
    assert "sensor.plug" in pol["detectors"]["power"]["entities"]
    assert store.get(sid)["status"] == "dismissed"


def test_undo_coverage_restores_shared_param_it_overwrote(tmp_path, store):
    """Review C/#3: a coverage suggestion whose params overwrite a SHARED
    detector-level value (e.g. power.max_watt, applied to ALL entities on
    that detector, not just the newly-added one) must have that value
    restored on undo -- not just have its entity removed -- mirroring
    apply_brain_tuning/remove_brain_tuning's snapshot/restore discipline."""
    from hiris.app.watcher.policy import save_policy, load_policy as _load_policy

    dd = str(tmp_path)
    # Pre-existing shared detector config (as if the user, or an earlier
    # brain action, set max_watt=3000 before this coverage suggestion).
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": [],
                                              "max_watt": 3000}}})

    suggs = [{"kind": "coverage", "title": "Plug", "rationale": "r",
              "config": {"detector": "power", "entity": "sensor.plug", "max_watt": 5000}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.plug"},
                                current_config=_load_policy(dd), create_proposal=lambda c, _sid: None, cap=5)
    assert len(applied) == 1
    pol = _load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 5000
    assert "sensor.plug" in pol["detectors"]["power"]["entities"]

    sid = store.list()[0]["id"]
    assert undo(store, dd, sid) is True

    pol2 = _load_policy(dd)
    assert "sensor.plug" not in pol2["detectors"]["power"]["entities"]
    # The shared param must be restored to its pre-apply value, not left at
    # the suggestion's overwritten value.
    assert pol2["detectors"]["power"]["max_watt"] == 3000


def test_undo_no_op_when_entity_not_in_registry(tmp_path, store):
    """Regression test: undo() should only mark dismissed when removal actually
    succeeds. If the entity is not in the brain sidecar registry (e.g., registry/policy
    desync or double-undo), undo() returns False and status stays 'applied'."""
    dd = str(tmp_path)
    # Manually record an "applied" suggestion with a delta pointing to a detector/entity
    # that was NEVER actually registered via apply_brain_detector.
    delta = {"detector": "fridge_temp", "entity": "sensor.ghost"}
    sid = store.record(kind="coverage", title="Ghost Sensor", rationale="r",
                       config={"detector": "fridge_temp", "entity": "sensor.ghost"},
                       status="applied", delta=delta)
    # Attempt undo: should return False (entity not in registry) and NOT mark dismissed.
    result = undo(store, dd, sid)
    assert result is False
    row = store.get(sid)
    assert row["status"] == "applied", "Status should remain 'applied' when undo fails"
