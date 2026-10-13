"""Cosa resta nella storia dopo un turno fallito: una regola sola (D-15; Chiusura, 13/10/2026).

Fino a quel giorno il ramo sincrono della chat scriveva la coppia domanda e
risposta solo a turno riuscito, mentre il ponte e il ripiego a scadenza
scrivevano la domanda prima di accodare e saltavano la sola risposta. Ora la
regola e' quella del ponte su ogni strada: la domanda si scrive prima del
turno, la risposta solo se il turno ha risposto davvero. La domanda rimasta
sola la toglie la lettura (`chat_store._purge_toxic_turns`).
"""
import pytest

from hiris.app.api import handlers_chat
from hiris.app.claude_runner import RunnerBackendError
from tests.test_chat_briefing import _build_chat_client


async def _written_after(aiohttp_client, tmp_path, monkeypatch, **runner_attr):
    scritti = []
    monkeypatch.setattr(handlers_chat, "append_messages",
                        lambda messaggi, *a, **kw: scritti.append(
                            [m["role"] for m in messaggi]))
    client, runner = await _build_chat_client(aiohttp_client, tmp_path)
    for nome, valore in runner_attr.items():
        setattr(runner, nome, valore)
    resp = await client.post("/api/chat", json={"message": "accendi la luce"})
    assert resp.status == 200
    return scritti


@pytest.mark.asyncio
async def test_il_ramo_sincrono_scrive_la_domanda_anche_se_il_turno_cade(
        aiohttp_client, tmp_path, monkeypatch):
    """Rossa sul codice di prima: nessuna scrittura."""
    from unittest.mock import AsyncMock
    scritti = await _written_after(
        aiohttp_client, tmp_path, monkeypatch,
        chat=AsyncMock(side_effect=RunnerBackendError("Errore Claude.")))
    assert scritti == [["user"]]


@pytest.mark.asyncio
async def test_un_turno_senza_risposta_non_scrive_la_frase_di_hiris(
        aiohttp_client, tmp_path, monkeypatch):
    """Il router che non ha avuto risposta da nessuno (o che si e' fermato
    dopo una scrittura, D-16) consegna una frase sua: non e' una risposta del
    modello, e in cronologia il turno dopo la rileggerebbe come tale.

    Mutazione ESEGUITA il 13/10/2026: la risposta scritta senza guardare
    `turn.answered` -- rossa."""
    scritti = await _written_after(aiohttp_client, tmp_path, monkeypatch,
                                  last_unanswered=True)
    assert scritti == [["user"]]


@pytest.mark.asyncio
async def test_un_turno_riuscito_scrive_domanda_e_risposta(
        aiohttp_client, tmp_path, monkeypatch):
    scritti = await _written_after(aiohttp_client, tmp_path, monkeypatch)
    assert scritti == [["user"], ["assistant"]]
