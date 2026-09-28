"""I token di UN giro, letti dove il fornitore li mette.

Una funzione per famiglia di risposta, importata da chi ne ha bisogno: il
runner Anthropic, il runner della catena e la lettura dello stream del ponte.
Tre letture scritte a mano diverrebbero tre verita' (spec §3, §4).
"""
from openai.types import CompletionUsage

from hiris.app.usage.giro import (
    anthropic_turn_tokens,
    cache_ttl,
    openai_turn_tokens,
    payload_rows_ponte,
)


def test_la_durata_della_cache():
    """Mutazione ESEGUITA: restituire «1h» anche col solo 5m -- rossa."""
    assert cache_ttl(0, 19510) == "1h"
    assert cache_ttl(300, 0) == "5m"
    assert cache_ttl(300, 19510) == "misto"
    assert cache_ttl(0, 0) is None
    assert cache_ttl(None, None) is None


def test_anthropic_da_DIZIONARIO_come_nello_stream_del_ponte():
    """La forma vera di un evento `assistant` della CLI 2.1.283
    (tests/fixtures/stream_due_giri_cli_2_1_283.ndjson).

    Mutazione ESEGUITA: leggere `cache_creation_input_tokens` come letture -- rossa."""
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 11368,
             "cache_read_input_tokens": 17722, "output_tokens": 1,
             "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 11368}}
    t = anthropic_turn_tokens(usage)
    assert t == {"input_tokens": 10, "output_tokens": 1,
                 "cache_read_tokens": 17722, "cache_write_tokens": 11368,
                 "cache_ttl": "1h"}


def test_anthropic_da_OGGETTO_come_nel_runner():
    """La stessa lettura, ma dall'oggetto `Usage` dell'SDK (non da un dizionario).

    Mutazione ESEGUITA: leggere `cache_write_tokens` da `cache_read_input_tokens`
    invece che da `cache_creation_input_tokens` -- rossa."""
    class _Uso:
        input_tokens = 100
        output_tokens = 20
        cache_creation_input_tokens = 30
        cache_read_input_tokens = 40
        cache_creation = None

    t = anthropic_turn_tokens(_Uso())
    assert t["input_tokens"] == 100 and t["cache_write_tokens"] == 30
    assert t["cache_ttl"] is None


def test_openai_i_token_nuovi_sono_il_prompt_MENO_la_cache_letta():
    """`prompt_tokens` COMPRENDE i cachati (documentazione OpenAI e
    OpenRouter; vedi `_cache_counts` in openai_compat_runner).

    Mutazione ESEGUITA: `input_tokens = prompt_tokens` -- rossa."""
    uso = CompletionUsage.model_validate({
        "prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050,
        "prompt_tokens_details": {"cached_tokens": 800,
                                  "cache_write_tokens": 0}})
    t = openai_turn_tokens(uso)
    assert t["input_tokens"] == 200
    assert t["cache_read_tokens"] == 800
    assert t["output_tokens"] == 50
    assert t["cache_ttl"] is None


def test_openai_SENZA_dettagli_la_cache_e_NULL_non_zero():
    """Ollama e qwen non dichiarano niente sulla cache: «non detto» non e'
    «zero letti».

    Mutazione ESEGUITA: restituire 0 invece di None per `cache_read_tokens` -- rossa."""
    uso = CompletionUsage.model_validate({
        "prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050})
    t = openai_turn_tokens(uso)
    assert t["input_tokens"] == 1000
    assert t["cache_read_tokens"] is None
    assert t["cache_write_tokens"] is None


def test_senza_usage_tutto_e_NULL():
    """Nessun giro (`usage` assente): ogni campo resta `None`, mai `0`.

    Mutazione ESEGUITA: `_int_or_none` restituisce `int(value or 0)` -- rossa."""
    assert all(v is None for v in anthropic_turn_tokens(None).values())
    assert all(v is None for v in openai_turn_tokens(None).values())


def test_un_campo_malformato_diventa_NULL_non_solleva():
    """Fix round 1 (Task 5, coordinatore): un aggiornamento della CLI puo'
    cambiare la forma dello stream senza preavviso. Un campo non numerico
    (stringa o dizionario dove ci si aspetta un intero) deve diventare NULL,
    mai far cadere il turno.

    Mutazione ESEGUITA (due, verificate separatamente): (1) ripristinato
    `_int_or_none` a `int(value)` senza `try/except` -- rossa (`ValueError`
    non catturato sul campo stringa); (2) con `_int_or_none` intatto,
    ripristinato `cache_ttl` a `int(x or 0)` -- rossa comunque
    (`TypeError` non catturato sul dizionario annidato: il guardiano di
    `cache_ttl` e' indipendente da quello di `_int_or_none`, entrambi
    necessari)."""
    t = anthropic_turn_tokens({"input_tokens": "n/a",
                               "cache_creation": {
                                   "ephemeral_1h_input_tokens": {"x": 1}}})
    assert t["input_tokens"] is None
    assert t["cache_ttl"] is None


def test_un_booleano_non_e_un_conteggio_di_token():
    """`bool` e' un sottotipo di `int` in Python: senza l'esclusione
    esplicita, `True` passerebbe per un conteggio di UN token vero.

    Mutazione ESEGUITA: tolta l'esclusione `isinstance(value, bool)` da
    `_int_or_none` -- rossa (`input_tokens` diventerebbe `1`, non `None`)."""
    t = anthropic_turn_tokens({"input_tokens": True})
    assert t["input_tokens"] is None


def test_prompt_tokens_malformato_diventa_NULL_non_solleva():
    """Reperto (revisione Task 5): `openai_turn_tokens` leggeva `prompt`
    senza passare da `_int_or_none`, cosi' `max(int(prompt) - ..., 0)`
    sollevava `ValueError` su un `prompt_tokens` non numerico -- e questa
    lettura corre sul giro della catena: un turno malformato faceva cadere
    l'intero turno, non solo il suo campo.

    Mutazione ESEGUITA: ripristinato `prompt = _field(usage, "prompt_tokens")`
    (bypassando `_int_or_none`) -- rossa (`ValueError` non catturato)."""
    uso = CompletionUsage.model_validate({
        "prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050})
    uso.prompt_tokens = "n/a"
    t = openai_turn_tokens(uso)
    assert t["input_tokens"] is None


def test_un_infinito_non_e_un_conteggio_di_token():
    """`json.loads` accetta `Infinity` come float valido: un fornitore che lo
    scrive nello stream non deve far cadere il turno. `int(float("inf"))`
    solleva `OverflowError`, non catturata dai due `except` esistenti.

    Mutazione ESEGUITA: tolto `OverflowError` dalla tupla catturata in
    `_int_or_none` -- rossa (`OverflowError` non catturato)."""
    t = anthropic_turn_tokens({"input_tokens": float("inf")})
    assert t["input_tokens"] is None


COMPOSIZIONE = {"guide_chars": 7000, "core_chars": 7600, "history_chars": 900}


def _giro(n_mcp=0, inp=10):
    return {"message_id": "m", "input_tokens": inp, "output_tokens": None,
            "cache_read_tokens": 5, "cache_write_tokens": 6,
            "cache_ttl": "1h", "mcp_calls": n_mcp}


def test_i_risultati_arrivano_al_modello_il_GIRO_DOPO():
    """Il giro 1 chiama due strumenti; i loro risultati entrano nel giro 2,
    e restano nel 3 (la conversazione li rispedisce tutti).

    Mutazione ESEGUITA: contare le chiamate del giro stesso -- rossa."""
    righe = payload_rows_ponte(
        COMPOSIZIONE, [_giro(n_mcp=2), _giro(n_mcp=1), _giro()],
        {"tools_chars": 45388, "tools_sent": 16, "results": [100, 200, 50]})
    assert [r["results_chars"] for r in righe] == [0, 300, 350]
    assert [r["iteration"] for r in righe] == [1, 2, 3]


def test_ogni_giro_rispedisce_la_composizione_e_porta_i_suoi_token():
    """La composizione torna a ogni giro (la conversazione si rispedisce),
    ogni giro porta i suoi token, e il piano non ha prezzo per giro.

    Mutazione ESEGUITA: `"input_tokens": exchanges[0].get("input_tokens")`
    (i token del primo giro su tutti) -- rossa ([10, 10] invece di [10, 8]);
    ripristinata, verde."""
    righe = payload_rows_ponte(COMPOSIZIONE, [_giro(inp=10), _giro(inp=8)],
                               {"tools_chars": 45388, "tools_sent": 16,
                                "results": []})
    assert all(r["guide_chars"] == 7000 and r["core_chars"] == 7600
               for r in righe)
    assert [r["input_tokens"] for r in righe] == [10, 8]
    assert all(r["cost_usd"] is None for r in righe), "il piano non ha prezzo per turno"


def test_le_definizioni_stanno_SOLO_sul_giro_in_cui_tools_list_e_servita():
    """Spec §4: le definizioni si registrano sul giro in cui `tools/list` e'
    stata servita, non su tutti. La CLI la chiede all'avvio, prima del giro
    1: il giro 1 porta i 45388 caratteri consegnati, i giri dopo 0.

    Mutazione ESEGUITA: `**served` su tutte le righe (senza
    `if index == 1`) -- rossa ([45388, 45388, 45388]); ripristinata, verde."""
    righe = payload_rows_ponte(COMPOSIZIONE, [_giro(), _giro(), _giro()],
                               {"tools_chars": 45388, "tools_sent": 16,
                                "results": []})
    assert [r["tools_chars"] for r in righe] == [45388, 0, 0]
    assert [r["tools_sent"] for r in righe] == [16, 0, 0]


def test_uno_stream_SENZA_giri_porta_comunque_le_definizioni_servite():
    """CLI uccisa dopo `tools/list`: le definizioni sono state consegnate, e
    la riga unica del turno le porta.

    Mutazione ESEGUITA: la riga unica senza `**served` -- rossa (0 invece
    di 45388); ripristinata, verde."""
    righe = payload_rows_ponte(COMPOSIZIONE, [],
                               {"tools_chars": 45388, "tools_sent": 16})
    assert righe[0]["tools_chars"] == 45388 and righe[0]["tools_sent"] == 16


def test_un_turno_SENZA_strumenti_ha_definizioni_a_zero_VERO():
    """Osservatore, analista, attuatore: nessuna `tools/list` servita. Zero
    qui e' un fatto -- nessuna definizione consegnata -- non un buco.

    Mutazione ESEGUITA: `"tools_chars": loads.get("tools_chars")` senza
    `int(... or 0)` (il buco al posto del fatto) -- rossa (None invece di
    0); ripristinata, verde."""
    righe = payload_rows_ponte(COMPOSIZIONE, [_giro()], None)
    assert righe[0]["tools_chars"] == 0 and righe[0]["tools_sent"] == 0


def test_uno_stream_SENZA_giri_scrive_una_riga_di_sola_composizione():
    """CLI uccisa: nessun evento assistant. Il turno ha comunque consegnato
    la sua composizione; i token restano NULL.

    Mutazione ESEGUITA: restituire [] quando non ci sono giri -- rossa."""
    righe = payload_rows_ponte(COMPOSIZIONE, [], None)
    assert len(righe) == 1
    assert righe[0]["input_tokens"] is None
    assert righe[0]["history_chars"] == 900


def test_senza_composizione_non_si_inventa_niente():
    """Senza la composizione consegnata (riga del ponte vecchia) non si
    fabbricano giri: nessuna riga, non righe di zeri.

    Mutazione ESEGUITA: tolto il ritorno anticipato `if composition is
    None` (con `composition or {}`) -- rossa (una riga invece di nessuna);
    ripristinata, verde."""
    assert payload_rows_ponte(None, [_giro()], None) == []
