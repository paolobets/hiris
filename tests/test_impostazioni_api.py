"""fetta E5 Task 2: le due rotte che ridanno una superficie alle impostazioni
della chat -- `GET/PUT /api/impostazioni-chat`.

Il punto di questi test non e' la forma del JSON: e' che un tester UAT possa
cambiare i sette campi senza scrivere a mano `/data/impostazioni_chat.json`, e
che quel cambiamento (a) sia visibile subito nella chat, senza riavvio, (b)
sopravviva al riavvio, (c) non possa passare a meta' -- un corpo sbagliato
lascia il file esattamente com'era, e dice quale campo non va.
"""
import json

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from hiris.app.api.handlers_impostazioni import (
    CAMPI, MAX_CARATTERI_MODELLO, MAX_CARATTERI_PROMPT, MODI_RISPOSTA,
)
from hiris.app.chat_store import close_all_stores
from hiris.app.impostazioni_chat import DEFAULT_SYSTEM_PROMPT, ImpostazioniChat
from hiris.app.server import create_app

ROTTA = "/api/impostazioni-chat"


@pytest.fixture(autouse=True)
def reset_chat_stores():
    """Chiude le connessioni SQLite dopo ogni test (file-lock su Windows)."""
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    """L'app VERA (`create_app`), non un'app costruita a mano con le sole due
    rotte: la rotta nuova deve passare dagli stessi middleware di ogni altra
    (`internal_auth_middleware`, `csrf_middleware`), e un test che le
    scavalcasse non direbbe niente su cio' che accade in produzione."""
    app = create_app()
    app["impostazioni_chat"] = ImpostazioniChat()
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


def _file(client) -> str:
    return str(client.app["data_dir"]) + "/impostazioni_chat.json"


def _su_disco(client) -> dict | None:
    try:
        with open(_file(client), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_su_data_vuota_restituisce_i_default_nel_codice(client):
    resp = await client.get(ROTTA)
    assert resp.status == 200
    body = await resp.json()
    default = ImpostazioniChat()
    assert body["nome"] == default.nome
    assert body["system_prompt"] == DEFAULT_SYSTEM_PROMPT
    assert body["model"] == default.model
    assert body["response_mode"] == default.response_mode
    assert body["thinking_budget"] == default.thinking_budget
    assert body["max_chat_turns"] == default.max_chat_turns
    assert body["restrict_to_home"] == default.restrict_to_home


@pytest.mark.asyncio
async def test_get_porta_anche_i_modi_ammessi_e_il_prompt_di_default(client):
    """La pagina non deve tenere una copia propria ne' dei valori ammessi per
    `response_mode` ne' del prompt di default: invecchierebbero al primo
    cambiamento nel codice. Viaggiano nel payload."""
    body = await (await client.get(ROTTA)).json()
    assert body["modi_risposta"] == list(MODI_RISPOSTA)
    assert body["default_system_prompt"] == DEFAULT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_get_mostra_cio_che_la_chat_sta_usando_non_il_disco(client):
    """`app["impostazioni_chat"]` e' l'oggetto che `handlers_chat.py` rilegge a
    ogni turno: la pagina legge quello, quindi non puo' mostrare qualcosa di
    diverso da cio' che e' in vigore."""
    client.app["impostazioni_chat"] = ImpostazioniChat(nome="Solo in memoria")
    body = await (await client.get(ROTTA)).json()
    assert body["nome"] == "Solo in memoria"


# ---------------------------------------------------------------------------
# PUT: persiste, aggiorna a caldo, sopravvive al riavvio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_persiste_e_aggiorna_a_caldo_le_impostazioni_in_memoria(client):
    nuove = {
        "nome": "Casa",
        "system_prompt": "Sei utile e conciso.",
        "model": "claude-haiku-4-5-20251001",
        "response_mode": "compact",
        "thinking_budget": 1024,
        "max_chat_turns": 5,
        "restrict_to_home": True,
    }
    resp = await client.put(ROTTA, json=nuove)
    assert resp.status == 200
    body = await resp.json()
    assert body["ok"] is True

    # (a) hot-update: senza questo, il salvataggio riesce e la chat continua a
    # usare i valori vecchi fino al riavvio dell'add-on.
    in_memoria = client.app["impostazioni_chat"]
    assert in_memoria.nome == "Casa"
    assert in_memoria.system_prompt == "Sei utile e conciso."
    assert in_memoria.model == "claude-haiku-4-5-20251001"
    assert in_memoria.response_mode == "compact"
    assert in_memoria.thinking_budget == 1024
    assert in_memoria.max_chat_turns == 5
    assert in_memoria.restrict_to_home is True

    # (b) persistenza: il file c'e' ed e' completo.
    assert _su_disco(client) == nuove


@pytest.mark.asyncio
async def test_put_sopravvive_al_riavvio(client, tmp_path):
    """Il "riavvio" e' esattamente cio' che fa `server._on_startup`:
    `ImpostazioniChat.carica(data_dir)` su una `/data` che ha gia' il file."""
    await client.put(ROTTA, json={"nome": "Dopo il riavvio", "max_chat_turns": 7})
    dopo_riavvio = ImpostazioniChat.carica(str(tmp_path))
    assert dopo_riavvio.nome == "Dopo il riavvio"
    assert dopo_riavvio.max_chat_turns == 7
    assert dopo_riavvio == client.app["impostazioni_chat"]


@pytest.mark.asyncio
async def test_put_scrive_in_modo_atomico_e_non_lascia_il_temporaneo(client):
    """Il `.tmp` non deve sopravvivere alla scrittura: se ci fosse, sarebbe la
    prova che il `os.replace` non e' avvenuto e che il file finale puo' essere
    stato scritto sul posto (quindi troncabile a meta')."""
    import os
    await client.put(ROTTA, json={"nome": "Atomico"})
    assert os.path.exists(_file(client))
    assert not os.path.exists(_file(client) + ".tmp")
    # Rileggibile come JSON completo: tutti e sette i campi, mai un troncone.
    assert sorted(_su_disco(client)) == sorted(CAMPI)


@pytest.mark.asyncio
async def test_put_di_un_solo_campo_non_azzera_gli_altri(client):
    await client.put(ROTTA, json={"nome": "Primo", "max_chat_turns": 9})
    await client.put(ROTTA, json={"nome": "Secondo"})
    corrente = client.app["impostazioni_chat"]
    assert corrente.nome == "Secondo"
    assert corrente.max_chat_turns == 9, "un campo assente conserva il valore corrente"


@pytest.mark.asyncio
async def test_put_con_system_prompt_vuoto_ripristina_il_default(client):
    await client.put(ROTTA, json={"system_prompt": "Un prompt personale."})
    assert client.app["impostazioni_chat"].system_prompt == "Un prompt personale."

    resp = await client.put(ROTTA, json={"system_prompt": "   "})
    assert resp.status == 200
    assert client.app["impostazioni_chat"].system_prompt == DEFAULT_SYSTEM_PROMPT
    assert (await resp.json())["system_prompt"] == DEFAULT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_put_con_model_vuoto_torna_ad_auto(client):
    await client.put(ROTTA, json={"model": "claude-opus-4-7"})
    resp = await client.put(ROTTA, json={"model": ""})
    assert resp.status == 200
    assert client.app["impostazioni_chat"].model == "auto"


# ---------------------------------------------------------------------------
# PUT: CSRF
# ---------------------------------------------------------------------------

@pytest.fixture
def csrf_stretto(monkeypatch):
    """Annulla il `HIRIS_ALLOW_NO_CSRF=1` che conftest.py mette per l'intera
    suite, cosi' il middleware torna a bloccare come in produzione."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_CSRF", "")
    yield


@pytest.mark.asyncio
async def test_put_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    """La rotta nuova passa dallo stesso `csrf_middleware` delle altre: non ha
    un'autenticazione propria. E' anche il motivo per cui la pagina manda
    sempre l'header (impostazioni-route.js, `api()`)."""
    resp = await client.put(ROTTA, json={"nome": "Da un sito ostile"})
    assert resp.status == 403
    assert (await resp.json())["error"] == "csrf_required"
    assert _su_disco(client) is None, "un 403 non deve aver toccato il disco"


@pytest.mark.asyncio
async def test_put_con_x_requested_with_passa_anche_a_csrf_stretto(client, csrf_stretto):
    resp = await client.put(ROTTA, json={"nome": "Dalla pagina"},
                            headers={"X-Requested-With": "fetch"})
    assert resp.status == 200
    assert client.app["impostazioni_chat"].nome == "Dalla pagina"


# ---------------------------------------------------------------------------
# PUT: validazione, campo per campo
# ---------------------------------------------------------------------------

CORPI_RIFIUTATI = [
    ("thinking_budget", {"thinking_budget": -1}, "negativo"),
    ("thinking_budget", {"thinking_budget": "1024"}, "numero intero"),
    ("thinking_budget", {"thinking_budget": True}, "numero intero"),
    ("max_chat_turns", {"max_chat_turns": -5}, "negativo"),
    ("max_chat_turns", {"max_chat_turns": 3.5}, "numero intero"),
    ("restrict_to_home", {"restrict_to_home": "si"}, "true o false"),
    ("restrict_to_home", {"restrict_to_home": 1}, "true o false"),
    ("response_mode", {"response_mode": "prolisso"}, "ammette solo"),
    ("nome", {"nome": "   "}, "non può essere vuoto"),
    ("nome", {"nome": 42}, "deve essere testo"),
    ("model", {"model": "claude opus"}, "spazi o caratteri di controllo"),
    ("model", {"model": "x" * (MAX_CARATTERI_MODELLO + 1)}, "supera i"),
    ("system_prompt", {"system_prompt": "x" * (MAX_CARATTERI_PROMPT + 1)}, "supera i"),
    ("modello", {"modello": "claude-opus-4-7"}, "Campi non riconosciuti"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("campo,corpo,frammento", CORPI_RIFIUTATI)
async def test_put_malformato_e_400_parlante_e_non_tocca_il_file(
    client, campo, corpo, frammento,
):
    """Ogni rifiuto deve (1) essere un 400, non un 500 e non un 200 silenzioso;
    (2) NOMINARE il campo che non va e dire cosa non va; (3) lasciare il file su
    disco esattamente com'era -- la validazione avviene per intero prima di
    qualunque scrittura, quindi non esiste un salvataggio a meta'."""
    await client.put(ROTTA, json={"nome": "Valore precedente"})
    prima = _su_disco(client)

    resp = await client.put(ROTTA, json=corpo)
    assert resp.status == 400
    body = await resp.json()
    assert body["campo"] == campo
    assert frammento in body["error"], body["error"]
    assert campo in body["error"], "il messaggio deve nominare il campo"

    assert _su_disco(client) == prima, "un corpo rifiutato non deve toccare il file"
    assert client.app["impostazioni_chat"].nome == "Valore precedente"


@pytest.mark.asyncio
async def test_put_con_corpo_non_json_e_400(client):
    resp = await client.put(ROTTA, data="non sono json",
                            headers={"Content-Type": "application/json"})
    assert resp.status == 400
    assert "JSON" in (await resp.json())["error"]
    assert _su_disco(client) is None


@pytest.mark.asyncio
async def test_put_con_corpo_che_non_e_un_oggetto_e_400(client):
    resp = await client.put(ROTTA, json=["nome", "HIRIS"])
    assert resp.status == 400
    assert "oggetto JSON" in (await resp.json())["error"]


@pytest.mark.asyncio
async def test_un_errore_di_scrittura_non_dice_salvato(client, monkeypatch):
    """Il silenzio peggiore sarebbe un 200 davanti a un disco che non ha
    accettato niente: si risponde 500 dichiarando il guasto, e le impostazioni
    in memoria restano quelle di prima (nessun hot-update)."""
    def esplodi(self, data_dir):
        raise OSError("disco pieno")

    monkeypatch.setattr(ImpostazioniChat, "salva", esplodi)
    resp = await client.put(ROTTA, json={"nome": "Non arrivera' mai"})
    assert resp.status == 500
    assert "non è stato possibile" in (await resp.json())["error"].lower()
    assert client.app["impostazioni_chat"].nome == "HIRIS"


# ---------------------------------------------------------------------------
# Le due rotte esistono davvero nell'app, coi metodi giusti
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_le_due_rotte_sono_registrate_su_create_app():
    app = create_app()
    registrate = {
        (r.method, r.resource.canonical)
        for r in app.router.routes() if r.resource is not None
    }
    assert ("GET", ROTTA) in registrate
    assert ("PUT", ROTTA) in registrate


@pytest.mark.asyncio
async def test_i_metodi_non_previsti_non_esistono(client):
    """Non c'e' un POST ne' un DELETE: le impostazioni non si creano e non si
    cancellano, esistono sempre (i default vivono nel codice)."""
    assert (await client.post(ROTTA, json={})).status == 405
    assert (await client.delete(ROTTA)).status == 405


@pytest.mark.asyncio
async def test_client_diretto_senza_token_resta_negato(tmp_path, monkeypatch):
    """La rotta nuova non ha un'autenticazione propria: eredita il
    rifiuto-per-default di `internal_auth_middleware` come tutte le altre."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "")
    app = create_app()
    app["impostazioni_chat"] = ImpostazioniChat()
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()
    async with TestClient(TestServer(app)) as c:
        assert (await c.get(ROTTA)).status == 401
