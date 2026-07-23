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
    # deterministic wrong code: guaranteed to differ from the real OTP
    # (de-flakes the ~1e-6 chance "000000" happens to be the generated OTP)
    wrong = "000000" if e["otp"] != "000000" else "111111"
    for _ in range(3):
        assert P.verify_otp(str(tmp_path), "paolo", wrong) is None
    # pending invalidated: even the correct code now fails
    assert P.verify_otp(str(tmp_path), "paolo", e["otp"]) is None


def test_invalidate_user_otp_pendings_leaves_at_most_one_live(tmp_path):
    """Two OTP pendings for the same user in flight is the exact ambiguity
    ``verify_otp``'s first-match scan can't safely resolve: a new step-up
    request must invalidate the previous one before creating the next, so a
    typed code always resolves to the action the user actually just saw."""
    first = P.create_pending(str(tmp_path), tool="call_ha_service",
                             inputs={"domain": "lock", "service": "unlock",
                                     "data": {"entity_id": "lock.front"}},
                             tier="red", origin="chat", label="lock.unlock",
                             user="paolo", with_otp=True)
    P.invalidate_user_otp_pendings(str(tmp_path), "paolo")
    second = P.create_pending(str(tmp_path), tool="call_ha_service",
                              inputs={"domain": "switch", "service": "turn_on",
                                      "data": {"entity_id": "switch.boiler"}},
                              tier="yellow", origin="chat", label="switch.turn_on",
                              user="paolo", with_otp=True)
    # the stale first OTP no longer resolves...
    assert P.verify_otp(str(tmp_path), "paolo", first["otp"]) is None
    # ...only the fresh one does, and it's bound to the NEW (frozen) action
    got = P.verify_otp(str(tmp_path), "paolo", second["otp"])
    assert got is not None and got["id"] == second["id"]
    assert got["inputs"]["data"]["entity_id"] == "switch.boiler"


def test_invalidate_user_otp_pendings_scoped_to_user(tmp_path):
    mine = P.create_pending(str(tmp_path), tool="call_ha_service", inputs={},
                            tier="yellow", origin="chat", label="x",
                            user="paolo", with_otp=True)
    other = P.create_pending(str(tmp_path), tool="call_ha_service", inputs={},
                             tier="yellow", origin="chat", label="y",
                             user="someone_else", with_otp=True)
    P.invalidate_user_otp_pendings(str(tmp_path), "paolo")
    assert P.verify_otp(str(tmp_path), "paolo", mine["otp"]) is None
    assert P.verify_otp(str(tmp_path), "someone_else", other["otp"]) is not None


def test_list_pending_never_exposes_otp(tmp_path):
    """FIX 1 (CRITICAL): GET /api/gateway/pending is reachable with the same
    X-HIRIS-Internal-Token the MCP gateway (Claude) holds, so list_pending
    must never leak the OTP or its attempt counter to that caller — while
    still surfacing the non-secret fields the Approvazioni page needs."""
    e = P.create_pending(str(tmp_path), tool="call_ha_service",
                         inputs={"domain": "lock", "service": "unlock",
                                 "data": {"entity_id": "lock.front"}},
                         tier="red", origin="chat", label="lock.unlock",
                         user="paolo", with_otp=True)
    pend = P.list_pending(str(tmp_path))
    assert len(pend) == 1
    listed = pend[0]
    assert "otp" not in listed
    assert "otp_attempts" not in listed
    # non-secret fields must still be present for the Approvazioni page
    assert listed["id"] == e["id"]
    assert listed["label"] == "lock.unlock"
    assert listed["tier"] == "red"
    assert listed["user"] == "paolo"
