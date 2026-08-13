import json

import pytest

# Reuse the aiohttp test-app fixture/factory from test_api.py (creates the real
# app via create_app(), mocks HA + claude_runner, sets app["data_dir"] to a
# tmp_path). Importing the fixture makes pytest pick it up in this module too.
from tests.test_api import client  # noqa: F401

_CONFIG_PROVIDER_IDS = ("subscription", "claude", "openai", "openrouter", "ollama")


@pytest.mark.asyncio
async def test_get_models_config_defaults(client):
    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()
    assert "chain_order" in body
    # fetta E5 Task 7: brain_model esce dal payload -- configurazione morta,
    # zero lettori da quando il Brain e' uscito con la E3.
    assert "brain_model" not in body


@pytest.mark.asyncio
async def test_get_models_config_porta_i_cinque_provider_e_l_appartenenza(client):
    """Il payload storico `providers[]` elenca tutti e cinque, ognuno con
    l'APPARTENENZA alla catena e la credenziale. Il campo si chiamava `active`
    (interruttore AND credenziale) e portava anche il `toggle` grezzo: erano la
    seconda rappresentazione dello stato, quella che permetteva alla pagina di
    mostrare spento un provider che stava lavorando."""
    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()

    providers = body["providers"]
    assert [p["id"] for p in providers] == list(_CONFIG_PROVIDER_IDS)
    for entry in providers:
        assert set(entry.keys()) == {"id", "label", "in_catena", "has_credential"}
        assert isinstance(entry["label"], str) and entry["label"]
        assert isinstance(entry["in_catena"], bool)
        assert isinstance(entry["has_credential"], bool)

    # The test client fixture wires app["claude_runner"] to a mock — so the
    # "claude" provider must report a credential even without CLAUDE_API_KEY.
    claude_entry = next(p for p in providers if p["id"] == "claude")
    assert claude_entry["has_credential"] is True

    # No openai_api_key/etc. are wired in the test fixture (on_startup is
    # cleared) — the other providers must report False rather than raising or
    # defaulting to True.
    for pid in ("subscription", "openai", "openrouter", "ollama"):
        entry = next(p for p in providers if p["id"] == pid)
        assert entry["has_credential"] is False


@pytest.mark.asyncio
async def test_l_interruttore_dell_addon_non_mette_piu_nessuno_in_catena(client, monkeypatch):
    """L'interruttore acceso non fa entrare in catena, e la credenziale nemmeno:
    ci si entra solo stando in `chain_order`. E' il difetto che questa fetta
    chiude, visto dal payload -- e con lui esce il campo `toggle`, che leggeva
    l'interruttore grezzo."""
    monkeypatch.setenv("PROVIDER_OPENROUTER", "true")
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = []

    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()

    providers_by_id = {p["id"]: p for p in body["providers"]}
    assert providers_by_id["openrouter"]["has_credential"] is True
    assert providers_by_id["openrouter"]["in_catena"] is False
    for pid in _CONFIG_PROVIDER_IDS:
        assert "toggle" not in providers_by_id[pid]
        assert "active" not in providers_by_id[pid]


@pytest.mark.asyncio
async def test_in_catena_segue_la_catena_del_runtime(client):
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["openrouter"]

    body = await (await client.get("/api/models/config")).json()
    providers_by_id = {p["id"]: p for p in body["providers"]}
    assert providers_by_id["openrouter"]["in_catena"] is True
    assert providers_by_id["claude"]["in_catena"] is False


@pytest.mark.asyncio
async def test_il_payload_porta_la_topologia_gia_composta(client):
    """Le due liste che la pagina disegnera'. Ogni voce ha esattamente sette
    campi: se la pagina dovesse aggiungerne uno, lo starebbe calcolando --
    l'invariante 2, rotto."""
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["openrouter"]
    client.app["ponte_attivo"] = False

    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["openrouter"]
    assert body["catena"][0]["posizione"] == 1
    assert [r["id"] for r in body["fuori_catena"]] == [
        "claude", "subscription", "openai", "ollama"]
    for r in body["catena"] + body["fuori_catena"]:
        assert set(r.keys()) == {"id", "nome", "modello", "natura",
                                 "ha_credenziale", "posizione", "riordinabile"}


@pytest.mark.asyncio
async def test_la_frase_e_la_catena_disegnata_leggono_la_stessa_lista(client):
    """Due rappresentazioni della stessa cosa nello STESSO payload sarebbero il
    difetto in miniatura: la frase dice chi risponde, le due liste dicono in che
    ordine, e devono venire dalla stessa misura."""
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["openrouter", "claude"]
    client.app["ponte_attivo"] = False

    body = await (await client.get("/api/models/config")).json()
    assert body["adesso"]["chi"] == body["catena"][0]["id"]


@pytest.mark.asyncio
async def test_col_ponte_acceso_il_piano_e_in_catena_anche_senza_chain_order(client, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    client.app["catena_modelli"] = []
    client.app["ponte_attivo"] = True

    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["subscription"]
    assert body["catena"][0]["riordinabile"] is False
    providers_by_id = {p["id"]: p for p in body["providers"]}
    assert providers_by_id["subscription"]["in_catena"] is True


@pytest.mark.asyncio
async def test_get_models_config_enriched_fields(client, monkeypatch):
    monkeypatch.setenv("LLM_STRATEGY", "cheap")
    monkeypatch.setenv("MEMORY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "text-embedding-3-small")
    client.app["local_model_name"] = "llama3.1:8b"

    resp = await client.get("/api/models/config")
    body = await resp.json()

    assert body["llm_strategy"] == "cheap"
    assert body["embeddings"] == {
        "provider": "openai",
        "model": "text-embedding-3-small",
    }
    assert body["ollama_model"] == "llama3.1:8b"


@pytest.mark.asyncio
async def test_get_models_config_never_leaks_secrets(client, monkeypatch):
    """Boolean has_credential only — the actual secret VALUE must never
    appear anywhere in the /api/models/config JSON payload."""
    fake_oauth_token = "sk-ant-oat01-super-secret-token-value"
    fake_claude_key = "sk-ant-api03-another-secret-value"
    fake_openai_key = "sk-openai-fake-secret-value"
    fake_openrouter_key = "sk-or-fake-secret-value"

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", fake_oauth_token)
    monkeypatch.setenv("CLAUDE_API_KEY", fake_claude_key)
    client.app["openai_api_key"] = fake_openai_key
    client.app["openrouter_api_key"] = fake_openrouter_key
    client.app["catena_modelli"] = ["claude", "openrouter", "openai"]

    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()
    dumped = json.dumps(body)

    for secret in (fake_oauth_token, fake_claude_key, fake_openai_key, fake_openrouter_key):
        assert secret not in dumped
    assert "sk-" not in dumped

    # La forma dell'attesa e' cambiata, il soggetto no. Fino alla 2.4.1 qui
    # c'erano `"api_key" not in dumped` e `"token" not in dumped.lower()`:
    # cercavano una sottostringa nell'INTERO payload, prosa compresa. Dalla
    # fetta «la catena diventa l'unica verita'» il payload porta anche le
    # diagnosi gia' scritte, e una di quelle dice «Il Piano Claude Max ha il
    # token, lo paghi, ed e' fuori dalla catena» -- una frase per l'utente, non
    # un segreto. Cercare la parola nel testo renderebbe questo test un veto
    # sul vocabolario del prodotto invece che una prova sulle chiavi. Si guarda
    # dove i segreti potrebbero davvero comparire: i NOMI DEI CAMPI, a ogni
    # livello.
    def _nomi_di_campo(nodo):
        if isinstance(nodo, dict):
            for k, v in nodo.items():
                yield k
                yield from _nomi_di_campo(v)
        elif isinstance(nodo, list):
            for v in nodo:
                yield from _nomi_di_campo(v)

    for campo in _nomi_di_campo(body):
        basso = campo.lower()
        assert "token" not in basso, campo
        assert "key" not in basso, campo
        assert "secret" not in basso, campo

    # Credentials ARE reflected as booleans, just never as values.
    providers_by_id = {p["id"]: p for p in body["providers"]}
    assert providers_by_id["subscription"]["has_credential"] is True
    assert providers_by_id["claude"]["has_credential"] is True
    assert providers_by_id["openai"]["has_credential"] is True
    assert providers_by_id["openrouter"]["has_credential"] is True


@pytest.mark.asyncio
async def test_put_models_config_persists_and_hot_updates(client):
    """fetta E5 Task 7: il soggetto storico di questo test era brain_model
    (uscito -- vedi test_get_models_config_defaults), ma il comportamento che
    verifica -- PUT persiste E il successivo GET riflette l'hot-update di
    request.app['models_config'] -- e' vivo e non coperto altrove: si sposta
    su chain_order invece di sparire."""
    resp = await client.put("/api/models/config", json={"chain_order": ["claude", "openai"]})
    assert resp.status == 200
    assert (await resp.json())["chain_order"] == ["claude", "openai"]
    resp2 = await client.get("/api/models/config")
    assert (await resp2.json())["chain_order"] == ["claude", "openai"]


@pytest.mark.asyncio
async def test_put_models_config_malformed_chain_order_is_graceful(client):
    """A non-list chain_order (e.g. null or a number) must not 500 — it should
    be coerced to an empty list, matching save_models_config's guard."""
    resp = await client.put("/api/models/config", json={"chain_order": 5})
    assert resp.status == 200
    body = await resp.json()
    assert body["chain_order"] == []


@pytest.mark.asyncio
async def test_list_models_never_leaks_secrets(client):
    resp = await client.get("/api/models")
    assert resp.status == 200
    body = await resp.json()
    dumped = str(body)
    assert "sk-" not in dumped and "api_key" not in dumped


@pytest.mark.asyncio
async def test_list_models_dichiara_l_appartenenza_alla_catena(client):
    resp = await client.get("/api/models")
    body = await resp.json()
    providers = body["providers"]
    assert providers, "expected at least the mocked claude provider"
    for entry in providers:
        assert "in_catena" in entry, (
            "il campo si chiamava `active` (interruttore AND credenziale): "
            "e' uscito con la derivazione che lo calcolava"
        )
        assert "active" not in entry
        assert "has_credential" in entry
        assert isinstance(entry["in_catena"], bool)
        assert isinstance(entry["has_credential"], bool)
    claude_entry = next(p for p in providers if p["id"] == "anthropic")
    assert claude_entry["has_credential"] is True
    assert claude_entry["in_catena"] is False, (
        "nessuna catena cablata nella fixture: la credenziale da sola non "
        "mette in catena"
    )


@pytest.mark.asyncio
async def test_il_payload_porta_la_decisione_gia_presa(client):
    """La pagina non deve poter ricostruire l'esito: lo riceve. È l'invariante
    2 della spec, e questo è il campo che lo rende possibile."""
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert "adesso" in body
    assert set(body["adesso"]) == {
        "chi", "nome", "modello", "natura", "via", "frase", "diagnosi"}
    assert isinstance(body["adesso"]["frase"], str) and body["adesso"]["frase"]


@pytest.mark.asyncio
async def test_il_payload_dichiara_se_il_ponte_e_acceso(client):
    """Senza questo campo lo stato «ponte acceso, nessun token» è INVISIBILE
    alla pagina: `toggle` di subscription legge solo PROVIDER_SUBSCRIPTION e
    non BRIDGE_ENABLED, e `active` collassa i due casi in false. Il progetto
    §4.3 dava il campo per già presente: non lo era."""
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert "ponte_attivo" in body
    assert isinstance(body["ponte_attivo"], bool)


@pytest.mark.asyncio
async def test_la_frase_nomina_il_primo_della_catena_del_runtime(client):
    """Non «il primo di chain_order»: il primo di `app["catena_modelli"]`,
    cioè la lista che il router prova davvero."""
    client.app["catena_modelli"] = ["openrouter", "claude"]
    client.app["ponte_attivo"] = False
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert body["adesso"]["chi"] == "openrouter"
    assert body["adesso"]["nome"] == "OpenRouter"


@pytest.mark.asyncio
async def test_ponte_acceso_senza_token_lo_dichiara_nel_payload(client, monkeypatch):
    """Invariante 5: lo stato «ponte acceso, nessun token» non deve poter
    passare in silenzio. E la scadenza dichiarata è quella CONFIGURATA --
    la stessa `BRIDGE_DEADLINE_MIN` che `_enqueue_chat_job` usa per far
    morire il turno -- non un cinque scritto a mano nel testo."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("BRIDGE_DEADLINE_MIN", "7")
    client.app["ponte_attivo"] = True
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert body["adesso"]["chi"] is None
    assert any("scade dopo 7 minuti" in d["testo"]
               for d in body["adesso"]["diagnosi"]), body["adesso"]["diagnosi"]
