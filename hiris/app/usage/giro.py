"""I token di UN giro, e le righe del registro che ne nascono.

**Una lettura per famiglia di risposta, in un posto solo** (spec «le misure
complete» §3-§4). La leggono il runner Anthropic, il runner della catena e la
lettura dello stream del ponte: tre copie scritte a mano sarebbero tre verita'
sulla stessa domanda, e questo prodotto ha gia' pagato due volte quel difetto
(`tests/test_composition_order.py`, i due pesatori di caratteri).

**NULL non e' zero.** Un campo che il fornitore non dichiara resta `None`: e'
«non misurato», e il registro lo scrive cosi'.
"""
from __future__ import annotations


def _field(source, name: str):
    """Un campo da un dizionario (lo stream del ponte) o da un oggetto
    (gli SDK): la stessa lettura per le due forme che arrivano davvero."""
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _int_or_none(value):
    """Un intero, o `None` -- MAI un'eccezione.

    Fix round 1 (Task 5, coordinatore): un aggiornamento della CLI puo'
    cambiare la forma dello stream senza preavviso, e un campo che arriva
    stringa o dizionario invece di numero non deve far cadere il turno --
    «la misura non fa mai cadere un turno». `bool` e' un sottotipo di `int`
    in Python (`isinstance(True, int)` e' vero): senza l'esclusione esplicita
    `int(True) == 1` passerebbe per un conteggio vero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def cache_ttl(five_minutes, one_hour) -> str | None:
    """Per quanto e' stata scritta la cache di questo giro.

    Conta perche' la scrittura a un'ora costa piu' di quella a cinque minuti,
    e i giri di fondo (un turno all'ora o al giorno) la scrivono senza mai
    rileggerla: misurato sulla casa il 27-28/09/2026.

    Fix round 1 (Task 5): gli argomenti passano per `_int_or_none`, non per
    `int(x or 0)` -- un valore malformato (stringa, dizionario) diventa un
    conteggio NULL invece di sollevare, e `None` decide come zero."""
    five = _int_or_none(five_minutes) or 0
    hour = _int_or_none(one_hour) or 0
    if five and hour:
        return "misto"
    if hour:
        return "1h"
    if five:
        return "5m"
    return None


def anthropic_turn_tokens(usage) -> dict:
    """I token di un giro nella forma Anthropic (SDK o stream della CLI)."""
    creation = _field(usage, "cache_creation")
    return {
        "input_tokens": _int_or_none(_field(usage, "input_tokens")),
        "output_tokens": _int_or_none(_field(usage, "output_tokens")),
        "cache_read_tokens": _int_or_none(_field(usage, "cache_read_input_tokens")),
        "cache_write_tokens": _int_or_none(
            _field(usage, "cache_creation_input_tokens")),
        "cache_ttl": cache_ttl(_field(creation, "ephemeral_5m_input_tokens"),
                               _field(creation, "ephemeral_1h_input_tokens")),
    }


def openai_turn_tokens(usage) -> dict:
    """I token di un giro nella forma OpenAI/OpenRouter.

    `prompt_tokens` COMPRENDE i token letti dalla cache (documentazione
    OpenAI; OpenRouter uguale): i nuovi sono la differenza. Senza
    `prompt_tokens_details` il fornitore non ha detto niente sulla cache, e
    i due campi della cache restano `None` -- non zero.
    """
    prompt = _int_or_none(_field(usage, "prompt_tokens"))
    details = _field(usage, "prompt_tokens_details")
    read = _int_or_none(_field(details, "cached_tokens"))
    written = _int_or_none(_field(details, "cache_write_tokens"))
    fresh = None if prompt is None else max(prompt - (read or 0), 0)
    return {
        "input_tokens": fresh,
        "output_tokens": _int_or_none(_field(usage, "completion_tokens")),
        "cache_read_tokens": read,
        "cache_write_tokens": written,
        "cache_ttl": None,
    }


def payload_rows_ponte(composition: dict | None, exchanges: list,
                       loads: dict | None) -> list[dict]:
    """Le righe di `payload` di un turno del ponte (spec §4, la scrittura).

    - **La composizione si rispedisce a ogni giro**: ogni chiamata all'API
      riporta il prompt di sistema e la conversazione. Per questo sta su
      tutti i giri, come sulla catena.
    - **I risultati entrano il giro DOPO**: le chiamate MCP del giro k
      tornano al modello nel giro k+1, e da li' restano. I caratteri si
      prendono nell'ordine in cui la rotta li ha serviti.
    - **Definizioni a zero quando non ne e' stata servita nessuna**: un turno
      senza strumenti non ne ha ricevute, ed e' un fatto.
    - **Nessun giro nello stream** (CLI uccisa): una riga sola, la
      composizione consegnata, token NULL.
    - `cost_usd` resta NULL: l'abbonamento non espone il prezzo del giro.
    """
    if composition is None:
        return []
    loads = loads or {}
    results = list(loads.get("results") or [])
    base = {"tools_chars": int(loads.get("tools_chars") or 0),
            "tools_sent": int(loads.get("tools_sent") or 0),
            "guide_chars": int(composition.get("guide_chars") or 0),
            "core_chars": int(composition.get("core_chars") or 0),
            "history_chars": int(composition.get("history_chars") or 0),
            "prefix_hash": ""}
    if not exchanges:
        return [{**base, "iteration": 1, "results_chars": 0,
                 "input_tokens": None, "output_tokens": None,
                 "cache_read_tokens": None, "cache_write_tokens": None,
                 "cache_ttl": None, "cost_usd": None}]
    rows = []
    calls_before = 0
    for index, exchange in enumerate(exchanges, start=1):
        rows.append({**base, "iteration": index,
                     "results_chars": sum(results[:calls_before]),
                     "input_tokens": exchange.get("input_tokens"),
                     "output_tokens": None,
                     "cache_read_tokens": exchange.get("cache_read_tokens"),
                     "cache_write_tokens": exchange.get("cache_write_tokens"),
                     "cache_ttl": exchange.get("cache_ttl"),
                     "cost_usd": None})
        calls_before += int(exchange.get("mcp_calls") or 0)
    return rows
