import json
from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.api import handlers_models

# Reuse the aiohttp test-app fixture/factory from test_api.py (creates the real
# app via create_app(), mocks HA + claude_runner, sets app["data_dir"] to a
# tmp_path). Importing the fixture makes pytest pick it up in this module too.
from tests.test_api import client  # noqa: F401

_CONFIG_PROVIDER_IDS = ("subscription", "claude", "openai", "openrouter", "ollama")


@pytest.fixture
def claude_con_elenco(client):
    """Claude API con una chiave, e la lettura MOCKATA.

    Dalla fetta «il modello del piano» Claude API si comporta come gli altri
    due provider che si interrogano: senza chiave e' «assente» e sparisce
    dall'elenco; con la chiave, `/api/models` chiama DAVVERO api.anthropic.com.

    I test che usano questa fixture parlano della FORMA della rotta -- quali id
    compaiono, che aspetto ha la voce «auto», che cosa NON c'e' piu' nel
    payload -- non della lettura, che vive tutta in
    `tests/test_elenco_anthropic.py`. La chiave serve solo perche' senza di lei
    Claude non comparirebbe affatto; il mock serve perche' una suite che esce
    sulla rete e' una suite che fallisce per ragioni sue.
    """
    client.app["claude_api_key"] = "sk-test"
    with patch.object(handlers_models, "_fetch_claude_models",
                      AsyncMock(return_value=(handlers_models._CLAUDE_MODELS,
                                              "riserva"))):
        yield client


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
async def test_il_get_pinna_l_insieme_esatto_delle_sue_chiavi(client):
    """L'INSIEME, non l'assenza di una. Il Task 4 ha imparato che un test
    scritto come «X non c'e'» lascia rientrare X con un nome diverso, e che una
    chiave rimessa a mano non fa cadere niente: la prova per mutazione che
    rimetteva `payload["llm_strategy"]` lasciava la suite intera verde.

    Le due uscite del Task 8 sono `providers[]` (l'appartenenza alla catena
    detta una seconda volta) e `llm_strategy` (il preset letto dall'ambiente
    accanto a `strategia_ultima` letto dall'archivio). Chi le rimette,
    rimette una seconda rappresentazione dello stato: qui si rompe."""
    body = await (await client.get("/api/models/config")).json()
    assert set(body) == {
        # l'archivio (load_models_config)
        "chain_order", "provider_models", "ponte", "ollama",
        "nascondi_gratuiti", "strategia_ultima",
        # I TRE SEGNI di migrazione. Si leggono (il GET descrive l'archivio
        # per intero), ma non si SCRIVONO da qui: `_MIGRATION_FLAGS` li tiene
        # fuori da cio' che una PUT puo' toccare -- vedi
        # `test_una_put_non_puo_riscrivere_i_segni_della_migrazione`.
        "seminato", "catena_seminata", "piano_seminato",
        # cio' che la pagina disegna
        "adesso", "catena", "fuori_catena", "fine_catena",
    }
    # `ponte_attivo` E' USCITO con la versione B, ed era l'ULTIMO residuo
    # dell'invariante 1 di tutto il payload: `app["ponte_attivo"]`, cioe'
    # `BRIDGE_ENABLED or _sub_first_class`, pubblicato ACCANTO a
    # `ponte["attivo"]`. Non era un doppione esatto -- poteva dire `true` con
    # l'archivio a `false` -- e quindi la pagina riceveva due risposte alla
    # stessa domanda. Tolta l'implicazione in `server.py`, il secondo valore
    # e' il primo, e ne resta uno.
    assert "ponte_attivo" not in body
    assert isinstance(body["ponte"]["attivo"], bool)
    # Task 9: `ollama_model` e `embeddings` sono usciti da qui. Il primo era
    # `app["local_model_name"]` accanto a `payload["ollama"]["modello"]` -- la
    # stessa cosa detta due volte, e la copia era pure ferma all'avvio. Il
    # secondo alimentava la sezione «03 Embeddings», uscita col Task 8: due
    # valori che nessuna riga di schermo mostra piu'.
    assert "ollama_model" not in body
    assert "embeddings" not in body


@pytest.mark.asyncio
async def test_i_cinque_provider_ci_sono_tutti_e_stanno_in_una_lista_sola(client):
    """Task 8: il payload storico `providers[]` E' USCITO. Elencava tutti e
    cinque con `in_catena` + `has_credential`, cioe' diceva l'appartenenza alla
    catena una SECONDA volta accanto a `catena`/`fuori_catena`, che la dicono
    per esteso -- due rappresentazioni della stessa cosa nello stesso payload,
    la miniatura del difetto che questa fetta chiude. Il suo unico lettore era
    la pagina, che adesso disegna la prima.

    Cio' che quel test proteggeva resta, e si guarda dove la cosa vive adesso:
    i cinque ci sono tutti, ognuno sta in UNA delle due liste, e la credenziale
    e' un booleano."""
    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()

    assert "providers" not in body, (
        "la seconda rappresentazione dell'appartenenza non deve tornare"
    )
    righe = {r["id"]: r for r in body["catena"] + body["fuori_catena"]}
    assert sorted(righe) == sorted(_CONFIG_PROVIDER_IDS)
    dentro = {r["id"] for r in body["catena"]}
    fuori = {r["id"] for r in body["fuori_catena"]}
    assert dentro & fuori == set(), "nessuno puo' stare dentro e fuori insieme"
    for riga in righe.values():
        assert isinstance(riga["nome"], str) and riga["nome"]
        assert isinstance(riga["ha_credenziale"], bool)

    # The test client fixture wires app["claude_runner"] to a mock — so the
    # "claude" provider must report a credential even without CLAUDE_API_KEY.
    assert righe["claude"]["ha_credenziale"] is True
    assert righe["claude"]["manca"] == ""

    # No openai_api_key/etc. are wired in the test fixture (on_startup is
    # cleared) — the other providers must report False rather than raising or
    # defaulting to True.
    for pid in ("subscription", "openai", "openrouter", "ollama"):
        assert righe[pid]["ha_credenziale"] is False
    # E quando manca, il payload dice QUALE credenziale manca: sono tre cose
    # diverse, e la parola che le distingue vive dove vivono le altre parole
    # del prodotto (decisione_modelli), non nella pagina.
    assert righe["subscription"]["manca"] == "manca il token"
    assert righe["openai"]["manca"] == "manca la chiave"
    assert righe["ollama"]["manca"] == "manca l'indirizzo"


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

    fuori = {r["id"]: r for r in body["fuori_catena"]}
    assert fuori["openrouter"]["ha_credenziale"] is True
    assert body["catena"] == [], (
        "l'interruttore acceso e la credenziale presente non mettono in catena"
    )
    for riga in body["catena"] + body["fuori_catena"]:
        assert "toggle" not in riga
        assert "active" not in riga
        assert "in_catena" not in riga, (
            "l'appartenenza e' la lista in cui la riga si trova, non un campo "
            "dentro la riga: un campo potrebbe contraddire la lista"
        )


@pytest.mark.asyncio
async def test_in_catena_segue_la_catena_del_runtime(client):
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["openrouter"]

    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["openrouter"]
    assert "claude" in {r["id"] for r in body["fuori_catena"]}


@pytest.mark.asyncio
async def test_il_payload_porta_la_topologia_gia_composta(client):
    """Le due liste che la pagina disegnera'. Ogni voce ha esattamente
    QUATTORDICI campi: se la pagina dovesse aggiungerne uno, lo starebbe
    calcolando -- l'invariante 2, rotto.

    Erano sette fino al Task 8, undici dopo, dodici col Task 9. Il Task 11
    aggiunge `esito` (il fatto grezzo: che cosa e' successo davvero a quel
    provider, o `None` se non e' mai stato interrogato) e `stato_testo` (la
    frase che lo racconta). Il fatto viaggia ACCANTO alla frase perche' la
    pagina possa disegnare diverso cio' che ha rifiutato senza dedurlo dal
    testo: leggere una regola dentro una frase e' come ricostruirla. Le voci nuove non sono calcoli,
    sono PAROLE o FATTI: quale credenziale manca (`manca`), perche' una riga
    non offre i gesti che offrono le altre (`nota`), cosa succede se quella
    riga non risponde (`connettore`), il tetto dei cinque minuti quando c'e'
    (`connettore_nota`) e -- col Task 9 -- se il modello di quella riga e' un
    ALIAS o un IDENTIFICATORE (`modello_alias`), che e' la differenza di natura
    che la pagina rende col carattere (progetto §6.2) e che senza questo campo
    dovrebbe dedurre da un `if (id === 'subscription')`. Il numero sale quando
    il backend smette di far dedurre qualcosa alla pagina: e' l'invariante 2
    che si stringe, non che si allenta."""
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["openrouter"]

    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["openrouter"]
    assert body["catena"][0]["posizione"] == 1
    assert [r["id"] for r in body["fuori_catena"]] == [
        "claude", "subscription", "openai", "ollama"]
    for r in body["catena"] + body["fuori_catena"]:
        assert set(r.keys()) == {"id", "nome", "modello", "modello_alias",
                                 "natura", "manca", "nota", "connettore",
                                 "connettore_nota", "ha_credenziale",
                                 "posizione", "riordinabile",
                                 "esito", "stato_testo"}
    # E la frase che chiude la catena e' della CATENA, non dell'ultima riga:
    # quale sia l'ultima cambia con un gesto, e la pagina riordina da se'.
    assert body["fine_catena"] == (
        "ultimo della catena: se non risponde, la chat da' errore".replace("da'", "dà"))
    assert all(r["connettore"] == "" for r in body["fuori_catena"]), (
        "chi sta fuori non ha un «dopo»: non e' in nessuna sequenza"
    )


@pytest.mark.asyncio
async def test_la_frase_e_la_catena_disegnata_leggono_la_stessa_lista(client):
    """Due rappresentazioni della stessa cosa nello STESSO payload sarebbero il
    difetto in miniatura: la frase dice chi risponde, le due liste dicono in che
    ordine, e devono venire dalla stessa misura."""
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["openrouter", "claude"]

    body = await (await client.get("/api/models/config")).json()
    assert body["adesso"]["chi"] == body["catena"][0]["id"]


@pytest.mark.asyncio
async def test_col_ponte_acceso_il_piano_e_in_catena_anche_senza_chain_order(client, monkeypatch):
    """Il ponte si accende SCRIVENDO L'ARCHIVIO, non un valore in memoria.

    Fino alla 2.5.0 questo test faceva `client.app["ponte_attivo"] = True`, e
    andava bene perche' il payload pubblicava quel valore. Dalla versione B il
    ponte ha una casa sola (`ponte.attivo`), e una prova che accendesse il
    ponte in un posto che il prodotto non ha piu' proverebbe uno stato
    irraggiungibile."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    client.app["catena_modelli"] = []
    await client.put("/api/models/config", json={"ponte": {"attivo": True}})

    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["subscription"]
    assert body["catena"][0]["riordinabile"] is False
    assert "subscription" not in {r["id"] for r in body["fuori_catena"]}


@pytest.mark.asyncio
async def test_il_modello_di_ollama_ha_una_casa_sola_e_la_riga_la_legge(client):
    """Il soggetto storico di questo test era `body["ollama_model"]`, cioe'
    `app["local_model_name"]`. Quello slot era una COPIA presa all'avvio: dopo
    un salvataggio la riga avrebbe continuato a mostrare il modello di prima,
    e il payload avrebbe portato due valori diversi per la stessa cosa. Il
    comportamento che conta -- la riga di Ollama dice quale modello risponde --
    si guarda dove la cosa vive adesso: l'archivio."""
    client.app["local_model_url"] = "http://192.168.1.42:11434"
    await client.put("/api/models/config", json={
        "chain_order": [], "ollama": {"modello": "llama3.1:8b", "timeout_s": 120}})

    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["catena"] + body["fuori_catena"]}
    assert righe["ollama"]["modello"] == "llama3.1:8b"
    assert body["ollama"]["modello"] == "llama3.1:8b"

    # E cambia dal salvataggio, non dal riavvio: era il punto in cui la copia
    # in memoria si sarebbe vista.
    await client.put("/api/models/config", json={
        "chain_order": [], "ollama": {"modello": "qwen2.5:14b", "timeout_s": 120}})
    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["catena"] + body["fuori_catena"]}
    assert righe["ollama"]["modello"] == "qwen2.5:14b"


@pytest.mark.asyncio
async def test_ollama_senza_modello_non_puo_entrare_in_catena_e_dice_perche(client):
    """Il buco dichiarato dal Task 7, chiuso qui. La credenziale di Ollama e'
    il SOLO indirizzo (l'indirizzo si custodisce, il modello si decide), ma per
    rispondere servono tutti e due: con la sola credenziale, Ollama poteva
    finire in catena senza un runner dietro -- un anello numerato in una pagina
    che descrive il runtime, mentre `LLMRouter._ordered_backends` lo saltava in
    silenzio. La riga resta credenziata (il pallino resta acceso: l'indirizzo
    c'e' davvero) e a mancare e' il GESTO."""
    client.app["local_model_url"] = "http://192.168.1.42:11434"
    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["fuori_catena"]}

    assert righe["ollama"]["ha_credenziale"] is True
    assert righe["ollama"]["manca"] == "", (
        "la credenziale c'e': dire «manca l'indirizzo» sarebbe falso"
    )
    assert righe["ollama"]["riordinabile"] is False, (
        "«Usa» qui scriverebbe una PUT accettata e buttata via dal runtime"
    )
    assert "il modello no" in righe["ollama"]["nota"]

    # E col modello scelto il gesto torna: la nota sparisce, la riga si muove.
    await client.put("/api/models/config", json={
        "chain_order": [], "ollama": {"modello": "llama3.1:8b", "timeout_s": 120}})
    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["fuori_catena"]}
    assert righe["ollama"]["riordinabile"] is True
    assert righe["ollama"]["nota"] == ""


@pytest.mark.asyncio
async def test_il_piano_porta_un_ALIAS_e_gli_altri_un_IDENTIFICATORE(client, monkeypatch):
    """Progetto §6.2: sono cose di natura diversa, e la pagina lo dice col
    carattere. Il campo esiste perche' la pagina NON debba saperlo: senza,
    servirebbe un `if (id === 'subscription')` nel frontend, cioe' la regola
    del prodotto scritta una seconda volta in un altro linguaggio."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["catena"] + body["fuori_catena"]}
    assert righe["subscription"]["modello_alias"] is True
    for pid in ("claude", "openai", "openrouter", "ollama"):
        assert righe[pid]["modello_alias"] is False, pid


@pytest.mark.asyncio
async def test_la_riga_di_openrouter_non_mostra_piu_un_modello_di_openai(client):
    """`OpenRouterRunner._resolve_model` non usa `AUTO_MODEL_MAP` (e' la mappa
    di OpenAI: su OpenRouter `gpt-4o` non e' nemmeno un nome valido). La riga
    diceva `gpt-4o` a chiunque non avesse scelto un modello: un identificatore
    preciso, e falso."""
    from hiris.app.backends.openrouter_runner import AUTO_OPENROUTER

    client.app["openrouter_api_key"] = "sk-or-presente"
    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["catena"] + body["fuori_catena"]}
    assert righe["openrouter"]["modello"] == AUTO_OPENROUTER
    assert righe["openrouter"]["modello"] != righe["openai"]["modello"]


@pytest.mark.asyncio
async def test_il_connettore_dichiara_il_tempo_CHE_IL_TURNO_SUBISCE(client, monkeypatch):
    """Il numero del connettore e' quello con cui `_enqueue_chat_job` scrive la
    scadenza. Fino al Task 10 erano DUE numeri -- `BRIDGE_DEADLINE_MIN` per il
    turno, `ponte.scadenza_min` per l'archivio -- e la pagina mostrava il
    primo perche' il secondo non aveva lettori: due rappresentazioni dello
    stesso valore nello stesso payload (invariante 1), e quella che l'utente
    poteva cambiare da questa pagina non era quella che il turno subiva.

    L'ambiente qui e' messo al CONTRARIO dell'archivio apposta: se qualcuno
    rimettesse la lettura d'ambiente, questo test lo direbbe subito."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    monkeypatch.setenv("BRIDGE_DEADLINE_MIN", "44")
    await client.put("/api/models/config",
                     json={"ponte": {"attivo": True, "scadenza_min": 9}})
    client.app["catena_modelli"] = []

    body = await (await client.get("/api/models/config")).json()
    assert body["catena"][0]["id"] == "subscription"
    assert "9 min" in body["catena"][0]["connettore"]
    assert "44" not in body["catena"][0]["connettore"]



@pytest.mark.asyncio
async def test_una_catena_vuota_non_ha_una_fine(client):
    """`fine_catena` e' la frase che chiude la sequenza: senza sequenza non c'e'
    niente da chiudere, e una riga «se non risponde, la chat da' errore» sotto
    una catena vuota parlerebbe di un anello che non esiste."""
    client.app["catena_modelli"] = []
    body = await (await client.get("/api/models/config")).json()
    assert body["catena"] == []
    assert body["fine_catena"] == ""


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
    righe = {r["id"]: r for r in body["catena"] + body["fuori_catena"]}
    assert righe["subscription"]["ha_credenziale"] is True
    assert righe["claude"]["ha_credenziale"] is True
    assert righe["openai"]["ha_credenziale"] is True
    assert righe["openrouter"]["ha_credenziale"] is True


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
async def test_list_models_non_dice_piu_l_appartenenza_alla_catena(claude_con_elenco):
    """Task 9: `in_catena` + `has_credential` erano la TERZA superficie che
    descriveva l'appartenenza, dopo che il Task 7 aveva tolto
    `providers[].active` e il Task 8 l'intero `providers[]` da
    `/api/models/config`. L'unico lettore era il picker uscito col Task 8;
    questa rotta serve adesso il pannello del modello, che l'appartenenza non
    la usa -- la riga da cui si apre sta gia' dentro `catena` o dentro
    `fuori_catena`, e sono quelle due liste a dirlo.

    E gli id sono i CINQUE del prodotto: l'id storico "anthropic" (che
    divergeva dal nome "claude" della catena, e costringeva a una mappa di
    riconciliazione) e' uscito con lui."""
    body = await (await claude_con_elenco.get("/api/models")).json()
    providers = body["providers"]
    assert providers
    for entry in providers:
        assert "in_catena" not in entry
        assert "active" not in entry
        assert "has_credential" not in entry
        assert entry["id"] in _CONFIG_PROVIDER_IDS
    assert "anthropic" not in {p["id"] for p in providers}


@pytest.mark.asyncio
async def test_il_pannello_arriva_gia_composto_e_dice_da_dove_viene_l_elenco(client):
    """La pagina disegna e non calcola: le parole del pannello -- la
    provenienza, la spiegazione, da quando ha effetto -- arrivano gia' scritte,
    come la frase di «Adesso» e le parole delle righe."""
    body = await (await client.get("/api/models?provider=claude")).json()
    assert [p["id"] for p in body["providers"]] == ["claude"]
    p = body["providers"][0]
    assert set(p) == {"id", "nome", "alias", "elenco_completo", "fonte",
                      "provenienza", "spiegazione", "quando", "dove", "scelto",
                      "casella", "modelli"}
    # La fixture `client` non porta una chiave di Claude API, quindi non c'e'
    # nessun elenco da leggere e il pannello lo DICE. Qui si asseriva `fonte ==
    # "riserva"` con una frase che dichiarava inesistente l'endpoint di elenco
    # di Anthropic: falso, `GET /v1/models` c'e'. Dalla fetta «il modello del
    # piano» Claude API si comporta come OpenAI e OpenRouter -- senza chiave,
    # «assente»; con la chiave, lettura viva e riserva dichiarata se fallisce
    # (`tests/test_elenco_anthropic.py`).
    assert p["fonte"] == "assente"
    assert "manca la chiave" in p["provenienza"]
    assert p["dove"] == ["provider_models", "claude"]


@pytest.mark.asyncio
async def test_il_pannello_del_piano_offre_tre_alias_E_SI_SCRIVE(client, monkeypatch):
    """`agent/runner.modello_cli` riduce QUALUNQUE modello risolto a
    opus/haiku/sonnet: offrire `claude-opus-4-7` sul piano sarebbe una
    precisione finta.

    Qui si asseriva anche `dove == []`, con la ragione scritta accanto: «il
    modello del piano e' un effetto di quello di Claude API, un pannello che
    offrisse di scriverlo manderebbe una PUT che nessuno legge». Era vera, ed
    era il difetto. Dalla fetta «il modello del piano» c'e' un campo suo, e
    `elenco_completo` tiene fuori il campo di testo libero: i tre alias si
    scelgono, ma non c'e' un quarto valore da incollare."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    body = await (await client.get("/api/models?provider=subscription")).json()
    p = body["providers"][0]
    assert [v["valore"] for v in p["modelli"]] == ["haiku", "sonnet", "opus"]
    assert p["dove"] == ["ponte", "modello"]
    assert p["alias"] is True
    assert p["elenco_completo"] is True
    assert p["fonte"] == "fissa", (
        "i tre alias non sono un ripiego: non descrivono il catalogo di "
        "qualcun altro, sono l'insieme esatto che modello_cli sa produrre"
    )
    assert "Claude API" not in p["spiegazione"], (
        "la spiegazione mandava a scegliere il modello sulla riga di Claude "
        "API: da questa fetta sarebbe mandare a cambiare il valore sbagliato"
    )
    assert p["scelto"] == "sonnet", (
        "il predefinito del campo su un archivio appena nato"
    )


@pytest.mark.asyncio
async def test_il_pannello_di_claude_senza_chiave_DICE_che_non_c_e_niente_da_leggere(
        client, monkeypatch):
    """L'eccezione che qui si difendeva E' MORTA, e va detto perche'.

    Diceva: la regola non e' «senza credenziale niente pannello» ma «senza
    ELENCO niente pannello», e l'elenco di Claude non veniva dal provider --
    quindi c'era anche senza chiave. La ragione per cui contava era scritta:
    su un'installazione col solo Piano Claude Max quello era l'UNICO posto da
    cui si sceglieva il modello del piano.

    Dalla fetta «il modello del piano» tutte e due le meta' sono cadute:
    l'elenco VIENE dal provider (`GET /v1/models` esiste, la frase contraria
    era falsa) e il piano ha un campo suo, quindi nessuno deve piu' passare di
    qui per sceglierlo. Claude API si comporta come OpenAI e OpenRouter.

    E' una PERDITA -- senza chiave non si sfogliano piu' quei modelli -- ma di
    voci inerti: senza chiave quel provider non entra in catena. La perdita e'
    scritta nella spec §6.3, non nascosta."""
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    client.app["claude_runner"] = None
    client.app["claude_api_key"] = ""
    body = await (await client.get("/api/models?provider=claude")).json()
    # La voce c'e' comunque: chi viene CHIESTO riceve sempre una risposta --
    # nascondere e' comodo per chi capisce e crudele per chi non capisce
    # perche' una cosa e' sparita. Quello che cambia e' cosa dice.
    assert [p["id"] for p in body["providers"]] == ["claude"]
    p_claude = body["providers"][0]
    assert p_claude["fonte"] == "assente"
    assert p_claude["modelli"] == []
    assert "manca la chiave" in p_claude["provenienza"]
    assert p_claude["dove"] == ["provider_models", "claude"]


@pytest.mark.asyncio
async def test_la_voce_auto_e_la_stringa_vuota_e_dice_a_cosa_si_risolve(claude_con_elenco):
    """Salvare la parola "auto" e' un difetto: `resolve_model("auto", "chat",
    "auto")` restituisce "auto" e la richiesta parte con `model="auto"`. La
    voce c'e' -- e' una scelta legittima -- ma il suo valore e' "" e la sua
    nota dice a quale modello si risolve oggi."""
    body = await (await claude_con_elenco.get("/api/models?provider=claude")).json()
    prima = body["providers"][0]["modelli"][0]
    assert prima["valore"] == ""
    assert prima["nota"].startswith("scelto da HIRIS")
    assert "claude-" in prima["nota"]
    assert "auto" not in [v["valore"] for v in body["providers"][0]["modelli"]]


@pytest.mark.asyncio
async def test_senza_provider_risponde_per_tutti_quelli_che_hanno_un_elenco(claude_con_elenco):
    """La forma storica della rotta resta: un client diverso dalla pagina
    esiste, e una rotta che cambia significato in silenzio e' la cosa che
    questa fetta ritira."""
    body = await (await claude_con_elenco.get("/api/models")).json()
    ids = [p["id"] for p in body["providers"]]
    # La fixture cabla solo `claude_runner`: nessuna chiave OpenAI/OpenRouter,
    # nessun indirizzo Ollama, nessun token del piano.
    assert ids == ["claude"]


@pytest.mark.asyncio
async def test_il_pannello_di_ollama_scrive_nella_sua_casa_non_in_provider_models(client):
    """`provider_models["ollama"]` e' un FANTASMA, non un doppione:
    `_PROVIDER_MODEL_KEYS` non lo contiene e `_clean_provider_models` lo scarta
    in lettura E in scrittura. Il percorso viaggia nel payload perche' la
    pagina non debba conoscerlo: senza, servirebbe un `if (id === 'ollama')`
    nel frontend."""
    client.app["local_model_url"] = "http://192.168.1.42:11434"
    body = await (await client.get("/api/models?provider=ollama")).json()
    p = body["providers"][0]
    assert p["dove"] == ["ollama", "modello"]
    assert p["casella"] is None
    # E il fantasma resta un fantasma anche passando dalla PUT.
    resp = await client.put("/api/models/config", json={
        "chain_order": [], "provider_models": {"ollama": "llama3.1:8b"}})
    assert "ollama" not in (await resp.json())["provider_models"]


@pytest.mark.asyncio
async def test_la_casella_dei_gratuiti_viaggia_come_percorso_solo_per_openrouter(client):
    """La casella vive SULLA LISTA CHE FILTRA, e la pagina la disegna senza
    sapere per chi: le arriva un'etichetta e un percorso dentro l'oggetto che
    gia' salva."""
    client.app["openrouter_api_key"] = "sk-or-presente"
    body = await (await client.get("/api/models?provider=openrouter")).json()
    p = body["providers"][0]
    assert p["casella"] == {"etichetta": "nascondi i gratuiti",
                            "dove": ["nascondi_gratuiti"]}
    assert p["dove"] == ["provider_models", "openrouter"]


@pytest.mark.asyncio
async def test_nessun_pannello_ha_piu_niente_da_confessare(client):
    """Invariante 4, chiuso invece che dichiarato. Fino al Task 10 questo campo
    portava la confessione: lo stesso valore -- il modello di Claude API --
    aveva effetto IMMEDIATO sul ponte (`_enqueue_chat_job` rilegge
    `app["models_config"]` a ogni turno) e SOLO AL RIAVVIO sull'API (i runner
    lo ricevevano alla costruzione), e la pagina ne dichiarava uno solo:
    sbagliata, non imprecisa. Adesso i runner LEGGONO, quindi non c'e' un
    tempo da dichiarare per nessuno dei cinque -- e la pagina non ne inventa
    uno quando il backend tace (pinnato in tests/js/models-route.test.mjs).

    Si guardano tutti e cinque, non solo quello che confessava: una didascalia
    di riavvio rimessa su un provider qualsiasi sarebbe la pagina che torna a
    mentire da un'altra riga."""
    for pid in _CONFIG_PROVIDER_IDS:
        body = await (await client.get("/api/models?provider=" + pid)).json()
        for p in body["providers"]:
            assert p["quando"] == "", (
                "il pannello di " + pid + " dichiara un tempo che non esiste: "
                + repr(p["quando"])
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
async def test_il_payload_dichiara_se_il_ponte_e_acceso_UNA_volta_sola(client):
    """Senza saperlo, lo stato «ponte acceso, nessun token» è INVISIBILE alla
    pagina: fino al Task 7 `toggle` di subscription leggeva solo
    PROVIDER_SUBSCRIPTION e non BRIDGE_ENABLED, e `active` collassava i due
    casi in false. Il progetto §4.3 dava il campo per già presente: non lo era,
    e il Task 7 lo aveva aggiunto come `ponte_attivo`.

    **Versione B**: il campo dedicato è uscito, ma il fatto no -- viaggia in
    `ponte.attivo`, che è dove vive. Quello che si pinna qui è che il payload
    lo dica UNA volta: due campi che rispondono alla stessa domanda sono
    l'invariante 1 violato, e questo payload ne ha già portati quattro (
    `providers[]`, `llm_strategy`, `ollama_model`, `ponte_attivo`) in quattro
    task diversi."""
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert isinstance(body["ponte"]["attivo"], bool)
    chiavi_che_parlano_del_ponte = [
        k for k in body if "ponte" in k.lower() and k != "ponte"]
    assert chiavi_che_parlano_del_ponte == [], (
        f"il payload dice il ponte in piu' di un posto: {chiavi_che_parlano_del_ponte}"
    )


@pytest.mark.asyncio
async def test_accendere_il_ponte_dalla_pagina_mette_il_piano_in_testa(client, monkeypatch):
    """**Il gesto che il Task 14 non poteva costruire**, dalla rotta.

    Il Task 14 aveva rinunciato al bottone «Mettilo primo» perché metà della
    condizione mancava: `ponte.attivo` veniva da `BRIDGE_ENABLED`, cioè
    dall'ambiente, e una PUT su un valore letto dall'ambiente torna 200 e viene
    buttata via al riavvio -- il bottone che sembra funzionare e non funziona.

    Questo è il giro intero, come lo fa la pagina: si legge (il piano è fuori,
    e la diagnosi porta il gesto), si scrive il percorso che il gesto dichiara,
    si rilegge. Se `ponte.attivo` tornasse a venire dall'ambiente, la seconda
    lettura mostrerebbe il piano ancora fuori."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    client.app["catena_modelli"] = ["claude"]

    prima = await (await client.get("/api/models/config")).json()
    assert "subscription" in {r["id"] for r in prima["fuori_catena"]}
    gesti = [d["azione"] for d in prima["adesso"]["diagnosi"] if d["azione"]]
    assert len(gesti) == 1, prima["adesso"]["diagnosi"]
    gesto = gesti[0]
    assert gesto["dove"] == ["ponte", "attivo"] and gesto["valore"] is True

    # La pagina applica il percorso a `state.cfg` e rimanda l'oggetto intero.
    corpo = dict(prima["ponte"])
    corpo[gesto["dove"][1]] = gesto["valore"]
    assert (await client.put("/api/models/config", json={"ponte": corpo})).status == 200

    dopo = await (await client.get("/api/models/config")).json()
    assert dopo["catena"][0]["id"] == "subscription"
    assert dopo["catena"][0]["posizione"] == 1
    assert dopo["adesso"]["chi"] == "subscription"


@pytest.mark.asyncio
async def test_col_ponte_acceso_il_gesto_e_quello_inverso(client, monkeypatch):
    """L'altra direzione, e non è simmetria di cortesia: togliendo
    `ponte.attivo` dalle opzioni dell'add-on si è tolto l'UNICO modo che c'era
    di spegnere il ponte. Un interruttore che si accende e non si spegne è
    peggio di nessun interruttore."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    client.app["catena_modelli"] = ["claude"]
    await client.put("/api/models/config", json={"ponte": {"attivo": True}})

    body = await (await client.get("/api/models/config")).json()
    gesti = [d["azione"] for d in body["adesso"]["diagnosi"] if d["azione"]]
    assert len(gesti) == 1, body["adesso"]["diagnosi"]
    assert gesti[0]["dove"] == ["ponte", "attivo"]
    assert gesti[0]["valore"] is False


@pytest.mark.asyncio
async def test_la_frase_nomina_il_primo_della_catena_del_runtime(client):
    """Non «il primo di chain_order»: il primo di `app["catena_modelli"]`,
    cioè la lista che il router prova davvero."""
    client.app["catena_modelli"] = ["openrouter", "claude"]
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert body["adesso"]["chi"] == "openrouter"
    assert body["adesso"]["nome"] == "OpenRouter"


@pytest.mark.asyncio
async def test_ponte_acceso_senza_token_lo_dichiara_nel_payload(client, monkeypatch):
    """Invariante 5: lo stato «ponte acceso, nessun token» non deve poter
    passare in silenzio.

    Dal Task 14 non è più una perdita (il turno scende alla catena) ma resta un
    fatto che costa, e su questa app di prova la catena è vuota: non risponde
    nessuno, e si dice. La scadenza non compare più QUI -- non c'è nessuna
    attesa da dichiarare quando il piano non riceve niente -- e il test gemello
    sotto la pinna dove adesso vive."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    await client.put("/api/models/config",
                     json={"ponte": {"attivo": True, "scadenza_min": 7}})
    resp = await client.get("/api/models/config")
    body = await resp.json()
    assert body["adesso"]["chi"] is None
    assert any("manca il token" in d["testo"]
               for d in body["adesso"]["diagnosi"]), body["adesso"]["diagnosi"]


@pytest.mark.asyncio
async def test_la_scadenza_del_payload_e_quella_salvata_non_un_cinque_a_mano(client, monkeypatch):
    """Lo stesso `ponte.scadenza_min` che `_enqueue_chat_job` usa per scrivere
    la scadenza del turno, e che dal Task 14 è il tempo dopo il quale il turno
    passa al successivo della catena. Attraversa tutto il payload da una
    lettura sola: la frase in cima e il connettore sotto la riga del piano non
    possono dire due minuti diversi."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")
    await client.put("/api/models/config",
                     json={"ponte": {"attivo": True, "scadenza_min": 7}})
    body = await (await client.get("/api/models/config")).json()
    assert body["adesso"]["chi"] == "subscription"
    assert any("entro 7 minuti" in d["testo"]
               for d in body["adesso"]["diagnosi"]), body["adesso"]["diagnosi"]
    piano = body["catena"][0]
    assert piano["id"] == "subscription" and piano["posizione"] == 1
    assert piano["connettore"] == "se non risponde entro 7 min"


@pytest.mark.asyncio
async def test_un_pannello_chiesto_risponde_SEMPRE_anche_senza_credenziale(client):
    """Nascondere e' comodo per chi capisce e crudele per chi non capisce
    perche' una cosa e' sparita. Il modello e' cliccabile su ogni riga, quindi
    ogni click deve produrre una risposta -- e la risposta la scrive il
    backend, con la stessa parola della riga (`MANCANZE`), non la pagina."""
    body = await (await client.get("/api/models?provider=openrouter")).json()
    assert len(body["providers"]) == 1
    p = body["providers"][0]
    assert p["fonte"] == "assente"
    assert p["modelli"] == [], (
        "un elenco dichiarato inesistente e disegnato lo stesso sarebbe la "
        "pagina che si contraddice in due righe"
    )
    assert p["provenienza"] == (
        "Non c'e' nessun elenco da leggere: manca la chiave.".replace("c'e'", "c'è")
    )
    assert p["dove"] == ["provider_models", "openrouter"], (
        "resta scrivibile: preparare un provider prima di usarlo e' un uso "
        "legittimo, e il campo di testo del pannello e' l'unico modo di farlo"
    )


@pytest.mark.asyncio
async def test_senza_richiesta_non_compare_chi_non_ha_un_elenco(claude_con_elenco):
    """La regola in una riga: chi viene CHIESTO riceve sempre una risposta,
    senza una richiesta compaiono solo quelli per cui un elenco esiste. Senza
    la seconda meta', la lettura completa mostrerebbe cinque pannelli vuoti."""
    body = await (await claude_con_elenco.get("/api/models")).json()
    assert [p["id"] for p in body["providers"]] == ["claude"]
    body = await (await claude_con_elenco.get("/api/models?provider=subscription")).json()
    assert [p["id"] for p in body["providers"]] == ["subscription"]
    assert body["providers"][0]["fonte"] == "assente"
    assert "manca il token" in body["providers"][0]["provenienza"]
    assert body["providers"][0]["modelli"] == [], (
        "i tre alias esistono sempre, ma disegnarli sotto una riga che dice "
        "«non c'e' nessun elenco da leggere» sarebbe la pagina che si "
        "contraddice in due righe"
    )


# ---------------------------------------------------------------------------
# LA PUT RIMETTE IN VIGORE (Task 10)
#
# Fino alla 2.4.1 questa rotta aggiornava `app["models_config"]` e basta. La
# catena del router si costruiva all'avvio, quindi un riordino salvato non
# cambiava il turno successivo; e siccome il GET qui sopra descrive il RUNTIME
# (`app["catena_modelli"]`, che e' la sola misura che ha), ricaricando la
# pagina si rivedeva l'ordine di prima e il salvataggio sembrava perso. C'era
# una riga in pagina che lo confessava: e' uscita con il difetto.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_la_put_rimette_in_vigore_DOPO_aver_aggiornato_l_archivio(client):
    """L'ordine conta: `ricalcola_catena` rilegge `app["models_config"]`, quindi
    chiamarla prima dell'aggiornamento rimetterebbe in vigore l'archivio
    VECCHIO -- un salvataggio che si applica con un giro di ritardo, cioe' un
    difetto peggiore di quello che sostituisce."""
    visto = []
    client.app["ricalcola_catena"] = lambda: visto.append(
        list(client.app["models_config"]["chain_order"]))

    resp = await client.put("/api/models/config",
                            json={"chain_order": ["openrouter", "claude"]})
    assert resp.status == 200
    assert visto == [["openrouter", "claude"]]


@pytest.mark.asyncio
async def test_la_put_non_esplode_su_un_installazione_senza_provider(client):
    """Il primo gesto di chi installa HIRIS. `app["ricalcola_catena"]` puo'
    mancare (nessun `_on_startup`, o un'app costruita da una fixture), e
    l'assenza del runtime da rimettere in vigore non e' un errore: e' 200."""
    assert "ricalcola_catena" not in client.app
    resp = await client.put("/api/models/config", json={"chain_order": ["claude"]})
    assert resp.status == 200
    assert (await resp.json())["chain_order"] == ["claude"]


@pytest.mark.asyncio
async def test_riordinare_e_ricaricare_mostra_l_ordine_NUOVO(client):
    """La promessa dell'utente, dal suo lato: si riordina, si ricarica, e si
    rivede quello che si e' appena fatto. E' la stessa lista che il router usa
    per il prossimo messaggio -- il GET la legge da `app["catena_modelli"]`,
    che il ricalcolo riscrive.

    Qui si usa la funzione VERA (`server._ricalcola_catena`), non una finta:
    di sua natura questa prova esiste per non fidarsi del cablaggio."""
    from hiris.app.llm_router import LLMRouter
    from hiris.app.server import _ricalcola_catena

    class _Runner:
        pass

    router = LLMRouter(claude=_Runner(), openrouter=_Runner(),
                       model_chain=["claude", "openrouter"])
    client.app["llm_router"] = router
    client.app["ricalcola_catena"] = lambda: _ricalcola_catena(client.app)
    client.app["models_config"] = {"chain_order": ["claude", "openrouter"]}
    client.app["catena_modelli"] = ["claude", "openrouter"]
    # Le due credenziali che il GET misura per disegnare le righe: senza,
    # `componi_topologia` sposterebbe OpenRouter fra chi sta fuori e la prova
    # guarderebbe un'altra cosa.
    client.app["openrouter_api_key"] = "sk-or-presente"

    await client.put("/api/models/config",
                     json={"chain_order": ["openrouter", "claude"]})
    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["openrouter", "claude"]
    assert router._chat_policy == ["openrouter", "claude"], (
        "la pagina mostrerebbe un ordine che il router non usa: e' la stessa "
        "divergenza che questa fetta chiude, spostata di un livello"
    )


@pytest.mark.asyncio
async def test_il_connettore_di_ollama_dichiara_il_timeout_DELL_ARCHIVIO(client, monkeypatch):
    """L'altro dei due numeri che il Task 8 aveva lasciato all'ambiente. Adesso
    e' il runner locale a riceverlo dall'archivio (`apply_timeout`, rifatto a
    ogni salvataggio), quindi la pagina lo legge dalla stessa casa: se lo
    prendesse ancora da `OLLAMA_REQUEST_TIMEOUT` prometterebbe un'attesa che
    nessuna richiesta subisce.

    L'ambiente e' messo al CONTRARIO dell'archivio apposta."""
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "777")
    client.app["local_model_url"] = "http://192.168.1.42:11434"
    await client.put("/api/models/config", json={
        "chain_order": ["ollama"],
        "ollama": {"modello": "llama3.1:8b", "timeout_s": 300}})
    client.app["catena_modelli"] = ["ollama"]

    body = await (await client.get("/api/models/config")).json()
    riga = {r["id"]: r for r in body["catena"]}["ollama"]
    assert riga["connettore"] == "se non risponde entro 300 s"


# ---------------------------------------------------------------------------
# Cio' che il traffico vero ha gia' prodotto (Task 11)
#
# La rotta legge `app["registro_esiti"]`, che nasce in `create_app` e viene
# scritto dal ciclo di ripiego del router. Nessuna sonda: la pagina riferisce
# osservazioni, non ne provoca -- sondare cinque provider a ogni apertura
# costerebbe denaro e quota (progetto §11.2).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_il_registro_degli_esiti_esiste_appena_l_app_esiste(client):
    """Nasce in `create_app`, non in `_on_startup`: un add-on senza nessuna
    credenziale ha comunque una pagina Modelli, e quella pagina deve poter
    dire «non l'hai ancora usato» invece di non dire niente. `_on_startup` e'
    anche cio' che OGNI fixture azzera -- un registro che nascesse li'
    avrebbe copertura zero (la lezione del debito E del Task 1)."""
    from hiris.app.esiti_provider import OccurrenceRegistry

    assert isinstance(client.app["registro_esiti"], OccurrenceRegistry)


@pytest.mark.asyncio
async def test_la_riga_riferisce_cio_che_il_registro_ha_visto(client):
    """Il caso del proprietario, dalla rotta: la chiave Claude a credito zero
    (`400 credit balance too low`) mentre OpenRouter serve i turni. Il
    registro e' scritto DA QUI, come lo scriverebbe il router, e la pagina
    riceve le due frasi gia' fatte."""
    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["claude", "openrouter"]
    registro = client.app["registro_esiti"]
    for _ in range(40):
        registro.fallimento("claude", family="credenziale", code=400,
                            message="credit balance too low", durata_s=0.4)
    registro.successo("openrouter")

    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["catena"]}
    assert righe["claude"]["esito"]["famiglia"] == "credenziale"
    assert righe["claude"]["esito"]["da_quante"] == 40
    assert righe["claude"]["stato_testo"].startswith(
        "ha rifiutato le ultime 40 richieste — credito esaurito (400), ")
    assert righe["openrouter"]["stato_testo"].startswith("ha risposto ")


@pytest.mark.asyncio
async def test_senza_osservazioni_la_pagina_non_afferma_niente(client):
    """Lo stato di un add-on appena partito: nessuna osservazione, e la pagina
    lo dice invece di regalare un successo che nessuno ha misurato. E' anche
    la prova che il registro non nasce popolato."""
    client.app["catena_modelli"] = ["claude"]

    body = await (await client.get("/api/models/config")).json()
    riga = {r["id"]: r for r in body["catena"]}["claude"]
    assert riga["esito"] is None
    assert riga["stato_testo"] == "non l'hai ancora usato"


@pytest.mark.asyncio
async def test_la_rotta_legge_l_orologio_e_l_eta_cresce_da_sola(client, monkeypatch):
    """Nessuna nuova chiamata fra le due letture: cambia SOLO l'orologio di
    parete che l'handler legge, e la riga invecchia. Se `adesso` fosse cotto
    dentro `componi_topologia` (o peggio, se il registro si aggiornasse da
    solo), la riga direbbe per sempre «poco fa» -- che e' esattamente la
    freschezza finta che ha fatto sopravvivere il difetto piu' grave della
    settimana a 1207 test."""
    import hiris.app.api.handlers_models as modulo

    client.app["catena_modelli"] = ["claude"]
    orologio = [5_000.0]
    # Il registro dell'app usa `time.time` vero: gli si scrive dentro un esito
    # con una data esplicita, cosi' l'unica variabile del test e' l'orologio
    # dell'handler.
    client.app["registro_esiti"]._per_provider["claude"] = {
        "tipo": "rifiutato", "famiglia": "irraggiungibile", "codice": None,
        "messaggio": "", "quando": 5_000.0, "da_quante": 2, "durata_s": 5.0}
    monkeypatch.setattr(modulo.time, "time", lambda: orologio[0])

    body = await (await client.get("/api/models/config")).json()
    assert {r["id"]: r for r in body["catena"]}["claude"]["stato_testo"] == (
        "non risponde all'indirizzo — ultimo tentativo poco fa")

    orologio[0] += 7200
    body = await (await client.get("/api/models/config")).json()
    assert {r["id"]: r for r in body["catena"]}["claude"]["stato_testo"] == (
        "non risponde all'indirizzo — ultimo tentativo 2 h fa")


@pytest.mark.asyncio
async def test_il_registro_e_lo_stesso_oggetto_che_il_router_scrive(client):
    """Due registri -- uno per il router, uno per la pagina -- sarebbero due
    rappresentazioni dello stesso fatto, e la pagina racconterebbe un traffico
    che non e' quello che c'e' stato. Qui il router e' costruito a mano con il
    registro dell'app, come fa `_on_startup`, e un turno vero lo riempie."""
    from unittest.mock import AsyncMock, MagicMock

    from hiris.app.claude_runner import RunnerBackendError
    from hiris.app.llm_router import LLMRouter

    rotto = MagicMock()
    rotto.chat = AsyncMock(side_effect=RunnerBackendError(
        "giu'", family="modello", code=404))
    buono = MagicMock()
    buono.chat = AsyncMock(return_value="ok")
    router = LLMRouter(claude=rotto, openrouter=buono,
                       model_chain=["claude", "openrouter"],
                       registry=client.app["registro_esiti"])
    await router.chat(model="auto")

    client.app["openrouter_api_key"] = "sk-or-presente"
    client.app["catena_modelli"] = ["claude", "openrouter"]
    body = await (await client.get("/api/models/config")).json()
    righe = {r["id"]: r for r in body["catena"]}
    assert righe["claude"]["stato_testo"].startswith("il modello non esiste più (404), ")
    assert righe["openrouter"]["stato_testo"].startswith("ha risposto ")


def test_l_avvio_consegna_al_router_IL_registro_dell_app():
    """Il cablaggio vero vive in `_on_startup`, che ogni fixture azzera
    (`app.on_startup.clear()`): senza questa guardia sul sorgente,
    `registro=app["registro_esiti"]` si potrebbe cancellare e la suite
    resterebbe verde -- e' la tecnica del Task 6/7 per lo stesso problema.
    Un router costruito SENZA registro non registra niente, e la pagina
    tornerebbe a non sapere niente senza che un solo test cada."""
    import ast
    import inspect

    from hiris.app import server as modulo

    albero = ast.parse(inspect.getsource(modulo))
    costruzioni = [n for n in ast.walk(albero)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "LLMRouter"]
    assert costruzioni, "nessuna costruzione di LLMRouter trovata in server.py"
    for chiamata in costruzioni:
        nomi = {k.arg for k in chiamata.keywords}
        assert "registry" in nomi, (
            "ogni LLMRouter costruito dall'avvio deve ricevere il registro "
            "degli esiti, o il ciclo di ripiego torna a buttare via cio' che "
            "vede"
        )
