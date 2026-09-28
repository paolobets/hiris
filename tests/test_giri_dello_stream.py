"""I giri del ponte, letti dallo stream VERO della CLI.

Fino al 28/09/2026 `_measure_turn` dichiarava «i pesi per giro non esistono
da questa parte». Falso: ogni evento `assistant` porta `message.usage`, e una
chiamata all'API emette piu' eventi con lo stesso `message.id` (uno per
blocco). Il giro e' il `message.id`, non l'evento.

Il campione e' un flusso VERO della CLI 2.1.283 (un turno, uno strumento, due
chiamate), ripulito da percorsi e identificativi.
"""
import json
import pathlib

from hiris.app.agent import runner

CAMPIONE = (pathlib.Path(__file__).parent / "fixtures"
            / "stream_due_giri_cli_2_1_283.ndjson")


def _campione() -> str:
    return CAMPIONE.read_text(encoding="utf-8")


def test_due_chiamate_sono_DUE_giri_non_quattro_eventi():
    """Mutazione ESEGUITA: un giro per evento `assistant` -- rossa (4 giri)."""
    e = runner.read_stream(_campione())
    assert len(e.exchanges) == 2
    assert e.exchanges[0]["input_tokens"] == 10
    assert e.exchanges[0]["cache_write_tokens"] == 11368
    assert e.exchanges[0]["cache_ttl"] == "1h"
    assert e.exchanges[1]["cache_read_tokens"] == 29090
    assert len(e.exchanges) == e.num_exchanges


def test_l_uscita_per_giro_e_NULL_e_quella_del_turno_viene_dal_result():
    """Nello stream `output_tokens` per evento vale 1: e' il conteggio
    parziale dello streaming, non l'uscita del giro.

    Mutazione ESEGUITA: copiare `output_tokens` dall'evento -- rossa."""
    e = runner.read_stream(_campione())
    assert all(g["output_tokens"] is None for g in e.exchanges)
    assert e.output_tokens == 623


def test_il_costo_a_listino_viene_da_modelUsage():
    """Il campione porta `modelUsage[...].costUSD = 0.0695702`.

    Mutazione ESEGUITA: leggerlo da `result.total_cost_usd` (assente) -- rossa."""
    e = runner.read_stream(_campione())
    assert e.list_cost_usd == 0.0695702


def test_senza_modelUsage_il_costo_a_listino_e_NULL():
    """Mutazione ESEGUITA: `list_cost_usd = 0.0` di default invece di `None`
    -- rossa (NULL non e' zero, vedi `usage/giro.py`)."""
    e = runner.read_stream(json.dumps({"type": "result", "usage": {}}))
    assert e.list_cost_usd is None


def test_ogni_giro_sa_quante_chiamate_MCP_ha_fatto():
    """Serve a distribuire i risultati degli strumenti sui giri (Task 8):
    i risultati delle chiamate del giro 1 arrivano al modello al giro 2.

    Mutazione ESEGUITA: contare anche gli strumenti propri della CLI -- rossa."""
    e = runner.read_stream(_campione())
    assert [g["mcp_calls"] for g in e.exchanges] == [1, 0]


def test_uno_strumento_della_CLI_non_e_una_chiamata_MCP():
    """Mutazione ESEGUITA: contare ogni `tool_use` come chiamata MCP, senza
    filtrare sul prefisso `mcp__hiris__` -- rossa (mcp_calls diventerebbe 1)."""
    righe = [json.dumps({"type": "assistant", "message": {
        "id": "msg_X", "content": [
            {"type": "tool_use", "id": "t1", "name": "ToolSearch", "input": {}}],
        "usage": {"input_tokens": 1}}})]
    e = runner.read_stream("\n".join(righe))
    assert e.exchanges[0]["mcp_calls"] == 0


def test_uno_stream_senza_assistant_ha_zero_giri_e_non_solleva():
    """CLI uccisa a meta': nessun evento assistant, nessun result.

    Mutazione ESEGUITA: inizializzare `exchanges` con un elemento fittizio
    invece di lista vuota -- rossa."""
    e = runner.read_stream(json.dumps({"type": "system", "subtype": "init"}))
    assert e.exchanges == []
    assert e.output_tokens is None


def test_un_messaggio_senza_id_non_si_fonde_con_un_altro():
    """Un evento senza `message.id` e' un giro a se': fonderlo col
    precedente direbbe un giro dove forse ce n'erano due.

    Mutazione ESEGUITA: fondere ogni evento senza id nell'ultimo giro aperto
    (`occurrence.exchanges[-1]` quando `message_id` non e' una stringa) --
    rossa (un solo giro, `input_tokens == 1`: il secondo evento si fonde nel
    primo invece di aprirne uno nuovo)."""
    righe = [json.dumps({"type": "assistant", "message": {
                 "content": [], "usage": {"input_tokens": 1}}}),
             json.dumps({"type": "assistant", "message": {
                 "content": [], "usage": {"input_tokens": 2}}})]
    e = runner.read_stream("\n".join(righe))
    assert [g["input_tokens"] for g in e.exchanges] == [1, 2]


def test_un_token_malformato_nello_stream_non_fa_cadere_il_turno():
    """Fix round 1 (Task 5, coordinatore): `read_stream` e' documentata come
    "non solleva mai" -- prima di questo fix un `input_tokens` non numerico
    nello stream vero (un aggiornamento della CLI che cambia forma) faceva
    risalire un `ValueError`/`TypeError` fino a `_invoca`, che non lo cattura.

    Mutazione ESEGUITA: ripristinato `giro._int_or_none` a `int(value)`
    senza `try/except` -- rossa (`read_stream` solleva `ValueError` invece
    di restituire un giro con `input_tokens is None`)."""
    riga = json.dumps({"type": "assistant", "message": {
        "id": "msg_X", "content": [],
        "usage": {"input_tokens": "n/a"}}})
    e = runner.read_stream(riga)
    assert e.exchanges[0]["input_tokens"] is None
