# tests/test_semaphore.py
from hiris.app.security.semaphore import (
    DANGEROUS_DOMAINS, gate_action, GateVerdict, effective_tier, normalize_target,
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
