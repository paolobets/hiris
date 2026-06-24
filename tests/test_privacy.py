from hiris.app.brain.privacy import VaultStore


def test_detect_pii_italian():
    from hiris.app.brain.privacy import detect_pii
    text = ("IBAN IT60X0542811101000000123456, CF RSSMRA85T10A562S, "
            "carta 4111 1111 1111 1111, mail a@b.it, tel +39 333 1234567")
    found = {t for _, _, t, _ in detect_pii(text)}
    assert {"iban", "codice_fiscale", "card", "email", "phone"} <= found


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
