"""La rotta della chat risponde gli errori in italiano (C-50; Chiusura, 13/10/2026).

Accanto ai messaggi italiani della stessa rotta ne restavano tre inglesi: il
413 (che la pagina mostra cosi' com'e', `chat/send.js`), il 503 e il 404 del
poll. Il 404 resta UNO per l'id che non c'e' e per l'id di un altro filo
(`chat_thread.unknown_id_text`), o chi prova gli id saprebbe quali sono
altrui.
"""
import pytest
from aiohttp.test_utils import TestClient, TestServer

from tests.test_chat_subscription_path import _make_app


@pytest.mark.asyncio
async def test_il_messaggio_troppo_lungo_si_dice_in_italiano(tmp_path):
    """Rossa sul codice di prima: «message too long (max 4000 chars)»."""
    app, _q, _r, _, _ = _make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "x" * 4001})
        assert resp.status == 413
        assert (await resp.json())["error"] == (
            "Il messaggio è troppo lungo: al massimo 4000 caratteri.")


@pytest.mark.asyncio
async def test_il_poll_risponde_in_italiano(tmp_path):
    app, _q, _r, _, _ = _make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/chat/reply/non-esiste")
        assert resp.status == 404
        assert (await resp.json())["error"] == (
            "non ho nessuna risposta in attesa con quell’identificatore.")
    app, _q, _r, _, _ = _make_app(tmp_path, with_queue=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/chat/reply/non-esiste")
        assert resp.status == 503
        assert (await resp.json())["error"] == "coda dei turni non disponibile"
