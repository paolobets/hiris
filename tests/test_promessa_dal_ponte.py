"""La consegna di un turno di promessa: chi chiude, e cosa resta appeso.

Fetta «le promesse seguono la catena» (22/08/2026). Il turno del ponte
finisce in uno di tre modi, e tutti e tre devono lasciare la promessa in uno
stato che si vede:

  - il modello ha chiamato `conclude` -> la promessa e' gia' chiusa dalla
    rotta MCP, e la consegna non la riapre;
  - il turno finisce senza aver concluso -> fallisce, col motivo che porta
    cio' che il modello aveva detto al suo posto (la forma della v3.9.3);
  - il turno scade -> fallisce dichiarando l'attesa.

Una promessa `in_corso` per sempre e' peggio di una fallita: non si vede.

**`q.submit()` azzera `context_json`.** L'id della promessa sopravvive perche'
l'accodamento lo mette anche in `wake`, che non viene azzerato -- e questo
file e' anche il pin di quella dipendenza: se un giorno lo si togliesse da
`wake` fidandosi del contesto, il primo test qui sotto cadrebbe invece di
lasciar fallire in silenzio ogni promessa servita dal ponte.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.chat_settings import ChatSettings
from hiris.app.reasoning.queue import ReasoningQueue
from hiris.app.schedulatore.archivio import AgendaStore

TOKEN = "token-di-prova-della-consegna"
INTESTAZIONI = {"X-HIRIS-Internal-Token": TOKEN}
ADESSO = 1787324400.0


@pytest_asyncio.fixture
async def consegna(aiohttp_client, tmp_path, monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)

    app = server.create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app["internal_token"] = TOKEN

    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    promesse = AgendaStore(str(tmp_path / "promesse.db"))
    app["reasoning_queue"] = coda
    app["promesse"] = promesse
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    try:
        yield client, coda, promesse
    finally:
        promesse.close()
        coda.close()


def _promessa_in_corso(promesse) -> str:
    ident = promesse.create({
        "specie": "chiedi", "frase": "fra un'ora verifica la temperatura",
        "quando_ts": ADESSO + 10, "domanda": "e' aumentata?", "recapito": None,
    }, now=ADESSO)["promessa"]["id"]
    assert promesse.prendi(ident, now=ADESSO + 11) is True
    return ident


def _accoda_e_prendi(coda, ident: str) -> dict:
    # La coda si giudica con l'orologio VERO (`submit` usa `_now(request)`),
    # mentre le promesse ricevono il loro `adesso` come argomento: le due
    # scale non si mescolano, e una scadenza ancorata a `ADESSO` sarebbe gia'
    # passata.
    adesso = time.time()
    coda.enqueue("promessa", {"promessa_id": ident},
                 {"promessa_id": ident, "history": [], "system_prompt": ""},
                 deadline_ts=adesso + 600, now=adesso)
    return coda.claim(now=adesso + 1)


async def _consegna(client, job, decision):
    return await client.post("/api/reasoning/submit", headers=INTESTAZIONI, json={
        "job_id": job["job_id"], "nonce": job["nonce"], "decision": decision})


@pytest.mark.asyncio
async def test_un_turno_che_finisce_senza_concludere_fa_fallire_la_promessa(consegna):
    """Stessa forma della v3.9.3 sul ramo sincrono: il motivo porta cio' che
    il modello aveva risposto al posto di concludere. Senza, si tornerebbe al
    «non so cosa dirti» che e' costato un'ora di indagine."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    risposta = await _consegna(client, job, {
        "reply": "Ho letto le otto stanze, ma da qui non posso mandarti una notifica."})

    assert risposta.status == 200
    p = promesse.read(ident)
    assert p["stato"] == "fallita"
    assert "non ha concluso" in p["motivo"]
    assert "non posso mandarti una notifica" in p["motivo"]


@pytest.mark.asyncio
async def test_se_concludi_e_gia_arrivato_la_consegna_non_riapre_niente(consegna):
    """`conclude` chiude SUBITO dalla rotta MCP (non aspetta la consegna):
    quando il job si chiude la promessa e' gia' mantenuta, e riaprirla
    cancellerebbe un testo che l'utente puo' gia' aver letto."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)
    promesse.concludi(ident, state="mantenuta", now=ADESSO + 20,
                      text="in bagno +0,4 gradi", avvisare=True)

    await _consegna(client, job, {"reply": "qualunque cosa"})

    p = promesse.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["testo"] == "in bagno +0,4 gradi"


@pytest.mark.asyncio
async def test_una_consegna_senza_risposta_fallisce_lo_stesso_dicendolo(consegna):
    """Il ramo in cui non c'e' proprio niente da riportare: la promessa
    fallisce comunque -- restare `in_corso` sarebbe invisibile -- e il motivo
    torna alla frase di prima invece di inventare un virgolettato vuoto."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    await _consegna(client, job, {})

    p = promesse.read(ident)
    assert p["stato"] == "fallita"
    assert "non ha concluso" in p["motivo"]
    assert "«»" not in p["motivo"]


@pytest.mark.asyncio
async def test_una_consegna_di_chat_non_tocca_le_promesse(consegna):
    """Il ramo della chat resta quello di sempre: un job di chat non deve
    poter far fallire una promessa che sta correndo accanto."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    adesso = time.time()
    coda.enqueue("chat", {}, {"history": []}, deadline_ts=adesso + 600, now=adesso)
    job = coda.claim(now=adesso + 1)

    await _consegna(client, job, {"reply": "ciao"})

    assert promesse.read(ident)["stato"] == "in_corso"


# --- la scadenza: niente resta appeso ---------------------------------------

def test_un_turno_scaduto_sul_piano_fa_fallire_la_promessa(tmp_path):
    """Una promessa `in_corso` per sempre non si vede: `risana()` la
    chiuderebbe solo al prossimo riavvio, cioe' forse mai."""
    from hiris.app.server import _close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        app = {"promesse": promesse,
               "models_config": {"ponte": {"scadenza_min": 10}}}

        _close_expired_promise(app, {"wake": {"promessa_id": ident}})

        p = promesse.read(ident)
        assert p["stato"] == "fallita"
        assert "10 minuti" in p["motivo"]
    finally:
        promesse.close()


def test_una_promessa_gia_conclusa_non_viene_riaperta_dalla_scadenza(tmp_path):
    """`conclude` puo' essere arrivato mentre il turno finiva: riaprirla
    cancellerebbe un testo che l'utente puo' gia' aver letto."""
    from hiris.app.server import _close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        promesse.concludi(ident, state="mantenuta", now=ADESSO + 20,
                          text="tutto fermo", avvisare=False)

        _close_expired_promise({"promesse": promesse, "models_config": {}},
                               {"wake": {"promessa_id": ident}})

        assert promesse.read(ident)["stato"] == "mantenuta"
    finally:
        promesse.close()


def test_un_job_scaduto_senza_promessa_non_esplode(tmp_path):
    from hiris.app.server import _close_expired_promise

    _close_expired_promise({"promesse": None, "models_config": {}}, {"wake": {}})
