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
