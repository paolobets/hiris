from hiris.app.brain.privacy import VaultStore


def test_pseudonymize_and_detokenize_roundtrip(tmp_path):
    """Legit path: within ONE request, a token that request's own pseudonymize
    call created is correctly restored to its real PII value in the reply,
    using the mapping that same call populated."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer
    p = Pseudonymizer(VaultStore(str(tmp_path / "vault.db")))
    raw = "Bonifico a Mario su IT60X0542811101000000123456 di 50 euro"
    mapping: dict[str, str] = {}
    masked = p.pseudonymize(raw, mapping)
    assert "IT60X0542811101000000123456" not in masked
    assert "[IBAN_1]" in masked
    assert mapping == {"[IBAN_1]": "IT60X0542811101000000123456"}
    # la risposta del modello cita il token: lo riportiamo al valore reale,
    # usando la mapping di QUESTA stessa richiesta
    reply = "Ho registrato il bonifico su [IBAN_1]."
    assert p.detokenize(reply, mapping) == "Ho registrato il bonifico su IT60X0542811101000000123456."


def test_detokenize_cross_request_token_left_verbatim(tmp_path):
    """SECURITY (review B/#7): request R1 (user A) tokenizes PII, minting
    [EMAIL_0] in the GLOBAL vault. Request R2 (user B) is a completely
    different exchange with its own (empty) mapping; even though [EMAIL_0]
    exists in the shared vault, R2's detokenize must NOT expand it — the
    token was never substituted into R2's own outbound prompt. Cross-
    conversation/cross-user PII must never leak this way."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer
    vault = VaultStore(str(tmp_path / "vault.db"))
    p = Pseudonymizer(vault)

    # R1: user A's request tokenizes their email into the shared vault.
    mapping_r1: dict[str, str] = {}
    masked_r1 = p.pseudonymize("Contattami a mario.rossi@example.it per favore", mapping_r1)
    assert "[EMAIL_1]" in masked_r1
    assert mapping_r1 == {"[EMAIL_1]": "mario.rossi@example.it"}

    # R2: a DIFFERENT request/user, own (empty) mapping. Its LLM output
    # happens to contain the exact same token string minted by R1.
    mapping_r2: dict[str, str] = {}
    leaked_output = "Il contatto salvato è [EMAIL_1]."
    result = p.detokenize(leaked_output, mapping_r2)

    # Must NOT resolve to R1's real email — left verbatim instead.
    assert result == "Il contatto salvato è [EMAIL_1]."
    assert "mario.rossi@example.it" not in result

    # Sanity: the vault DOES still hold the mapping (durable numbering is
    # unaffected) — proving this is a detokenize-scoping fix, not a vault
    # regression. value_for is a low-level lookup, no longer reachable from
    # detokenize.
    assert vault.value_for("[EMAIL_1]") == "mario.rossi@example.it"
    vault.close()


def test_detokenize_hallucinated_or_injected_token_left_verbatim(tmp_path):
    """A [TYPE_N]-shaped token that was never created by ANY pseudonymize
    call (model-hallucinated, or injected via a poisoned document/HA state)
    must never resolve to real PII — it isn't even in the vault."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer
    p = Pseudonymizer(VaultStore(str(tmp_path / "vault.db")))
    mapping: dict[str, str] = {}
    text = "Il tuo IBAN è [IBAN_5]."
    assert p.detokenize(text, mapping) == text


def test_detokenize_without_mapping_defaults_to_no_expansion(tmp_path):
    """Fail-safe default: calling detokenize with no mapping at all (mapping
    omitted/None) must never fall back to a global/vault lookup — everything
    stays verbatim."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer
    vault = VaultStore(str(tmp_path / "vault.db"))
    vault.token_for("iban", "IT60X0542811101000000123456")  # pre-existing vault entry
    p = Pseudonymizer(vault)
    text = "Saldo su [IBAN_1]."
    assert p.detokenize(text) == text
    assert p.detokenize(text, None) == text
    vault.close()


def test_detect_pii_italian():
    from hiris.app.brain.privacy import detect_pii
    text = ("IBAN IT60X0542811101000000123456, CF RSSMRA85T10A562S, "
            "carta 4111 1111 1111 1111, mail a@b.it, tel +39 333 1234567")
    found = {t for _, _, t, _ in detect_pii(text)}
    assert {"iban", "codice_fiscale", "card", "email", "phone"} <= found


def test_detect_pii_card_no_trailing_separator():
    from hiris.app.brain.privacy import detect_pii
    spans = [s for s in detect_pii("carta 4111 1111 1111 1111 next") if s[2] == "card"]
    assert spans, "card not detected"
    value = spans[0][3]
    assert value == "4111 1111 1111 1111"   # no trailing space
    assert not value.endswith(" ")


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
