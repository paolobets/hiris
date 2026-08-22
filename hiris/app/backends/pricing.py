"""Centralized pricing table (USD/MTok) for all supported LLM models.

Single source of truth shared by ClaudeRunner and OpenAICompatRunner.
Ollama / local models are free (cost 0).
"""
from __future__ import annotations

PRICING: dict[str, dict[str, float]] = {
    # Claude models — input/output/cache_write/cache_read in USD/MTok
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0,  "cache_write": 3.75,  "cache_read": 0.30},
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0,  "cache_write": 18.75, "cache_read": 1.50},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25,  "cache_write": 0.30,  "cache_read": 0.03},
    # OpenAI models — input/output only
    "gpt-4o":                    {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":               {"input": 0.15, "output":  0.60},
    "gpt-4.1":                   {"input": 2.00, "output":  8.00},
    "gpt-4.1-mini":              {"input": 0.40, "output":  1.60},
    "gpt-4.1-nano":              {"input": 0.10, "output":  0.40},
    "o3":                        {"input": 10.0, "output": 40.00},
    "o3-mini":                   {"input": 1.10, "output":  4.40},
    "o4-mini":                   {"input": 1.10, "output":  4.40},
    # Fallback for unknown models (Ollama / local = free)
    "_default":                  {"input": 0.0,  "output":  0.00},
}


def get_price(model: str) -> dict[str, float]:
    """Il prezzo di un modello, col ripiego sul predefinito.

    Il censimento del 17/08/2026 la dava senza chiamanti, e la cancellazione
    sarebbe stata l'istinto sbagliato: i due runner facevano ENTRAMBI
    `PRICING.get(model, PRICING["_default"])` in linea, cioe' la stessa regola
    scritta tre volte, e l'unica copia non usata era quella con un nome. Adesso
    la chiamano, e il ripiego vive in un posto solo.

    Morto e scollegato non sono la stessa cosa: il primo si toglie, il secondo
    si collega.
    """
    return PRICING.get(model, PRICING["_default"])


def prezzo_noto(model: str) -> bool:
    """Se di questo modello conosciamo davvero il listino.

    `get_price` ripiega su `_default` (zero) per qualunque nome sconosciuto, e
    quello zero e' indistinguibile da «gratuito» per chi legge il risultato:
    e' il meccanismo per cui il costo di OpenRouter e' sempre stato 0,00 senza
    che niente lo dicesse. Qui la domanda si fa esplicita, ed e' l'unico modo
    perche' il costo di un modello fuori tabella possa uscire come `null`
    invece che come uno zero che afferma.
    """
    return model in PRICING and model != "_default"
