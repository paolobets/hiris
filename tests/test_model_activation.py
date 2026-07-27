from hiris.app.model_activation import derive_active_providers


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
