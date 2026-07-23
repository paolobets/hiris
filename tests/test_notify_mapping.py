from hiris.app.api.handlers_gateway_policy import notify_service_for_user


class _App(dict):
    pass


def test_mapped_user_gets_own_service():
    app = _App(gateway_settings={"notify_service": "notify.home",
                                 "notify_users": {"paolo": "notify.mobile_app_bet"}})
    assert notify_service_for_user(app, "paolo") == "notify.mobile_app_bet"


def test_unmapped_user_falls_back_global():
    app = _App(gateway_settings={"notify_service": "notify.home", "notify_users": {}})
    assert notify_service_for_user(app, "someone") == "notify.home"


def test_none_user_falls_back_global():
    app = _App(gateway_settings={"notify_service": "notify.home"})
    assert notify_service_for_user(app, None) == "notify.home"
