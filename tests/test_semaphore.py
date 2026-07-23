# tests/test_semaphore.py
from hiris.app.security.semaphore import (
    DANGEROUS_DOMAINS, gate_action, GateVerdict, effective_tier,
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
