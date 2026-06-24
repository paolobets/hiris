from hiris.app.brain.identity import resolve_owner


class _Req:
    def __init__(self, headers):
        self.headers = headers


def test_resolve_owner_from_header():
    req = _Req({"X-Remote-User-Id": "abc123"})
    assert resolve_owner(req) == "abc123"


def test_resolve_owner_defaults_home():
    assert resolve_owner(_Req({})) == "home"
