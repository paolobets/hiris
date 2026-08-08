# tests/test_semaphore.py
#
# Review finale fetta E2, I-1 (cascata verificata): `gate_action`,
# `normalize_target`/`NormalizedTarget` e `GateVerdict` sono uscite da
# security/semaphore.py -- `task_engine.py` era il loro ultimo chiamante di
# produzione (il dispatcher che le chiamava anche lui era gia' uscito nel
# Task 7), e I-1 ha tolto il ramo `call_ha_service` da `_run_action`: nessuna
# superficie esegue piu' un `call_ha_service` da gate-are. I test che le
# esercitavano (gate_action: green/off/yellow/red/dangerous/entity-override/
# mixed-targets/unrecognized-tier; normalize_target: merge/union/dedup/
# group-target/no-mutation) sono usciti con il loro soggetto.
#
# summarize_autonomy sopravvive: serve ancora il riepilogo Autonomia
# dell'editor Chatbot (handlers_gateway_policy.py::handle_autonomy_summary).
from hiris.app.security.semaphore import summarize_autonomy


# ---------------------------------------------------------------------------
# summarize_autonomy: display-only tier counts for the Chatbot editor's
# Autonomia summary (review finding, SP-4 Fase B Task 4). Reuses
# DANGEROUS_DOMAINS + effective_tier so this is the ONE source of truth for
# what the UI shows; a domain added to DANGEROUS_DOMAINS can never desync
# silently from the UI again.
# ---------------------------------------------------------------------------

def test_summarize_autonomy_dangerous_domain_never_counted_as_a_tier():
    # cover is in DANGEROUS_DOMAINS AND configured green -- the Sentinel's
    # own gate would still always deny it. The summary must show that as
    # "dangerous", NOT as green (the bug this whole task fixes).
    counts = summarize_autonomy(["cover.living"], tiers={"cover": "green"}, entity_tiers={})
    assert counts == {"green": 0, "yellow": 0, "red": 0, "off": 0, "dangerous": 1}


def test_summarize_autonomy_dangerous_wins_even_with_entity_override_green():
    # Per-entity override normally beats the domain tier (effective_tier) --
    # but the denylist beats BOTH.
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
