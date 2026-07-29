# tests/test_semaphore.py
from hiris.app.security.semaphore import (
    DANGEROUS_DOMAINS, gate_action, GateVerdict, effective_tier, normalize_target,
    summarize_autonomy,
)


def _gate(domain, service="turn_on", entity_ids=None, tiers=None, entity_tiers=None):
    return gate_action(
        domain=domain, service=service, entity_ids=entity_ids or [],
        tiers=tiers or {}, entity_tiers=entity_tiers or {},
    )


def test_green_domain_allows():
    v = _gate("light", entity_ids=["light.kitchen"], tiers={"light": "green"})
    assert v.decision == "allow"


def test_unconfigured_domain_denies_off():
    v = _gate("light", entity_ids=["light.kitchen"])  # no tiers -> off
    assert v.decision == "deny_off"


def test_off_tier_denies():
    v = _gate("light", entity_ids=["light.x"], tiers={"light": "off"})
    assert v.decision == "deny_off"


def test_yellow_requires_confirm():
    v = _gate("switch", entity_ids=["switch.x"], tiers={"switch": "yellow"})
    assert v.decision == "confirm" and v.tier == "yellow"


def test_red_requires_confirm():
    v = _gate("switch", entity_ids=["switch.x"], tiers={"switch": "red"})
    assert v.decision == "confirm" and v.tier == "red"


def test_dangerous_domain_blocked_even_if_green():
    v = _gate("lock", entity_ids=["lock.front"], tiers={"lock": "green"})
    assert v.decision == "deny_dangerous"


def test_dangerous_entity_with_spoofed_safe_domain_blocked():
    # caller says domain=light but the entity is a lock -> still dangerous
    v = _gate("light", entity_ids=["lock.front"], tiers={"light": "green", "lock": "green"})
    assert v.decision == "deny_dangerous"


def test_entity_override_beats_domain():
    v = _gate("light", entity_ids=["light.special"],
              tiers={"light": "green"}, entity_tiers={"light.special": "off"})
    assert v.decision == "deny_off"


def test_no_entity_uses_domain_tier():
    v = _gate("light", entity_ids=[], tiers={"light": "green"})
    assert v.decision == "allow"


# ---------------------------------------------------------------------------
# summarize_autonomy: display-only tier counts for the Chatbot editor's
# Autonomia summary (review finding, SP-4 Fase B Task 4). Reuses
# DANGEROUS_DOMAINS + effective_tier -- the same authority gate_action uses --
# so this is the ONE source of truth for what the UI shows; a domain added to
# DANGEROUS_DOMAINS can never desync silently from the UI again.
# ---------------------------------------------------------------------------

def test_summarize_autonomy_dangerous_domain_never_counted_as_a_tier():
    # cover is in DANGEROUS_DOMAINS AND configured green -- gate_action would
    # still always deny_dangerous it. The summary must show that as
    # "dangerous", NOT as green (the bug this whole task fixes).
    counts = summarize_autonomy(["cover.living"], tiers={"cover": "green"}, entity_tiers={})
    assert counts == {"green": 0, "yellow": 0, "red": 0, "off": 0, "dangerous": 1}


def test_summarize_autonomy_dangerous_wins_even_with_entity_override_green():
    # Per-entity override normally beats the domain tier (effective_tier) --
    # but the denylist beats BOTH, exactly like gate_action's ordering.
    counts = summarize_autonomy(
        ["lock.front"], tiers={}, entity_tiers={"lock.front": "green"}
    )
    assert counts == {"green": 0, "yellow": 0, "red": 0, "off": 0, "dangerous": 1}


def test_summarize_autonomy_domain_glob_pattern():
    # Scope pills add domain-glob patterns (e.g. "light.*"), not just concrete
    # entity ids -- effective_tier's domain-prefix split handles both the
    # same way, no separate branch needed.
    counts = summarize_autonomy(["light.*"], tiers={"light": "yellow"}, entity_tiers={})
    assert counts == {"green": 0, "yellow": 1, "red": 0, "off": 0, "dangerous": 0}


def test_summarize_autonomy_mixed_scope():
    counts = summarize_autonomy(
        ["light.kitchen", "switch.x", "cover.living", "fan.y"],
        tiers={"light": "green", "switch": "red"},
        entity_tiers={},
    )
    assert counts == {"green": 1, "yellow": 0, "red": 1, "off": 1, "dangerous": 1}


def test_summarize_autonomy_empty_scope():
    assert summarize_autonomy([], tiers={}, entity_tiers={}) == \
        {"green": 0, "yellow": 0, "red": 0, "off": 0, "dangerous": 0}


def test_mixed_targets_worst_wins():
    v = _gate("light", entity_ids=["light.a", "light.b"],
              tiers={"light": "green"}, entity_tiers={"light.b": "red"})
    assert v.decision == "confirm" and v.tier == "red"


def test_unrecognized_tier_string_fails_closed():
    # A tier value that is neither off/green/yellow/red (e.g. corrupted config
    # or a typo) must NOT fall through to allow.
    v = _gate("light", entity_ids=["light.kitchen"], tiers={"light": "boh"})
    assert v.decision == "deny_off"


# ── review A/#5: normalize_target (shared gated-set == executed-set helper) ──


def test_normalize_target_merges_target_entity_into_data():
    n = normalize_target({}, {"entity_id": "light.kitchen"})
    assert n.data == {"entity_id": "light.kitchen"}
    assert n.entity_ids == ["light.kitchen"]
    assert n.has_group_target is False


def test_normalize_target_unions_data_and_target_entity_ids():
    n = normalize_target({"entity_id": "light.a"}, {"entity_id": "light.b"})
    assert n.data == {"entity_id": ["light.a", "light.b"]}
    assert n.entity_ids == ["light.a", "light.b"]


def test_normalize_target_dedupes_overlapping_entity_ids():
    n = normalize_target({"entity_id": "light.a"}, {"entity_id": "light.a"})
    assert n.data == {"entity_id": "light.a"}
    assert n.entity_ids == ["light.a"]


def test_normalize_target_empty_data_and_target_stays_domain_wide():
    n = normalize_target({}, {})
    assert n.data == {}
    assert n.entity_ids == []
    assert n.has_group_target is False


def test_normalize_target_group_target_detected_in_target_field():
    n = normalize_target({}, {"area_id": "cucina"})
    assert n.has_group_target is True


def test_normalize_target_group_target_detected_in_data_field():
    n = normalize_target({"device_id": "abc123"}, {})
    assert n.has_group_target is True


def test_normalize_target_does_not_mutate_caller_dicts():
    data = {"entity_id": "light.a"}
    target = {"entity_id": "light.b"}
    normalize_target(data, target)
    assert data == {"entity_id": "light.a"}
    assert target == {"entity_id": "light.b"}
