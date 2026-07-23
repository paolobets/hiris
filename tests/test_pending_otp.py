import pytest
from hiris.app.api import handlers_gateway_pending as P


def test_create_pending_with_otp_and_user(tmp_path):
    e = P.create_pending(str(tmp_path), tool="call_ha_service",
                         inputs={"domain": "lock", "service": "unlock",
                                 "data": {"entity_id": "lock.front"}},
                         tier="red", origin="chat", label="lock.unlock",
                         user="paolo", with_otp=True)
    assert e["user"] == "paolo"
    assert isinstance(e["otp"], str) and e["otp"].isdigit() and len(e["otp"]) == 6


def test_verify_otp_success_consumes(tmp_path):
    e = P.create_pending(str(tmp_path), tool="call_ha_service", inputs={},
                         tier="yellow", origin="chat", label="x",
                         user="paolo", with_otp=True)
    got = P.verify_otp(str(tmp_path), "paolo", e["otp"])
    assert got is not None and got["id"] == e["id"]
    # single-use: second attempt fails
    assert P.verify_otp(str(tmp_path), "paolo", e["otp"]) is None


def test_verify_otp_wrong_user_denied(tmp_path):
    e = P.create_pending(str(tmp_path), tool="call_ha_service", inputs={},
                         tier="yellow", origin="chat", label="x",
                         user="paolo", with_otp=True)
    assert P.verify_otp(str(tmp_path), "someone_else", e["otp"]) is None


def test_verify_otp_lockout_after_3(tmp_path):
    e = P.create_pending(str(tmp_path), tool="call_ha_service", inputs={},
                         tier="yellow", origin="chat", label="x",
                         user="paolo", with_otp=True)
    for _ in range(3):
        assert P.verify_otp(str(tmp_path), "paolo", "000000") is None
    # pending invalidated: even the correct code now fails
    assert P.verify_otp(str(tmp_path), "paolo", e["otp"]) is None
