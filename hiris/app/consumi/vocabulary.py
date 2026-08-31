"""Le parole dei consumi: cinque stati del costo, e il giorno della casa.

Il costo di una riga non e' sempre un numero, e i modi in cui puo' non esserlo
non sono lo stesso modo. Un modello in casa costa zero DAVVERO; l'abbonamento
non espone il prezzo del singolo turno; un modello fuori listino ha un prezzo
che noi non conosciamo. Appiattirli tutti su 0,00 e' la bugia da cui nasce
questa fetta, e la pagina Consumi la commetteva su due fronti insieme --
ogni identificativo OpenRouter e, misurato il 21/08/2026 sull'installazione
vera, anche `claude-opus-4-8`, che in `pricing.py` non c'e'.
"""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..backends.pricing import prezzo_noto

# Dal piu' DEBOLE al piu' forte. `reale` sta sopra `misurato` perche' e' un
# fatto -- quanto e' stato addebitato -- e non una stima da listino.
STATES: tuple[str, ...] = ("non_noto", "compreso", "gratuito", "misurato", "reale")

LABEL: dict[str, str] = {
    "claude": "API Anthropic",
    "openai": "API OpenAI",
    "openrouter": "OpenRouter",
    "ollama": "Ollama (in casa)",
    "ponte": "Abbonamento Claude",
}

# La differenza fra `misurato` e `reale` si dichiara UNA VOLTA per sezione, non
# riga per riga: i due stati non convivono mai nella stessa sezione, perche' e'
# il provider a determinarli.
NOTE: dict[str, str] = {
    "claude": "Costo calcolato sul listino Anthropic.",
    "openai": "Costo calcolato sul listino OpenAI.",
    "openrouter": ("Costo dichiarato da OpenRouter: e' quanto e' stato "
                   "addebitato, non una stima."),
    "ollama": "Modelli in casa: nessun costo.",
    "ponte": ("L'abbonamento non espone il prezzo del singolo turno. I token "
              "si', e sono questi."),
}


def piu_debole(a: str, b: str) -> str:
    """Lo stato piu' debole fra due.

    Una riga non puo' mai affermare piu' della chiamata peggiore che contiene:
    se in uno stesso giorno lo stesso modello produce una chiamata col costo
    dichiarato e una senza, la riga dice `non_noto`, non `reale`.
    """
    return min(a, b, key=lambda s: STATES.index(s) if s in STATES else 0)


def cost_state_and_value(provider: str, model: str, *,
                  cost_dichiarato: float | None,
                  cost_da_listino: float | None) -> tuple[str, float | None]:
    """Lo stato del costo di UNA chiamata, e il costo che le corrisponde.

    `costo_dichiarato` e' quello che il provider ha detto di aver addebitato --
    OpenRouter lo mette in `usage.cost` a ogni risposta, sempre, anche in
    streaming. `costo_da_listino` e' quello che il runner ha calcolato dai
    prezzi in `pricing.py`, e vale solo se quel modello e' davvero in tabella:
    altrimenti e' lo zero del ripiego, che non significa «gratis».
    """
    if provider == "ponte":
        return "compreso", None
    if provider == "ollama" or model.endswith(":free"):
        return "gratuito", 0.0
    if cost_dichiarato is not None:
        return "reale", float(cost_dichiarato)
    if prezzo_noto(model):
        return "misurato", float(cost_da_listino or 0.0)
    return "non_noto", None


def local_day(now: float, timezone: str = "") -> str:
    """Il giorno in cui cade questo istante, nel fuso della casa.

    In UTC le 00:30 del 22 agosto a Roma sono ancora il 21: un secchiello
    giornaliero calcolato in UTC racconterebbe una bugia ogni notte. Il fuso lo
    sa l'anagrafe (`ArchivioCasa.sistema_di_riferimento()['fuso']`), che tace
    quando non lo sa: senza, si ripiega su UTC -- e la pagina lo dichiara,
    invece di far passare un giorno spostato per un giorno.
    """
    try:
        tz = ZoneInfo(timezone) if timezone else UTC
    except (ZoneInfoNotFoundError, ValueError):
        tz = UTC
    return datetime.fromtimestamp(now, tz).strftime("%Y-%m-%d")
