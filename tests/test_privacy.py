from hiris.app.brain.privacy import VaultStore


def test_token_for_is_stable_and_typed(tmp_path):
    v = VaultStore(str(tmp_path / "vault.db"))
    t1 = v.token_for("iban", "IT60X0542811101000000123456")
    t2 = v.token_for("iban", "IT60X0542811101000000123456")
    t3 = v.token_for("iban", "IT00A0000000000000000000000")
    assert t1 == t2                 # stesso valore → stesso token
    assert t1 != t3                 # valori diversi → token diversi
    assert t1.startswith("[IBAN_") and t1.endswith("]")
    assert v.value_for(t1) == "IT60X0542811101000000123456"
    v.close()
