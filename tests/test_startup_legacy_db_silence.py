"""L'avvio non annuncia piu' nessun file di un'installazione precedente.

Un «silenzio dichiarato» era una riga di registro che l'avvio scriveva quando
incontrava un file di un'installazione precedente che nessun codice legge piu'.
Erano dodici. Undici riguardavano gli archivi dismessi, e dal 23/09/2026
`cancella_residui` quei file li cancella: i loro annunci dicevano «il file
resta su disco, intatto» subito prima della cancellazione, o stavano dopo e
non giravano mai. Sono usciti il 02/10/2026 con le ventidue prove che li
fissavano; che l'avvio non prometta piu' cio' che non mantiene lo prova
`tests/test_residui_cancellati.py`, eseguendo l'avvio vero.

L'ultimo era `chatbots.json`, che restava per decisione del proprietario
(D6 della Tappa 8: prima si guarda, poi si cancella). Lo Sprint gliel'ha
mostrato l'08/10/2026, e da li' e' un residuo come il suo predecessore
`agents.json`: l'avvio li cancella entrambi e lo dice, e l'annuncio
(`announce_chatbots_json`) e' uscito.

Fino al 03/10/2026 il blocco si ritagliava dal testo di `_on_startup` e si
eseguiva isolato; adesso l'app si avvia davvero (`tests/_avvio.py`) sulla
`data_dir` della prova, e si legge il registro di `conservazione.py`.
"""
import logging

import pytest

CONSERVATION_LOGGER = "hiris.app.conservazione"


async def _startup_lines(data_dir, caplog) -> list[str]:
    """Le righe che l'avvio vero ha scritto nei registri di `server.py` e
    della conservazione: l'annuncio sta nel secondo, ma su una casa pulita
    il secondo tace, e la prova che il registro catturi qualcosa la da' il
    primo."""
    from tests._avvio import SERVER_LOGGER, started_with

    with caplog.at_level(logging.INFO, logger=SERVER_LOGGER), \
            caplog.at_level(logging.INFO, logger=CONSERVATION_LOGGER):
        async with started_with(data_dir):
            pass
    return [rec.getMessage() for rec in caplog.records
            if rec.name in (SERVER_LOGGER, CONSERVATION_LOGGER)]


def _announced(lines) -> bool:
    return any("chatbots.json" in line and "installazione precedente" in line
               for line in lines)


@pytest.mark.asyncio
async def test_agents_json_e_chatbots_json_si_cancellano(tmp_path, caplog):
    """**Rovesciata due volte nella Tappa 8 (Task 7, D6).** Fino all'08/10/2026
    `agents.json` si annunciava e restava; poi si cancellava e
    `chatbots.json` restava, annunciato. Adesso il proprietario lo ha visto, e
    si cancellano tutti e due: l'avvio dice cosa ha cancellato, e non
    annuncia piu' un file che resta.

    Mutazione ESEGUITA (08/10/2026): tolto `"chatbots.json"` da
    `RESIDUI_DISMESSI` -- rossa (il file resta su disco)."""
    (tmp_path / "agents.json").write_text("{}")
    (tmp_path / "chatbots.json").write_text("{}")
    lines = await _startup_lines(tmp_path, caplog)

    for name in ("agents.json", "chatbots.json"):
        assert not (tmp_path / name).exists(), name
        assert any(line.startswith(f"{name} cancellato") for line in lines), lines
    assert not _announced(lines)
    assert not any("resta" in line and ".json" in line for line in lines), lines


@pytest.mark.asyncio
async def test_chatbots_json_silent_when_both_files_absent(tmp_path, caplog):
    """Su una casa pulita l'avvio non dice niente di questi file.

    Mutazione ESEGUITA (03/10/2026): la condizione resa `if True:` -- rossa.
    Dall'08/10/2026 l'annuncio non c'e' piu': la prova resta perche' la stessa
    frase non torni."""
    lines = await _startup_lines(tmp_path, caplog)
    assert lines, "il registro dell'avvio non ha catturato niente"
    assert not _announced(lines), (
        "ne' chatbots.json ne' agents.json sul disco -- nessun annuncio"
    )
