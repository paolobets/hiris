from hiris.app.model_activation import derive_active_providers, reconcile_chain


def _creds(**kw):
    base = {"claude": False, "openai": False, "openrouter": False,
            "ollama": False, "subscription": False}
    base.update(kw)
    return base


def test_legacy_install_derives_from_credentials():
    # tutti i toggle al default false => migrazione: attivo = credenziale presente
    cfg = {"provider_subscription": False, "provider_claude": False,
           "provider_openai": False, "provider_openrouter": False,
           "provider_ollama": False}
    creds = _creds(claude=True, ollama=True)
    active = derive_active_providers(cfg, creds)
    assert active == {"subscription": False, "claude": True, "openai": False,
                      "openrouter": False, "ollama": True}


def test_explicit_toggles_win_over_credentials():
    # almeno un toggle esplicito => NON si migra; conta (toggle AND credenziale)
    cfg = {"provider_subscription": False, "provider_claude": True,
           "provider_openai": True, "provider_openrouter": False,
           "provider_ollama": False}
    creds = _creds(claude=True, openai=False, ollama=True)  # openai toggle ON ma senza key
    active = derive_active_providers(cfg, creds)
    assert active["claude"] is True          # toggle ON + key
    assert active["openai"] is False         # toggle ON ma manca key => inattivo
    assert active["ollama"] is False         # key c'è ma toggle OFF => escluso


def test_legacy_subscription_flag_migrates():
    cfg = {"provider_subscription": False, "provider_claude": False,
           "provider_openai": False, "provider_openrouter": False,
           "provider_ollama": False, "chat_via_subscription": True}
    creds = _creds(subscription=True)
    active = derive_active_providers(cfg, creds)
    assert active["subscription"] is True


_STRATEGY = ["claude", "openrouter", "openai", "ollama"]  # "balanced" order


def test_reconcile_chain_appends_newly_active_provider_missing_from_manual():
    # Fail-open regression (SP-2 final review): chain_order=["ollama"] was
    # persisted when only Ollama was active; Claude becomes active later
    # without the user re-saving #/models. The reconciled chain must
    # include BOTH -- Ollama first (honors the saved order), Claude appended
    # (never silently dropped from failover / from the egress classification).
    active = {"ollama": True, "claude": True, "openai": False, "openrouter": False}
    chain = reconcile_chain(_STRATEGY, ["ollama"], active)
    assert chain == ["ollama", "claude"]


def test_reconcile_chain_no_manual_uses_strategy_active_order():
    active = {"claude": True, "openrouter": False, "openai": True, "ollama": True}
    chain = reconcile_chain(_STRATEGY, None, active)
    assert chain == ["claude", "openai", "ollama"]

    # empty list treated same as absent
    chain_empty = reconcile_chain(_STRATEGY, [], active)
    assert chain_empty == ["claude", "openai", "ollama"]


def test_reconcile_chain_manual_drops_inactive_provider():
    # manual lists a provider that is no longer active -- it must be dropped,
    # not just left in place.
    active = {"claude": False, "openrouter": True, "openai": False, "ollama": True}
    chain = reconcile_chain(_STRATEGY, ["claude", "ollama"], active)
    # "claude" dropped (inactive); "ollama" kept from manual;
    # "openrouter" appended afterwards (active, missing from manual).
    assert chain == ["ollama", "openrouter"]


def test_reconcile_chain_all_invalid_manual_falls_back_to_strategy_active():
    active = {"claude": True, "openrouter": False, "openai": False, "ollama": False}
    # manual only references inactive/unknown providers -> filters to [] ->
    # fallback appends strategy-active providers (same as the empty-result
    # guard for the pre-fix inline logic).
    chain = reconcile_chain(_STRATEGY, ["openai", "openrouter"], active)
    assert chain == ["claude"]
