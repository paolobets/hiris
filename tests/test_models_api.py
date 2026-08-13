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
        "nascondi_gratuiti", "strategia_ultima", "seminato",
        # cio' che la pagina disegna
        "adesso", "catena", "fuori_catena", "fine_catena",
        # l'ULTIMO residuo dichiarato: esce col Task 13/14, e non e' un
        # doppione esatto di `ponte.attivo` (e' `BRIDGE_ENABLED or
        # _sub_first_class`, quindi chi lo toglie toglie anche l'implicazione)
        "ponte_attivo",
    }
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
    """Le due liste che la pagina disegnera'. Ogni voce ha esattamente DODICI
    campi: se la pagina dovesse aggiungerne uno, lo starebbe calcolando --
    l'invariante 2, rotto.

    Erano sette fino al Task 8, undici dopo. Le voci nuove non sono calcoli,
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
    client.app["ponte_attivo"] = False

    body = await (await client.get("/api/models/config")).json()
    assert [r["id"] for r in body["catena"]] == ["openrouter"]
    assert body["catena"][0]["posizione"] == 1
    assert [r["id"] for r in body["fuori_catena"]] == [
        "claude", "subscription", "openai", "ollama"]
    for r in body["catena"] + body["fuori_catena"]:
        assert set(r.keys()) == {"id", "nome", "modello", "modello_alias",
                                 "natura", "manca", "nota", "connettore",
                                 "connettore_nota", "ha_credenziale",
                                 "posizione", "riordinabile"}
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
    scadenza, non la copia nell'archivio: l'archivio ne tiene una che oggi
    nessun runner legge, e prenderla da li' farebbe promettere alla pagina
    un'attesa diversa da quella vera. Le due letture diventano una sola col
    Task 10."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    monkeypatch.setenv("BRIDGE_DEADLINE_MIN", "9")
    client.app["catena_modelli"] = []
    client.app["ponte_attivo"] = True

    body = await (await client.get("/api/models/config")).json()
    assert body["catena"][0]["id"] == "subscription"
    assert "9 min" in body["catena"][0]["connettore"]


@pytest.mark.asyncio
async def test_una_catena_vuota_non_ha_una_fine(client):
    """`fine_catena` e' la frase che chiude la sequenza: senza sequenza non c'e'
    niente da chiudere, e una riga «se non risponde, la chat da' errore» sotto
    una catena vuota parlerebbe di un anello che non esiste."""
    client.app["catena_modelli"] = []
    client.app["ponte_attivo"] = False
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
async def test_list_models_non_dice_piu_l_appartenenza_alla_catena(client):
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
    body = await (await client.get("/api/models")).json()
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
    assert set(p) == {"id", "nome", "alias", "fonte", "provenienza",
                      "spiegazione", "quando", "dove", "scelto", "casella",
                      "modelli"}
    # Anthropic non pubblica un elenco: questa lista e' scritta a mano e
    # invecchia. Chiamarla «viva» per farla sembrare migliore sarebbe una
    # parola piu' larga del fatto.
    assert p["fonte"] == "riserva"
    assert "Anthropic non pubblica un elenco" in p["provenienza"]
    assert p["dove"] == ["provider_models", "claude"]


@pytest.mark.asyncio
async def test_il_pannello_del_piano_offre_tre_alias_e_non_si_scrive(client, monkeypatch):
    """`agent/runner.modello_cli` riduce QUALUNQUE modello risolto a
    opus/haiku/sonnet: offrire `claude-opus-4-7` sul piano sarebbe una
    precisione finta. E non c'e' niente da salvare -- il modello del piano e'
    un effetto di quello di Claude API -- quindi `dove` e' vuoto: un pannello
    che offrisse di scriverlo manderebbe una PUT che nessuno legge."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-presente")
    body = await (await client.get("/api/models?provider=subscription")).json()
    p = body["providers"][0]
    assert [v["valore"] for v in p["modelli"]] == ["haiku", "sonnet", "opus"]
    assert p["dove"] == []
    assert p["alias"] is True
    assert p["fonte"] == "fissa", (
        "i tre alias non sono un ripiego: non descrivono il catalogo di "
        "qualcun altro, sono l'insieme esatto che modello_cli sa produrre"
    )
    assert "segue il modello di Claude API" in p["spiegazione"]
    assert p["scelto"] == "sonnet", (
        "senza un modello scelto per Claude API, resolve_model risolve su "
        "sonnet e il ponte usa quell'alias"
    )


@pytest.mark.asyncio
async def test_il_pannello_di_claude_apre_anche_senza_la_chiave(client, monkeypatch):
    """L'eccezione che il progetto §6.4 non poteva vedere: la regola non e'
    «senza credenziale niente pannello», e' «senza ELENCO niente pannello», e
    l'elenco di Claude non viene dal provider. Su un'installazione col solo
    Piano Claude Max questo e' l'UNICO posto da cui si sceglie il modello del
    piano: chiuderlo li' significherebbe rispondere «da nessuna parte» alla
    prima domanda del proprietario."""
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    client.app["claude_runner"] = None
    body = await (await client.get("/api/models?provider=claude")).json()
    assert [p["id"] for p in body["providers"]] == ["claude"]
    # E non basta che la voce ci sia: deve portare l'ELENCO. Una voce presente
    # ma dichiarata «assente», senza modelli, sarebbe la stessa porta chiusa
    # con un cartello diverso.
    p_claude = body["providers"][0]
    assert p_claude["fonte"] == "riserva"
    assert [v["valore"] for v in p_claude["modelli"] if v["valore"]] == [
        "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"]
    assert p_claude["dove"] == ["provider_models", "claude"]


@pytest.mark.asyncio
async def test_la_voce_auto_e_la_stringa_vuota_e_dice_a_cosa_si_risolve(client):
    """Salvare la parola "auto" e' un difetto: `resolve_model("auto", "chat",
    "auto")` restituisce "auto" e la richiesta parte con `model="auto"`. La
    voce c'e' -- e' una scelta legittima -- ma il suo valore e' "" e la sua
    nota dice a quale modello si risolve oggi."""
    body = await (await client.get("/api/models?provider=claude")).json()
    prima = body["providers"][0]["modelli"][0]
    assert prima["valore"] == ""
    assert prima["nota"].startswith("scelto da HIRIS")
    assert "claude-" in prima["nota"]
    assert "auto" not in [v["valore"] for v in body["providers"][0]["modelli"]]


@pytest.mark.asyncio
async def test_senza_provider_risponde_per_tutti_quelli_che_hanno_un_elenco(client):
    """La forma storica della rotta resta: un client diverso dalla pagina
    esiste, e una rotta che cambia significato in silenzio e' la cosa che
    questa fetta ritira."""
    body = await (await client.get("/api/models")).json()
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
async def test_il_pannello_confessa_i_DUE_modi_in_cui_il_modello_di_claude_si_applica(client):
    """Invariante 4, reso visibile invece che taciuto: lo stesso valore ha
    effetto IMMEDIATO sul ponte (`_enqueue_chat_job` rilegge
    `app["models_config"]` a ogni turno) e SOLO AL RIAVVIO sull'API (i runner
    lo ricevono alla costruzione). La pagina non puo' risolverlo -- lo fa il
    Task 10 -- ma puo' smettere di dichiarare una cosa sola su un valore che
    se ne comporta due. Quel giorno questa stringa diventa "" e la pagina tace
    senza essere toccata."""
    body = await (await client.get("/api/models?provider=claude")).json()
    quando = body["providers"][0]["quando"]
    assert "dal prossimo messaggio" in quando
    assert "dal riavvio dell'add-on" in quando

    # Sul piano non c'e' niente da salvare, quindi non c'e' niente da
    # confessare: una didascalia sopra un pannello che non scrive sarebbe una
    # frase su un gesto che non esiste.
    body = await (await client.get("/api/models?provider=subscription")).json()
    assert body["providers"] == [] or body["providers"][0]["quando"] == ""


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
    assert p["provenienza"] == "Non c'e' nessun elenco da leggere: manca la chiave.".replace("c'e'", "c'è")
    assert p["dove"] == ["provider_models", "openrouter"], (
        "resta scrivibile: preparare un provider prima di usarlo e' un uso "
        "legittimo, e il campo di testo del pannello e' l'unico modo di farlo"
    )


@pytest.mark.asyncio
async def test_senza_richiesta_non_compare_chi_non_ha_un_elenco(client):
    """La regola in una riga: chi viene CHIESTO riceve sempre una risposta,
    senza una richiesta compaiono solo quelli per cui un elenco esiste. Senza
    la seconda meta', la lettura completa mostrerebbe cinque pannelli vuoti."""
    body = await (await client.get("/api/models")).json()
    assert [p["id"] for p in body["providers"]] == ["claude"]
    body = await (await client.get("/api/models?provider=subscription")).json()
    assert [p["id"] for p in body["providers"]] == ["subscription"]
    assert body["providers"][0]["fonte"] == "assente"
    assert "manca il token" in body["providers"][0]["provenienza"]
    assert body["providers"][0]["modelli"] == [], (
        "i tre alias esistono sempre, ma disegnarli sotto una riga che dice "
        "«non c'e' nessun elenco da leggere» sarebbe la pagina che si "
        "contraddice in due righe"
    )
