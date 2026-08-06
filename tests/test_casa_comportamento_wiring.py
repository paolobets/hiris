import os
from unittest.mock import AsyncMock

import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.server import sentinella_comportamento


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


@pytest.fixture
def cartella(tmp_path):
    c = tmp_path / "ha"
    c.mkdir()
    (c / "automations.yaml").write_text("- id: '1'\n  alias: Sveglia\n", encoding="utf-8")
    (c / "scripts.yaml").write_text("saluta:\n  alias: Saluta\n", encoding="utf-8")
    return c


def _client():
    client = AsyncMock()
    client.get_states = AsyncMock(return_value=[])
    return client


@pytest.mark.asyncio
async def test_la_prima_chiamata_legge_sempre(archivio, cartella):
    client = _client()
    guarda = sentinella_comportamento(client, archivio, cartella)
    assert await guarda() is True
    assert client.get_states.await_count == 1


@pytest.mark.asyncio
async def test_se_i_file_non_cambiano_non_si_rilegge(archivio, cartella):
    client = _client()
    guarda = sentinella_comportamento(client, archivio, cartella)
    await guarda()
    assert await guarda() is False
    assert await guarda() is False
    assert client.get_states.await_count == 1


@pytest.mark.asyncio
async def test_un_file_toccato_fa_rileggere(archivio, cartella):
    client = _client()
    guarda = sentinella_comportamento(client, archivio, cartella)
    await guarda()
    f = cartella / "scripts.yaml"
    os.utime(f, (f.stat().st_atime + 10, f.stat().st_mtime + 10))
    assert await guarda() is True
    assert client.get_states.await_count == 2


@pytest.mark.asyncio
async def test_senza_cartella_non_esplode(archivio):
    """Fuori dal Supervisor la cartella di HA non c'e': si legge comunque lo
    stato, e tutte le voci risultano senza corpo. Non e' un guasto."""
    client = _client()
    guarda = sentinella_comportamento(client, archivio, None)
    assert await guarda() is True


@pytest.mark.asyncio
async def test_senza_cartella_si_rilegge_una_volta_sola(archivio):
    """Senza cartella l'impronta e' sempre None: senza una difesa esplicita
    contro il "mai letto", guarda() la scambierebbe per "gia' letta,
    invariata" solo al secondo giro, e per "mai letta" al primo -- in
    realta' e' l'opposto, e senza distinguerli si rileggerebbe a ogni
    chiamata invece che una volta sola."""
    client = _client()
    guarda = sentinella_comportamento(client, archivio, None)
    assert await guarda() is True
    assert await guarda() is False
    assert await guarda() is False
    assert client.get_states.await_count == 1


@pytest.mark.asyncio
async def test_una_rilettura_fallita_non_blocca_le_successive(archivio, cartella):
    """Se la sentinella memorizzasse l'mtime prima di aver letto davvero, un
    guasto passeggero congelerebbe il comportamento fino al prossimo tocco."""
    client = _client()
    client.get_states = AsyncMock(side_effect=[OSError("HA giu'"), []])
    guarda = sentinella_comportamento(client, archivio, cartella)
    assert await guarda() is False      # fallita, e lo dice
    assert await guarda() is True       # riprova senza aspettare un tocco
