"""Il silenzio dichiarato su `chatbots.json`: l'unico rimasto.

Un «silenzio dichiarato» e' una riga di registro che l'avvio scrive quando
incontra un file di un'installazione precedente che nessun codice legge piu'.
Erano dodici. Undici riguardavano gli archivi dismessi, e dal 23/09/2026
`cancella_residui` quei file li cancella: i loro annunci dicevano «il file
resta su disco, intatto» subito prima della cancellazione, o stavano dopo e
non giravano mai. Sono usciti il 02/10/2026 con le ventidue prove che li
fissavano; che l'avvio non prometta piu' cio' che non mantiene lo prova
`tests/test_residui_cancellati.py`, eseguendo l'avvio vero.

Resta `chatbots.json` (con il suo predecessore `agents.json`): non e' fra i
residui che si cancellano, per decisione del proprietario, e il suo annuncio
dice il vero.

Fino al 03/10/2026 il blocco si ritagliava dal testo di `_on_startup` e si
eseguiva isolato; adesso l'app si avvia davvero (`tests/_avvio.py`) sulla
`data_dir` della prova, e si legge il registro di `server.py`.
"""
import logging

import pytest


async def _startup_lines(data_dir, caplog) -> list[str]:
    """Le righe che l'avvio vero ha scritto nel registro di `server.py`."""
    from tests._avvio import SERVER_LOGGER, started_with

    with caplog.at_level(logging.INFO, logger=SERVER_LOGGER):
        async with started_with(data_dir):
            pass
    return [rec.getMessage() for rec in caplog.records
            if rec.name == SERVER_LOGGER]


def _announced(lines) -> bool:
    return any("chatbots.json" in line and "installazione precedente" in line
               for line in lines)


@pytest.mark.asyncio
async def test_chatbots_json_presence_logged_when_file_exists(tmp_path, caplog):
    """Mutazione ESEGUITA (03/10/2026): tolto il `logger.info` del silenzio
    dichiarato -- rossa."""
    (tmp_path / "chatbots.json").write_text("{}")
    assert _announced(await _startup_lines(tmp_path, caplog))


@pytest.mark.asyncio
async def test_agents_json_legacy_presence_logged_when_file_exists(tmp_path, caplog):
    """Il predecessore di chatbots.json (prima della rinomina SP-4 Fase A)
    deve dichiararsi anche da solo, senza che chatbots.json esista.

    Mutazione ESEGUITA (03/10/2026): la condizione guarda il solo
    `chatbots.json` -- rossa."""
    (tmp_path / "agents.json").write_text("{}")
    assert _announced(await _startup_lines(tmp_path, caplog))


@pytest.mark.asyncio
async def test_chatbots_json_silent_when_both_files_absent(tmp_path, caplog):
    """Sull'avvio intero il registro scrive altre righe: si guarda che non
    scriva QUESTA (la prova di prima, sul blocco isolato, guardava il
    silenzio totale del blocco -- che e' la stessa cosa, perche' il blocco
    scrive solo lei).

    Mutazione ESEGUITA (03/10/2026): la condizione resa `if True:` -- rossa."""
    lines = await _startup_lines(tmp_path, caplog)
    assert lines, "il registro dell'avvio non ha catturato niente"
    assert not _announced(lines), (
        "ne' chatbots.json ne' agents.json sul disco -- nessun annuncio"
    )
